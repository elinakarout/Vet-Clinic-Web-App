// fetch wrapper that attaches the JWT Authorization header and throws on non-2xx. (Phase 5)
//
// Every server call in the app goes through `apiFetch`. That single choke point
// is what makes three things possible without repeating them everywhere: the
// bearer header, a typed error, and one global reaction to an expired session.

const BASE_URL: string =
  import.meta.env.VITE_API_URL || 'http://localhost:8000';

const TOKEN_KEY = 'vetclinic.token';

/**
 * A non-2xx response, unwrapped.
 *
 * FastAPI answers `{"detail": "..."}` for handled errors and an array of issue
 * objects for a 422. `detail` here is always a string a human can read; `status`
 * is what callers branch on. Both matter: the UI copy for a 409 on booking is
 * completely different from a 409 on deleting a pet, and only the caller knows
 * which one it asked for.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }

  /** 4xx that a retry cannot fix. TanStack Query uses this to not retry. */
  get isClientError(): boolean {
    return this.status >= 400 && this.status < 500;
  }
}

// --- Token storage --------------------------------------------------------

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    // Private-mode Safari and "block site data" both throw rather than return
    // null. An unreadable store means logged out, not a crash on boot.
    return null;
  }
}

export function setToken(token: string | null): void {
  try {
    if (token === null) localStorage.removeItem(TOKEN_KEY);
    else localStorage.setItem(TOKEN_KEY, token);
  } catch {
    // Non-fatal: the session simply won't survive a reload.
  }
}

// --- Expired-session handling --------------------------------------------

let onUnauthorized: (() => void) | null = null;

/**
 * Registered once by AuthProvider. A module-level callback rather than an
 * import, because api/client.ts must not depend on the auth module that depends
 * on it.
 *
 * Tokens last 60 minutes and there is no refresh token, so a long-lived tab
 * WILL hit this. Handling it in one place is the difference between "your
 * session expired, please sign in" and every page failing in its own way.
 */
export function setUnauthorizedHandler(handler: (() => void) | null): void {
  onUnauthorized = handler;
}

// --- The request ----------------------------------------------------------

export interface RequestOptions {
  method?: string;
  /** Serialised as JSON. Use `form` for the one form-encoded endpoint. */
  body?: unknown;
  /** POST /auth/login only — the OAuth2 password flow is form-encoded. */
  form?: Record<string, string>;
  query?: Record<string, string | number | boolean | undefined | null>;
  /** Login and register are the two calls made while signed out. */
  auth?: boolean;
  signal?: AbortSignal;
}

function buildUrl(
  path: string,
  query?: RequestOptions['query'],
): string {
  const url = new URL(path.replace(/^\//, ''), `${BASE_URL.replace(/\/$/, '')}/`);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== null && value !== '') {
        url.searchParams.set(key, String(value));
      }
    }
  }
  return url.toString();
}

/** Turns any error body into one readable sentence. */
async function readError(response: Response): Promise<string> {
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    return response.statusText || `Request failed (${response.status})`;
  }

  if (payload && typeof payload === 'object' && 'detail' in payload) {
    const { detail } = payload as { detail: unknown };
    if (typeof detail === 'string') return detail;
    // FastAPI's 422: [{loc: [...], msg: "...", type: "..."}]. Show the field and
    // the message, because "Field required" alone tells the user nothing.
    if (Array.isArray(detail)) {
      const messages = detail.map((issue) => {
        if (!issue || typeof issue !== 'object') return String(issue);
        const { loc, msg } = issue as { loc?: unknown[]; msg?: string };
        const field = Array.isArray(loc)
          ? loc.filter((p) => p !== 'body').join('.')
          : '';
        return field ? `${field}: ${msg ?? 'is invalid'}` : (msg ?? 'is invalid');
      });
      return messages.join('; ');
    }
  }
  return response.statusText || `Request failed (${response.status})`;
}

export async function apiFetch<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const { method = 'GET', body, form, query, auth = true, signal } = options;

  const headers: Record<string, string> = {};
  if (auth) {
    const token = getToken();
    if (token) headers.Authorization = `Bearer ${token}`;
  }

  let payload: BodyInit | undefined;
  if (form) {
    headers['Content-Type'] = 'application/x-www-form-urlencoded';
    // URLSearchParams rather than FormData: tsconfig's lib has no DOM.Iterable,
    // and this is also exactly the encoding OAuth2PasswordRequestForm wants.
    payload = new URLSearchParams(form).toString();
  } else if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
    payload = JSON.stringify(body);
  }

  let response: Response;
  try {
    response = await fetch(buildUrl(path, query), {
      method,
      headers,
      body: payload,
      signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error;
    // A dead backend and a CORS rejection are indistinguishable here, and the
    // most likely cause in development is the first.
    throw new ApiError(
      0,
      'Could not reach the clinic server. Check your connection and try again.',
    );
  }

  if (response.status === 401 && auth) {
    // Do not fire on a failed login — that 401 means "wrong password", not
    // "your session ended", and logging out a user who is not in would be odd.
    onUnauthorized?.();
    throw new ApiError(401, 'Your session has expired. Please sign in again.');
  }

  if (!response.ok) {
    throw new ApiError(response.status, await readError(response));
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
