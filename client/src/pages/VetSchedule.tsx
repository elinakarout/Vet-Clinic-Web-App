// Vet's today/this-week appointments. (Phase 5)

import { useMemo, useState } from 'react';
import { ApiError } from '../api/client';
import { useAuth } from '../auth/useAuth';
import { AppointmentCard } from '../components/AppointmentCard';
import { Card } from '../components/ui/Card';
import { ConfirmDialog } from '../components/ui/ConfirmDialog';
import { EmptyState, ErrorState, SkeletonList } from '../components/ui/States';
import { useToast } from '../components/ui/useToast';
import {
  useAppointments,
  useCancelAppointment,
  useSetAppointmentStatus,
} from '../hooks/useAppointments';
import { usePetMap } from '../hooks/usePets';
import { useVetMap } from '../hooks/useVets';
import { cn } from '../lib/cn';
import {
  addDays,
  clinicToday,
  groupByClinicDay,
  startOfDayUtc,
} from '../lib/datetime';
import { AppointmentStatus, Role } from '../types/api';
import type { AppointmentOut } from '../types/api';

type Range = 'today' | 'week';

export function VetSchedule() {
  const { user } = useAuth();
  const toast = useToast();
  const [range, setRange] = useState<Range>('today');
  const [cancelling, setCancelling] = useState<AppointmentOut | null>(null);

  const today = clinicToday();
  // `date_to` is EXCLUSIVE on this endpoint, so a single day asks for today
  // through tomorrow, and a week asks for seven days through the eighth.
  const dateFrom = startOfDayUtc(today);
  const dateTo = startOfDayUtc(addDays(today, range === 'today' ? 1 : 7));

  const appointmentsQuery = useAppointments({
    date_from: dateFrom,
    date_to: dateTo,
    limit: 200,
  });
  const petMap = usePetMap();
  const vetMap = useVetMap();
  const setStatus = useSetAppointmentStatus();
  const cancel = useCancelAppointment();

  const appointments = useMemo(
    () =>
      (appointmentsQuery.data ?? [])
        .slice()
        .sort((a, b) => a.starts_at.localeCompare(b.starts_at)),
    [appointmentsQuery.data],
  );

  const counts = useMemo(() => {
    const tally = {
      total: appointments.length,
      confirmed: 0,
      requested: 0,
      completed: 0,
      cancelled: 0,
    };
    for (const appointment of appointments) {
      if (appointment.status === AppointmentStatus.CONFIRMED) tally.confirmed += 1;
      else if (appointment.status === AppointmentStatus.REQUESTED) tally.requested += 1;
      else if (appointment.status === AppointmentStatus.COMPLETED) tally.completed += 1;
      else tally.cancelled += 1;
    }
    return tally;
  }, [appointments]);

  const days = groupByClinicDay(appointments);
  const busy = setStatus.isPending || cancel.isPending;

  function handleStatus(appointment: AppointmentOut, status: AppointmentStatus) {
    setStatus.mutate(
      { id: appointment.id, status },
      {
        onSuccess: () =>
          toast.success(
            status === AppointmentStatus.COMPLETED
              ? 'Marked as completed.'
              : 'Appointment confirmed.',
          ),
        onError: (error) =>
          toast.error(
            error instanceof ApiError ? error.detail : 'Could not update that.',
          ),
      },
    );
  }

  function handleCancel() {
    if (!cancelling) return;
    cancel.mutate(cancelling.id, {
      onSuccess: () => {
        toast.success('Appointment cancelled.');
        setCancelling(null);
      },
      onError: (error) => {
        toast.error(
          error instanceof ApiError ? error.detail : 'Could not cancel that.',
        );
        setCancelling(null);
      },
    });
  }

  return (
    <div>
      <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-ink-900 dark:text-ink-50">
            Schedule
          </h1>
          <p className="mt-1 text-sm text-ink-500 dark:text-ink-400">
            {user?.role === Role.ADMIN
              ? 'Every appointment across the clinic.'
              : 'Your own appointments. Colleagues’ diaries are private.'}
          </p>
        </div>

        <div
          className="inline-flex rounded-lg bg-ink-100 p-1 dark:bg-ink-800"
          role="tablist"
          aria-label="Date range"
        >
          {(['today', 'week'] as Range[]).map((value) => (
            <button
              key={value}
              type="button"
              role="tab"
              aria-selected={range === value}
              onClick={() => setRange(value)}
              className={cn(
                'rounded-md px-4 py-1.5 text-sm font-medium transition-colors',
                range === value
                  ? 'bg-white text-ink-900 shadow-xs dark:bg-ink-700 dark:text-ink-50'
                  : 'text-ink-600 hover:text-ink-900 dark:text-ink-300 dark:hover:text-ink-50',
              )}
            >
              {value === 'today' ? 'Today' : 'Next 7 days'}
            </button>
          ))}
        </div>
      </header>

      <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          { label: 'Booked', value: counts.total },
          { label: 'Confirmed', value: counts.confirmed },
          { label: 'Completed', value: counts.completed },
          { label: 'Cancelled', value: counts.cancelled },
        ].map((stat) => (
          <Card key={stat.label} className="px-4 py-3">
            <p className="text-xs text-ink-500 dark:text-ink-400">{stat.label}</p>
            <p className="mt-0.5 text-2xl font-semibold tabular-nums text-ink-900 dark:text-ink-50">
              {stat.value}
            </p>
          </Card>
        ))}
      </div>

      {appointmentsQuery.isPending && <SkeletonList rows={4} />}

      {appointmentsQuery.isError && (
        <ErrorState
          message={
            appointmentsQuery.error instanceof ApiError
              ? appointmentsQuery.error.detail
              : 'Could not load the schedule.'
          }
          onRetry={() => void appointmentsQuery.refetch()}
        />
      )}

      {appointmentsQuery.isSuccess && appointments.length === 0 && (
        <EmptyState
          title={range === 'today' ? 'Nothing booked today' : 'A clear week ahead'}
          description="Appointments booked by clients will appear here as they come in."
        />
      )}

      <div className="space-y-8">
        {days.map((day) => (
          <section key={day.date}>
            <h2 className="mb-3 text-sm font-semibold text-ink-700 dark:text-ink-200">
              {day.label}
              <span className="ml-2 font-normal text-ink-400">
                {day.items.length} appointment{day.items.length === 1 ? '' : 's'}
              </span>
            </h2>
            <div className="space-y-3">
              {day.items.map((appointment) => (
                <AppointmentCard
                  key={appointment.id}
                  appointment={appointment}
                  pet={petMap[appointment.pet_id]}
                  vet={vetMap[appointment.vet_id]}
                  viewerRole={user?.role ?? Role.VET}
                  busy={busy}
                  onCancel={setCancelling}
                  onStatusChange={handleStatus}
                />
              ))}
            </div>
          </section>
        ))}
      </div>

      <ConfirmDialog
        open={cancelling !== null}
        title="Cancel this appointment?"
        message="The slot becomes bookable again. The client is not notified automatically — reminders arrive in a later phase."
        confirmLabel="Cancel appointment"
        cancelLabel="Keep it"
        loading={cancel.isPending}
        onConfirm={handleCancel}
        onCancel={() => setCancelling(null)}
      />
    </div>
  );
}
