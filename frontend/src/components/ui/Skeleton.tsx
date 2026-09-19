import React from 'react';

export interface SkeletonProps {
  className?: string;
  variant?: 'text' | 'rect' | 'circle';
  count?: number;
}

export const Skeleton: React.FC<SkeletonProps> = ({
  className = '',
  variant = 'rect',
  count = 1,
}) => {
  const variantStyles = {
    text: 'h-4 w-full rounded',
    rect: 'h-24 w-full rounded-lg',
    circle: 'w-10 h-10 rounded-full',
  };

  if (count > 1) {
    return (
      <div className="space-y-2.5 w-full">
        {Array.from({ length: count }).map((_, i) => (
          <div
            key={i}
            className={`bg-slate-200/80 animate-pulse ${variantStyles[variant]} ${className}`}
          />
        ))}
      </div>
    );
  }

  return (
    <div
      className={`bg-slate-200/80 animate-pulse ${variantStyles[variant]} ${className}`}
    />
  );
};
