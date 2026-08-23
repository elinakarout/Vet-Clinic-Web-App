// TypeScript interfaces mirroring the backend's Pydantic schemas. (Phase 5)
//
// Source of truth is api/app/schemas/*.py and API.md. Two rules govern this file:
//
//  1. No TS `enum` anywhere. tsconfig has `erasableSyntaxOnly: true`, which
//     rejects them outright. Const objects plus a derived union give the same
//     ergonomics and erase cleanly.
//  2. Every field that the server may return as null is typed `| null`, not
//     optional. The API distinguishes "absent" from "null" in a PATCH body, and
//     conflating them here is how a cleared field turns into an untouched one.

export const Role = {
  ADMIN: 'ADMIN',
  VET: 'VET',
  CLIENT: 'CLIENT',
} as const;
export type Role = (typeof Role)[keyof typeof Role];

export const AppointmentStatus = {
  REQUESTED: 'REQUESTED',
  CONFIRMED: 'CONFIRMED',
  CANCELLED: 'CANCELLED',
  COMPLETED: 'COMPLETED',
} as const;
export type AppointmentStatus =
  (typeof AppointmentStatus)[keyof typeof AppointmentStatus];

export const Sex = {
  MALE: 'MALE',
  FEMALE: 'FEMALE',
  UNKNOWN: 'UNKNOWN',
} as const;
export type Sex = (typeof Sex)[keyof typeof Sex];

// --- Auth -----------------------------------------------------------------

/** POST /auth/login response. */
export interface TokenOut {
  access_token: string;
  token_type: string;
}

/** GET /auth/me, POST /auth/register. `full_name` is null for an ADMIN. */
export interface UserOut {
  id: number;
  email: string;
  role: Role;
  is_active: boolean;
  created_at: string;
  full_name: string | null;
}

/** POST /auth/register body. Sending a `role` is a deliberate 422. */
export interface ClientRegister {
  email: string;
  password: string;
  full_name: string;
  phone?: string | null;
  address?: string | null;
}

// --- Profile --------------------------------------------------------------

/**
 * GET /me/profile. One flat shape over client_profiles and vet_profiles, with
 * the half that does not apply left null. 404 for an ADMIN — that is the data
 * model, not an error.
 *
 * `id` is the *profile* id, which is what a pet's `owner_id` points at.
 * `user_id` is the account id. They are rarely equal.
 */
export interface ProfileOut {
  id: number;
  user_id: number;
  role: Role;
  email: string;
  full_name: string;
  phone: string | null;
  address: string | null;
  specialty: string | null;
  license_no: string | null;
}

/** PATCH /me/profile. Sending a field from the other profile type is a 422. */
export interface ProfileUpdate {
  full_name?: string;
  phone?: string | null;
  address?: string | null;
  specialty?: string | null;
  license_no?: string | null;
}

// --- Pets -----------------------------------------------------------------

export interface PetOut {
  id: number;
  owner_id: number;
  name: string;
  species: string;
  breed: string | null;
  sex: Sex;
  date_of_birth: string | null;
  weight_kg: number | null;
  notes: string | null;
}

/** POST /pets. `owner_id` is required for staff and optional for a client. */
export interface PetCreate {
  name: string;
  species: string;
  breed?: string | null;
  sex?: Sex;
  date_of_birth?: string | null;
  weight_kg?: number | null;
  notes?: string | null;
  owner_id?: number;
}

/** PATCH /pets/{id}. There is no `owner_id` here — re-parenting is a 422. */
export type PetUpdate = Omit<PetCreate, 'owner_id' | 'name' | 'species'> & {
  name?: string;
  species?: string;
};

export interface PetListParams {
  /** Staff only — ignored by the server for a CLIENT. */
  owner_id?: number;
  /** Staff only — ignored by the server for a CLIENT. */
  q?: string;
  limit?: number;
  offset?: number;
}

// --- Vets -----------------------------------------------------------------

/** GET /vets. `id` is the vet_profiles.id that appointment.vet_id references. */
export interface VetOut {
  id: number;
  full_name: string;
  specialty: string | null;
}

/** Clinic-LOCAL wall clock, unlike every other time in this API. */
export interface AvailabilityOut {
  id: number;
  vet_id: number;
  /** 0 = Monday .. 6 = Sunday */
  weekday: number;
  start_time: string;
  end_time: string;
  slot_minutes: number;
}

export interface TimeOffOut {
  id: number;
  vet_id: number;
  starts_at: string;
  ends_at: string;
  reason: string | null;
}

export interface VetAvailabilityOut {
  vet_id: number;
  timezone: string;
  availability: AvailabilityOut[];
  time_off: TimeOffOut[];
}

// --- Appointments ---------------------------------------------------------

/** GET /appointments/slots. `starts_at`/`ends_at` are UTC with an offset. */
export interface SlotOut {
  starts_at: string;
  ends_at: string;
  vet_id: number;
  slot_minutes: number;
}

/**
 * Note what is NOT here: no pet name, no vet name. Every appointment view joins
 * against GET /pets and GET /vets on the client — see hooks/usePets.ts and
 * hooks/useVets.ts.
 */
export interface AppointmentOut {
  id: number;
  pet_id: number;
  vet_id: number;
  starts_at: string;
  ends_at: string;
  reason: string | null;
  status: AppointmentStatus;
  created_by: number | null;
}

/** POST /appointments. `starts_at` MUST carry a UTC offset — naive is a 422. */
export interface AppointmentCreate {
  pet_id: number;
  vet_id: number;
  starts_at: string;
  reason?: string | null;
}

export interface AppointmentListParams {
  status?: AppointmentStatus;
  pet_id?: number;
  vet_id?: number;
  /** UTC datetime. */
  date_from?: string;
  /** UTC datetime, EXCLUSIVE. */
  date_to?: string;
  limit?: number;
  offset?: number;
}
