// Upcoming appointments, quick links. (Phase 5)
//
// One page, three shapes. A client wants to know what is coming up and get to
// their pets; a vet wants today's list; an admin wants the clinic's totals.

import { useMemo } from 'react';
import { Link } from 'react-router-dom';
import { ApiError } from '../api/client';
import { useAuth } from '../auth/useAuth';
import { AppointmentCard } from '../components/AppointmentCard';
import { Card, CardHeader } from '../components/ui/Card';
import { EmptyState, ErrorState, SkeletonList } from '../components/ui/States';
import { buttonClasses } from '../components/ui/buttonStyles';
import { useAppointments } from '../hooks/useAppointments';
import { usePetMap, usePets } from '../hooks/usePets';
import { useVetMap, useVets } from '../hooks/useVets';
import {
  addDays,
  clinicToday,
  describeAge,
  isPast,
  startOfDayUtc,
} from '../lib/datetime';
import { AppointmentStatus, Role } from '../types/api';

function greeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return 'Good morning';
  if (hour < 18) return 'Good afternoon';
  return 'Good evening';
}

function StatCard({ label, value }: { label: string; value: number | string }) {
  return (
    <Card className="px-4 py-3">
      <p className="text-xs text-ink-500 dark:text-ink-400">{label}</p>
      <p className="mt-0.5 text-2xl font-semibold tabular-nums text-ink-900 dark:text-ink-50">
        {value}
      </p>
    </Card>
  );
}

export function Dashboard() {
  const { user } = useAuth();
  const isStaff = user?.role === Role.VET || user?.role === Role.ADMIN;

  const today = clinicToday();
  const appointmentsQuery = useAppointments(
    isStaff
      ? { date_from: startOfDayUtc(today), date_to: startOfDayUtc(addDays(today, 1)), limit: 200 }
      : { limit: 200 },
  );
  const petsQuery = usePets({ limit: 200 });
  const vetsQuery = useVets();
  const petMap = usePetMap();
  const vetMap = useVetMap();

  const pets = petsQuery.data ?? [];

  const upcoming = useMemo(
    () =>
      (appointmentsQuery.data ?? [])
        .filter(
          (appointment) =>
            !isPast(appointment.starts_at) &&
            (appointment.status === AppointmentStatus.CONFIRMED ||
              appointment.status === AppointmentStatus.REQUESTED),
        )
        .sort((a, b) => a.starts_at.localeCompare(b.starts_at)),
    [appointmentsQuery.data],
  );

  const todayList = useMemo(
    () =>
      (appointmentsQuery.data ?? [])
        .slice()
        .sort((a, b) => a.starts_at.localeCompare(b.starts_at)),
    [appointmentsQuery.data],
  );

  const list = isStaff ? todayList : upcoming.slice(0, 3);

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight text-ink-900 dark:text-ink-50">
          {greeting()}
          {user?.full_name ? `, ${user.full_name.split(' ')[0]}` : ''}
        </h1>
        <p className="mt-1 text-sm text-ink-500 dark:text-ink-400">
          {user?.role === Role.CLIENT
            ? 'Here is what is coming up for your pets.'
            : user?.role === Role.VET
              ? 'Your day at a glance.'
              : 'The clinic at a glance.'}
        </p>
      </header>

      {isStaff && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatCard label="Today" value={todayList.length} />
          <StatCard label="Still to come today" value={upcoming.length} />
          <StatCard label="Patients" value={pets.length} />
          <StatCard label="Vets" value={(vetsQuery.data ?? []).length} />
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[1fr_18rem] lg:items-start">
        <Card>
          <CardHeader
            title={isStaff ? 'Today’s appointments' : 'Next appointments'}
            action={
              <Link
                to={isStaff ? '/schedule' : '/appointments'}
                className="text-sm font-medium text-brand-700 underline-offset-2 hover:underline dark:text-brand-300"
              >
                See all
              </Link>
            }
          />
          <div className="p-5">
            {appointmentsQuery.isPending && <SkeletonList rows={2} />}

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

            {appointmentsQuery.isSuccess && list.length === 0 && (
              <EmptyState
                title={isStaff ? 'Nothing booked today' : 'No appointments booked'}
                description={
                  isStaff
                    ? 'A clear day. Bookings appear here as clients make them.'
                    : 'When you book a visit, it will show up here.'
                }
                action={
                  !isStaff && (
                    <Link to="/book" className={buttonClasses('primary', 'md')}>
                      Book an appointment
                    </Link>
                  )
                }
              />
            )}

            {list.length > 0 && (
              <div className="space-y-3">
                {list.map((appointment) => (
                  <AppointmentCard
                    key={appointment.id}
                    appointment={appointment}
                    pet={petMap[appointment.pet_id]}
                    vet={vetMap[appointment.vet_id]}
                    viewerRole={user?.role ?? Role.CLIENT}
                  />
                ))}
              </div>
            )}
          </div>
        </Card>

        <Card>
          <CardHeader
            title={isStaff ? 'Patients' : 'My pets'}
            action={
              <Link
                to="/pets"
                className="text-sm font-medium text-brand-700 underline-offset-2 hover:underline dark:text-brand-300"
              >
                Manage
              </Link>
            }
          />
          <div className="p-5">
            {petsQuery.isPending && <SkeletonList rows={2} />}

            {petsQuery.isSuccess && pets.length === 0 && (
              <EmptyState
                icon={
                  <span className="text-3xl" aria-hidden="true">
                    🐾
                  </span>
                }
                title="No pets yet"
                description="Add your first pet to start booking."
                action={
                  <Link to="/pets" className={buttonClasses('primary', 'sm')}>
                    Add a pet
                  </Link>
                }
              />
            )}

            {pets.length > 0 && (
              <ul className="space-y-3">
                {pets.slice(0, 6).map((pet) => (
                  <li key={pet.id} className="flex items-center gap-3">
                    <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-brand-50 text-base dark:bg-brand-500/15">
                      <span aria-hidden="true">🐾</span>
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-ink-900 dark:text-ink-50">
                        {pet.name}
                      </p>
                      <p className="truncate text-xs text-ink-500 dark:text-ink-400">
                        {pet.species}
                        {describeAge(pet.date_of_birth)
                          ? ` · ${describeAge(pet.date_of_birth)}`
                          : ''}
                      </p>
                    </div>
                    <Link
                      to={`/book?pet=${pet.id}`}
                      className="text-xs font-medium text-brand-700 underline-offset-2 hover:underline dark:text-brand-300"
                    >
                      Book
                    </Link>
                  </li>
                ))}
                {pets.length > 6 && (
                  <li className="text-xs text-ink-500 dark:text-ink-400">
                    and {pets.length - 6} more…
                  </li>
                )}
              </ul>
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}
