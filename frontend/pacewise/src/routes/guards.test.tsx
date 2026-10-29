import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { RequireRole, homeFor } from './guards';

const mocks = vi.hoisted(() => ({
  state: { authReady: true, user: null as null | { role: 'student' | 'instructor' | 'guest' } },
}));

vi.mock('../store/AppStore', () => ({
  useAppStore: () => ({ state: mocks.state }),
}));

function Location() {
  const location = useLocation();
  return <h1>{location.pathname}</h1>;
}

function renderGuard(expectedRole: 'student' | 'instructor') {
  render(
    <MemoryRouter initialEntries={['/protected']}>
      <Routes>
        <Route
          path="/protected"
          element={(
            <RequireRole role={expectedRole}>
              <h1>protected</h1>
            </RequireRole>
          )}
        />
        <Route path="*" element={<Location />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('role-aware navigation recovery', () => {
  beforeEach(() => {
    mocks.state = { authReady: true, user: null };
  });

  it.each([
    ['student', 'instructor', '/plan'],
    ['instructor', 'student', '/instructor'],
  ] as const)('returns a %s to its home when history points at a %s page', (currentRole, expectedRole, home) => {
    mocks.state = { authReady: true, user: { role: currentRole } };
    renderGuard(expectedRole);
    expect(screen.getByRole('heading', { name: home })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: '/403' })).not.toBeInTheDocument();
  });

  it('sends an unauthenticated visitor to the canonical login route', () => {
    renderGuard('student');
    expect(screen.getByRole('heading', { name: '/login' })).toBeInTheDocument();
  });

  it('does not use 403 as a guest home route', () => {
    expect(homeFor('guest')).toBe('/login');
  });
});
