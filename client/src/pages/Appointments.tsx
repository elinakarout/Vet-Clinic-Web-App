// Every appointment the signed-in user can see, upcoming and past. (Phase 5)
//
// Not in PROJECT_PLAN.md §3's file tree — the plan folds this into the
// dashboard. Splitting them keeps the dashboard a summary you can take in at a
// glance, and gives cancelling and history somewhere to live.

import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { ApiError } from '../api/client';
import { useAuth } from '../auth/useAuth';
import { AppointmentCard } from '../components/AppointmentCard';
import { ConfirmDialog } from '../components/ui/ConfirmDialog';
import { EmptyState, ErrorState, SkeletonList } from '../components/ui/States';
import { buttonClasses } from '../components/ui/buttonStyles';
import { useToast } from '../components/ui/useToast';
import { useAppointments, useCancelAppointment } from '../hooks/useAppointments';
import { usePetMap } from '../hooks/usePets';
import { useVetMap } from '../hooks/useVets';
import { cn } from '../lib/cn';
import { groupByClinicDay, isPast } from '../lib/datetime';
import { AppointmentStatus, Role } from '../types/api';
import type { AppointmentOut } from '../types/api';

type Tab = 'upcoming' | 'past';

export function Appointments() {
  const { user } = useAuth();
  const toast = useToast();
  const [tab, setTab] = useState<Tab>('upcoming');
  const [cancelling, setCancelling] = useState<AppointmentOut | null>(null);

  const appointmentsQuery = useAppointments({ limit: 200 });
  const petMap = usePetMap();
  const vetMap = useVetMap();
  const cancel = useCancelAppointment();

  const { upcoming, past } = useMemo(() => {
    const all = appointmentsQuery.data ?? [];
    // "Upcoming" means still going to happen AND still live. A cancelled booking
    // next Tuesday belongs in history, not in the list of what to expect.
    const isUpcoming = (appointment: AppointmentOut) =>
      !isPast(appointment.starts_at) &&
      (appointment.status === AppointmentStatus.CONFIRMED ||
        appointment.status === AppointmentStatus.REQUESTED);

    return {
      upcoming: all
        .filter(isUpcoming)
        .sort((a, b) => a.starts_at.localeCompare(b.starts_at)),
      past: all
        .filter((appointment) => !isUpcoming(appointment))
        .sort((a, b) => b.starts_at.localeCompare(a.starts_at)),
    };
  }, [appointmentsQuery.data]);

  const shown = tab === 'upcoming' ? upcoming : past;
  const days = groupByClinicDay(shown);

  function handleCancel() {
    if (!cancelling) return;
    cancel.mutate(cancelling.id, {
      onSuccess: () => {
        toast.success('Appointment cancelled. The slot is free again.');
        setCancelling(null);
      },
      onError: (error) => {
        toast.error(
          error instanceof ApiError && error.status === 409
            ? `${error.detail} Please call the clinic if you need to change it.`
            : error instanceof ApiError
              ? error.detail
              : 'Could not cancel that appointment.',
        );
        setCancelling(null);
      },
    });
  }

  return (
    <div>
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-ink-900 dark:text-ink-50">
          Appointments
        </h1>
        <p className="mt-1 text-sm text-ink-500 dark:text-ink-400">
          {user?.role === Role.CLIENT
            ? 'Everything booked for your pets.'
            : user?.role === Role.VET
              ? 'Your own schedule.'
              : 'Every appointment in the clinic.'}
        </p>
      </header>

      <div
        className="mb-6 inline-flex rounded-lg bg-ink-100 p-1 dark:bg-ink-800"
        role="tablist"
        aria-label="Appointment lists"
      >
        {(['upcoming', 'past'] as Tab[]).map((value) => (
          <button
            key={value}
            type="button"
            role="tab"
            aria-selected={tab === value}
            onClick={() => setTab(value)}
            className={cn(
              'rounded-md px-4 py-1.5 text-sm font-medium capitalize transition-colors',
              tab === value
                ? 'bg-white text-ink-900 shadow-xs dark:bg-ink-700 dark:text-ink-50'
                : 'text-ink-600 hover:text-ink-900 dark:text-ink-300 dark:hover:text-ink-50',
            )}
          >
            {value}
            <span className="ml-1.5 text-xs text-ink-400">
              {value === 'upcoming' ? upcoming.length : past.length}
            </span>
          </button>
        ))}
      </div>

      {appointmentsQuery.isPending && <SkeletonList rows={3} />}

      {appointmentsQuery.isError && (
        <ErrorState
          message={
            appointmentsQuery.error instanceof ApiError
              ? appointmentsQuery.error.detail
              : 'Could not load appointments.'
          }
          onRetry={() => void appointmentsQuery.refetch()}
        />
      )}

      {appointmentsQuery.isSuccess && shown.length === 0 && (
        <EmptyState
          title={tab === 'upcoming' ? 'Nothing booked' : 'No past appointments'}
          description={
            tab === 'upcoming'
              ? 'When you book a visit it will appear here.'
              : 'Completed and cancelled visits show up here.'
          }
          action={
            tab === 'upcoming' && (
              <Link to="/book" className={buttonClasses('primary', 'md')}>
                Book an appointment
              </Link>
            )
          }
        />
      )}

      <div className="space-y-8">
        {days.map((day) => (
          <section key={day.date}>
            <h2 className="mb-3 text-sm font-semibold text-ink-700 dark:text-ink-200">
              {day.label}
            </h2>
            <div className="space-y-3">
              {day.items.map((appointment) => (
                <AppointmentCard
                  key={appointment.id}
                  appointment={appointment}
                  pet={petMap[appointment.pet_id]}
                  vet={vetMap[appointment.vet_id]}
                  viewerRole={user?.role ?? Role.CLIENT}
                  busy={cancel.isPending}
                  onCancel={setCancelling}
                />
              ))}
            </div>
          </section>
        ))}
      </div>

      <ConfirmDialog
        open={cancelling !== null}
        title="Cancel this appointment?"
        message="The time becomes available for someone else. You can book again if you change your mind."
        confirmLabel="Cancel appointment"
        cancelLabel="Keep it"
        loading={cancel.isPending}
        onConfirm={handleCancel}
        onCancel={() => setCancelling(null)}
      />
    </div>
  );
}
