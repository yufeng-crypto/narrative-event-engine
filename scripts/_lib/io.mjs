import { mkdirSync, writeFileSync, readFileSync, existsSync } from 'node:fs';
import { dirname } from 'node:path';

export function writeJson(path, data) {
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, JSON.stringify(data, null, 2), 'utf8');
}

export function readJson(path) {
  if (!existsSync(path)) {
    throw new Error(`File not found: ${path}. Run prior stage first.`);
  }
  return JSON.parse(readFileSync(path, 'utf8'));
}

export function timestamp() {
  return new Date().toISOString();
}
