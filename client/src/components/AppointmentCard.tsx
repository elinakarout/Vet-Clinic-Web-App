// One appointment, with the names joined in and only the legal actions shown. (Phase 5)
//
// AppointmentOut carries pet_id and vet_id and no names at all, so the pet and
// vet are passed in from the cached /pets and /vets lists. When one is missing
// (a staff list paginated past it, say) the id is shown rather than nothing —
// a card reading "Pet #14" is unhelpful but honest; a blank one looks broken.

import {
  formatClinicDateLong,
  formatClinicTime,
  hoursUntil,
  isPast,
} from '../lib/datetime';
import { AppointmentStatus, Role } from '../types/api';
import type { AppointmentOut, PetOut, VetOut } from '../types/api';
import { Badge } from './ui/Badge';
import type { BadgeTone } from './ui/Badge';
import { Button } from './ui/Button';
import { Card } from './ui/Card';

const statusTone: Record<AppointmentStatus, BadgeTone> = {
  [AppointmentStatus.REQUESTED]: 'warning',
  [AppointmentStatus.CONFIRMED]: 'success',
  [AppointmentStatus.CANCELLED]: 'danger',
  [AppointmentStatus.COMPLETED]: 'neutral',
};

const statusLabel: Record<AppointmentStatus, string> = {
  [AppointmentStatus.REQUESTED]: 'Requested',
  [AppointmentStatus.CONFIRMED]: 'Confirmed',
  [AppointmentStatus.CANCELLED]: 'Cancelled',
  [AppointmentStatus.COMPLETED]: 'Completed',
};

/**
 * Mirrors the server's transition graph exactly:
 *   REQUESTED -> CONFIRMED | CANCELLED
 *   CONFIRMED -> COMPLETED | CANCELLED
 *   CANCELLED, COMPLETED -> terminal
 * Offering a move the server will reject with a 409 is worse than not offering
 * it, so the buttons are derived from this rather than guessed at.
 */
function staffMoves(status: AppointmentStatus): AppointmentStatus[] {
  if (status === AppointmentStatus.REQUESTED) return [AppointmentStatus.CONFIRMED];
  if (status === AppointmentStatus.CONFIRMED) return [AppointmentStatus.COMPLETED];
  return [];
}

const moveLabel: Partial<Record<AppointmentStatus, string>> = {
  [AppointmentStatus.CONFIRMED]: 'Confirm',
  [AppointmentStatus.COMPLETED]: 'Mark completed',
};

export function AppointmentCard({
  appointment,
  pet,
  vet,
  viewerRole,
  cancellationCutoffHours = 2,
  busy = false,
  onCancel,
  onStatusChange,
}: {
  appointment: AppointmentOut;
  pet?: PetOut;
  vet?: VetOut;
  viewerRole: Role;
  cancellationCutoffHours?: number;
  busy?: boolean;
  onCancel?: (appointment: AppointmentOut) => void;
  onStatusChange?: (appointment: AppointmentOut, status: AppointmentStatus) => void;
}) {
  const active =
    appointment.status === AppointmentStatus.REQUESTED ||
    appointment.status === AppointmentStatus.CONFIRMED;
  const started = isPast(appointment.starts_at);
  const isStaff = viewerRole === Role.VET || viewerRole === Role.ADMIN;

  // A client inside the cutoff gets a 409, so the button is replaced by the
  // reason rather than left there to fail.
  const withinCutoff =
    !isStaff && hoursUntil(appointment.starts_at) < cancellationCutoffHours;
  const canCancel = active && !started && Boolean(onCancel) && !withinCutoff;
  const moves = isStaff ? staffMoves(appointment.status) : [];

  return (
    <Card className="flex flex-col gap-4 p-5 sm:flex-row sm:items-center">
      <div className="flex shrink-0 flex-col items-center justify-center rounded-lg bg-brand-50 px-4 py-3 text-center dark:bg-brand-500/10">
        <span className="text-xl font-semibold tabular-nums text-brand-800 dark:text-brand-200">
          {formatClinicTime(appointment.starts_at)}
        </span>
        <span className="mt-0.5 text-xs text-brand-700/80 dark:text-brand-300/80">
          {formatClinicTime(appointment.ends_at)}
        </span>
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-base font-semibold text-ink-900 dark:text-ink-50">
            {pet ? pet.name : `Pet #${appointment.pet_id}`}
          </h3>
          <Badge tone={statusTone[appointment.status]}>
            {statusLabel[appointment.status]}
          </Badge>
        </div>
        <p className="mt-0.5 text-sm text-ink-600 dark:text-ink-300">
          {formatClinicDateLong(appointment.starts_at)}
          {' · '}
          {vet ? vet.full_name : `Vet #${appointment.vet_id}`}
        </p>
        {appointment.reason && (
          <p className="mt-1.5 text-sm text-ink-500 dark:text-ink-400">
            {appointment.reason}
          </p>
        )}
        {withinCutoff && active && !started && (
          <p className="mt-1.5 text-xs text-amber-700 dark:text-amber-300">
            Starting within {cancellationCutoffHours} hours — please call the clinic
            to cancel.
          </p>
        )}
      </div>

      {(canCancel || moves.length > 0) && (
        <div className="flex shrink-0 flex-wrap gap-2">
          {moves.map((status) => (
            <Button
              key={status}
              size="sm"
              disabled={busy}
              onClick={() => onStatusChange?.(appointment, status)}
            >
              {moveLabel[status] ?? status}
            </Button>
          ))}
          {canCancel && (
            <Button
              variant="secondary"
              size="sm"
              disabled={busy}
              onClick={() => onCancel?.(appointment)}
            >
              Cancel
            </Button>
          )}
        </div>
      )}
    </Card>
  );
}
