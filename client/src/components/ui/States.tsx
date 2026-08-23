import type { ReactNode } from 'react';
import { cn } from '../../lib/cn';
import { Button } from './Button';

/** A grey block standing in for content that is still loading. */
export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        'animate-pulse rounded-lg bg-ink-200/70 dark:bg-ink-800',
        className,
      )}
      aria-hidden="true"
    />
  );
}

/**
 * Skeletons rather than a spinner for lists: the page keeps its shape, so
 * nothing jumps when the data lands.
 */
export function SkeletonList({ rows = 3 }: { rows?: number }) {
  return (
    <div className="space-y-3" role="status" aria-label="Loading">
      {Array.from({ length: rows }, (_, index) => (
        <Skeleton key={index} className="h-20 w-full" />
      ))}
    </div>
  );
}

/** An empty state always names the next action — never just "nothing here". */
export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon?: ReactNode;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-card border border-dashed border-ink-300 px-6 py-12 text-center dark:border-ink-700">
      {icon && (
        <div className="mb-3 text-brand-600 dark:text-brand-400" aria-hidden="true">
          {icon}
        </div>
      )}
      <h3 className="text-base font-semibold text-ink-900 dark:text-ink-50">
        {title}
      </h3>
      {description && (
        <p className="mt-1.5 max-w-sm text-sm text-ink-500 dark:text-ink-400">
          {description}
        </p>
      )}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

/** A failed request, with the server's own sentence and a way to try again. */
export function ErrorState({
  title = 'Something went wrong',
  message,
  onRetry,
}: {
  title?: string;
  message?: string;
  onRetry?: () => void;
}) {
  return (
    <div
      role="alert"
      className="rounded-card border border-rose-200 bg-rose-50 px-5 py-4 dark:border-rose-500/30 dark:bg-rose-500/10"
    >
      <h3 className="text-sm font-semibold text-rose-900 dark:text-rose-200">
        {title}
      </h3>
      {message && (
        <p className="mt-1 text-sm text-rose-800 dark:text-rose-300">{message}</p>
      )}
      {onRetry && (
        <Button variant="secondary" size="sm" className="mt-3" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}

/** A neutral inline note — used for the admin's "no profile" explanation. */
export function InfoPanel({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="rounded-card border border-brand-200 bg-brand-50 px-5 py-4 dark:border-brand-500/30 dark:bg-brand-500/10">
      <h3 className="text-sm font-semibold text-brand-900 dark:text-brand-200">
        {title}
      </h3>
      <div className="mt-1 text-sm text-brand-800 dark:text-brand-300">
        {children}
      </div>
    </div>
  );
}
