// One chat turn: the bubble, what the assistant checked, and the live caret. (Phase 8)
//
// The text is written by a language model, so two rules hold throughout this
// file: it is rendered as text nodes only — there is no `dangerouslySetInnerHTML`
// here and there must never be — and the small amount of formatting understood
// below (paragraphs, bullet and numbered lists, `**bold**`) is applied to those
// nodes rather than parsed as HTML. That is the whole reason this exists instead
// of `react-markdown`: the surface a model can reach stays four lines wide.

import { Fragment } from 'react';
import type { ReactNode } from 'react';
import { cn } from '../../lib/cn';
import { formatClinicTime } from '../../lib/datetime';
import { Spinner } from '../ui/Spinner';
import type { ChatTurn } from '../../hooks/useChat';
import { ChatRole } from '../../types/api';

// --- The formatter --------------------------------------------------------

const BULLET = /^\s*[-*•]\s+(.*)$/;
const NUMBERED = /^\s*\d+[.)]\s+(.*)$/;

interface Block {
  type: 'p' | 'ul' | 'ol';
  lines: string[];
}

/** Groups consecutive lines into paragraphs and lists. */
function toBlocks(text: string): Block[] {
  const blocks: Block[] = [];
  let open: Block | null = null;

  for (const line of text.split('\n')) {
    if (line.trim() === '') {
      open = null;
      continue;
    }
    const bullet = BULLET.exec(line);
    const numbered = bullet ? null : NUMBERED.exec(line);
    const type: Block['type'] = bullet ? 'ul' : numbered ? 'ol' : 'p';
    const content = (bullet?.[1] ?? numbered?.[1] ?? line).trim();

    if (open && open.type === type) {
      open.lines.push(content);
    } else {
      open = { type, lines: [content] };
      blocks.push(open);
    }
  }
  return blocks;
}

/** `**bold**` becomes <strong>. Everything else stays literal. */
function renderInline(text: string): ReactNode[] {
  return text.split(/\*\*(.+?)\*\*/g).map((part, index) =>
    index % 2 === 1 ? (
      <strong key={index} className="font-semibold">
        {part}
      </strong>
    ) : (
      <Fragment key={index}>{part}</Fragment>
    ),
  );
}

function RichText({ text }: { text: string }) {
  return (
    <>
      {toBlocks(text).map((block, index) => {
        if (block.type === 'p') {
          return (
            <p key={index} className="whitespace-pre-wrap">
              {block.lines.map((line, lineIndex) => (
                <Fragment key={lineIndex}>
                  {lineIndex > 0 && <br />}
                  {renderInline(line)}
                </Fragment>
              ))}
            </p>
          );
        }
        const items = block.lines.map((line, itemIndex) => (
          <li key={itemIndex}>{renderInline(line)}</li>
        ));
        return block.type === 'ul' ? (
          <ul key={index} className="list-disc space-y-1 pl-5">
            {items}
          </ul>
        ) : (
          <ol key={index} className="list-decimal space-y-1 pl-5">
            {items}
          </ol>
        );
      })}
    </>
  );
}

// --- Tool activity --------------------------------------------------------

/**
 * "Checking availability…" while a tool runs.
 *
 * The label is whatever the server sent on `tool_start`; the client keeps no
 * name→label table, so a new tool needs no frontend change. `aria-live` because
 * a blind user otherwise gets silence between question and answer.
 */
export function ToolStatusLine({ label }: { label: string }) {
  return (
    <p
      className="flex items-center gap-2 text-xs text-ink-500 dark:text-ink-400"
      aria-live="polite"
    >
      <Spinner className="h-3.5 w-3.5" />
      {label}
    </p>
  );
}

/** What the finished turn looked at — kept quiet, but never hidden. */
export function ToolTrace({ labels }: { labels: string[] }) {
  if (labels.length === 0) return null;
  return (
    <p className="flex flex-wrap items-center gap-1.5 text-[11px] text-ink-400 dark:text-ink-500">
      <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path
          stroke="currentColor"
          strokeWidth="2.4"
          strokeLinecap="round"
          strokeLinejoin="round"
          d="m5 13 4 4L19 7"
        />
      </svg>
      {labels.map((label) => (
        <span
          key={label}
          className="rounded-full bg-ink-100 px-2 py-0.5 dark:bg-ink-800"
        >
          {label.replace(/\.\.\.$|…$/, '')}
        </span>
      ))}
    </p>
  );
}

// --- The bubble -----------------------------------------------------------

/** Three dots while the model is thinking and no token has landed yet. */
function ThinkingDots() {
  return (
    <span className="flex items-center gap-1 py-1" aria-label="Thinking">
      {[0, 1, 2].map((dot) => (
        <span
          key={dot}
          className="h-1.5 w-1.5 animate-bounce rounded-full bg-ink-400 dark:bg-ink-500"
          style={{ animationDelay: `${dot * 140}ms` }}
        />
      ))}
    </span>
  );
}

/**
 * `children` is where the panel puts the confirm cards, so a proposal sits
 * under the sentence that introduced it rather than in a column of its own.
 */
export function MessageBubble({
  turn,
  children,
}: {
  turn: ChatTurn;
  children?: ReactNode;
}) {
  const isUser = turn.role === ChatRole.USER;
  const showDots = turn.pending && turn.text === '' && turn.activeTool === null;

  return (
    <div className={cn('flex flex-col gap-1.5', isUser ? 'items-end' : 'items-start')}>
      <div
        className={cn(
          'max-w-[88%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed',
          isUser
            ? 'rounded-br-md bg-brand-600 text-white dark:bg-brand-500 dark:text-ink-950'
            : 'rounded-bl-md bg-white text-ink-800 ring-1 ring-ink-200/70 dark:bg-ink-800 dark:text-ink-100 dark:ring-ink-700',
        )}
      >
        <div className="space-y-2.5">
          {showDots ? <ThinkingDots /> : <RichText text={turn.text} />}
          {turn.pending && turn.text !== '' && (
            <span
              className="-mb-0.5 ml-0.5 inline-block h-4 w-[3px] animate-pulse rounded-full bg-brand-500 align-middle dark:bg-brand-300"
              aria-hidden="true"
            />
          )}
        </div>
      </div>

      {turn.activeTool !== null && <ToolStatusLine label={turn.activeTool} />}
      {!turn.pending && !isUser && <ToolTrace labels={turn.toolLabels} />}

      {children}

      {turn.error !== null && (
        <p
          role="alert"
          className="max-w-[88%] rounded-xl bg-rose-50 px-3 py-2 text-xs text-rose-800 dark:bg-rose-500/10 dark:text-rose-300"
        >
          {turn.error}
        </p>
      )}
      {turn.interrupted && (
        <p className="text-[11px] text-ink-400 dark:text-ink-500">Stopped</p>
      )}
      {turn.createdAt !== null && (
        <p className="text-[11px] text-ink-400 tabular-nums dark:text-ink-500">
          {formatClinicTime(turn.createdAt)}
        </p>
      )}
    </div>
  );
}
