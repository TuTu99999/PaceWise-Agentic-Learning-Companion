import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { syncCanvas } from '../../services/api';
import { LmsConnectionCard } from './LmsConnectionCard';

const fixture = vi.hoisted(() => ({ dispatch: vi.fn(), toast: vi.fn() }));
vi.mock('../../store/AppStore', () => ({ useAppStore: () => ({ dispatch: fixture.dispatch, state: {
  settings: { staleData: false, lastSync: '2026-10-09T02:00:00Z' },
} }) }));
vi.mock('../ui/Toast', () => ({ useToast: () => fixture.toast }));
vi.mock('../../services/api', () => ({ syncCanvas: vi.fn() }));

beforeEach(() => vi.resetAllMocks());
describe('Canvas connection status', () => {
  it('shows last-sync state and retries through the existing authorized sync', async () => {
    vi.mocked(syncCanvas).mockResolvedValue({ tasks: [], courses: [], courseData: {}, syncedAt: '2026-10-09T03:00:00Z', source: 'lms', activeCourseId: '7' });
    render(<LmsConnectionCard />);
    expect(screen.getByText('Đã đồng bộ LMS')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Đồng bộ Canvas lại' }));
    await waitFor(() => expect(fixture.dispatch).toHaveBeenCalledWith(expect.objectContaining({ type: 'SYNC_CANVAS', tasks: [], courses: [] })));
  });
  it('reports errors instead of declaring the integration disconnected', async () => {
    vi.mocked(syncCanvas).mockRejectedValue(new Error('LMS unavailable'));
    render(<LmsConnectionCard />);
    fireEvent.click(screen.getByRole('button', { name: 'Đồng bộ Canvas lại' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('LMS unavailable');
    expect(fixture.dispatch).toHaveBeenCalledWith({ type: 'UPDATE_SETTINGS', patch: { staleData: true } });
    expect(fixture.toast).not.toHaveBeenCalled();
  });
});
