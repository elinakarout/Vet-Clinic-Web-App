// Slide-out chatbot panel. (Phase 5 shell; Phase 8 fills in the streaming body.)
//
// The shell ships now so Phase 8 is a body swap rather than a layout change, and
// so the safety disclaimer that PROJECT_PLAN.md §8.5 requires is already in the
// place users will look for it. Nothing here calls /chat — that endpoint does
// not exist yet.

import { useState } from 'react';

export function ChatPanel() {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="fixed bottom-5 right-5 z-40 flex h-14 w-14 items-center justify-center rounded-full bg-brand-600 text-white shadow-lg transition-transform hover:scale-105 hover:bg-brand-700 dark:bg-brand-500 dark:text-ink-950 dark:hover:bg-brand-400"
        aria-label="Open the clinic assistant"
        aria-expanded={open}
      >
        <svg className="h-6 w-6" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M21 11.5a8.4 8.4 0 0 1-9 8.4 9.3 9.3 0 0 1-2.9-.4L4 21l1.4-3.8A8.2 8.2 0 0 1 3 11.5a8.4 8.4 0 0 1 9-8.4 8.4 8.4 0 0 1 9 8.4Z"
          />
        </svg>
      </button>

      {open && (
        <div className="fixed inset-0 z-50 flex justify-end">
          <button
            type="button"
            className="absolute inset-0 bg-ink-950/40"
            aria-label="Close the assistant"
            onClick={() => setOpen(false)}
          />
          <aside
            role="dialog"
            aria-modal="true"
            aria-label="Clinic assistant"
            className="relative flex h-full w-full max-w-md flex-col bg-white shadow-xl dark:bg-ink-900"
          >
            <header className="border-b border-ink-200 px-5 py-4 dark:border-ink-800">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h2 className="text-base font-semibold text-ink-900 dark:text-ink-50">
                    Clinic assistant
                  </h2>
                  <p className="mt-1 text-xs text-ink-500 dark:text-ink-400">
                    Provides general information, not medical advice. For anything
                    urgent, call the clinic.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setOpen(false)}
                  className="-mr-2 rounded-lg p-2 text-ink-500 hover:bg-ink-100 hover:text-ink-900 dark:text-ink-400 dark:hover:bg-ink-800 dark:hover:text-ink-50"
                  aria-label="Close the assistant"
                >
                  <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                    <path
                      stroke="currentColor"
                      strokeWidth="1.8"
                      strokeLinecap="round"
                      d="M6 6l12 12M18 6 6 18"
                    />
                  </svg>
                </button>
              </div>
            </header>

            <div className="flex flex-1 flex-col items-center justify-center px-8 text-center">
              <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-brand-50 text-brand-600 dark:bg-brand-500/15 dark:text-brand-300">
                <svg className="h-7 w-7" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                  <path
                    stroke="currentColor"
                    strokeWidth="1.8"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M12 3v2m0 14v2M3 12h2m14 0h2M6 6l1.5 1.5M16.5 16.5 18 18M18 6l-1.5 1.5M7.5 16.5 6 18"
                  />
                </svg>
              </div>
              <h3 className="text-sm font-semibold text-ink-900 dark:text-ink-50">
                Coming soon
              </h3>
              <p className="mt-2 max-w-xs text-sm text-ink-500 dark:text-ink-400">
                The assistant will answer questions about the clinic and help you
                find an appointment. It is not switched on yet — for now, book
                from the Book page or call us.
              </p>
            </div>
          </aside>
        </div>
      )}
    </>
  );
}
