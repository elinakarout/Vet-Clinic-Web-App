// TanStack Query wrappers for /pets. (Phase 5)

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useMemo } from 'react';
import * as petsApi from '../api/pets';
import type { PetCreate, PetListParams, PetOut, PetUpdate } from '../types/api';

export const petKeys = {
  all: ['pets'] as const,
  list: (params: PetListParams) => ['pets', params] as const,
};

export function usePets(params: PetListParams = {}) {
  return useQuery({
    queryKey: petKeys.list(params),
    queryFn: () => petsApi.listPets(params),
    staleTime: 30 * 1000,
  });
}

/**
 * pets.id -> pet, for joining onto appointments.
 *
 * `limit: 200` is the server's cap and is deliberate: a partial page would make
 * an appointment card render "Pet #14" for anything past the first fifty.
 */
export function usePetMap(): Record<number, PetOut> {
  const { data } = usePets({ limit: 200 });
  return useMemo(() => {
    const map: Record<number, PetOut> = {};
    for (const pet of data ?? []) map[pet.id] = pet;
    return map;
  }, [data]);
}

export function useCreatePet() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: PetCreate) => petsApi.createPet(payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: petKeys.all }),
  });
}

export function useUpdatePet() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: PetUpdate }) =>
      petsApi.updatePet(id, payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: petKeys.all }),
  });
}

export function useDeletePet() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => petsApi.deletePet(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: petKeys.all }),
  });
}
