import { createContext } from 'react';
import type { ClientRegister, Role, UserOut } from '../types/api';

export interface AuthState {
  user: UserOut | null;
  /**
   * True until the stored token has been checked against /auth/me.
   *
   * Without this every hard refresh flashes a redirect to /login: the token is
   * in localStorage but `user` is still null on the first render, so
   * ProtectedRoute bounces before the check finishes. Routes do not render
   * until this is false.
   */
  bootstrapping: boolean;
  /** Set when a 401 ended the session, so /login can explain what happened. */
  sessionExpired: boolean;
  login: (email: string, password: string) => Promise<UserOut>;
  register: (payload: ClientRegister) => Promise<void>;
  logout: () => void;
  clearSessionExpired: () => void;
  hasRole: (...roles: Role[]) => boolean;
}

/**
 * In its own module, away from AuthProvider: a file that exports both a
 * component and a context cannot be hot-reloaded cleanly, and oxlint's
 * react/only-export-components says so.
 */
export const AuthContext = createContext<AuthState | null>(null);
