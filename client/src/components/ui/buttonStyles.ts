// Button class recipe, in its own module so both <Button> and react-router's
// <Link> can wear it without oxlint's only-export-components complaining.

import { cn } from '../../lib/cn';

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';
export type ButtonSize = 'sm' | 'md' | 'lg';

const base =
  'inline-flex items-center justify-center gap-2 rounded-lg font-medium ' +
  'transition-colors select-none ' +
  'disabled:cursor-not-allowed disabled:opacity-50';

const variants: Record<ButtonVariant, string> = {
  primary:
    'bg-brand-600 text-white hover:bg-brand-700 active:bg-brand-800 ' +
    'dark:bg-brand-500 dark:hover:bg-brand-400 dark:active:bg-brand-300 dark:text-ink-950',
  secondary:
    'bg-white text-ink-800 ring-1 ring-ink-200 hover:bg-ink-50 ' +
    'dark:bg-ink-800 dark:text-ink-100 dark:ring-ink-700 dark:hover:bg-ink-700',
  ghost:
    'text-ink-600 hover:bg-ink-100 hover:text-ink-900 ' +
    'dark:text-ink-300 dark:hover:bg-ink-800 dark:hover:text-ink-50',
  // Rose rather than red: it reads as serious without the alarm of a system error.
  danger:
    'bg-rose-600 text-white hover:bg-rose-700 active:bg-rose-800 ' +
    'dark:bg-rose-600 dark:hover:bg-rose-500',
};

const sizes: Record<ButtonSize, string> = {
  sm: 'h-8 px-3 text-sm',
  md: 'h-10 px-4 text-sm',
  lg: 'h-12 px-6 text-base',
};

export function buttonClasses(
  variant: ButtonVariant = 'primary',
  size: ButtonSize = 'md',
  extra?: string,
): string {
  return cn(base, variants[variant], sizes[size], extra);
}
