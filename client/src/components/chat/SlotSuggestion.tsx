// The assistant's confirm cards: a proposed booking, and a proposed cancellation. (Phase 8)
//
// **The chatbot never writes to the calendar.** It proposes; the user clicks;
// the click goes through the ordinary useBookAppointment / useCancelAppointment
// mutations — the same POST /appointments and POST /appointments/{id}/cancel as
// the manual flow, with the same ownership checks, the same cancellation cutoff
// and the same double-booking index behind them. If the model misunderstood, the
// worst case is a card somebody declines.
//
// `starts_at` is passed through EXACTLY as it arrived. It is already an exact
// slot boundary carrying a UTC offset, which is what the server requires;
// re-parsing it in browser time or rebuilding it from the label on screen is how
// you get a 409, or a booking on the wrong day.

import { useState } from 'react';
import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { ApiError } from '../../api/client';
import { useBookAppointment, useCancelAppointment } from '../../hooks/useAppointments';
import { clinicZoneLabel, formatClinicDateTime } from '../../lib/datetime';
import type { AppointmentProposal, CancellationProposal } from '../../types/api';
import { Button } from '../ui/Button';
import { useToast } from '../ui/useToast';

type CardState = 'idle' | 'done' | 'declined';

function CardShell({
  tone,
  eyebrow,
  children,
}: {
  tone: 'brand' | 'rose';
  eyebrow: string;
  children: ReactNode;
}) {
  return (
    <div
      className={
        tone === 'brand'
          ? 'w-[88%] rounded-2xl border border-brand-200 bg-brand-50/70 p-3.5 dark:border-brand-500/30 dark:bg-brand-500/10'
          : 'w-[88%] rounded-2xl border border-rose-200 bg-rose-50/70 p-3.5 dark:border-rose-500/30 dark:bg-rose-500/10'
      }
    >
      <p
        className={
          tone === 'brand'
            ? 'mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-brand-700 dark:text-brand-300'
            : 'mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-rose-700 dark:text-rose-300'
        }
      >
        {eyebrow}
      </p>
      {children}
    </div>
  );
}

/** Pet, vet, when — the three things a card has to answer at a glance. */
function When({ startsAt }: { startsAt: string }) {
  return (
    <p className="mt-1 text-sm font-semibold text-ink-900 dark:text-ink-50">
      {formatClinicDateTime(startsAt)}{' '}
      <span className="font-normal text-ink-500 dark:text-ink-400">
        ({clinicZoneLabel()})
      </span>
    </p>
  );
}

function DoneNote({ children }: { children: ReactNode }) {
  return (
    <p className="flex items-center gap-2 text-sm text-ink-700 dark:text-ink-200">
      <svg
        className="h-4 w-4 shrink-0 text-brand-600 dark:text-brand-400"
        viewBox="0 0 24 24"
        fill="none"
        aria-hidden="true"
      >
        <path
          stroke="currentColor"
          strokeWidth="2.2"
          strokeLinecap="round"
          strokeLinejoin="round"
          d="m5 13 4 4L19 7"
        />
      </svg>
      {children}
    </p>
  );
}

/** A booking the assistant is suggesting. Nothing is written until Confirm. */
export function SlotSuggestion({
  proposal,
  onAsk,
}: {
  proposal: AppointmentProposal;
  /** Sends a follow-up message — used when the slot has just gone. */
  onAsk: (message: string) => void;
}) {
  const [state, setState] = useState<CardState>('idle');
  const [failure, setFailure] = useState<ApiError | null>(null);
  const book = useBookAppointment();
  const toast = useToast();

  const confirm = () => {
    setFailure(null);
    book.mutate(
      {
        pet_id: proposal.pet_id,
        vet_id: proposal.vet_id,
        starts_at: proposal.starts_at,
        reason: proposal.reason,
      },
      {
        onSuccess: () => {
          setState('done');
          toast.success(
            `Booked ${proposal.pet_name} for ${formatClinicDateTime(proposal.starts_at)}`,
          );
        },
        onError: (error) => {
          setFailure(
            error instanceof ApiError
              ? error
              : new ApiError(0, 'Could not book that time. Please try again.'),
          );
        },
      },
    );
  };

  if (state === 'done') {
    return (
      <CardShell tone="brand" eyebrow="Booked">
        <DoneNote>
          {proposal.pet_name} — {formatClinicDateTime(proposal.starts_at)} with{' '}
          {proposal.vet_name}
        </DoneNote>
        <Link
          to="/appointments"
          className="mt-2 inline-block text-sm font-medium text-brand-700 underline underline-offset-2 hover:text-brand-800 dark:text-brand-300 dark:hover:text-brand-200"
        >
          View my appointments
        </Link>
      </CardShell>
    );
  }

  if (state === 'declined') {
    return (
      <CardShell tone="brand" eyebrow="Not booked">
        <p className="text-sm text-ink-600 dark:text-ink-300">
          Left alone. Ask for another time whenever you like.
        </p>
      </CardShell>
    );
  }

  return (
    <CardShell tone="brand" eyebrow="Suggested appointment">
      <p className="text-sm text-ink-700 dark:text-ink-200">
        <span className="font-semibold text-ink-900 dark:text-ink-50">
          {proposal.pet_name}
        </span>{' '}
        with {proposal.vet_name}
      </p>
      <When startsAt={proposal.starts_at} />
      {proposal.reason && (
        <p className="mt-1 text-sm text-ink-600 dark:text-ink-300">
          {proposal.reason}
        </p>
      )}

      {failure && (
        <p role="alert" className="mt-2 text-sm text-rose-700 dark:text-rose-300">
          {failure.status === 409
            ? 'That time was taken while we were talking.'
            : failure.detail}
        </p>
      )}

      <div className="mt-3 flex flex-wrap gap-2">
        {failure?.status === 409 ? (
          <Button
            size="sm"
            onClick={() => onAsk('That time is taken — what else is free?')}
          >
            Find another time
          </Button>
        ) : (
          <Button size="sm" loading={book.isPending} onClick={confirm}>
            Confirm booking
          </Button>
        )}
        <Button
          size="sm"
          variant="ghost"
          disabled={book.isPending}
          onClick={() => setState('declined')}
        >
          Not now
        </Button>
      </div>
    </CardShell>
  );
}

/** A cancellation the assistant is suggesting. Same rule: it never writes. */
export function CancellationSuggestion({
  proposal,
}: {
  proposal: CancellationProposal;
}) {
  const [state, setState] = useState<CardState>('idle');
  const [failure, setFailure] = useState<ApiError | null>(null);
  const cancel = useCancelAppointment();
  const toast = useToast();

  const confirm = () => {
    setFailure(null);
    cancel.mutate(proposal.appointment_id, {
      onSuccess: () => {
        setState('done');
        toast.success('Appointment cancelled');
      },
      onError: (error) => {
        // A client inside the two-hour cutoff gets a 409 with a sentence that
        // explains it. Show the server's words rather than guessing at the rule.
        setFailure(
          error instanceof ApiError
            ? error
            : new ApiError(0, 'Could not cancel that appointment.'),
        );
      },
    });
  };

  if (state === 'done') {
    return (
      <CardShell tone="rose" eyebrow="Cancelled">
        <DoneNote>
          {proposal.pet_name} — {formatClinicDateTime(proposal.starts_at)}
        </DoneNote>
      </CardShell>
    );
  }

  if (state === 'declined') {
    return (
      <CardShell tone="rose" eyebrow="Kept">
        <p className="text-sm text-ink-600 dark:text-ink-300">
          The appointment is still booked.
        </p>
      </CardShell>
    );
  }

  return (
    <CardShell tone="rose" eyebrow="Cancel this appointment?">
      <p className="text-sm text-ink-700 dark:text-ink-200">
        <span className="font-semibold text-ink-900 dark:text-ink-50">
          {proposal.pet_name}
        </span>{' '}
        with {proposal.vet_name}
      </p>
      <When startsAt={proposal.starts_at} />
      {proposal.reason && (
        <p className="mt-1 text-sm text-ink-600 dark:text-ink-300">
          {proposal.reason}
        </p>
      )}

      {failure && (
        <p role="alert" className="mt-2 text-sm text-rose-700 dark:text-rose-300">
          {failure.detail}
        </p>
      )}

      <div className="mt-3 flex flex-wrap gap-2">
        <Button
          size="sm"
          variant="danger"
          loading={cancel.isPending}
          onClick={confirm}
        >
          Yes, cancel it
        </Button>
        <Button
          size="sm"
          variant="ghost"
          disabled={cancel.isPending}
          onClick={() => setState('declined')}
        >
          Keep it
        </Button>
      </div>
    </CardShell>
  );
}
