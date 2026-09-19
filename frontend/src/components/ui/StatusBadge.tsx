import React from 'react';
import { Badge } from './Badge';

export interface StatusBadgeProps {
  status: string | null | undefined;
  className?: string;
  dot?: boolean;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status, className = '', dot = true }) => {
  if (!status) return null;

  const normalized = status.toUpperCase();

  switch (normalized) {
    case 'COMPLETED':
    case 'EXTRACTED':
    case 'CONFIRMED':
    case 'RESOLVED':
    case 'MATCHED':
      return (
        <Badge variant="success" dot={dot} className={className}>
          {status.replace('_', ' ')}
        </Badge>
      );

    case 'PROCESSING':
    case 'QUEUED':
    case 'PENDING':
      return (
        <Badge variant="info" dot={dot} className={className}>
          {status.replace('_', ' ')}
        </Badge>
      );

    case 'PARTIAL':
    case 'AMBIGUOUS':
    case 'UNMATCHED':
    case 'OPEN':
    case 'LOW':
    case 'MEDIUM':
      return (
        <Badge variant="warning" dot={dot} className={className}>
          {status.replace('_', ' ')}
        </Badge>
      );

    case 'FAILED':
    case 'REVIEW_REQUIRED':
    case 'REJECTED':
    case 'CRITICAL':
    case 'HIGH':
      return (
        <Badge variant="danger" dot={dot} className={className}>
          {status.replace('_', ' ')}
        </Badge>
      );

    default:
      return (
        <Badge variant="default" dot={dot} className={className}>
          {status.replace('_', ' ')}
        </Badge>
      );
  }
};
