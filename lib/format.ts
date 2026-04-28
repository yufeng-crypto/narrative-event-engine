export function formatPrice(n: number | null | undefined, digits = 3): string {
  if (n == null || Number.isNaN(n)) return '—';
  return n.toFixed(digits);
}

export function formatPercent(n: number | null | undefined, digits = 2): string {
  if (n == null || Number.isNaN(n)) return '—';
  const sign = n > 0 ? '+' : '';
  return `${sign}${n.toFixed(digits)}%`;
}

export function formatBjTime(iso: string): string {
  const d = new Date(iso);
  const fmt = new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
  return fmt.format(d);
}

export function categoryLabel(cat: string): string {
  switch (cat) {
    case 'dividend_etf_a':
      return 'A 股红利 ETF';
    case 'dividend_etf_hk':
      return '港股红利 ETF';
    case 'reit':
      return '公募 REIT';
    default:
      return cat;
  }
}
