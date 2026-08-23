import type { HTMLAttributes, ReactNode } from 'react';
import { cn } from '../../lib/cn';

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
}

export function Card({ className, children, ...rest }: CardProps) {
  return (
    <div
      className={cn(
        'rounded-card bg-white ring-1 ring-ink-200/70 shadow-xs',
        'dark:bg-ink-900 dark:ring-ink-800',
        className,
      )}
      {...rest}
    >
      {children}
    </div>
  );
}

export function CardHeader({
  title,
  description,
  action,
}: {
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3 border-b border-ink-200/70 px-5 py-4 dark:border-ink-800">
      <div className="min-w-0">
        <h2 className="text-base font-semibold text-ink-900 dark:text-ink-50">
          {title}
        </h2>
        {description && (
          <p className="mt-0.5 text-sm text-ink-500 dark:text-ink-400">
            {description}
          </p>
        )}
      </div>
      {action}
    </div>
  );
}
