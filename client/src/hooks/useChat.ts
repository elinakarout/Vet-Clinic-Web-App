// The chat panel's state machine: one turn at a time, over a stream. (Phase 8)
//
// Everything else in this app reads the server through TanStack Query. A chat
// reply cannot: it arrives as hundreds of small events and mutates the same
// object each time, which is a cache invalidation per token. So the transcript
// lives in local state here, and Query is used only for the thread *list*,
// which is ordinary JSON and shared with the history view.
//
// The turn — not the message — is the unit. One assistant turn can interleave
// prose, tool calls and more prose (see api/app/chat/agent.py's loop), so tool
// activity belongs inside the bubble it happened in, not beside it.

import { useCallback, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import * as chatApi from '../api/chat';
import { ApiError } from '../api/client';
import { useAuth } from '../auth/useAuth';
import type {
  ChatEvent,
  ChatMessageOut,
  ProposalEnvelope,
} from '../types/api';
import { ChatRole } from '../types/api';

export const chatKeys = {
  conversations: ['chat', 'conversations'] as const,
};

export interface ChatTurn {
  /** Stable across re-renders; the server's message id once there is one. */
  key: string;
  role: ChatRole;
  text: string;
  /** Human-readable labels for what the assistant looked at, in order. */
  toolLabels: string[];
  /** The label of the tool running right now, or null. */
  activeTool: string | null;
  proposals: ProposalEnvelope[];
  /** An `error` event mid-stream: the reply stopped, the text so far stands. */
  error: string | null;
  /** The user pressed Stop. */
  interrupted: boolean;
  /** True while tokens are still arriving — drives the caret. */
  pending: boolean;
  /** UTC instant, for history rows. Null on a turn created in this session. */
  createdAt: string | null;
}

export type ChatStatus = 'idle' | 'streaming' | 'loading';

let turnCounter = 0;
function nextKey(prefix: string): string {
  turnCounter += 1;
  return `${prefix}-${turnCounter}`;
}

function blankTurn(role: ChatRole, text: string, pending: boolean): ChatTurn {
  return {
    key: nextKey(role.toLowerCase()),
    role,
    text,
    toolLabels: [],
    activeTool: null,
    proposals: [],
    error: null,
    interrupted: false,
    pending,
    createdAt: null,
  };
}

/**
 * A stored message becomes a turn again.
 *
 * `payload.proposals` is what lets a refresh re-render the confirm cards
 * without re-running the model. `payload.tools_used` holds tool *names* —
 * labels are only ever sent live — so they are humanised generically rather
 * than mapped through a table the client would have to keep in step.
 */
function turnFromMessage(message: ChatMessageOut): ChatTurn {
  return {
    key: `msg-${message.id}`,
    role: message.role,
    text: message.content,
    toolLabels: (message.payload?.tools_used ?? []).map((name) =>
      name.replace(/_/g, ' '),
    ),
    activeTool: null,
    proposals: message.payload?.proposals ?? [],
    error: null,
    interrupted: false,
    pending: false,
    createdAt: message.created_at,
  };
}

/** The list of past threads, for the history view. */
export function useConversations(enabled: boolean) {
  return useQuery({
    queryKey: chatKeys.conversations,
    queryFn: () => chatApi.listConversations(50),
    enabled,
    staleTime: 30 * 1000,
  });
}

export function useDeleteConversation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => chatApi.deleteConversation(id),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: chatKeys.conversations }),
  });
}

export function useChat() {
  const { user } = useAuth();
  const queryClient = useQueryClient();

  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [status, setStatus] = useState<ChatStatus>('idle');
  const [error, setError] = useState<ApiError | null>(null);
  const [conversationId, setConversationIdState] = useState<number | null>(null);

  // Refs shadow the state that `send` reads while it runs: the callback is
  // created once and would otherwise close over the values as they were when
  // the panel opened.
  const conversationIdRef = useRef<number | null>(null);
  const streamingRef = useRef(false);
  const abortRef = useRef<AbortController | null>(null);
  const lastMessageRef = useRef('');
  const loadedRef = useRef(false);

  const setConversationId = useCallback(
    (id: number | null) => {
      conversationIdRef.current = id;
      setConversationIdState(id);
      if (user) chatApi.writeActiveConversation(user.id, id);
    },
    [user],
  );

  /** Rewrites the turn at the end of the list — the one being streamed into. */
  const updateOpenTurn = useCallback(
    (update: (turn: ChatTurn) => ChatTurn) => {
      setTurns((previous) => {
        const last = previous[previous.length - 1];
        if (!last || last.role !== ChatRole.ASSISTANT) return previous;
        const next = previous.slice();
        next[next.length - 1] = update(last);
        return next;
      });
    },
    [],
  );

  const handleEvent = useCallback(
    (event: ChatEvent) => {
      switch (event.type) {
        case 'token':
          updateOpenTurn((turn) => ({ ...turn, text: turn.text + event.text }));
          break;
        case 'tool_start':
          updateOpenTurn((turn) => ({
            ...turn,
            activeTool: event.label,
            toolLabels: turn.toolLabels.includes(event.label)
              ? turn.toolLabels
              : [...turn.toolLabels, event.label],
          }));
          break;
        case 'tool_end':
          updateOpenTurn((turn) => ({ ...turn, activeTool: null }));
          break;
        case 'proposal': {
          // Rebuilt member by member rather than spread, so the discriminant and
          // its payload stay correlated for TypeScript.
          const envelope: ProposalEnvelope =
            event.kind === 'appointment'
              ? { kind: 'appointment', proposal: event.proposal }
              : { kind: 'cancellation', proposal: event.proposal };
          updateOpenTurn((turn) => ({
            ...turn,
            proposals: [...turn.proposals, envelope],
          }));
          break;
        }
        case 'error':
          updateOpenTurn((turn) => ({
            ...turn,
            error: event.detail,
            activeTool: null,
            pending: false,
          }));
          break;
        case 'done':
          setConversationId(event.conversation_id);
          // The thread's title and position in the list just changed.
          void queryClient.invalidateQueries({
            queryKey: chatKeys.conversations,
          });
          break;
      }
    },
    [queryClient, setConversationId, updateOpenTurn],
  );

  const send = useCallback(
    async (raw: string) => {
      const message = raw.trim();
      if (message === '' || streamingRef.current) return;

      setError(null);
      lastMessageRef.current = message;
      const controller = new AbortController();
      abortRef.current = controller;
      streamingRef.current = true;
      setStatus('streaming');
      setTurns((previous) => [
        ...previous,
        blankTurn(ChatRole.USER, message, false),
        blankTurn(ChatRole.ASSISTANT, '', true),
      ]);

      try {
        await chatApi.sendMessage({
          message,
          conversationId: conversationIdRef.current,
          signal: controller.signal,
          onEvent: handleEvent,
        });
      } catch (caught) {
        if (caught instanceof DOMException && caught.name === 'AbortError') {
          // stop() already marked the turn; a deliberate stop is not an error.
        } else if (caught instanceof ApiError) {
          // Every status that can arrive here is raised *before* the server
          // persists anything, so nothing was said and both turns come back off
          // — the text returns to the composer via retry().
          setError(caught);
          setTurns((previous) => previous.slice(0, -2));
        } else {
          setError(
            new ApiError(0, 'Something went wrong. Please try again.'),
          );
          setTurns((previous) => previous.slice(0, -2));
        }
      } finally {
        streamingRef.current = false;
        abortRef.current = null;
        setStatus('idle');
        updateOpenTurn((turn) => ({
          ...turn,
          pending: false,
          activeTool: null,
        }));
      }
    },
    [handleEvent, updateOpenTurn],
  );

  /** Stop the reply but keep what has already been written. */
  const stop = useCallback(() => {
    if (!streamingRef.current) return;
    updateOpenTurn((turn) => ({
      ...turn,
      interrupted: true,
      pending: false,
      activeTool: null,
    }));
    abortRef.current?.abort();
  }, [updateOpenTurn]);

  const retry = useCallback(() => {
    const message = lastMessageRef.current;
    if (message === '') return;
    void send(message);
  }, [send]);

  const startNewThread = useCallback(() => {
    abortRef.current?.abort();
    setTurns([]);
    setError(null);
    setConversationId(null);
    loadedRef.current = true;
  }, [setConversationId]);

  const openThread = useCallback(
    async (id: number) => {
      abortRef.current?.abort();
      loadedRef.current = true;
      setStatus('loading');
      setError(null);
      try {
        const detail = await chatApi.getConversation(id);
        setTurns(detail.messages.map(turnFromMessage));
        setConversationId(id);
      } catch (caught) {
        if (
          caught instanceof ApiError &&
          (caught.status === 403 || caught.status === 404)
        ) {
          // Deleted on another device, or never ours. Start clean rather than
          // showing an error for a thread the user did not ask for.
          setTurns([]);
          setConversationId(null);
        } else if (caught instanceof ApiError) {
          setError(caught);
        }
      } finally {
        setStatus('idle');
      }
    },
    [setConversationId],
  );

  /**
   * Reopen whatever thread this user was in, once, the first time the panel is
   * opened. Deliberately not an effect on mount: a user who never opens the
   * assistant should not spend a request on it.
   */
  const restoreLastThread = useCallback(() => {
    if (loadedRef.current || !user) return;
    loadedRef.current = true;
    const stored = chatApi.readActiveConversation(user.id);
    if (stored !== null) void openThread(stored);
  }, [openThread, user]);

  return {
    turns,
    status,
    error,
    conversationId,
    send,
    stop,
    retry,
    startNewThread,
    openThread,
    restoreLastThread,
  };
}
