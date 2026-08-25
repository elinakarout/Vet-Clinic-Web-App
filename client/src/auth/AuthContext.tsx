// Holds the token and user, persists to localStorage, exposes login()/logout(). (Phase 5)

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import * as authApi from '../api/auth';
import { clearActiveConversations } from '../api/chat';
import { setToken, setUnauthorizedHandler } from '../api/client';
import { AuthContext } from './authContext';
import type { AuthState } from './authContext';
import type { ClientRegister, Role, UserOut } from '../types/api';

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserOut | null>(null);
  const [bootstrapping, setBootstrapping] = useState(true);
  const [sessionExpired, setSessionExpired] = useState(false);
  const queryClient = useQueryClient();

  // Kept in a ref so the unauthorized handler registered below never closes over
  // a stale `user` and re-fires for an already-ended session. Written in an
  // effect rather than during render — a ref mutated while rendering is torn
  // under StrictMode's double invocation.
  const signedIn = useRef(false);
  useEffect(() => {
    signedIn.current = user !== null;
  }, [user]);

  const endSession = useCallback(
    (expired: boolean) => {
      setToken(null);
      setUser(null);
      if (expired) setSessionExpired(true);
      // Otherwise the next person to sign in on this browser briefly sees the
      // previous user's pets from the cache — or reopens their chat thread.
      queryClient.clear();
      clearActiveConversations();
    },
    [queryClient],
  );

  // One global reaction to an expired token, wherever the call was made from.
  useEffect(() => {
    setUnauthorizedHandler(() => {
      if (signedIn.current) endSession(true);
    });
    return () => setUnauthorizedHandler(null);
  }, [endSession]);

  // Resolve the stored token exactly once, on boot.
  useEffect(() => {
    let cancelled = false;
    authApi
      .me()
      .then((me) => {
        if (!cancelled) setUser(me);
      })
      .catch(() => {
        // No token, or a stale one. Either way: signed out, silently — this is
        // the ordinary first visit, not an error worth showing anyone.
        if (!cancelled) setToken(null);
      })
      .finally(() => {
        if (!cancelled) setBootstrapping(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(
    async (email: string, password: string) => {
      const { access_token } = await authApi.login(email, password);
      setToken(access_token);
      try {
        const me = await authApi.me();
        setUser(me);
        setSessionExpired(false);
        return me;
      } catch (error) {
        // A token we cannot use is worse than none — don't leave it behind.
        setToken(null);
        throw error;
      }
    },
    [],
  );

  const register = useCallback(
    async (payload: ClientRegister) => {
      await authApi.register(payload);
      await login(payload.email, payload.password);
    },
    [login],
  );

  const logout = useCallback(() => endSession(false), [endSession]);

  const hasRole = useCallback(
    (...roles: Role[]) => (user ? roles.includes(user.role) : false),
    [user],
  );

  const value = useMemo<AuthState>(
    () => ({
      user,
      bootstrapping,
      sessionExpired,
      login,
      register,
      logout,
      clearSessionExpired: () => setSessionExpired(false),
      hasRole,
    }),
    [user, bootstrapping, sessionExpired, login, register, logout, hasRole],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
