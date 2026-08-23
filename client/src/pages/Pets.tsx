// List, add, edit, delete pets. (Phase 5)

import { useMemo, useState } from 'react';
import { ApiError } from '../api/client';
import { useAuth } from '../auth/useAuth';
import { PetCard } from '../components/PetCard';
import { PetFormDialog } from '../components/PetFormDialog';
import { Button } from '../components/ui/Button';
import { ConfirmDialog } from '../components/ui/ConfirmDialog';
import { Input } from '../components/ui/Field';
import { useToast } from '../components/ui/useToast';
import { EmptyState, ErrorState, Skeleton } from '../components/ui/States';
import { useCreatePet, useDeletePet, usePets, useUpdatePet } from '../hooks/usePets';
import { Role } from '../types/api';
import type { PetCreate, PetOut, PetUpdate } from '../types/api';

export function Pets() {
  const { user } = useAuth();
  const toast = useToast();
  const isStaff = user?.role === Role.VET || user?.role === Role.ADMIN;

  // `q` is a staff filter — the server ignores it for a client, so the control
  // is only rendered for staff rather than silently doing nothing.
  const [search, setSearch] = useState('');
  const petsQuery = usePets(isStaff && search ? { q: search, limit: 200 } : { limit: 200 });

  const [editing, setEditing] = useState<PetOut | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  // Bumped on every open so the form remounts with fresh initial values, rather
  // than syncing itself from props in an effect.
  const [dialogKey, setDialogKey] = useState(0);
  const [deleting, setDeleting] = useState<PetOut | null>(null);

  const createPet = useCreatePet();
  const updatePet = useUpdatePet();
  const deletePet = useDeletePet();

  const pets = useMemo(() => petsQuery.data ?? [], [petsQuery.data]);

  /**
   * Owner suggestions for staff, derived from the pets already on file. There is
   * no client-directory endpoint (Phase 3 left it out on purpose), so this is the
   * only client identity the frontend can see.
   */
  const ownerOptions = useMemo(() => {
    const byOwner = new Map<number, string[]>();
    for (const pet of pets) {
      const names = byOwner.get(pet.owner_id);
      if (names) names.push(pet.name);
      else byOwner.set(pet.owner_id, [pet.name]);
    }
    return [...byOwner.entries()]
      .sort(([a], [b]) => a - b)
      .map(([id, names]) => ({ id, label: `Client #${id} — ${names.join(', ')}` }));
  }, [pets]);

  const ownerLabel = useMemo(() => {
    const map: Record<number, string> = {};
    for (const option of ownerOptions) map[option.id] = `Client #${option.id}`;
    return map;
  }, [ownerOptions]);

  function openAdd() {
    setEditing(null);
    createPet.reset();
    updatePet.reset();
    setDialogKey((key) => key + 1);
    setDialogOpen(true);
  }

  function openEdit(pet: PetOut) {
    setEditing(pet);
    createPet.reset();
    updatePet.reset();
    setDialogKey((key) => key + 1);
    setDialogOpen(true);
  }

  function handleSubmit(payload: PetCreate | PetUpdate) {
    if (editing) {
      updatePet.mutate(
        { id: editing.id, payload: payload as PetUpdate },
        {
          onSuccess: (pet) => {
            toast.success(`${pet.name} updated.`);
            setDialogOpen(false);
          },
        },
      );
    } else {
      createPet.mutate(payload as PetCreate, {
        onSuccess: (pet) => {
          toast.success(`${pet.name} added.`);
          setDialogOpen(false);
        },
      });
    }
  }

  function handleDelete() {
    if (!deleting) return;
    deletePet.mutate(deleting.id, {
      onSuccess: () => {
        toast.success(`${deleting.name} removed.`);
        setDeleting(null);
      },
      onError: (error) => {
        // 409 means the pet has clinical history. That is a rule, not a failure
        // to retry — say what it means and close the dialog.
        toast.error(
          error instanceof ApiError && error.status === 409
            ? `${deleting.name} has appointments or medical history, so their record must stay.`
            : error instanceof ApiError
              ? error.detail
              : 'Could not delete that pet.',
        );
        setDeleting(null);
      },
    });
  }

  return (
    <div>
      <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-ink-900 dark:text-ink-50">
            {isStaff ? 'Patients' : 'My pets'}
          </h1>
          <p className="mt-1 text-sm text-ink-500 dark:text-ink-400">
            {isStaff
              ? 'Every pet registered with the clinic.'
              : 'The animals in your care, and their details on file.'}
          </p>
        </div>
        <Button onClick={openAdd}>Add a pet</Button>
      </header>

      {isStaff && (
        <div className="mb-6 max-w-sm">
          <Input
            label="Search"
            type="search"
            placeholder="Name or species…"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </div>
      )}

      {petsQuery.isPending && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }, (_, index) => (
            <Skeleton key={index} className="h-64" />
          ))}
        </div>
      )}

      {petsQuery.isError && (
        <ErrorState
          message={
            petsQuery.error instanceof ApiError
              ? petsQuery.error.detail
              : 'Could not load your pets.'
          }
          onRetry={() => void petsQuery.refetch()}
        />
      )}

      {petsQuery.isSuccess && pets.length === 0 && (
        <EmptyState
          icon={
            <span className="text-4xl" aria-hidden="true">
              🐾
            </span>
          }
          title={search ? 'No pets match that search' : 'No pets yet'}
          description={
            search
              ? 'Try a different name or species.'
              : 'Add your first pet and you can book them a visit straight away.'
          }
          action={!search && <Button onClick={openAdd}>Add your first pet</Button>}
        />
      )}

      {petsQuery.isSuccess && pets.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {pets.map((pet) => (
            <PetCard
              key={pet.id}
              pet={pet}
              ownerName={isStaff ? ownerLabel[pet.owner_id] : undefined}
              onEdit={openEdit}
              onDelete={setDeleting}
            />
          ))}
        </div>
      )}

      <PetFormDialog
        key={dialogKey}
        open={dialogOpen}
        pet={editing}
        viewerRole={user?.role ?? Role.CLIENT}
        ownerOptions={ownerOptions}
        saving={createPet.isPending || updatePet.isPending}
        error={editing ? updatePet.error : createPet.error}
        onSubmit={handleSubmit}
        onClose={() => setDialogOpen(false)}
      />

      <ConfirmDialog
        open={deleting !== null}
        title={`Delete ${deleting?.name ?? 'this pet'}?`}
        message="This removes their record from the clinic. Pets with appointments or medical history cannot be deleted."
        confirmLabel="Delete"
        loading={deletePet.isPending}
        onConfirm={handleDelete}
        onCancel={() => setDeleting(null)}
      />
    </div>
  );
}
