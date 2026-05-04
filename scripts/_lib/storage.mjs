/**
 * 统一存储抽象 — 让脚本同时支持本地 fs（开发）和 GitHub API 写回（Vercel cron）。
 *
 * 用法：脚本 import 这个 module 而不是 io.mjs，根据 STORAGE_MODE 自动切换。
 *
 *   STORAGE_MODE=local（默认）: 本地 data/*.json 读写，开发环境
 *   STORAGE_MODE=github: 通过 GitHub Contents API 读写，Vercel cron 用
 *
 * 注意：本 module 全部 async，调用方需要 await。如需 sync 的本地行为，继续用 io.mjs。
 */

import * as local from './io.mjs';
import * as github from './github_writer.mjs';

const MODE = process.env.STORAGE_MODE || 'local';

/**
 * 读 JSON 文件。
 * @param {string} path 项目内相对路径（如 'data/screened.json'）
 * @returns {Promise<any>}
 */
export async function readJson(path) {
  if (MODE === 'github') {
    const txt = await github.readFile(path);
    if (txt == null) throw new Error(`File not found in GitHub: ${path}`);
    return JSON.parse(txt);
  }
  return local.readJson(path);
}

/**
 * 写 JSON 文件。
 * @param {string} path 项目内相对路径
 * @param {any} data 任何 JSON-serializable 对象
 * @param {Object} [opts]
 * @param {string} [opts.message] commit message（仅 github mode 用）
 * @returns {Promise<{commit?:string,html_url?:string,path?:string}|undefined>}
 */
export async function writeJson(path, data, opts = {}) {
  if (MODE === 'github') {
    return await github.writeFile(path, data, opts);
  }
  local.writeJson(path, data);
  return undefined;
}

export const timestamp = local.timestamp;

/** 当前运行模式（debug 用） */
export function currentMode() {
  return MODE;
}
