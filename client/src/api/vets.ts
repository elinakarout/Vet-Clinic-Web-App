// Calls to /vets. (Phase 5)
//
// Not in PROJECT_PLAN.md §3's file tree: GET /vets was built in Phase 4, after
// that tree was written. The booking flow cannot work without it.

import { apiFetch } from './client';
import type { VetAvailabilityOut, VetOut } from '../types/api';

/** Active vets only — a departed vet keeps their row so history survives. */
export function listVets(): Promise<VetOut[]> {
  return apiFetch<VetOut[]>('/vets');
}

/** The weekly grid plus the blocks overriding it, and the clinic's zone. */
export function getAvailability(vetId: number): Promise<VetAvailabilityOut> {
  return apiFetch<VetAvailabilityOut>(`/vets/${vetId}/availability`);
}
