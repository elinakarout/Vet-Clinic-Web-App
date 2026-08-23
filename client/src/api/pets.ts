// Calls to /pets. (Phase 5)

import { apiFetch } from './client';
import type { PetCreate, PetListParams, PetOut, PetUpdate } from '../types/api';

/**
 * A CLIENT gets their own pets; a VET or ADMIN gets every pet in the clinic.
 * `owner_id` and `q` are staff filters — the server ignores them for a client
 * rather than honouring them, so a client cannot widen the query by guessing an
 * id. The UI only renders those controls for staff.
 */
export function listPets(params: PetListParams = {}): Promise<PetOut[]> {
  return apiFetch<PetOut[]>('/pets', { query: { ...params } });
}

export function getPet(id: number): Promise<PetOut> {
  return apiFetch<PetOut>(`/pets/${id}`);
}

/**
 * `owner_id` is optional for a CLIENT (defaults to their own profile) and
 * REQUIRED for a VET or ADMIN, who have no client profile to default to.
 * Omitting it as staff is a 422, not a silent assignment.
 */
export function createPet(payload: PetCreate): Promise<PetOut> {
  return apiFetch<PetOut>('/pets', { method: 'POST', body: payload });
}

/** An empty body is a 422 — callers must not send a no-op patch. */
export function updatePet(id: number, payload: PetUpdate): Promise<PetOut> {
  return apiFetch<PetOut>(`/pets/${id}`, { method: 'PATCH', body: payload });
}

/** 409 when the pet has any appointment, medical record or vaccination. */
export function deletePet(id: number): Promise<void> {
  return apiFetch<void>(`/pets/${id}`, { method: 'DELETE' });
}
