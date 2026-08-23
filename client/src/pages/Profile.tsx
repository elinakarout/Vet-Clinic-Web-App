// GET/PATCH /me/profile. (Phase 5)
//
// Not in PROJECT_PLAN.md §3's file tree: the /me/profile pair was built in
// Phase 3 and would otherwise be unreachable from the UI.

import { useState } from 'react';
import type { FormEvent } from 'react';
import { ApiError } from '../api/client';
import { useAuth } from '../auth/useAuth';
import { Button } from '../components/ui/Button';
import { Card, CardHeader } from '../components/ui/Card';
import { Input } from '../components/ui/Field';
import { ErrorState, InfoPanel, Skeleton } from '../components/ui/States';
import { useToast } from '../components/ui/useToast';
import { useProfile, useUpdateProfile } from '../hooks/useProfile';
import { Role } from '../types/api';
import type { ProfileOut, ProfileUpdate } from '../types/api';

/**
 * The editable half, split out and mounted with `key={profile.id}` so its
 * initial values come straight from the loaded profile. Initialising state from
 * props at mount beats syncing them in an effect: there is no window in which
 * the form shows one profile's values while another is loaded.
 */
function ProfileForm({ profile }: { profile: ProfileOut }) {
  const toast = useToast();
  const updateProfile = useUpdateProfile();
  const isVet = profile.role === Role.VET;

  const [form, setForm] = useState(() => ({
    full_name: profile.full_name ?? '',
    phone: profile.phone ?? '',
    address: profile.address ?? '',
    specialty: profile.specialty ?? '',
    license_no: profile.license_no ?? '',
  }));

  function update(key: keyof typeof form, value: string) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();

    // Only ever send the half that belongs to this profile type. A client
    // sending `specialty` is a 422, and vice versa — the server will not quietly
    // ignore the field.
    const payload: ProfileUpdate = isVet
      ? {
          full_name: form.full_name.trim(),
          specialty: form.specialty.trim() || null,
          license_no: form.license_no.trim() || null,
        }
      : {
          full_name: form.full_name.trim(),
          phone: form.phone.trim() || null,
          address: form.address.trim() || null,
        };

    updateProfile.mutate(payload, {
      onSuccess: () => toast.success('Profile updated.'),
      onError: (error) =>
        toast.error(
          error instanceof ApiError ? error.detail : 'Could not save your profile.',
        ),
    });
  }

  return (
    <Card>
      <CardHeader
        title={isVet ? 'Practitioner details' : 'Contact details'}
        description={
          isVet
            ? 'Shown to clients when they choose who to book with.'
            : 'How the clinic reaches you about an appointment.'
        }
      />
      <form onSubmit={handleSubmit} className="space-y-4 p-5" noValidate>
        <Input
          label="Full name"
          required
          value={form.full_name}
          onChange={(event) => update('full_name', event.target.value)}
        />

        {isVet ? (
          <>
            <Input
              label="Specialty"
              value={form.specialty}
              placeholder="Small animal medicine"
              onChange={(event) => update('specialty', event.target.value)}
            />
            <Input
              label="Licence number"
              value={form.license_no}
              hint="Must be unique across the practice."
              onChange={(event) => update('license_no', event.target.value)}
            />
          </>
        ) : (
          <>
            <Input
              label="Phone"
              type="tel"
              autoComplete="tel"
              value={form.phone}
              onChange={(event) => update('phone', event.target.value)}
            />
            <Input
              label="Address"
              autoComplete="street-address"
              value={form.address}
              onChange={(event) => update('address', event.target.value)}
            />
          </>
        )}

        <div className="flex justify-end pt-2">
          <Button type="submit" loading={updateProfile.isPending}>
            Save changes
          </Button>
        </div>
      </form>
    </Card>
  );
}

export function Profile() {
  const { user } = useAuth();
  const isAdmin = user?.role === Role.ADMIN;

  // Skip the request entirely for an admin: the answer is a guaranteed 404.
  const profileQuery = useProfile(!isAdmin);

  return (
    <div className="mx-auto max-w-2xl">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-ink-900 dark:text-ink-50">
          Your profile
        </h1>
        <p className="mt-1 text-sm text-ink-500 dark:text-ink-400">
          Signed in as {user?.email}.
        </p>
      </header>

      {isAdmin && (
        <InfoPanel title="Admin accounts have no profile">
          There is no profile table for administrators — that is the data model,
          not a missing page. Names, phone numbers and addresses belong to client
          and vet accounts.
        </InfoPanel>
      )}

      {!isAdmin && profileQuery.isPending && (
        <div className="space-y-4">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
        </div>
      )}

      {!isAdmin && profileQuery.isError && (
        <ErrorState
          message={
            profileQuery.error instanceof ApiError
              ? profileQuery.error.detail
              : 'Could not load your profile.'
          }
          onRetry={() => void profileQuery.refetch()}
        />
      )}

      {profileQuery.isSuccess && (
        <ProfileForm key={profileQuery.data.id} profile={profileQuery.data} />
      )}
    </div>
  );
}
