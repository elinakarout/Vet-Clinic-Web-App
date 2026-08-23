// Login form, posts to /auth/login. (Phase 5)

import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { ApiError } from '../api/client';
import { useAuth } from '../auth/useAuth';
import { AuthShell } from '../components/AuthShell';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Field';
import { ErrorState, InfoPanel } from '../components/ui/States';

export function Login() {
  const { login, sessionExpired, clearSessionExpired } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // The notice belongs to this visit only; sign in again and it is stale.
  useEffect(() => () => clearSessionExpired(), [clearSessionExpired]);

  // Where ProtectedRoute bounced them from, so they land back there.
  const state = location.state as { from?: string } | null;
  const destination = state?.from ?? '/';

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await login(email.trim(), password);
      navigate(destination, { replace: true });
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.detail
          : 'Could not sign in. Please try again.',
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthShell
      title="Welcome back"
      subtitle="Sign in to manage your pets and appointments."
      footer={
        <>
          New here?{' '}
          <Link
            to="/register"
            className="font-medium text-brand-700 underline-offset-2 hover:underline dark:text-brand-300"
          >
            Create an account
          </Link>
        </>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        {sessionExpired && (
          <InfoPanel title="Your session expired">
            Sessions last an hour. Please sign in again to continue.
          </InfoPanel>
        )}
        {error && <ErrorState title="Sign in failed" message={error} />}

        <Input
          label="Email"
          type="email"
          required
          autoComplete="username"
          autoFocus
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />
        <Input
          label="Password"
          type="password"
          required
          autoComplete="current-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />

        <Button type="submit" className="w-full" size="lg" loading={submitting}>
          Sign in
        </Button>
      </form>

      {import.meta.env.DEV && (
        <div className="mt-6 rounded-lg bg-ink-50 px-4 py-3 text-xs text-ink-500 dark:bg-ink-800/60 dark:text-ink-400">
          <p className="font-medium text-ink-700 dark:text-ink-200">
            Demo logins (from scripts/seed.py)
          </p>
          <ul className="mt-1.5 space-y-0.5">
            <li>client.jones@example.test · client1234</li>
            <li>vet.patel@vetclinic.test · vet1234</li>
            <li>admin@vetclinic.test · admin1234</li>
          </ul>
        </div>
      )}
    </AuthShell>
  );
}
