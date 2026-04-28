import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: '分红资产监控 · Stock Monitor',
  description: '400w 资金低风险分红资产监控仪表盘',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
