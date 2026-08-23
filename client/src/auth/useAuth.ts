// The auth hook, in its own module. (Phase 5)
//
// Split from AuthContext.tsx because oxlint's `react/only-export-components`
// warns when a file exports both a component and a non-component. The context
// object itself lives in authContext.ts for the same reason.

import { useContext } from 'react';
import { AuthContext } from './authContext';
import type { AuthState } from './authContext';

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (context === null) {
    throw new Error('useAuth must be used inside <AuthProvider>');
  }
  return context;
}
