// TanStack Query wrappers for /vets. (Phase 5)

import { useQuery } from '@tanstack/react-query';
import { useMemo } from 'react';
import * as vetsApi from '../api/vets';
import type { VetOut } from '../types/api';

export const vetKeys = {
  all: ['vets'] as const,
  availability: (vetId: number) => ['vets', vetId, 'availability'] as const,
};

export function useVets() {
  return useQuery({
    queryKey: vetKeys.all,
    queryFn: vetsApi.listVets,
    staleTime: 5 * 60 * 1000, // The staff list barely changes within a session.
  });
}

export function useVetAvailability(vetId: number | null) {
  return useQuery({
    queryKey: vetKeys.availability(vetId ?? 0),
    queryFn: () => vetsApi.getAvailability(vetId as number),
    enabled: vetId !== null,
    staleTime: 5 * 60 * 1000,
  });
}

/**
 * vet_profiles.id -> vet, for the client-side join.
 *
 * AppointmentOut carries `vet_id` and no name, so every appointment view needs
 * this. Reusing the cached ['vets'] query means the join costs no extra request.
 */
export function useVetMap(): Record<number, VetOut> {
  const { data } = useVets();
  return useMemo(() => {
    const map: Record<number, VetOut> = {};
    for (const vet of data ?? []) map[vet.id] = vet;
    return map;
  }, [data]);
}
