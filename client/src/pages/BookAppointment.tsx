// Pick pet -> vet -> date -> free slot -> confirm. (Phase 5)

import { useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { ApiError } from '../api/client';
import { SlotPicker } from '../components/SlotPicker';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { Input, Select, Textarea } from '../components/ui/Field';
import { EmptyState, ErrorState, InfoPanel } from '../components/ui/States';
import { buttonClasses } from '../components/ui/buttonStyles';
import { useToast } from '../components/ui/useToast';
import { useBookAppointment, useSlots } from '../hooks/useAppointments';
import { usePets } from '../hooks/usePets';
import { useVets } from '../hooks/useVets';
import {
  addDays,
  clinicToday,
  clinicZoneLabel,
  formatClinicDateLong,
  formatClinicTime,
  relativeDayLabel,
} from '../lib/datetime';
import type { SlotOut } from '../types/api';

/**
 * A week at a time. The endpoint caps a range at 31 days, but a week is what a
 * person actually decides over, and asking for one keeps the grid readable.
 */
const RANGE_DAYS = 6;

function StepHeading({ step, title }: { step: number; title: string }) {
  return (
    <div className="mb-3 flex items-center gap-2">
      <span className="flex h-6 w-6 items-center justify-center rounded-full bg-brand-600 text-xs font-semibold text-white dark:bg-brand-500 dark:text-ink-950">
        {step}
      </span>
      <h2 className="text-sm font-semibold text-ink-800 dark:text-ink-100">
        {title}
      </h2>
    </div>
  );
}

export function BookAppointment() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const toast = useToast();

  const petsQuery = usePets({ limit: 200 });
  const vetsQuery = useVets();
  const book = useBookAppointment();

  const [petIdInput, setPetId] = useState<string>(searchParams.get('pet') ?? '');
  const [vetIdInput, setVetId] = useState<string>('');
  // Clinic-local dates throughout: `date_from`/`date_to` are the clinic's days,
  // not the browser's, and not UTC.
  const [dateFrom, setDateFrom] = useState<string>(clinicToday());
  const [selectedStart, setSelectedStart] = useState<string | null>(null);
  const [reason, setReason] = useState('');

  const pets = useMemo(() => petsQuery.data ?? [], [petsQuery.data]);
  const vets = useMemo(() => vetsQuery.data ?? [], [vetsQuery.data]);

  // Preselect the only sensible answer rather than making the user pick from a
  // list of one. Derived during render, not synced in an effect: there is no
  // second state to keep in step, and the value is correct on the first paint
  // after the lists arrive.
  const petId = petIdInput || (pets.length === 1 ? String(pets[0].id) : '');
  const vetId = vetIdInput || (vets.length === 1 ? String(vets[0].id) : '');

  const dateTo = addDays(dateFrom, RANGE_DAYS);
  const slotsQuery = useSlots(vetId ? Number(vetId) : null, dateFrom, dateTo);
  const slots = useMemo(() => slotsQuery.data ?? [], [slotsQuery.data]);

  // Resolved against the slots currently on screen rather than held as its own
  // object. A selection that is no longer offered — because the vet changed, the
  // week changed, or somebody else just booked it — evaporates on its own,
  // which is exactly what should happen after a 409.
  const selected: SlotOut | null =
    slots.find((slot) => slot.starts_at === selectedStart) ?? null;

  const chosenPet = pets.find((pet) => String(pet.id) === petId);
  const chosenVet = vets.find((vet) => String(vet.id) === vetId);
  const ready = Boolean(chosenPet && chosenVet && selected);

  function handleBook() {
    if (!selected || !chosenPet) return;
    book.mutate(
      {
        pet_id: chosenPet.id,
        vet_id: selected.vet_id,
        // Passed straight through from the slot: it is already an exact
        // boundary and already carries a UTC offset, both of which the server
        // requires and neither of which this app should be constructing.
        starts_at: selected.starts_at,
        reason: reason.trim() || null,
      },
      {
        onSuccess: () => {
          toast.success(
            `Booked for ${chosenPet.name} on ${formatClinicDateLong(selected.starts_at)} at ${formatClinicTime(selected.starts_at)}.`,
          );
          navigate('/appointments');
        },
        onError: (error) => {
          if (error instanceof ApiError && error.status === 409) {
            // Someone else took it while this user was deciding. The mutation's
            // onError already invalidated the slot query, so the grid below is
            // refreshing as this message appears — and the selection resolves to
            // null on its own once the taken slot is gone from the list.
            setSelectedStart(null);
            toast.error('That time was just taken. Here are the latest openings.');
            return;
          }
          toast.error(
            error instanceof ApiError ? error.detail : 'Could not book that time.',
          );
        },
      },
    );
  }

  if (petsQuery.isSuccess && pets.length === 0) {
    return (
      <EmptyState
        icon={
          <span className="text-4xl" aria-hidden="true">
            🐾
          </span>
        }
        title="Add a pet first"
        description="Appointments are booked for a pet, so there needs to be one on file before you can pick a time."
        action={
          <Link to="/pets" className={buttonClasses('primary', 'md')}>
            Go to pets
          </Link>
        }
      />
    );
  }

  return (
    <div>
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-ink-900 dark:text-ink-50">
          Book an appointment
        </h1>
        <p className="mt-1 text-sm text-ink-500 dark:text-ink-400">
          All times are clinic time ({clinicZoneLabel()}).
        </p>
      </header>

      <div className="grid gap-6 lg:grid-cols-[1fr_20rem] lg:items-start">
        <div className="space-y-6">
          <Card className="p-5">
            <StepHeading step={1} title="Who is the visit for?" />
            <div className="grid gap-4 sm:grid-cols-2">
              <Select
                label="Pet"
                required
                value={petId}
                onChange={(event) => setPetId(event.target.value)}
              >
                <option value="">Choose a pet…</option>
                {pets.map((pet) => (
                  <option key={pet.id} value={pet.id}>
                    {pet.name} ({pet.species})
                  </option>
                ))}
              </Select>
              <Select
                label="Vet"
                required
                value={vetId}
                onChange={(event) => setVetId(event.target.value)}
              >
                <option value="">Choose a vet…</option>
                {vets.map((vet) => (
                  <option key={vet.id} value={vet.id}>
                    {vet.full_name}
                    {vet.specialty ? ` — ${vet.specialty}` : ''}
                  </option>
                ))}
              </Select>
            </div>
            {vetsQuery.isError && (
              <div className="mt-4">
                <ErrorState
                  message="Could not load the clinic's vets."
                  onRetry={() => void vetsQuery.refetch()}
                />
              </div>
            )}
          </Card>

          <Card className="p-5">
            <StepHeading step={2} title="When suits you?" />
            <div className="flex flex-wrap items-end gap-3">
              <div className="w-48">
                <Input
                  label="Week beginning"
                  type="date"
                  min={clinicToday()}
                  value={dateFrom}
                  onChange={(event) =>
                    setDateFrom(event.target.value || clinicToday())
                  }
                />
              </div>
              <div className="flex gap-2 pb-0.5">
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={dateFrom <= clinicToday()}
                  onClick={() =>
                    setDateFrom((current) => {
                      const previous = addDays(current, -7);
                      const today = clinicToday();
                      return previous < today ? today : previous;
                    })
                  }
                >
                  ← Earlier
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => setDateFrom((current) => addDays(current, 7))}
                >
                  Later →
                </Button>
              </div>
              <p className="pb-2 text-xs text-ink-500 dark:text-ink-400">
                {relativeDayLabel(dateFrom)} to {relativeDayLabel(dateTo)}
              </p>
            </div>

            <div className="mt-6 border-t border-ink-100 pt-6 dark:border-ink-800">
              <StepHeading step={3} title="Pick a time" />
              {!vetId ? (
                <p className="text-sm text-ink-500 dark:text-ink-400">
                  Choose a vet above to see their free times.
                </p>
              ) : slotsQuery.isError ? (
                <ErrorState
                  message={
                    slotsQuery.error instanceof ApiError
                      ? slotsQuery.error.detail
                      : 'Could not load available times.'
                  }
                  onRetry={() => void slotsQuery.refetch()}
                />
              ) : (
                <SlotPicker
                  slots={slots}
                  selected={selected}
                  onSelect={(slot) => setSelectedStart(slot.starts_at)}
                  loading={slotsQuery.isPending || slotsQuery.isFetching}
                  disabled={book.isPending}
                />
              )}
            </div>
          </Card>
        </div>

        <Card className="p-5 lg:sticky lg:top-24">
          <StepHeading step={4} title="Confirm" />
          <dl className="space-y-2 text-sm">
            <div className="flex justify-between gap-3">
              <dt className="text-ink-500 dark:text-ink-400">Pet</dt>
              <dd className="text-right font-medium text-ink-800 dark:text-ink-100">
                {chosenPet?.name ?? '—'}
              </dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-ink-500 dark:text-ink-400">Vet</dt>
              <dd className="text-right font-medium text-ink-800 dark:text-ink-100">
                {chosenVet?.full_name ?? '—'}
              </dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-ink-500 dark:text-ink-400">When</dt>
              <dd className="text-right font-medium text-ink-800 dark:text-ink-100">
                {selected
                  ? `${formatClinicDateLong(selected.starts_at)}, ${formatClinicTime(selected.starts_at)}`
                  : '—'}
              </dd>
            </div>
            {selected && (
              <div className="flex justify-between gap-3">
                <dt className="text-ink-500 dark:text-ink-400">Length</dt>
                <dd className="text-right font-medium text-ink-800 dark:text-ink-100">
                  {selected.slot_minutes} minutes
                </dd>
              </div>
            )}
          </dl>

          <div className="mt-4">
            <Textarea
              label="Reason for the visit"
              rows={3}
              maxLength={300}
              value={reason}
              placeholder="Vaccination, limping, annual check-up…"
              hint="Helps the vet prepare. Not required."
              onChange={(event) => setReason(event.target.value)}
            />
          </div>

          <Button
            className="mt-4 w-full"
            size="lg"
            disabled={!ready}
            loading={book.isPending}
            onClick={handleBook}
          >
            Confirm booking
          </Button>

          <div className="mt-4">
            <InfoPanel title="Feeling unwell in an emergency?">
              If your pet is struggling to breathe, collapsed, seizing, bleeding
              heavily, or may have swallowed something toxic, call the clinic now
              rather than booking.
            </InfoPanel>
          </div>
        </Card>
      </div>
    </div>
  );
}
