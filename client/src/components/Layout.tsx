// Shared app shell: nav, chat panel slot, page outlet. (Phase 5)

import { useState } from 'react';
import { Link, NavLink, Outlet } from 'react-router-dom';
import { useAuth } from '../auth/useAuth';
import { cn } from '../lib/cn';
import { CLINIC_TIMEZONE, clinicZoneLabel, viewerIsInAnotherZone } from '../lib/datetime';
import { Role } from '../types/api';
import { ChatPanel } from './chat/ChatPanel';
import { ThemeToggle } from './ThemeToggle';
import { Button } from './ui/Button';

interface NavItem {
  to: string;
  label: string;
  roles: Role[];
}

const NAV: NavItem[] = [
  { to: '/', label: 'Dashboard', roles: [Role.CLIENT, Role.VET, Role.ADMIN] },
  { to: '/pets', label: 'Pets', roles: [Role.CLIENT, Role.VET, Role.ADMIN] },
  { to: '/book', label: 'Book', roles: [Role.CLIENT, Role.VET, Role.ADMIN] },
  {
    to: '/appointments',
    label: 'Appointments',
    roles: [Role.CLIENT, Role.VET, Role.ADMIN],
  },
  { to: '/schedule', label: 'Schedule', roles: [Role.VET, Role.ADMIN] },
];

function PawMark() {
  return (
    <svg className="h-6 w-6" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <ellipse cx="7.5" cy="8" rx="2.1" ry="2.8" />
      <ellipse cx="12" cy="6.4" rx="2.1" ry="2.9" />
      <ellipse cx="16.5" cy="8" rx="2.1" ry="2.8" />
      <ellipse cx="19.4" cy="12.4" rx="1.9" ry="2.3" />
      <path d="M12 11.4c2.7 0 5.4 2.3 5.4 4.8 0 2-1.6 3.2-3.6 3.2-1 0-1.3-.3-1.8-.3s-.8.3-1.8.3c-2 0-3.6-1.2-3.6-3.2 0-2.5 2.7-4.8 5.4-4.8Z" />
    </svg>
  );
}

function navLinkClasses({ isActive }: { isActive: boolean }): string {
  return cn(
    'rounded-lg px-3 py-2 text-sm font-medium transition-colors',
    isActive
      ? 'bg-brand-50 text-brand-800 dark:bg-brand-500/15 dark:text-brand-200'
      : 'text-ink-600 hover:bg-ink-100 hover:text-ink-900 dark:text-ink-300 dark:hover:bg-ink-800 dark:hover:text-ink-50',
  );
}

export function Layout() {
  const { user, logout } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);

  // The drawer closes from the event that navigates (below), not from an effect
  // watching the location — one fewer render, and no state to fall out of step.
  const closeMenu = () => setMenuOpen(false);

  const items = NAV.filter((item) => user && item.roles.includes(user.role));

  return (
    <div className="flex min-h-screen flex-col">
      {/* Keyboard users should not have to tab the whole nav on every page. */}
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-brand-600 focus:px-4 focus:py-2 focus:text-white"
      >
        Skip to content
      </a>

      <header className="sticky top-0 z-30 border-b border-ink-200/80 bg-white/85 backdrop-blur-sm dark:border-ink-800 dark:bg-ink-900/85">
        <div className="mx-auto flex h-16 max-w-6xl items-center gap-4 px-4">
          <Link
            to="/"
            className="flex items-center gap-2 text-brand-700 dark:text-brand-300"
          >
            <PawMark />
            <span className="text-base font-semibold tracking-tight text-ink-900 dark:text-ink-50">
              Paws &amp; Claws
            </span>
          </Link>

          <nav aria-label="Main" className="ml-4 hidden items-center gap-1 md:flex">
            {items.map((item) => (
              <NavLink key={item.to} to={item.to} end={item.to === '/'} className={navLinkClasses}>
                {item.label}
              </NavLink>
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-1">
            <ThemeToggle />
            <div className="hidden items-center gap-2 sm:flex">
              <Link
                to="/profile"
                className="max-w-[12rem] truncate rounded-lg px-3 py-2 text-sm text-ink-600 hover:bg-ink-100 hover:text-ink-900 dark:text-ink-300 dark:hover:bg-ink-800 dark:hover:text-ink-50"
              >
                {user?.full_name || user?.email}
              </Link>
              <Button variant="secondary" size="sm" onClick={logout}>
                Sign out
              </Button>
            </div>
            <button
              type="button"
              className="rounded-lg p-2 text-ink-600 hover:bg-ink-100 md:hidden dark:text-ink-300 dark:hover:bg-ink-800"
              onClick={() => setMenuOpen((open) => !open)}
              aria-label="Menu"
              aria-expanded={menuOpen}
            >
              <svg className="h-6 w-6" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <path
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  d={menuOpen ? 'M6 6l12 12M18 6 6 18' : 'M4 7h16M4 12h16M4 17h16'}
                />
              </svg>
            </button>
          </div>
        </div>

        {menuOpen && (
          <nav
            aria-label="Main"
            className="border-t border-ink-200 px-4 py-3 md:hidden dark:border-ink-800"
          >
            <div className="flex flex-col gap-1">
              {items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.to === '/'}
                  className={navLinkClasses}
                  onClick={closeMenu}
                >
                  {item.label}
                </NavLink>
              ))}
              <NavLink to="/profile" className={navLinkClasses} onClick={closeMenu}>
                Profile
              </NavLink>
              <Button variant="secondary" size="sm" className="mt-2" onClick={logout}>
                Sign out
              </Button>
            </div>
          </nav>
        )}
      </header>

      <main id="main" className="mx-auto w-full max-w-6xl flex-1 px-4 py-8">
        <Outlet />
      </main>

      <footer className="border-t border-ink-200/80 px-4 py-5 text-center text-xs text-ink-500 dark:border-ink-800 dark:text-ink-400">
        <p>
          All times shown in clinic time — {CLINIC_TIMEZONE.replace('_', ' ')} (
          {clinicZoneLabel()})
          {viewerIsInAnotherZone() && ', which is not your device’s time zone'}.
        </p>
      </footer>

      <ChatPanel />
    </div>
  );
}
