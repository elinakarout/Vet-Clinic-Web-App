// TanStack Query wrappers for /appointments. (Phase 5)

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import * as appointmentsApi from '../api/appointments';
import type {
  AppointmentCreate,
  AppointmentListParams,
  AppointmentStatus,
} from '../types/api';
import type { IsoDate } from '../lib/datetime';

export const appointmentKeys = {
  all: ['appointments'] as const,
  list: (params: AppointmentListParams) => ['appointments', params] as const,
  slots: (vetId: number, from: IsoDate, to: IsoDate) =>
    ['slots', vetId, from, to] as const,
};

export function useAppointments(params: AppointmentListParams = {}) {
  return useQuery({
    queryKey: appointmentKeys.list(params),
    queryFn: () => appointmentsApi.listAppointments(params),
    staleTime: 15 * 1000,
  });
}

/**
 * Free slots for one vet over a clinic-local date range.
 *
 * `staleTime: 0` and a refetch on window focus, unlike every other query here:
 * a slot list is the one thing in this app that another user can invalidate
 * from the other side of the clinic while it is on screen.
 */
export function useSlots(
  vetId: number | null,
  dateFrom: IsoDate,
  dateTo: IsoDate,
) {
  return useQuery({
    queryKey: appointmentKeys.slots(vetId ?? 0, dateFrom, dateTo),
    queryFn: () => appointmentsApi.getSlots(vetId as number, dateFrom, dateTo),
    enabled: vetId !== null,
    staleTime: 0,
    refetchOnWindowFocus: true,
  });
}

/**
 * Every mutation invalidates BOTH lists. Booking removes a slot and adds an
 * appointment; cancelling does the reverse — refreshing only one leaves the
 * other showing a state the server no longer agrees with.
 */
function useAppointmentMutationDefaults() {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: appointmentKeys.all });
    void queryClient.invalidateQueries({ queryKey: ['slots'] });
  };
}

export function useBookAppointment() {
  const invalidate = useAppointmentMutationDefaults();
  return useMutation({
    mutationFn: (payload: AppointmentCreate) =>
      appointmentsApi.bookAppointment(payload),
    onSuccess: invalidate,
    // A 409 means someone else took the slot. The grid must refresh even though
    // the mutation failed, or the user clicks the same dead slot again.
    onError: invalidate,
  });
}

export function useCancelAppointment() {
  const invalidate = useAppointmentMutationDefaults();
  return useMutation({
    mutationFn: (id: number) => appointmentsApi.cancelAppointment(id),
    onSuccess: invalidate,
  });
}

export function useSetAppointmentStatus() {
  const invalidate = useAppointmentMutationDefaults();
  return useMutation({
    mutationFn: ({ id, status }: { id: number; status: AppointmentStatus }) =>
      appointmentsApi.setAppointmentStatus(id, status),
    onSuccess: invalidate,
  });
}
