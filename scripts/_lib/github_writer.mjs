/**
 * GitHub Contents API 写回 — 用于 cron 在 Vercel 跑时把评估结果 commit 回 repo。
 *
 * Vercel cron 跑出的 JSON 数据需要持久化，又不想引入 KV/Postgres。
 * 做法：直接用 GitHub PAT 调 Contents API 写文件，commit 后 Vercel 自动重 build。
 *
 * 配置（.env 或 Vercel env）：
 *   GITHUB_TOKEN: PAT，scope 只需 contents:write
 *   GITHUB_REPO:  owner/name，例 yufeng-crypto/narrative-event-engine
 *   GITHUB_BRANCH: 默认 main
 *   GITHUB_PATH_PREFIX: 路径前缀，例 logic/stock/.claude/worktrees/sweet-buck-bd2f4f/
 *                      （当前 repo 是 monorepo，stock 项目在子目录）
 *
 * API 文档: https://docs.github.com/en/rest/repos/contents
 */

const API_BASE = 'https://api.github.com';

function getConfig() {
  const token = process.env.GITHUB_TOKEN;
  const repo = process.env.GITHUB_REPO;
  if (!token) throw new Error('GITHUB_TOKEN not set');
  if (!repo) throw new Error('GITHUB_REPO not set (format: owner/name)');
  return {
    token,
    repo,
    branch: process.env.GITHUB_BRANCH || 'main',
    pathPrefix: process.env.GITHUB_PATH_PREFIX || '',
  };
}

/**
 * 拉文件当前 SHA（更新文件需要）。如果文件不存在返回 null。
 */
async function getFileSha(path) {
  const { token, repo, branch } = getConfig();
  const url = `${API_BASE}/repos/${repo}/contents/${encodeURIComponent(path)}?ref=${branch}`;
  const res = await fetch(url, {
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
    },
  });
  if (res.status === 404) return null;
  if (!res.ok) {
    const txt = await res.text().catch(() => '');
    throw new Error(`GitHub GET ${path} failed: ${res.status} ${txt.slice(0, 300)}`);
  }
  const j = await res.json();
  return j.sha;
}

/**
 * 写文件（创建或更新）到 GitHub repo。
 * @param {string} relPath 项目内相对路径（会自动加 GITHUB_PATH_PREFIX）
 * @param {string|object} content 要写的内容（object 自动 JSON.stringify）
 * @param {Object} [opts]
 * @param {string} [opts.message] commit 消息，默认 'chore: cron auto-update <path>'
 * @returns {Promise<{ commit: string, html_url: string }>}
 */
export async function writeFile(relPath, content, opts = {}) {
  const { token, repo, branch, pathPrefix } = getConfig();
  const fullPath = pathPrefix.replace(/\/+$/, '') + (pathPrefix ? '/' : '') + relPath.replace(/^\/+/, '');
  const message = opts.message || `chore: cron auto-update ${relPath}`;

  const body = typeof content === 'string' ? content : JSON.stringify(content, null, 2) + '\n';
  const base64 = Buffer.from(body, 'utf8').toString('base64');

  const sha = await getFileSha(fullPath);

  const payload = {
    message,
    content: base64,
    branch,
    ...(sha && { sha }),
    committer: {
      name: 'stock-dashboard-cron',
      email: 'cron@stock-dashboard.local',
    },
  };

  const url = `${API_BASE}/repos/${repo}/contents/${encodeURIComponent(fullPath)}`;
  const res = await fetch(url, {
    method: 'PUT',
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const txt = await res.text().catch(() => '');
    throw new Error(`GitHub PUT ${fullPath} failed: ${res.status} ${txt.slice(0, 500)}`);
  }
  const j = await res.json();
  return {
    commit: j.commit?.sha,
    html_url: j.commit?.html_url,
    path: fullPath,
  };
}

/**
 * 读文件（用于 cron 增量更新场景，如读现有 quality_scores 拼新结果）。
 * @param {string} relPath
 * @returns {Promise<string|null>} utf8 string，文件不存在返回 null
 */
export async function readFile(relPath) {
  const { token, repo, branch, pathPrefix } = getConfig();
  const fullPath = pathPrefix.replace(/\/+$/, '') + (pathPrefix ? '/' : '') + relPath.replace(/^\/+/, '');
  const url = `${API_BASE}/repos/${repo}/contents/${encodeURIComponent(fullPath)}?ref=${branch}`;
  const res = await fetch(url, {
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
    },
  });
  if (res.status === 404) return null;
  if (!res.ok) {
    const txt = await res.text().catch(() => '');
    throw new Error(`GitHub GET ${fullPath} failed: ${res.status} ${txt.slice(0, 300)}`);
  }
  const j = await res.json();
  return Buffer.from(j.content, 'base64').toString('utf8');
}
