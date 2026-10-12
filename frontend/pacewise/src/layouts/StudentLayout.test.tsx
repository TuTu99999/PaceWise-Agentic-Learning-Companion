import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { StudentLayout } from './StudentLayout';

const mocks = vi.hoisted(() => ({
  state: { activeSession: null } as { activeSession: null | { id: string; blockId: string; taskId: string; accumulatedMs: number; runningSince: number | null } },
  heartbeat: vi.fn(),
}));
vi.mock('../components/domain/CourseSwitcher', () => ({ CourseSwitcher: () => null }));
vi.mock('../components/domain/ReminderCenter', () => ({ ReminderCenter: () => null }));
vi.mock('../store/AppStore', () => ({ useAppStore: () => ({ state: mocks.state }) }));
vi.mock('../hooks/useActiveStudySessionHeartbeat', () => ({ useActiveStudySessionHeartbeat: mocks.heartbeat }));
vi.mock('./AppShell', () => ({
  AppShell: ({ items }: { items: Array<{ to: string; label: string; primary?: boolean }> }) => (
    <nav>{items.map((item) => <a key={item.to} href={item.to} data-primary={String(Boolean(item.primary))}>{item.label}</a>)}</nav>
  ),
}));

describe('StudentLayout navigation', () => {
  beforeEach(() => {
    mocks.state = { activeSession: null };
    vi.clearAllMocks();
  });

  it('exposes weekly reflection as a primary Plan-Do-Reflect destination', () => {
    render(<MemoryRouter><StudentLayout /></MemoryRouter>);
    expect(screen.getByRole('link', { name: 'Reflect tuần' })).toHaveAttribute('href', '/reflect');
    expect(screen.getByRole('link', { name: 'Reflect tuần' })).toHaveAttribute('data-primary', 'true');
    expect(screen.getByRole('link', { name: 'Cài đặt' })).toHaveAttribute('data-primary', 'false');
    expect(mocks.heartbeat).toHaveBeenCalledWith(false);
  });

  it('routes Do back to the active timed session', () => {
    mocks.state = { activeSession: { id: 'SS-1', blockId: 'b 1', taskId: '1:a', accumulatedMs: 0, runningSince: 1 } };
    render(<MemoryRouter initialEntries={['/plan']}><StudentLayout /></MemoryRouter>);
    expect(screen.getByRole('link', { name: 'Do' })).toHaveAttribute('href', '/study/1%3Aa/session?blockId=b%201');
  });
});
