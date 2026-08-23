import { useCallback, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { cn } from '../../lib/cn';
import { ToastContext } from './toastContext';
import type { ToastApi, ToastTone } from './toastContext';

interface Toast {
  id: number;
  tone: ToastTone;
  message: string;
}

const tones: Record<ToastTone, string> = {
  success:
    'bg-emerald-600 text-white dark:bg-emerald-500 dark:text-emerald-950',
  error: 'bg-rose-600 text-white dark:bg-rose-500 dark:text-rose-950',
  info: 'bg-ink-800 text-white dark:bg-ink-200 dark:text-ink-900',
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(1);

  const push = useCallback((tone: ToastTone, message: string) => {
    const id = nextId.current++;
    setToasts((current) => [...current, { id, tone, message }]);
    // Errors linger: they usually need reading, and the action failed anyway.
    const ttl = tone === 'error' ? 7000 : 4000;
    window.setTimeout(
      () => setToasts((current) => current.filter((t) => t.id !== id)),
      ttl,
    );
  }, []);

  const api = useMemo<ToastApi>(
    () => ({
      success: (message: string) => push('success', message),
      error: (message: string) => push('error', message),
      info: (message: string) => push('info', message),
    }),
    [push],
  );

  return (
    <ToastContext.Provider value={api}>
      {children}
      {/*
        aria-live="polite" so a screen reader announces the result of a mutation
        without interrupting whatever the user is doing.
      */}
      <div
        className="pointer-events-none fixed inset-x-0 bottom-0 z-[60] flex flex-col items-center gap-2 p-4"
        aria-live="polite"
        aria-atomic="false"
      >
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={cn(
              'pointer-events-auto max-w-md rounded-lg px-4 py-2.5 text-sm font-medium shadow-lg',
              tones[toast.tone],
            )}
          >
            {toast.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
