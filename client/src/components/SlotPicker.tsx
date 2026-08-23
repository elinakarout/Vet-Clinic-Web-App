// Grid of bookable appointment slots. (Phase 5)

import { formatClinicTime, groupByClinicDay } from '../lib/datetime';
import type { SlotOut } from '../types/api';
import { cn } from '../lib/cn';
import { EmptyState, Skeleton } from './ui/States';

/**
 * Slots grouped into clinic-local days.
 *
 * Real <button> elements, not divs: a keyboard user tabs the grid and presses
 * Enter, and `aria-pressed` tells a screen reader which one is chosen. The
 * empty state distinguishes "the vet doesn't work then" from "it's all taken",
 * because those lead the user to different next actions.
 */
export function SlotPicker({
  slots,
  selected,
  onSelect,
  loading = false,
  disabled = false,
}: {
  slots: SlotOut[];
  selected: SlotOut | null;
  onSelect: (slot: SlotOut) => void;
  loading?: boolean;
  disabled?: boolean;
}) {
  if (loading) {
    return (
      <div className="space-y-4" role="status" aria-label="Loading available times">
        <Skeleton className="h-4 w-32" />
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4">
          {Array.from({ length: 8 }, (_, index) => (
            <Skeleton key={index} className="h-11" />
          ))}
        </div>
      </div>
    );
  }

  if (slots.length === 0) {
    return (
      <EmptyState
        title="No free times in this range"
        description="This vet may not be working then, or the day is fully booked. Try another date, or a different vet."
      />
    );
  }

  const days = groupByClinicDay(slots);

  return (
    <div className="space-y-6">
      {days.map((day) => (
        <div key={day.date}>
          <h3 className="mb-2 text-sm font-semibold text-ink-700 dark:text-ink-200">
            {day.label}
            <span className="ml-2 font-normal text-ink-400">
              {day.items.length} free
            </span>
          </h3>
          <div
            className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4"
            role="group"
            aria-label={`Available times on ${day.label}`}
          >
            {day.items.map((slot) => {
              const isSelected = selected?.starts_at === slot.starts_at;
              return (
                <button
                  key={slot.starts_at}
                  type="button"
                  disabled={disabled}
                  aria-pressed={isSelected}
                  onClick={() => onSelect(slot)}
                  className={cn(
                    'h-11 rounded-lg text-sm font-medium tabular-nums transition-colors',
                    'disabled:cursor-not-allowed disabled:opacity-50',
                    isSelected
                      ? 'bg-brand-600 text-white ring-2 ring-brand-600 ring-offset-2 dark:bg-brand-500 dark:text-ink-950 dark:ring-brand-400 dark:ring-offset-ink-950'
                      : 'bg-white text-ink-800 ring-1 ring-ink-200 hover:bg-brand-50 hover:ring-brand-300 dark:bg-ink-800 dark:text-ink-100 dark:ring-ink-700 dark:hover:bg-ink-700',
                  )}
                >
                  {formatClinicTime(slot.starts_at)}
                  <span className="sr-only">
                    {' '}
                    on {day.label}, {slot.slot_minutes} minutes
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
