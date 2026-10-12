import { StrictMode } from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AppStoreProvider, useAppStore } from '../src/store/AppStore';
const api = vi.hoisted(() => ({ saveWorkspace: vi.fn(), loadWorkspace: vi.fn() }));
vi.mock('../src/services/api', () => ({
  getCurrentSession: async () => ({ id: 'qa', name: 'QA', email: 'qa@example.invalid', role: 'student', courseId: '1', courseIds: ['1'] }),
  loadWorkspace: api.loadWorkspace,
  saveWorkspace: api.saveWorkspace,
  syncCanvas: async () => ({ courses: [], tasks: [], courseData: {}, guidance: [], assessments: [] }),
  lmsEventStreamUrl: () => '/not-used',
}));
function Editor() {
  const { state, dispatch, persistence, retrySave } = useAppStore();
  return <><span data-testid="ready">{String(state.workspaceReady)}</span><span data-testid="status">{persistence.status}</span>
    <button onClick={() => dispatch({ type: 'SAVE_CALENDAR_DRAFT', blocks: [{ id: 'b', taskId: 't', date: '2026-10-10', start: '10:07', end: '11:07' }] })}>First</button>
    <button onClick={() => dispatch({ type: 'SAVE_CALENDAR_DRAFT', blocks: [] })}>Second</button><button onClick={retrySave}>Retry</button></>;
}
beforeEach(() => {
  vi.clearAllMocks();
  api.loadWorkspace.mockResolvedValue({ state: {}, version: 0, updatedAt: null });
  api.saveWorkspace.mockImplementation(async (_state, version: number) => ({ version: version + 1, updatedAt: new Date().toISOString() }));
});
describe('durable calendar autosave', () => {
  it('reports saved draft under StrictMode instead of silently leaving status pending', async () => {
    render(<StrictMode><AppStoreProvider><Editor /></AppStoreProvider></StrictMode>);
    await waitFor(() => expect(screen.getByTestId('ready')).toHaveTextContent('true'));
    fireEvent.click(screen.getByRole('button', { name: 'First' }));
    expect(screen.getByTestId('status')).toHaveTextContent('saving');
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('saved'));
    expect(api.saveWorkspace).toHaveBeenLastCalledWith(expect.objectContaining({ calendarDraft: expect.objectContaining({ blocks: [expect.objectContaining({ start: '10:07' })] }) }), expect.any(Number));
  });
  it('serializes newer edits behind an in-flight save and warns on premature reload', async () => {
    render(<AppStoreProvider><Editor /></AppStoreProvider>);
    await waitFor(() => expect(screen.getByTestId('ready')).toHaveTextContent('true'));
    let release!: (value: { version: number; updatedAt: string }) => void;
    api.saveWorkspace.mockImplementationOnce(() => new Promise((resolve) => { release = resolve; }));
    fireEvent.click(screen.getByRole('button', { name: 'First' }));
    await waitFor(() => expect(api.saveWorkspace).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole('button', { name: 'Second' }));
    const unload = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(unload); expect(unload.defaultPrevented).toBe(true);
    await act(async () => { release({ version: 1, updatedAt: '2026-10-10T00:00:00Z' }); });
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('saved'));
    expect(api.saveWorkspace).toHaveBeenLastCalledWith(expect.objectContaining({ calendarDraft: expect.objectContaining({ blocks: [] }) }), 1);
    const after = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(after); expect(after.defaultPrevented).toBe(false);
  });
  it('keeps the draft after network failure and allows an explicit retry', async () => {
    render(<AppStoreProvider><Editor /></AppStoreProvider>);
    await waitFor(() => expect(screen.getByTestId('ready')).toHaveTextContent('true'));
    api.saveWorkspace.mockRejectedValueOnce(new Error('offline'));
    fireEvent.click(screen.getByRole('button', { name: 'First' }));
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('error'));
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('saved'));
    expect(api.saveWorkspace).toHaveBeenLastCalledWith(expect.objectContaining({ calendarDraft: expect.objectContaining({ blocks: [expect.objectContaining({ start: '10:07' })] }) }), 0);
  });
});
