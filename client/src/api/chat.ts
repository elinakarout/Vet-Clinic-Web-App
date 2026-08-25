// Calls to /chat and /chat/conversations. (Phase 8)
//
// One of these is not like the others: `sendMessage` streams. It goes through
// `apiStream` rather than `apiFetch` for the reason written up there, and the
// events it yields are the contract in API.md, typed as `ChatEvent`.

import { apiFetch, apiStream } from './client';
import type {
  ChatEvent,
  ConversationDetailOut,
  ConversationOut,
} from '../types/api';

/**
 * Send one turn and receive the reply as it is written.
 *
 * Omit `conversationId` to start a thread; read the id the server made off the
 * `done` event and pass it next time. There is no history parameter — the
 * server rebuilds it from the database, keyed on the JWT, so the browser cannot
 * forge what it said earlier.
 */
export function sendMessage(options: {
  message: string;
  conversationId: number | null;
  signal?: AbortSignal;
  onEvent: (event: ChatEvent) => void;
}): Promise<void> {
  const { message, conversationId, signal, onEvent } = options;
  return apiStream('/chat', {
    body:
      conversationId === null
        ? { message }
        : { message, conversation_id: conversationId },
    signal,
    // The server is the only writer of these frames and its schema is pinned by
    // api/app/schemas/chat.py, so this cast is the boundary, not a guess.
    onEvent: (event) => onEvent(event as ChatEvent),
  });
}

/** The caller's own threads, most recently used first. No staff bypass. */
export function listConversations(
  limit = 20,
  offset = 0,
): Promise<ConversationOut[]> {
  return apiFetch<ConversationOut[]>('/chat/conversations', {
    query: { limit, offset },
  });
}

/** One thread with its transcript, oldest first. 403 even for an admin. */
export function getConversation(id: number): Promise<ConversationDetailOut> {
  return apiFetch<ConversationDetailOut>(`/chat/conversations/${id}`);
}

/** A real delete, unlike a pet — a transcript is the user's own. */
export function deleteConversation(id: number): Promise<void> {
  return apiFetch<void>(`/chat/conversations/${id}`, { method: 'DELETE' });
}

// --- Which thread this browser is in the middle of ------------------------
//
// PROJECT_PLAN.md Phase 8 step 6: a refresh must not lose the conversation. The
// messages themselves live on the server; all that has to survive locally is
// which thread was open.
//
// Keyed by user id, because a shared browser must not resume somebody else's
// conversation — the same worry that makes sign-out call `queryClient.clear()`.
// The server would refuse it anyway (403), but the fix for that is not to ask.

const THREAD_KEY_PREFIX = 'vetclinic.chat.thread.';

export function readActiveConversation(userId: number): number | null {
  try {
    const raw = localStorage.getItem(`${THREAD_KEY_PREFIX}${userId}`);
    if (raw === null) return null;
    const id = Number(raw);
    return Number.isInteger(id) && id > 0 ? id : null;
  } catch {
    // Private-mode Safari and "block site data" throw rather than return null.
    return null;
  }
}

export function writeActiveConversation(
  userId: number,
  conversationId: number | null,
): void {
  try {
    const key = `${THREAD_KEY_PREFIX}${userId}`;
    if (conversationId === null) localStorage.removeItem(key);
    else localStorage.setItem(key, String(conversationId));
  } catch {
    // Non-fatal: the thread simply won't be reopened after a reload.
  }
}

/** Called on sign-out, for every user this browser has seen. */
export function clearActiveConversations(): void {
  try {
    for (const key of Object.keys(localStorage)) {
      if (key.startsWith(THREAD_KEY_PREFIX)) localStorage.removeItem(key);
    }
  } catch {
    // Nothing to clear if the store is unreadable.
  }
}
