// Registration form, posts to /auth/register. (Phase 5)

import { useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ApiError } from '../api/client';
import { useAuth } from '../auth/useAuth';
import { AuthShell } from '../components/AuthShell';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Field';
import { ErrorState } from '../components/ui/States';

/**
 * bcrypt truncates silently past 72 BYTES, so the server rejects anything
 * longer — and a byte is not a character. Counting bytes here means an emoji
 * password fails with an explanation rather than a 422 about a limit the user
 * appeared to be well under.
 */
function passwordByteLength(value: string): number {
  return new TextEncoder().encode(value).length;
}

type Errors = Record<string, string>;

export function Register() {
  const { register } = useAuth();
  const navigate = useNavigate();

  const [form, setForm] = useState({
    full_name: '',
    email: '',
    password: '',
    phone: '',
    address: '',
  });
  const [errors, setErrors] = useState<Errors>({});
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function update(key: keyof typeof form, value: string) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function validate(): Errors {
    const found: Errors = {};
    if (!form.full_name.trim()) found.full_name = 'Please tell us your name.';
    if (!form.email.trim()) found.email = 'An email address is required.';
    if (form.password.length < 8) {
      found.password = 'At least 8 characters.';
    } else if (passwordByteLength(form.password) > 72) {
      found.password =
        'Too long — the limit is 72 bytes, and accented or emoji characters count for more than one.';
    }
    return found;
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const found = validate();
    setErrors(found);
    if (Object.keys(found).length > 0) return;

    setSubmitting(true);
    setError(null);
    try {
      // Registers and signs in, so a new client lands on the dashboard rather
      // than at a login form they just filled the details into.
      await register({
        email: form.email.trim(),
        password: form.password,
        full_name: form.full_name.trim(),
        phone: form.phone.trim() || null,
        address: form.address.trim() || null,
      });
      navigate('/', { replace: true });
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.detail
          : 'Could not create your account. Please try again.',
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthShell
      title="Create your account"
      subtitle="For pet owners. Clinic staff accounts are created by the practice."
      footer={
        <>
          Already registered?{' '}
          <Link
            to="/login"
            className="font-medium text-brand-700 underline-offset-2 hover:underline dark:text-brand-300"
          >
            Sign in
          </Link>
        </>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        {error && <ErrorState title="Could not register" message={error} />}

        <Input
          label="Full name"
          required
          autoComplete="name"
          autoFocus
          value={form.full_name}
          error={errors.full_name}
          onChange={(event) => update('full_name', event.target.value)}
        />
        <Input
          label="Email"
          type="email"
          required
          autoComplete="username"
          value={form.email}
          error={errors.email}
          onChange={(event) => update('email', event.target.value)}
        />
        <Input
          label="Password"
          type="password"
          required
          autoComplete="new-password"
          value={form.password}
          error={errors.password}
          hint="At least 8 characters."
          onChange={(event) => update('password', event.target.value)}
        />
        <Input
          label="Phone"
          type="tel"
          autoComplete="tel"
          value={form.phone}
          hint="So the clinic can reach you about an appointment."
          onChange={(event) => update('phone', event.target.value)}
        />
        <Input
          label="Address"
          autoComplete="street-address"
          value={form.address}
          onChange={(event) => update('address', event.target.value)}
        />

        <Button type="submit" className="w-full" size="lg" loading={submitting}>
          Create account
        </Button>
      </form>
    </AuthShell>
  );
}
