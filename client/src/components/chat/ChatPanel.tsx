// The clinic assistant: a slide-out panel available on every page. (Phase 8)
//
// The Phase 5 shell's layout survives — floating button, right-hand drawer, the
// safety disclaimer in the header where users look for it (PROJECT_PLAN.md
// section 8.5). Phase 8 replaced the "coming soon" body with the real thing:
// a streamed transcript, tool status lines, confirm cards, and the thread
// history.
//
// The drawer is a dialog and behaves like one — Escape closes it, focus moves to
// the composer and returns to the button, Tab cycles inside, the page behind
// does not scroll. That is the same treatment components/ui/Modal.tsx gives the
// app's two modals, repeated here rather than imported because this panel needs
// its own header, its own body and no footer.

import { useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { ApiError } from '../../api/client';
import { useAuth } from '../../auth/useAuth';
import { useChat } from '../../hooks/useChat';
import { cn } from '../../lib/cn';
import { Role } from '../../types/api';
import { ErrorState, Skeleton } from '../ui/States';
import { ChatComposer } from './ChatComposer';
import { ChatHistory } from './ChatHistory';
import { MessageBubble } from './MessageBubble';
import { CancellationSuggestion, SlotSuggestion } from './SlotSuggestion';

const FOCUSABLE =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

const CLIENT_STARTERS = [
  'When is my pet due for vaccinations?',
  'What are your opening hours?',
  'I would like a check-up next week',
];

const STAFF_STARTERS = [
  'What does the clinic advise about kitten vaccinations?',
  'What are the signs of an emergency?',
  'What are your opening hours?',
];

/** The server's sentences are already written for a human — keep them. */
function errorTitle(error: ApiError): string {
  if (error.status === 429) return 'One at a time';
  if (error.status === 503) return 'The assistant is unavailable';
  if (error.status === 0) return 'No connection';
  return 'That did not go through';
}

function IconButton({
  label,
  onClick,
  children,
}: {
  label: string;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      title={label}
      className="rounded-lg p-2 text-ink-500 hover:bg-ink-100 hover:text-ink-900 dark:text-ink-400 dark:hover:bg-ink-800 dark:hover:text-ink-50"
    >
      {children}
    </button>
  );
}

export function ChatPanel() {
  const { user } = useAuth();
  const chat = useChat();
  const [open, setOpen] = useState(false);
  const [view, setView] = useState<'chat' | 'history'>('chat');
  const [draft, setDraft] = useState('');
  const [atBottom, setAtBottom] = useState(true);

  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const { restoreLastThread } = chat;

  // Opening the panel is what loads the last thread — not mounting it. Every
  // page renders this component; most visits never open it.
  useEffect(() => {
    if (!open) return;
    restoreLastThread();

    const trigger = triggerRef.current;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    // The composer when there is one, the panel itself when the history view is
    // showing — never nothing, or the first Tab escapes to the page behind.
    (inputRef.current ?? panelRef.current)?.focus();

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        event.preventDefault();
        setOpen(false);
        return;
      }
      if (event.key !== 'Tab' || !panelRef.current) return;
      const items = panelRef.current.querySelectorAll<HTMLElement>(FOCUSABLE);
      if (items.length === 0) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      document.body.style.overflow = previousOverflow;
      trigger?.focus();
    };
  }, [open, restoreLastThread]);

  // Follow the reply as it is written — but only if the user is already at the
  // bottom. Yanking the view away from something they scrolled back to read is
  // the single most irritating thing a chat panel can do.
  useEffect(() => {
    if (!atBottom || view !== 'chat') return;
    const node = scrollRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [chat.turns, atBottom, view]);

  const ask = (text: string) => {
    setView('chat');
    setAtBottom(true);
    void chat.send(text);
  };

  const submit = () => {
    const text = draft;
    setDraft('');
    ask(text);
  };

  const starters = user?.role === Role.CLIENT ? CLIENT_STARTERS : STAFF_STARTERS;
  const streaming = chat.status === 'streaming';

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpen(true)}
        className="fixed bottom-5 right-5 z-40 flex h-14 w-14 items-center justify-center rounded-full bg-brand-600 text-white shadow-lg transition-transform hover:scale-105 hover:bg-brand-700 dark:bg-brand-500 dark:text-ink-950 dark:hover:bg-brand-400"
        aria-label="Open the clinic assistant"
        aria-haspopup="dialog"
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
            tabIndex={-1}
            onClick={() => setOpen(false)}
          />
          <div
            ref={panelRef}
            role="dialog"
            aria-modal="true"
            aria-label="Clinic assistant"
            tabIndex={-1}
            className="relative flex h-full w-full max-w-md flex-col bg-sand-50 shadow-xl dark:bg-ink-950"
          >
            <header className="border-b border-ink-200 bg-white px-4 py-3 dark:border-ink-800 dark:bg-ink-900">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <h2 className="text-base font-semibold text-ink-900 dark:text-ink-50">
                    Clinic assistant
                  </h2>
                  <p className="mt-0.5 text-xs text-ink-500 dark:text-ink-400">
                    Provides general information, not medical advice. For anything
                    urgent, call the clinic.
                  </p>
                </div>
                <div className="flex shrink-0 items-center">
                  <IconButton
                    label={view === 'history' ? 'Back to conversation' : 'Past conversations'}
                    onClick={() => setView(view === 'history' ? 'chat' : 'history')}
                  >
                    <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                      <path
                        stroke="currentColor"
                        strokeWidth="1.8"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        d="M12 8v4l2.5 2.5M3.5 12a8.5 8.5 0 1 0 2.2-5.7M5 4v3h3"
                      />
                    </svg>
                  </IconButton>
                  <IconButton
                    label="New conversation"
                    onClick={() => {
                      chat.startNewThread();
                      setDraft('');
                      setView('chat');
                      setAtBottom(true);
                    }}
                  >
                    <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                      <path
                        stroke="currentColor"
                        strokeWidth="1.8"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        d="M4 20h4L19 9a2.1 2.1 0 0 0-3-3L5 17v3ZM14.5 6.5l3 3"
                      />
                    </svg>
                  </IconButton>
                  <IconButton label="Close the assistant" onClick={() => setOpen(false)}>
                    <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                      <path
                        stroke="currentColor"
                        strokeWidth="1.8"
                        strokeLinecap="round"
                        d="M6 6l12 12M18 6 6 18"
                      />
                    </svg>
                  </IconButton>
                </div>
              </div>
            </header>

            {view === 'history' ? (
              <div className="flex-1 overflow-y-auto">
                <ChatHistory
                  activeId={chat.conversationId}
                  onOpen={(id) => {
                    void chat.openThread(id);
                    setView('chat');
                    setAtBottom(true);
                  }}
                  onDeleted={(id) => {
                    // Deleting the thread you are in leaves the transcript on
                    // screen pointing at a row that no longer exists; the next
                    // message would be a 404 the user cannot act on.
                    if (id === chat.conversationId) chat.startNewThread();
                  }}
                />
              </div>
            ) : (
              <>
                <div
                  ref={scrollRef}
                  role="log"
                  aria-label="Conversation"
                  aria-busy={streaming}
                  onScroll={(event) => {
                    const node = event.currentTarget;
                    setAtBottom(
                      node.scrollHeight - node.scrollTop - node.clientHeight < 48,
                    );
                  }}
                  className="flex-1 space-y-4 overflow-y-auto overscroll-contain px-4 py-4"
                >
                  {chat.status === 'loading' && (
                    <div className="space-y-3 pt-2" role="status" aria-label="Loading the conversation">
                      <Skeleton className="ml-auto h-10 w-2/3" />
                      <Skeleton className="h-20 w-5/6" />
                    </div>
                  )}

                  {chat.turns.length === 0 && chat.status !== 'loading' && (
                    <div className="pt-6">
                      <p className="text-sm text-ink-600 dark:text-ink-300">
                        Hello{user?.full_name ? `, ${user.full_name.split(' ')[0]}` : ''}.
                        Ask me about your pet's care, the clinic, or finding a time
                        to come in.
                      </p>
                      <div className="mt-4 flex flex-col items-start gap-2">
                        {starters.map((starter) => (
                          <button
                            key={starter}
                            type="button"
                            onClick={() => ask(starter)}
                            className="rounded-full border border-ink-200 bg-white px-3.5 py-2 text-left text-sm text-ink-700 transition-colors hover:border-brand-300 hover:bg-brand-50 hover:text-brand-800 dark:border-ink-700 dark:bg-ink-800 dark:text-ink-200 dark:hover:border-brand-500/40 dark:hover:bg-brand-500/10 dark:hover:text-brand-200"
                          >
                            {starter}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                  {chat.turns.map((turn) => (
                    <MessageBubble key={turn.key} turn={turn}>
                      {turn.proposals.map((envelope, index) =>
                        envelope.kind === 'appointment' ? (
                          <SlotSuggestion
                            key={`${turn.key}-p${index}`}
                            proposal={envelope.proposal}
                            onAsk={ask}
                          />
                        ) : (
                          <CancellationSuggestion
                            key={`${turn.key}-p${index}`}
                            proposal={envelope.proposal}
                          />
                        ),
                      )}
                    </MessageBubble>
                  ))}

                  {chat.error && (
                    <ErrorState
                      title={errorTitle(chat.error)}
                      message={chat.error.detail}
                      onRetry={chat.retry}
                    />
                  )}
                </div>

                {!atBottom && (
                  <button
                    type="button"
                    onClick={() => {
                      setAtBottom(true);
                      const node = scrollRef.current;
                      if (node) node.scrollTop = node.scrollHeight;
                    }}
                    className={cn(
                      'absolute bottom-24 left-1/2 -translate-x-1/2 rounded-full px-3 py-1.5 text-xs font-medium shadow-md',
                      'bg-ink-900 text-white dark:bg-ink-100 dark:text-ink-900',
                    )}
                  >
                    Jump to latest
                  </button>
                )}

                <ChatComposer
                  value={draft}
                  onChange={setDraft}
                  onSend={submit}
                  onStop={chat.stop}
                  streaming={streaming}
                  inputRef={inputRef}
                />
              </>
            )}
          </div>
        </div>
      )}
    </>
  );
}
