// GET/PATCH /me/profile. (Phase 5)

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import * as authApi from '../api/auth';
import { ApiError } from '../api/client';
import type { ProfileUpdate } from '../types/api';

export const profileKeys = { me: ['profile', 'me'] as const };

export function useProfile(enabled = true) {
  return useQuery({
    queryKey: profileKeys.me,
    queryFn: authApi.getProfile,
    enabled,
    // An ADMIN has no profile row, so 404 is the correct answer rather than a
    // failure — retrying it would just be four more 404s.
    retry: (failureCount, error) =>
      !(error instanceof ApiError && error.status === 404) && failureCount < 2,
  });
}

export function useUpdateProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ProfileUpdate) => authApi.updateProfile(payload),
    onSuccess: (profile) => {
      queryClient.setQueryData(profileKeys.me, profile);
    },
  });
}
