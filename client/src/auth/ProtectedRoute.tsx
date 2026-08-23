// Redirects to /login when there's no user, optionally checks role. (Phase 5)

import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from './useAuth';
import { Spinner } from '../components/ui/Spinner';
import { EmptyState } from '../components/ui/States';
import type { Role } from '../types/api';

function BootSplash() {
  return (
    <div className="flex min-h-screen items-center justify-center" role="status">
      <Spinner className="h-6 w-6 text-brand-600 dark:text-brand-400" />
      <span className="sr-only">Loading</span>
    </div>
  );
}

/**
 * Wraps every signed-in route.
 *
 * The `bootstrapping` check comes first and matters most: on a hard refresh the
 * token is in localStorage but /auth/me has not answered yet, so `user` is null
 * for a tick. Redirecting on that tick throws the user back to /login every
 * time they reload a page they are perfectly entitled to see.
 */
export function ProtectedRoute({ roles }: { roles?: Role[] }) {
  const { user, bootstrapping } = useAuth();
  const location = useLocation();

  if (bootstrapping) return <BootSplash />;

  if (!user) {
    // Remember where they were headed so login can send them back there.
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  if (roles && !roles.includes(user.role)) {
    // A wrong role is not a dead end and not a redirect loop — say so plainly.
    return (
      <div className="mx-auto max-w-lg px-4 py-16">
        <EmptyState
          title="Not available for your role"
          description={`This page is for ${roles
            .map((role) => role.toLowerCase())
            .join(' and ')} accounts. You are signed in as ${user.role.toLowerCase()}.`}
        />
      </div>
    );
  }

  return <Outlet />;
}

/** Keeps a signed-in user off /login and /register. */
export function PublicOnlyRoute() {
  const { user, bootstrapping } = useAuth();
  if (bootstrapping) return <BootSplash />;
  if (user) return <Navigate to="/" replace />;
  return <Outlet />;
}
