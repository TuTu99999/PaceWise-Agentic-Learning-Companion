import React from 'react';
import { Icon, type IconName } from '../ui/Icon';

export function StatTile({ label, value, hint, icon }: { label: string; value: React.ReactNode; hint?: string; icon?: IconName }) {
  return (
    <div className="rounded-2xl border border-line bg-white p-4 shadow-card">
      <div className="flex items-center gap-2 text-muted">
        {icon && <Icon name={icon} size={18} />}
        <p className="text-sm font-medium">{label}</p>
      </div>
      <p className="mt-2 text-2xl font-bold tabular-nums">{value}</p>
      {hint && <p className="caption mt-0.5">{hint}</p>}
    </div>
  );
}
