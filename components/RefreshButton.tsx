'use client';

import { useTransition } from 'react';
import { refreshDashboard } from '@/app/actions';

export function RefreshButton() {
  const [pending, startTransition] = useTransition();

  return (
    <button
      type="button"
      disabled={pending}
      onClick={() => startTransition(() => refreshDashboard())}
      className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-60"
    >
      {pending ? '刷新中...' : '刷新数据'}
    </button>
  );
}
