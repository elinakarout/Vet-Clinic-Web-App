// Past conversations, inside the panel. (Phase 8)
//
// Deleting is inline — two taps in the row — rather than the app's ConfirmDialog.
// That dialog is a real modal: it traps focus and swallows Escape, and nesting
// one inside the drawer (which does the same) leaves two components fighting over
// the same key. A chat transcript is also not a pet: `DELETE /chat/conversations`
// is a plain delete the user is entitled to, not a clinical record.

import { useState } from 'react';
import { useConversations, useDeleteConversation } from '../../hooks/useChat';
import { cn } from '../../lib/cn';
import { formatClinicTime, relativeDayLabel, toClinicDate } from '../../lib/datetime';
import type { ConversationOut } from '../../types/api';
import { Button } from '../ui/Button';
import { EmptyState, ErrorState, SkeletonList } from '../ui/States';

function when(conversation: ConversationOut): string {
  const date = toClinicDate(conversation.updated_at);
  const day = relativeDayLabel(date);
  return day === 'Today' ? formatClinicTime(conversation.updated_at) : day;
}

export function ChatHistory({
  activeId,
  onOpen,
  onDeleted,
}: {
  activeId: number | null;
  onOpen: (id: number) => void;
  /** So the panel can let go of a thread that is no longer there. */
  onDeleted: (id: number) => void;
}) {
  const { data, isPending, isError, refetch } = useConversations(true);
  const remove = useDeleteConversation();
  const [confirming, setConfirming] = useState<number | null>(null);

  if (isPending) {
    return (
      <div className="p-4">
        <SkeletonList rows={4} />
      </div>
    );
  }

  if (isError) {
    return (
      <div className="p-4">
        <ErrorState
          message="Your past conversations could not be loaded."
          onRetry={() => void refetch()}
        />
      </div>
    );
  }

  if (data.length === 0) {
    return (
      <div className="p-4">
        <EmptyState
          title="No conversations yet"
          description="Anything you ask the assistant will be kept here, so you can pick it up later."
        />
      </div>
    );
  }

  return (
    <ul className="divide-y divide-ink-200/70 dark:divide-ink-800">
      {data.map((conversation) => {
        const isConfirming = confirming === conversation.id;
        return (
          <li key={conversation.id} className="px-2 py-1">
            <div
              className={cn(
                'flex items-center gap-2 rounded-xl px-2 py-2',
                conversation.id === activeId && 'bg-brand-50 dark:bg-brand-500/10',
              )}
            >
              <button
                type="button"
                onClick={() => onOpen(conversation.id)}
                className="min-w-0 flex-1 text-left"
                aria-current={conversation.id === activeId || undefined}
              >
                <span className="block truncate text-sm text-ink-800 dark:text-ink-100">
                  {conversation.title ?? 'Untitled conversation'}
                </span>
                <span className="mt-0.5 block text-[11px] text-ink-400 dark:text-ink-500">
                  {when(conversation)}
                </span>
              </button>

              {isConfirming ? (
                <span className="flex shrink-0 items-center gap-1">
                  <Button
                    size="sm"
                    variant="danger"
                    loading={remove.isPending}
                    onClick={() =>
                      remove.mutate(conversation.id, {
                        onSuccess: () => onDeleted(conversation.id),
                        onSettled: () => setConfirming(null),
                      })
                    }
                  >
                    Delete
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setConfirming(null)}>
                    Keep
                  </Button>
                </span>
              ) : (
                <button
                  type="button"
                  onClick={() => setConfirming(conversation.id)}
                  className="shrink-0 rounded-lg p-2 text-ink-400 hover:bg-ink-100 hover:text-rose-600 dark:hover:bg-ink-800 dark:hover:text-rose-400"
                  aria-label={`Delete conversation: ${conversation.title ?? 'untitled'}`}
                >
                  <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                    <path
                      stroke="currentColor"
                      strokeWidth="1.8"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M5 7h14M10 7V5h4v2m-7 0 .8 12.1a1 1 0 0 0 1 .9h6.4a1 1 0 0 0 1-.9L18 7"
                    />
                  </svg>
                </button>
              )}
            </div>
          </li>
        );
      })}
    </ul>
  );
}
