import React from 'react';

export interface ConfidenceBadgeProps {
  score: number | null | undefined;
  className?: string;
}

export const ConfidenceBadge: React.FC<ConfidenceBadgeProps> = ({ score, className = '' }) => {
  if (score === null || score === undefined) {
    return (
      <span className={`inline-flex items-center text-xs font-mono text-slate-400 ${className}`}>
        —
      </span>
    );
  }

  const percentage = Math.round(score * 100);

  let badgeColor = 'bg-emerald-50 text-emerald-700 border-emerald-200';
  let dotColor = 'bg-emerald-500';
  let label = 'High';

  if (score < 0.60) {
    badgeColor = 'bg-rose-50 text-rose-700 border-rose-200';
    dotColor = 'bg-rose-500';
    label = 'Review';
  } else if (score < 0.85) {
    badgeColor = 'bg-amber-50 text-amber-700 border-amber-200';
    dotColor = 'bg-amber-500';
    label = 'Partial';
  }

  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md border text-xs font-mono font-medium ${badgeColor} ${className}`}
      title={`Confidence Score: ${score.toFixed(3)} (${label})`}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${dotColor}`} />
      <span>{percentage}%</span>
      <span className="text-[10px] font-sans font-normal opacity-80">{label}</span>
    </span>
  );
};
