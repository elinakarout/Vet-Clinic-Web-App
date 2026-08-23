/**
 * The one place a UTC instant from the API becomes text a human reads.
 *
 * This mirrors the backend rule that `api/app/services/timeutils.py` is the only
 * module that converts. The rule here is narrower and worth stating plainly:
 *
 *   **Everything is rendered in the CLINIC's time zone, never the browser's.**
 *
 * The API returns instants as UTC (`2026-08-31T06:00:00Z`) but `date_from` /
 * `date_to` on `GET /appointments/slots` are *clinic-local dates*, because a
 * client asking for "Tuesday" means Tuesday at the clinic. If we rendered in the
 * browser's zone, a user abroad would pick Tuesday, be shown times labelled
 * Monday, and book an appointment displayed three hours from when it happens.
 *
 * `Intl.DateTimeFormat` does the conversion natively, so this needs no extra
 * dependency. `en-CA` is used wherever a `YYYY-MM-DD` string is wanted — it is
 * the one common locale whose short date format is already ISO order.
 */

import { addDays as addDaysFn, format, parseISO } from 'date-fns';

export const CLINIC_TIMEZONE: string =
  import.meta.env.VITE_CLINIC_TIMEZONE || 'Asia/Beirut';

/** A calendar date with no time part, e.g. `2026-08-31`. */
export type IsoDate = string;

const isoDateFormatter = new Intl.DateTimeFormat('en-CA', {
  timeZone: CLINIC_TIMEZONE,
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
});

const timeFormatter = new Intl.DateTimeFormat('en-GB', {
  timeZone: CLINIC_TIMEZONE,
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
});

const longDateFormatter = new Intl.DateTimeFormat('en-GB', {
  timeZone: CLINIC_TIMEZONE,
  weekday: 'long',
  day: 'numeric',
  month: 'long',
});

const shortDateFormatter = new Intl.DateTimeFormat('en-GB', {
  timeZone: CLINIC_TIMEZONE,
  weekday: 'short',
  day: 'numeric',
  month: 'short',
});

/** Today's date *at the clinic*, which is not always today in the browser. */
export function clinicToday(): IsoDate {
  return isoDateFormatter.format(new Date());
}

/** The clinic-local calendar date an instant falls on. */
export function toClinicDate(instant: string | Date): IsoDate {
  return isoDateFormatter.format(new Date(instant));
}

/** `09:00` — clinic wall clock. */
export function formatClinicTime(instant: string | Date): string {
  return timeFormatter.format(new Date(instant));
}

/** `Monday 31 August` */
export function formatClinicDateLong(instant: string | Date): string {
  return longDateFormatter.format(new Date(instant));
}

/** `Mon 31 Aug` */
export function formatClinicDateShort(instant: string | Date): string {
  return shortDateFormatter.format(new Date(instant));
}

/** `Mon 31 Aug at 09:00` — the label used on every appointment card. */
export function formatClinicDateTime(instant: string | Date): string {
  return `${formatClinicDateShort(instant)} at ${formatClinicTime(instant)}`;
}

/**
 * `GMT+3` — appended wherever a time is shown, so a user in another zone can
 * see at a glance that the clinic's clock is not theirs.
 */
export function clinicZoneLabel(): string {
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: CLINIC_TIMEZONE,
    timeZoneName: 'shortOffset',
  }).formatToParts(new Date());
  return parts.find((p) => p.type === 'timeZoneName')?.value ?? CLINIC_TIMEZONE;
}

/** True when the viewer's own zone differs from the clinic's, to the minute. */
export function viewerIsInAnotherZone(): boolean {
  const viewer = new Intl.DateTimeFormat('en-CA', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date());
  const clinic = new Intl.DateTimeFormat('en-CA', {
    timeZone: CLINIC_TIMEZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date());
  return viewer !== clinic;
}

/** Calendar arithmetic on a bare `YYYY-MM-DD`, DST-safe via date-fns. */
export function addDays(date: IsoDate, days: number): IsoDate {
  return format(addDaysFn(parseISO(date), days), 'yyyy-MM-dd');
}

/** `Today` / `Tomorrow` / `Monday 31 August`, for a bare clinic-local date. */
export function relativeDayLabel(date: IsoDate): string {
  const today = clinicToday();
  if (date === today) return 'Today';
  if (date === addDays(today, 1)) return 'Tomorrow';
  if (date === addDays(today, -1)) return 'Yesterday';
  // parseISO gives local midnight; formatting with date-fns (not Intl) keeps the
  // calendar date exactly as written rather than shifting it into the clinic zone.
  return format(parseISO(date), 'EEEE d MMMM');
}

/** `31 August 2026` for a bare date — pet dates of birth, not instants. */
export function formatIsoDate(date: IsoDate): string {
  return format(parseISO(date), 'd MMMM yyyy');
}

export interface SlotDay<T> {
  date: IsoDate;
  label: string;
  items: T[];
}

/**
 * Groups anything with a `starts_at` into clinic-local days, in time order.
 * The slot grid and the vet's week view both render from this.
 */
export function groupByClinicDay<T extends { starts_at: string }>(
  items: T[],
): SlotDay<T>[] {
  const byDate = new Map<IsoDate, T[]>();
  for (const item of items) {
    const date = toClinicDate(item.starts_at);
    const bucket = byDate.get(date);
    if (bucket) bucket.push(item);
    else byDate.set(date, [item]);
  }
  return [...byDate.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, list]) => ({
      date,
      label: relativeDayLabel(date),
      items: list.sort((a, b) => a.starts_at.localeCompare(b.starts_at)),
    }));
}

/** Midnight UTC at the start of a clinic-local date, for GET /appointments. */
export function startOfDayUtc(date: IsoDate): string {
  return `${date}T00:00:00Z`;
}

export function isPast(instant: string): boolean {
  return new Date(instant).getTime() < Date.now();
}

/** Hours from now until an instant. Negative once it has started. */
export function hoursUntil(instant: string): number {
  return (new Date(instant).getTime() - Date.now()) / 3_600_000;
}

/** `3 years 2 months`, `7 months`, `3 weeks` — a pet's age from its DOB. */
export function describeAge(dateOfBirth: string | null): string | null {
  if (!dateOfBirth) return null;
  const born = parseISO(dateOfBirth);
  if (Number.isNaN(born.getTime())) return null;
  const now = new Date();
  if (born > now) return null;

  let months =
    (now.getFullYear() - born.getFullYear()) * 12 +
    (now.getMonth() - born.getMonth());
  if (now.getDate() < born.getDate()) months -= 1;

  if (months < 1) {
    const days = Math.max(
      0,
      Math.floor((now.getTime() - born.getTime()) / 86_400_000),
    );
    if (days < 14) return `${days} day${days === 1 ? '' : 's'}`;
    const weeks = Math.floor(days / 7);
    return `${weeks} week${weeks === 1 ? '' : 's'}`;
  }
  if (months < 24) return `${months} month${months === 1 ? '' : 's'}`;

  const years = Math.floor(months / 12);
  const rest = months % 12;
  return rest === 0
    ? `${years} years`
    : `${years} year${years === 1 ? '' : 's'} ${rest} month${rest === 1 ? '' : 's'}`;
}
