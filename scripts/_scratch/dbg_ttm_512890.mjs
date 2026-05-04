import { lookupTTMDividend } from '../_lib/doubao_ttm_dividend.mjs';

const r = await lookupTTMDividend(
  { code: '512890', name: '红利低波 ETF（华泰柏瑞）', category: 'dividend_etf_a' },
  { verbose: true },
);
console.log('---');
console.log('parsed:', JSON.stringify(r.parsed, null, 2));
console.log('---stage A tail (last 600):');
console.log((r.raw || '').slice(-600));
