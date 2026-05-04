/**
 * Round-trip test：通过 GitHub Contents API 写一个测试文件 + 读回来 + 删除。
 *
 * 前置：
 *   .env 里设置：
 *     GITHUB_TOKEN=<fine-grained PAT 仅 contents:write>
 *     GITHUB_REPO=yufeng-crypto/narrative-event-engine
 *     GITHUB_BRANCH=main
 *     GITHUB_PATH_PREFIX=logic/stock/.claude/worktrees/sweet-buck-bd2f4f
 *
 * 用法：node --env-file=.env scripts/_scratch/test_github_writer.mjs
 */

import { writeFile, readFile } from '../_lib/github_writer.mjs';

const TEST_PATH = 'data/_test_github_writer.json';
const TEST_DATA = {
  test: true,
  timestamp: new Date().toISOString(),
  message: 'GitHub writer round-trip test from能力 5 build',
};

async function main() {
  console.log('Round-trip test: GitHub Contents API');
  console.log('  GITHUB_REPO        =', process.env.GITHUB_REPO);
  console.log('  GITHUB_BRANCH      =', process.env.GITHUB_BRANCH || 'main');
  console.log('  GITHUB_PATH_PREFIX =', process.env.GITHUB_PATH_PREFIX);
  console.log('  test path          =', TEST_PATH);
  console.log('---');

  // 1. 写
  console.log('1. Writing test file...');
  const w = await writeFile(TEST_PATH, TEST_DATA, {
    message: 'test: 能力 5 GitHub writer round-trip',
  });
  console.log('  ✓ commit:', w.commit?.slice(0, 8), '→', w.html_url);
  console.log('  full path in repo:', w.path);

  // 2. 读
  console.log('\n2. Reading back...');
  const txt = await readFile(TEST_PATH);
  if (!txt) throw new Error('readFile returned null after write');
  const parsed = JSON.parse(txt);
  console.log('  ✓ readback:', JSON.stringify(parsed).slice(0, 100));
  if (parsed.timestamp !== TEST_DATA.timestamp) {
    throw new Error(`Timestamp mismatch: wrote ${TEST_DATA.timestamp}, read ${parsed.timestamp}`);
  }
  console.log('  ✓ content matches');

  console.log('\n✅ Round-trip OK. 测试文件留在 repo，记得手动删除：');
  console.log(`   git pull && rm "<repo>/${w.path}" && git commit -am 'cleanup test file' && git push`);
}

main().catch((e) => {
  console.error('❌ Failed:', e.message);
  process.exit(1);
});
