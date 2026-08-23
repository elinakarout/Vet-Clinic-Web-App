// The centred card that Login and Register sit in — outside the app shell,
// because neither page has navigation to show. (Phase 5)

import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { ThemeToggle } from './ThemeToggle';

export function AuthShell({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle: string;
  children: ReactNode;
  footer: ReactNode;
}) {
  return (
    <div className="flex min-h-screen flex-col bg-sand-50 dark:bg-ink-950">
      <div className="flex justify-end p-4">
        <ThemeToggle />
      </div>
      <div className="flex flex-1 items-start justify-center px-4 pb-16 pt-4 sm:items-center sm:pt-0">
        <div className="w-full max-w-md">
          <Link
            to="/login"
            className="mb-8 flex items-center justify-center gap-2 text-brand-700 dark:text-brand-300"
          >
            <svg className="h-7 w-7" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
              <ellipse cx="7.5" cy="8" rx="2.1" ry="2.8" />
              <ellipse cx="12" cy="6.4" rx="2.1" ry="2.9" />
              <ellipse cx="16.5" cy="8" rx="2.1" ry="2.8" />
              <ellipse cx="19.4" cy="12.4" rx="1.9" ry="2.3" />
              <path d="M12 11.4c2.7 0 5.4 2.3 5.4 4.8 0 2-1.6 3.2-3.6 3.2-1 0-1.3-.3-1.8-.3s-.8.3-1.8.3c-2 0-3.6-1.2-3.6-3.2 0-2.5 2.7-4.8 5.4-4.8Z" />
            </svg>
            <span className="text-xl font-semibold tracking-tight text-ink-900 dark:text-ink-50">
              Paws &amp; Claws
            </span>
          </Link>

          <div className="rounded-card bg-white p-6 shadow-xs ring-1 ring-ink-200/70 sm:p-8 dark:bg-ink-900 dark:ring-ink-800">
            <h1 className="text-xl font-semibold text-ink-900 dark:text-ink-50">
              {title}
            </h1>
            <p className="mt-1 text-sm text-ink-500 dark:text-ink-400">{subtitle}</p>
            <div className="mt-6">{children}</div>
          </div>

          <div className="mt-6 text-center text-sm text-ink-500 dark:text-ink-400">
            {footer}
          </div>
        </div>
      </div>
    </div>
  );
}
