// The message box: auto-growing textarea, Send, and Stop while streaming. (Phase 8)

import { useEffect } from 'react';
import type { RefObject } from 'react';
import { cn } from '../../lib/cn';
import { Button } from '../ui/Button';

/** The server's own cap (schemas/chat.py). Enforced here so 4001 is not a 422. */
const MAX_LENGTH = 4000;
const MAX_ROWS_PX = 132;

export function ChatComposer({
  value,
  onChange,
  onSend,
  onStop,
  streaming,
  inputRef,
}: {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  onStop: () => void;
  streaming: boolean;
  inputRef: RefObject<HTMLTextAreaElement | null>;
}) {
  // Grow with the text up to about five rows, then scroll. Measured from the
  // element rather than counting newlines, so a long wrapped line counts too.
  useEffect(() => {
    const node = inputRef.current;
    if (!node) return;
    node.style.height = 'auto';
    node.style.height = `${Math.min(node.scrollHeight, MAX_ROWS_PX)}px`;
  }, [value, inputRef]);

  const canSend = value.trim() !== '' && !streaming;

  return (
    <form
      className="border-t border-ink-200 bg-white px-3 py-3 dark:border-ink-800 dark:bg-ink-900"
      onSubmit={(event) => {
        event.preventDefault();
        if (canSend) onSend();
      }}
    >
      <div className="flex items-end gap-2">
        <label className="sr-only" htmlFor="chat-message">
          Message the clinic assistant
        </label>
        <textarea
          id="chat-message"
          ref={inputRef}
          rows={1}
          value={value}
          maxLength={MAX_LENGTH}
          placeholder="Ask about your pet, or find an appointment…"
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={(event) => {
            // Enter sends, Shift+Enter writes a new line. The composer is one
            // line tall most of the time, so the common case should not need a
            // trip to the mouse.
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault();
              if (canSend) onSend();
            }
          }}
          className={cn(
            'max-h-[132px] min-h-[42px] flex-1 resize-none rounded-xl px-3.5 py-2.5 text-sm',
            'bg-ink-100 text-ink-900 placeholder:text-ink-400',
            'ring-1 ring-transparent focus:bg-white focus:ring-brand-500 focus:outline-none',
            'dark:bg-ink-800 dark:text-ink-50 dark:placeholder:text-ink-500 dark:focus:bg-ink-800',
          )}
        />

        {streaming ? (
          <Button variant="secondary" size="md" onClick={onStop} aria-label="Stop the reply">
            Stop
          </Button>
        ) : (
          <Button
            type="submit"
            size="md"
            disabled={!canSend}
            className="w-11 px-0"
            aria-label="Send message"
          >
            <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M5 12h13M12 5l7 7-7 7"
              />
            </svg>
          </Button>
        )}
      </div>

      {/* Silent until it matters — a counter on an empty box is just noise. */}
      {value.length > MAX_LENGTH - 400 && (
        <p className="mt-1.5 text-right text-[11px] text-ink-400 tabular-nums dark:text-ink-500">
          {value.length} / {MAX_LENGTH}
        </p>
      )}
    </form>
  );
}
