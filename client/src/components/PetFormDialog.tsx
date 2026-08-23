// Add or edit a pet. (Phase 5)
//
// The validation here mirrors the server's rules rather than inventing new ones,
// so the user hears about a bad weight before the round trip instead of after.
// Anything the server rejects that this misses still surfaces — the mutation's
// error is rendered at the top of the form.

import { useState } from 'react';
import type { FormEvent } from 'react';
import { ApiError } from '../api/client';
import { clinicToday } from '../lib/datetime';
import { Role, Sex } from '../types/api';
import type { PetCreate, PetOut, PetUpdate } from '../types/api';
import { Button } from './ui/Button';
import { Input, Select, Textarea } from './ui/Field';
import { Modal } from './ui/Modal';
import { ErrorState } from './ui/States';

interface FormState {
  name: string;
  species: string;
  breed: string;
  sex: Sex;
  date_of_birth: string;
  weight_kg: string;
  notes: string;
  owner_id: string;
}

const EMPTY: FormState = {
  name: '',
  species: '',
  breed: '',
  sex: Sex.UNKNOWN,
  date_of_birth: '',
  weight_kg: '',
  notes: '',
  owner_id: '',
};

function toFormState(pet: PetOut | null): FormState {
  if (!pet) return EMPTY;
  return {
    name: pet.name,
    species: pet.species,
    breed: pet.breed ?? '',
    sex: pet.sex,
    date_of_birth: pet.date_of_birth ?? '',
    weight_kg: pet.weight_kg === null ? '' : String(pet.weight_kg),
    notes: pet.notes ?? '',
    owner_id: String(pet.owner_id),
  };
}

type Errors = Partial<Record<keyof FormState, string>>;

function validate(form: FormState, needsOwner: boolean): Errors {
  const errors: Errors = {};
  if (!form.name.trim()) errors.name = 'Give your pet a name.';
  if (!form.species.trim()) errors.species = 'Dog, cat, rabbit — whatever they are.';

  if (form.weight_kg !== '') {
    const weight = Number(form.weight_kg);
    if (Number.isNaN(weight)) errors.weight_kg = 'Use a number, e.g. 17.4';
    else if (weight < 0) errors.weight_kg = 'Weight cannot be negative.';
    else if (weight > 500) errors.weight_kg = 'That looks too heavy — check the value.';
  }

  // The server rejects a future date of birth; catch it here so the message is
  // about the pet rather than about a 422.
  if (form.date_of_birth && form.date_of_birth > clinicToday()) {
    errors.date_of_birth = 'A date of birth cannot be in the future.';
  }

  // Staff have no client profile to default to, so POST /pets needs an owner.
  if (needsOwner && !form.owner_id.trim()) {
    errors.owner_id = 'Choose which client this pet belongs to.';
  }
  return errors;
}

export function PetFormDialog({
  open,
  pet,
  viewerRole,
  ownerOptions,
  saving,
  error,
  onSubmit,
  onClose,
}: {
  open: boolean;
  /** null = adding. */
  pet: PetOut | null;
  viewerRole: Role;
  /** Staff only: the client profiles a new pet can be attached to. */
  ownerOptions?: { id: number; label: string }[];
  saving: boolean;
  error: unknown;
  onSubmit: (payload: PetCreate | PetUpdate) => void;
  onClose: () => void;
}) {
  // Initialised once per mount. The parent remounts this via a changing `key`
  // each time the dialog opens, so last time's values cannot leak into this
  // time's without an effect syncing props into state.
  const [form, setForm] = useState<FormState>(() => toFormState(pet));
  const [errors, setErrors] = useState<Errors>({});

  const isEditing = pet !== null;
  const isStaff = viewerRole === Role.VET || viewerRole === Role.ADMIN;
  // owner_id is not a field on PATCH — sending it is a 422, so it is only ever
  // asked for when creating.
  const needsOwner = isStaff && !isEditing;

  function update<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const found = validate(form, needsOwner);
    setErrors(found);
    if (Object.keys(found).length > 0) return;

    const base = {
      name: form.name.trim(),
      species: form.species.trim(),
      breed: form.breed.trim() || null,
      sex: form.sex,
      date_of_birth: form.date_of_birth || null,
      weight_kg: form.weight_kg === '' ? null : Number(form.weight_kg),
      notes: form.notes.trim() || null,
    };

    onSubmit(
      needsOwner ? { ...base, owner_id: Number(form.owner_id) } : base,
    );
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      size="lg"
      title={isEditing ? `Edit ${pet.name}` : 'Add a pet'}
      description={
        isEditing
          ? 'Change anything that has moved on — a weight check, a new note.'
          : 'Only a name and a species are required. The rest helps your vet.'
      }
    >
      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        {error instanceof ApiError && (
          <ErrorState title="Could not save" message={error.detail} />
        )}

        <div className="grid gap-4 sm:grid-cols-2">
          <Input
            label="Name"
            required
            value={form.name}
            error={errors.name}
            autoComplete="off"
            onChange={(event) => update('name', event.target.value)}
          />
          <Input
            label="Species"
            required
            value={form.species}
            error={errors.species}
            placeholder="Dog, Cat, Rabbit…"
            autoComplete="off"
            onChange={(event) => update('species', event.target.value)}
          />
          <Input
            label="Breed"
            value={form.breed}
            autoComplete="off"
            onChange={(event) => update('breed', event.target.value)}
          />
          <Select
            label="Sex"
            value={form.sex}
            onChange={(event) => update('sex', event.target.value as Sex)}
          >
            <option value={Sex.UNKNOWN}>Not known</option>
            <option value={Sex.FEMALE}>Female</option>
            <option value={Sex.MALE}>Male</option>
          </Select>
          <Input
            label="Date of birth"
            type="date"
            max={clinicToday()}
            value={form.date_of_birth}
            error={errors.date_of_birth}
            hint="Approximate is fine — it drives the age shown on their card."
            onChange={(event) => update('date_of_birth', event.target.value)}
          />
          <Input
            label="Weight (kg)"
            type="number"
            min="0"
            step="0.1"
            inputMode="decimal"
            value={form.weight_kg}
            error={errors.weight_kg}
            onChange={(event) => update('weight_kg', event.target.value)}
          />
        </div>

        {needsOwner && (
          <>
            <Input
              label="Owner (client profile ID)"
              required
              type="number"
              min="1"
              step="1"
              inputMode="numeric"
              list="known-owner-ids"
              value={form.owner_id}
              error={errors.owner_id}
              hint={
                <>
                  This is a <strong>client profile</strong> id, not a user id.
                  Existing clients are suggested below; a brand-new client must
                  register first — a staff client directory arrives in Phase&nbsp;9.
                </>
              }
              onChange={(event) => update('owner_id', event.target.value)}
            />
            <datalist id="known-owner-ids">
              {(ownerOptions ?? []).map((owner) => (
                <option key={owner.id} value={owner.id}>
                  {owner.label}
                </option>
              ))}
            </datalist>
          </>
        )}

        <Textarea
          label="Notes for the vet"
          value={form.notes}
          rows={3}
          placeholder="Nervous around clippers; muzzle-trained."
          onChange={(event) => update('notes', event.target.value)}
        />

        <div className="flex justify-end gap-2 pt-2">
          <Button variant="secondary" onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button type="submit" loading={saving}>
            {isEditing ? 'Save changes' : 'Add pet'}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
