// Calls to /appointments and /appointments/slots. (Phase 5)

import { apiFetch } from './client';
import type {
  AppointmentCreate,
  AppointmentListParams,
  AppointmentOut,
  AppointmentStatus,
  SlotOut,
} from '../types/api';
import type { IsoDate } from '../lib/datetime';

/**
 * Free openings for one vet.
 *
 * `dateFrom`/`dateTo` are CLINIC-LOCAL dates (inclusive), not UTC and not the
 * browser's dates — a client asking for "Tuesday" means Tuesday at the clinic.
 * The returned instants are UTC. The range is capped at 31 days server-side.
 */
export function getSlots(
  vetId: number,
  dateFrom: IsoDate,
  dateTo: IsoDate,
): Promise<SlotOut[]> {
  return apiFetch<SlotOut[]>('/appointments/slots', {
    query: { vet_id: vetId, date_from: dateFrom, date_to: dateTo },
  });
}

/** A client's own, a vet's own schedule, everything for an admin. */
export function listAppointments(
  params: AppointmentListParams = {},
): Promise<AppointmentOut[]> {
  return apiFetch<AppointmentOut[]>('/appointments', { query: { ...params } });
}

export function getAppointment(id: number): Promise<AppointmentOut> {
  return apiFetch<AppointmentOut>(`/appointments/${id}`);
}

/**
 * `starts_at` must be an exact slot boundary AND must carry a UTC offset — a
 * naive datetime is a 422. Passing the `starts_at` straight through from a
 * SlotOut satisfies both, which is why nothing in this app constructs one.
 *
 * 409 means the slot went while the user was deciding. That is expected traffic,
 * not an exception: the caller refetches and asks again.
 */
export function bookAppointment(
  payload: AppointmentCreate,
): Promise<AppointmentOut> {
  return apiFetch<AppointmentOut>('/appointments', {
    method: 'POST',
    body: payload,
  });
}

/**
 * Returns the updated appointment rather than a 204, so a card on screen does
 * not need a second request. A CLIENT cannot cancel within 2 hours of the
 * start (409); staff can.
 */
export function cancelAppointment(id: number): Promise<AppointmentOut> {
  return apiFetch<AppointmentOut>(`/appointments/${id}/cancel`, {
    method: 'POST',
  });
}

/**
 * VET or ADMIN only, and a vet only on their own appointments.
 * REQUESTED -> CONFIRMED | CANCELLED, CONFIRMED -> COMPLETED | CANCELLED.
 * CANCELLED and COMPLETED are terminal; anything else is a 409.
 */
export function setAppointmentStatus(
  id: number,
  status: AppointmentStatus,
): Promise<AppointmentOut> {
  return apiFetch<AppointmentOut>(`/appointments/${id}/status`, {
    method: 'POST',
    body: { status },
  });
}
