// Displays a single pet's summary. (Phase 5)

import { Link } from 'react-router-dom';
import { describeAge, formatIsoDate } from '../lib/datetime';
import { Sex } from '../types/api';
import type { PetOut } from '../types/api';
import { Badge } from './ui/Badge';
import { Button } from './ui/Button';
import { Card } from './ui/Card';

/** A rough species glyph. Falls back to a paw for anything unrecognised. */
function speciesEmoji(species: string): string {
  const key = species.trim().toLowerCase();
  if (key.includes('dog')) return '🐕';
  if (key.includes('cat')) return '🐈';
  if (key.includes('rabbit')) return '🐇';
  if (key.includes('bird') || key.includes('parrot')) return '🐦';
  if (key.includes('hamster') || key.includes('rodent')) return '🐹';
  if (key.includes('reptile') || key.includes('lizard')) return '🦎';
  if (key.includes('horse')) return '🐴';
  return '🐾';
}

const sexLabel: Record<Sex, string> = {
  [Sex.MALE]: 'Male',
  [Sex.FEMALE]: 'Female',
  [Sex.UNKNOWN]: 'Sex unknown',
};

export function PetCard({
  pet,
  ownerName,
  onEdit,
  onDelete,
}: {
  pet: PetOut;
  /** Shown to staff, who see every client's pets in one list. */
  ownerName?: string;
  onEdit: (pet: PetOut) => void;
  onDelete: (pet: PetOut) => void;
}) {
  const age = describeAge(pet.date_of_birth);

  return (
    <Card className="flex flex-col p-5">
      <div className="flex items-start gap-3">
        <span className="text-3xl leading-none" aria-hidden="true">
          {speciesEmoji(pet.species)}
        </span>
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-base font-semibold text-ink-900 dark:text-ink-50">
            {pet.name}
          </h3>
          <p className="truncate text-sm text-ink-500 dark:text-ink-400">
            {pet.species}
            {pet.breed && ` · ${pet.breed}`}
          </p>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap gap-1.5">
        {age && <Badge tone="brand">{age}</Badge>}
        <Badge>{sexLabel[pet.sex]}</Badge>
        {pet.weight_kg !== null && <Badge>{pet.weight_kg} kg</Badge>}
      </div>

      <dl className="mt-4 space-y-1 text-sm">
        {pet.date_of_birth && (
          <div className="flex gap-2">
            <dt className="text-ink-500 dark:text-ink-400">Born</dt>
            <dd className="text-ink-700 dark:text-ink-200">
              {formatIsoDate(pet.date_of_birth)}
            </dd>
          </div>
        )}
        {ownerName && (
          <div className="flex gap-2">
            <dt className="text-ink-500 dark:text-ink-400">Owner</dt>
            <dd className="truncate text-ink-700 dark:text-ink-200">{ownerName}</dd>
          </div>
        )}
      </dl>

      {pet.notes && (
        <p className="mt-3 line-clamp-3 rounded-lg bg-ink-50 px-3 py-2 text-sm text-ink-600 dark:bg-ink-800/60 dark:text-ink-300">
          {pet.notes}
        </p>
      )}

      <div className="mt-5 flex flex-wrap gap-2 border-t border-ink-100 pt-4 dark:border-ink-800">
        <Link
          to={`/book?pet=${pet.id}`}
          className="inline-flex h-8 items-center rounded-lg bg-brand-600 px-3 text-sm font-medium text-white transition-colors hover:bg-brand-700 dark:bg-brand-500 dark:text-ink-950 dark:hover:bg-brand-400"
        >
          Book a visit
        </Link>
        <Button variant="secondary" size="sm" onClick={() => onEdit(pet)}>
          Edit
        </Button>
        <Button
          variant="ghost"
          size="sm"
          className="ml-auto text-rose-600 hover:bg-rose-50 hover:text-rose-700 dark:text-rose-400 dark:hover:bg-rose-500/10"
          onClick={() => onDelete(pet)}
        >
          Delete
        </Button>
      </div>
    </Card>
  );
}
