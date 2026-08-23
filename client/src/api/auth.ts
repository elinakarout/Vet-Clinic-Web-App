// Calls to /auth/register, /auth/login, /auth/me. (Phase 5)

import { apiFetch } from './client';
import type {
  ClientRegister,
  ProfileOut,
  ProfileUpdate,
  TokenOut,
  UserOut,
} from '../types/api';

/**
 * The one form-encoded endpoint in the API. The OAuth2 password flow names the
 * field `username`; the email address goes there.
 */
export function login(email: string, password: string): Promise<TokenOut> {
  return apiFetch<TokenOut>('/auth/login', {
    method: 'POST',
    form: { username: email, password },
    auth: false,
  });
}

/** Always creates a CLIENT. There is no `role` field, deliberately. */
export function register(payload: ClientRegister): Promise<UserOut> {
  return apiFetch<UserOut>('/auth/register', {
    method: 'POST',
    body: payload,
    auth: false,
  });
}

export function me(): Promise<UserOut> {
  return apiFetch<UserOut>('/auth/me');
}

/** 404 for an ADMIN — there is no admin profile table. Callers must expect it. */
export function getProfile(): Promise<ProfileOut> {
  return apiFetch<ProfileOut>('/me/profile');
}

export function updateProfile(payload: ProfileUpdate): Promise<ProfileOut> {
  return apiFetch<ProfileOut>('/me/profile', { method: 'PATCH', body: payload });
}
