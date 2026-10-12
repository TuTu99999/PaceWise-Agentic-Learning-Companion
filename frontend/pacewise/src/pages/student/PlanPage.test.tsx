import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { StrictMode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { initialState, reducer, type AppState, type Action } from '../../store/AppStore';
import { PlanPage } from './PlanPage';
import type { ComponentProps } from 'react';
import type { PlanCalendarBoard } from '../../components/domain/PlanCalendarBoard';
type PlanCalendarBoardProps = ComponentProps<typeof PlanCalendarBoard>;

const fixture = vi.hoisted(() => ({ state: {} as AppState, board: {} as PlanCalendarBoardProps, toast: vi.fn(), confirm: vi.fn(), propose: vi.fn(), generate: vi.fn() }));
vi.mock('../../services/api', () => ({ confirmPlan: fixture.confirm, generatePlan: fixture.generate, proposeWeeklyGoals: fixture.propose }));
vi.mock('../../store/AppStore', async (original) => ({ ...await original<typeof import('../../store/AppStore')>(),
  useAppStore: () => ({ state: fixture.state, dispatch: (action: Action) => { fixture.state = reducer(fixture.state, action); }, persistence: { status: 'saved' } }) }));
vi.mock('../../components/ui/Toast', () => ({ useToast: () => fixture.toast }));
vi.mock('../../components/domain/ReminderCenter', () => ({ ReminderCenter: () => null }));
vi.mock('../../components/domain/PlanCalendarBoard', () => ({ PlanCalendarBoard: (props: PlanCalendarBoardProps) => {
  fixture.board = props; return <div data-testid="board">{props.items.map((item) => <span key={item.id}>{item.title}</span>)}</div>;
} }));
const view = (entry = '/plan') => <MemoryRouter initialEntries={[entry]}><PlanPage /></MemoryRouter>;
beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] }); vi.setSystemTime(new Date('2026-10-05T08:00:00+07:00'));
  fixture.toast.mockClear();
  fixture.confirm.mockReset();
  fixture.propose.mockReset().mockResolvedValue([]);
  fixture.generate.mockReset().mockResolvedValue({ input: { goal: '', tasks: [], availability: [], unavailable: [], preferred: 'evening' },
    blocks: [{ id: 'draft-b', taskId: 't2', date: '2026-10-09', start: '11:00', end: '12:00' }], createdAt: 'new-replan',
    reasons: [], assumptions: [], feasibility: { feasible: true, availableMin: 300, requiredMin: 300, remainingMin: 0, deficitMin: 0, shortfalls: [] } });
  fixture.state = { ...initialState, workspaceReady: true, routineProfile: null,
    courses: [{ id: '1', code: 'TRR', name: 'Toán rời rạc', tone: 'primary' }, { id: '2', code: 'CS', name: 'Lập trình', tone: 'accent' }],
    tasks: [{ id: 't1', courseId: '1', title: 'Quan hệ hai ngôi', objective: 'Giải thích', deadline: '2026-10-08', dueAt: '2026-10-08T12:00:00+07:00', estimateMin: 240, loggedMin: 0, status: 'todo', priority: 'high' },
      { id: 't2', courseId: '2', title: 'Python', objective: 'Học', deadline: '2026-10-10', estimateMin: 60, loggedMin: 0, status: 'todo', priority: 'high' }],
    availability: initialState.availability.map((day) => ({ ...day, enabled: true, start: '00:00', end: '24:00' })),
    plan: { id: 'plan', weekStart: '2026-10-05', version: 1, savedAt: '2026-10-05T00:00:00Z', blocks: [
      { id: 'b1', taskId: 't1', date: '2026-10-08', start: '10:00', end: '11:00' },
      { id: 'b2', taskId: 't2', date: '2026-10-09', start: '10:00', end: '11:00' }] },
    unavailable: [{ id: 'meal', label: 'Ăn trưa', source: 'manual', category: 'meal', date: '2026-10-08', weekday: 3, start: '13:00', end: '14:00' }],
  };
});
afterEach(() => vi.useRealTimers());
describe('student calendar editing workflow', () => {
  it('automatically analyzes an LMS notification in Plan once, without a Recover or goal-selection step', async () => {
    const applied = fixture.state.plan;
    fixture.state.planImpacts = [{ id: 'new-task', kind: 'assignment_added', title: 'Có deadline mới', message: 'New task',
      taskId: 't2', courseId: '2', deficitMin: 60, affectedBlockIds: [], detectedAt: '2026-10-05T08:00:00+07:00' }];
    render(<StrictMode>{view('/plan?reanalyze=lms&impactId=new-task')}</StrictMode>);
    await waitFor(() => expect(fixture.generate).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(fixture.state.planDraft?.replan?.impactIds).toEqual(['new-task']));
    expect(fixture.generate.mock.calls[0][0].tasks.map((item: { taskId: string }) => item.taskId)).toEqual(['t1', 't2']);
    expect(fixture.propose).not.toHaveBeenCalled();
    expect(fixture.confirm).not.toHaveBeenCalled();
    expect(fixture.state.plan).toBe(applied);
    expect(screen.queryByRole('dialog', { name: /mục tiêu/i })).not.toBeInTheDocument();
  });
  it('turns a confirmed Reflect decision into a Plan draft without applying it', async () => {
    const applied = fixture.state.plan;
    render(<StrictMode>{view('/plan?reanalyze=reflection&scope=activity&taskId=t1')}</StrictMode>);
    await waitFor(() => expect(fixture.generate).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(fixture.state.planDraft).toBeDefined());
    expect(fixture.generate.mock.calls[0][0].tasks.map((item: { taskId: string }) => item.taskId)).toEqual(['t1', 't2']);
    expect(fixture.generate.mock.calls[0][0].replanContext).toEqual({ trigger: 'reflection', scope: 'activity', taskIds: ['t1'] });
    expect(fixture.propose).not.toHaveBeenCalled();
    expect(fixture.confirm).not.toHaveBeenCalled();
    expect(fixture.state.plan).toBe(applied);
  });
  it('turns a confirmed weekly Reflect into a different draft without replacing the applied plan', async () => {
    const applied = fixture.state.plan;
    render(<StrictMode>{view('/plan?reanalyze=reflection&scope=weekly')}</StrictMode>);

    await waitFor(() => expect(fixture.generate).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(fixture.state.planDraft?.replan).toBeDefined());

    expect(fixture.generate.mock.calls[0][0].tasks.map((item: { taskId: string }) => item.taskId)).toEqual(['t1', 't2']);
    expect(fixture.state.planDraft?.createdAt).toBe('new-replan');
    expect(fixture.state.planDraft?.blocks).not.toEqual(applied?.blocks);
    expect(fixture.confirm).not.toHaveBeenCalled();
    expect(fixture.state.plan).toBe(applied);
  });
  it('waits for hydration before consuming a notification hand-off', async () => {
    const tasks = fixture.state.tasks;
    fixture.state = { ...fixture.state, workspaceReady: false, tasks: [] };
    const mounted = render(view('/plan?reanalyze=lms&impactId=new-task'));
    expect(fixture.generate).not.toHaveBeenCalled();
    fixture.state = { ...fixture.state, workspaceReady: true, tasks };
    mounted.rerender(view('/plan?reanalyze=lms&impactId=new-task'));
    await waitFor(() => expect(fixture.generate).toHaveBeenCalledTimes(1));
  });
  it('opens an unchanged re-plan draft again without repeating the API call', async () => {
    const first = render(view('/plan?reanalyze=lms&impactId=new-task'));
    await waitFor(() => expect(fixture.state.planDraft?.replan).toBeDefined());
    first.unmount();
    render(view('/plan?reanalyze=lms&impactId=new-task'));
    await waitFor(() => expect(fixture.board.items.some(item => item.entityId === 'draft-b')).toBe(true));
    expect(fixture.generate).toHaveBeenCalledTimes(1);
  });
  it('unpins affected future placements for re-plan but preserves elapsed history', async () => {
    fixture.state.plan!.blocks[0].placementSource = 'student';
    fixture.state.plan!.blocks.push({ id: 'history', taskId: 't1', date: '2026-10-04', start: '10:00', end: '11:00', status: 'history' });
    fixture.state.planImpacts = [{ id: 'deadline-change', kind: 'deadline_earlier', title: 'Deadline đổi', message: '',
      taskId: 't1', courseId: '1', deficitMin: 60, affectedBlockIds: ['b1', 'history'], detectedAt: '' }];
    render(view('/plan?reanalyze=lms&impactId=deadline-change'));
    await waitFor(() => expect(fixture.generate).toHaveBeenCalledOnce());
    expect(fixture.generate.mock.calls[0][0].pinnedBlocks.map((block: { id: string }) => block.id)).toEqual(['history']);
    expect(fixture.state.plan!.blocks.find(block => block.id === 'b1')?.start).toBe('10:00');
  });
  it('sends the personal routine and 90-minute session cap into re-plan', async () => {
    fixture.state.routineProfile = { wakeTime: '07:00', sleepTime: '23:10', preferred: ['morning', 'evening'] };
    fixture.state.studyPreferences = { sessionMinutes: 90, breakMinutes: 10, checkpointMinutes: 5, adaptiveSuggestionsEnabled: true, activityRhythms: [] };
    fixture.state.availability = fixture.state.availability.map((day) => ({ ...day, enabled: false }));

    render(view('/plan?reanalyze=progress&taskId=t1'));
    await waitFor(() => expect(fixture.generate).toHaveBeenCalledOnce());

    const input = fixture.generate.mock.calls[0][0];
    expect(input.studyPreferences).toMatchObject({ sessionMinutes: 90, breakMinutes: 10, checkpointMinutes: 5 });
    expect(input.preferred).toEqual(['morning', 'evening']);
    expect(input.availability).toHaveLength(7);
    expect(input.availability.every((day: { enabled: boolean; start: string; end: string }) => day.enabled && day.start === '00:00' && day.end === '24:00')).toBe(true);
    expect(input.unavailable).toEqual(expect.arrayContaining([
      expect.objectContaining({ source: 'routine', category: 'sleep', start: '23:10', end: '24:00' }),
      expect.objectContaining({ source: 'routine', category: 'sleep', start: '00:00', end: '07:00' }),
    ]));
  });
  it('does not reselect expired tasks from historical pins or the fixed demo start', async () => {
    vi.setSystemTime(new Date('2026-10-10T11:00:00+07:00'));
    fixture.state.tasks.push({ ...fixture.state.tasks[1], id: 'same-day-expired', dueAt: '2026-10-10T10:45:00+07:00' });
    fixture.state.plan!.blocks.push({ ...fixture.state.plan!.blocks[0], id: 'same-day-pin', taskId: 'same-day-expired', date: '2026-10-10', start: '09:00', end: '10:00' });
    render(view());
    fireEvent.click(screen.getByRole('button', { name: /AI (?:lập kế hoạch|phân tích lại)/ }));
    await waitFor(() => expect(fixture.propose).toHaveBeenCalled());
    expect(fixture.propose.mock.calls[0][0].map((t: { id: string }) => t.id)).toEqual(['t2']);
    expect(fixture.state.plan!.blocks).toHaveLength(3);
  });
  it('re-analyzes weekly goals when the student explicitly clicks AI with an existing draft', async () => {
    fixture.state.planDraft = {
      input: { goal: 'Old goal', tasks: [], availability: [], unavailable: [], preferred: 'evening' },
      weeklyGoals: [{ id: 'old-goal', title: 'Old goal', taskIds: ['t2'], confirmed: true }],
      blocks: [], createdAt: 'old', reasons: [], assumptions: [],
      feasibility: { feasible: true, availableMin: 60, requiredMin: 60, remainingMin: 0, deficitMin: 0, shortfalls: [] },
    };
    fixture.propose.mockResolvedValueOnce([{ id: 'fresh-goal', title: 'Phân tích lại Python', taskIds: ['t2'], confirmed: true, analysisSource: 'model' }]);

    render(view());
    fireEvent.click(screen.getByRole('button', { name: /AI (?:lập kế hoạch|phân tích lại)/ }));

    await waitFor(() => expect(fixture.propose).toHaveBeenCalledOnce());
    expect(fixture.generate).not.toHaveBeenCalled();
    expect(await screen.findByRole('dialog', { name: /Mục tiêu tuần AI đề xuất/i })).toBeInTheDocument();
    expect(screen.getByDisplayValue('Phân tích lại Python')).toBeInTheDocument();
  });
  it('labels expired cached capacity stale instead of repeating a nine-hour future shortage', () => {
    vi.setSystemTime(new Date('2026-10-10T11:00:00+07:00'));
    fixture.state.planDraft = { input: { goal: '', tasks: [], availability: [], unavailable: [], preferred: 'evening' },
      blocks: [], createdAt: 'old', reasons: [], assumptions: [],
      feasibility: { feasible: false, availableMin: 60, requiredMin: 600, remainingMin: -540, deficitMin: 540, shortfalls: [{ taskId: 't1', missingMin: 540 }] } };
    render(view());
    expect(screen.getByRole('alert')).toHaveTextContent('nhiệm vụ đã quá hạn');
    expect(screen.getByText('Bản nháp cũ · cần tính lại capacity')).toBeInTheDocument();
    expect(screen.queryByText('Thiếu 9 giờ capacity')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Xác nhận phần lịch hợp lệ' })).not.toBeInTheDocument();
  });
  it('opens today without the duplicate add-calendar button or menu', () => {
    render(view()); expect(screen.getByLabelText('Chọn ngày')).toHaveValue('2026-10-05');
    expect(screen.queryByRole('button', { name: 'Thêm vào lịch' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Thêm ca tự học' })).not.toBeInTheDocument();
    expect(screen.queryByRole('dialog', { name: 'Thêm vào lịch' })).not.toBeInTheDocument();
  });
  it('keeps the funnel filter icon distinct from tab navigation', () => {
    render(view());
    const filter = screen.getByRole('button', { name: 'Lọc và hiển thị lịch' });
    expect(filter.querySelector('path')).toHaveAttribute('d', 'M3 4h18l-7 8v7l-4 2v-9z');
    expect(filter.querySelector('svg')).toHaveAttribute('aria-hidden', 'true');
  });
  it('rejects a drag beyond the hour-specific deadline before changing any state', () => {
    render(view());
    if (fixture.board.readOnly) throw new Error('Expected editable calendar');
    fixture.board.onMoveBlock('b1', '2026-10-08', '17:00');
    expect(fixture.state.calendarDraft).toBeNull();
    expect(fixture.toast).toHaveBeenLastCalledWith(expect.objectContaining({ description: expect.stringContaining('deadline') }));
  });
  it('keeps edited placements after leaving and reopening the page, without applying them', () => {
    const mounted = render(view());
    if (fixture.board.readOnly) throw new Error('Expected editable calendar');
    fixture.board.onMoveBlock('b1', '2026-10-08', '10:15'); mounted.unmount(); render(view());
    expect(fixture.state.calendarDraft?.blocks[0].start).toBe('10:15');
    expect(fixture.state.plan?.blocks[0].start).toBe('10:00');
    expect(fixture.board.items.find((item) => item.entityId === 'b1')?.start).toBe('10:15');
  });
  it('moves a generated block without counting checkpoint time as unfinished task work', () => {
    fixture.state.tasks[1].estimateMin = 60;
    fixture.state.plan!.blocks[1] = { ...fixture.state.plan!.blocks[1], end: '11:15', checkpointMinutes: 15 };
    render(view());
    if (fixture.board.readOnly) throw new Error('Expected editable calendar');
    fixture.board.onMoveBlock('b2', '2026-10-09', '12:00');
    expect(fixture.state.calendarDraft?.blocks.find((block) => block.id === 'b2')).toMatchObject({
      start: '12:00',
      end: '13:15',
    });
    expect(fixture.toast).not.toHaveBeenCalledWith(expect.objectContaining({ title: expect.stringContaining('Không thể') }));
  });
  it('uses routine availability when moving an AI block instead of disabled legacy availability', () => {
    fixture.state.availability = fixture.state.availability.map((day) => ({ ...day, enabled: false }));
    fixture.state.routineProfile = { wakeTime: '07:00', sleepTime: '00:00', preferred: ['morning', 'evening'] };
    render(view());
    if (fixture.board.readOnly) throw new Error('Expected editable calendar');
    fixture.board.onMoveBlock('b2', '2026-10-09', '12:00');
    expect(fixture.state.calendarDraft?.blocks.find((block) => block.id === 'b2')?.start).toBe('12:00');
    expect(fixture.toast).not.toHaveBeenCalledWith(expect.objectContaining({
      description: expect.stringContaining('ngoài thời gian bạn có thể học'),
    }));
  });
  it('saves a moved preferred-study window and the reanalysis draft atomically', () => {
    fixture.state.unavailable.push({ id: 'preferred', label: 'Giờ tự học', source: 'manual', category: 'self_study', date: '2026-10-09', weekday: 4, start: '18:00', end: '20:00' });
    render(view());
    if (fixture.board.readOnly) throw new Error('Expected editable calendar');
    fixture.board.onMoveBusy('preferred', '2026-10-10', '20:15');
    expect(fixture.state.unavailable.find((slot) => slot.id === 'preferred')).toMatchObject({
      date: '2026-10-10', weekday: 5, start: '20:15', end: '22:15',
    });
    expect(fixture.state.calendarDraft).toMatchObject({ needsAnalysis: true, blocks: fixture.state.plan!.blocks });
  });
  it.each([
    ['meal', 'Ăn uống'],
    ['self_study', 'Giờ tự học'],
    ['sleep', 'Ngủ'],
    ['other', 'Bận khác'],
  ] as const)('does not add %s to elapsed calendar time', (category, label) => {
    const before = fixture.state.unavailable;
    render(view());
    if (fixture.board.readOnly) throw new Error('Expected editable calendar');

    fixture.board.onAddBusy('2026-10-04', '18:00', category, label);

    expect(fixture.state.unavailable).toBe(before);
    expect(fixture.state.calendarDraft).toBeNull();
    expect(fixture.toast).toHaveBeenLastCalledWith({
      tone: 'warning',
      title: 'Không thể thêm hoạt động',
      description: expect.stringContaining('thời gian đã qua'),
    });
  });
  it('does not move an existing personal activity into the past', () => {
    render(view());
    if (fixture.board.readOnly) throw new Error('Expected editable calendar');

    fixture.board.onMoveBusy('meal', '2026-10-05', '07:00');

    expect(fixture.state.unavailable.find((slot) => slot.id === 'meal')).toMatchObject({
      date: '2026-10-08', start: '13:00', end: '14:00',
    });
    expect(fixture.state.calendarDraft).toBeNull();
    expect(fixture.toast).toHaveBeenLastCalledWith(expect.objectContaining({
      title: 'Không thể dời hoạt động',
      description: expect.stringContaining('thời gian đã qua'),
    }));
  });
  it('shows the API cause and retry delay when plan analysis is rate limited', async () => {
    const error = Object.assign(new Error('Bạn thao tác quá nhanh.'), {
      code: 'RATE_LIMITED', requestId: 'PW-REQ-RATE', retryAfterSeconds: 7,
    });
    fixture.generate.mockRejectedValueOnce(error);
    fixture.state.wizardInput = {
      goal: 'Học đúng hạn', weekStart: '2026-10-05', tasks: [], availability: fixture.state.availability,
      unavailable: [], preferred: ['evening'], weeklyGoals: [{ id: 'goal-1', title: 'Hoàn thành bài', taskIds: ['t1'], confirmed: true }],
    };
    fixture.propose.mockResolvedValueOnce([{ id: 'goal-1', title: 'Hoàn thành bài', taskIds: ['t1'], confirmed: true, analysisSource: 'model' }]);
    render(view());
    fireEvent.click(screen.getByRole('button', { name: /AI (?:lập kế hoạch|phân tích lại)/ }));
    await screen.findByRole('dialog', { name: /Mục tiêu tuần AI đề xuất/i });
    fireEvent.click(screen.getByRole('button', { name: 'Xác nhận và lập lịch' }));
    await waitFor(() => expect(fixture.toast).toHaveBeenLastCalledWith(expect.objectContaining({
      title: 'AI chưa thể phân tích kế hoạch',
      description: expect.stringContaining('7 giây'),
    })));
  });
  it('shows filters but still checks conflicts with hidden personal items', () => {
    render(view()); fireEvent.click(screen.getByRole('button', { name: 'Lọc và hiển thị lịch' }));
    fireEvent.change(screen.getByLabelText('Lọc lịch theo môn học'), { target: { value: '1' } });
    fireEvent.click(screen.getByLabelText('Hiện lịch cá nhân và giờ tự học ưu tiên'));
    expect(fixture.board.items.some((item) => item.source === 'busy')).toBe(false);
    expect(fixture.board.items.some((item) => item.taskId === 't2')).toBe(false);
    if (fixture.board.readOnly) throw new Error('Expected editable calendar');
    fixture.board.onMoveBlock('b2', '2026-10-08', '13:00');
    expect(fixture.state.calendarDraft).toBeNull();
    expect(fixture.toast).toHaveBeenLastCalledWith(expect.objectContaining({ description: expect.stringContaining('trùng lịch') }));
  });
  it('does not lock Do for an unchanged confirmed session because another session was edited', () => {
    fixture.state = reducer(fixture.state, { type: 'SAVE_CALENDAR_DRAFT', blocks: fixture.state.plan!.blocks.map((b) => b.id === 'b2' ? { ...b, start: '10:15', end: '11:15' } : b) });
    render(view()); if (fixture.board.readOnly) throw new Error('Expected editable calendar');
    act(() => { if (!fixture.board.readOnly) fixture.board.onOpenBlock('b1'); });
    expect(screen.getByRole('button', { name: 'Bắt đầu Do' })).toBeInTheDocument();
  });
  it('requires confirmation for a moved session, not for all sessions', () => {
    fixture.state = reducer(fixture.state, { type: 'SAVE_CALENDAR_DRAFT', blocks: fixture.state.plan!.blocks.map((b) => b.id === 'b1' ? { ...b, start: '10:15', end: '11:15' } : b) });
    render(view());
    act(() => { if (!fixture.board.readOnly) fixture.board.onOpenBlock('b1'); });
    expect(screen.getByRole('button', { name: 'Bắt đầu Do' })).toBeDisabled();
    expect(screen.getByText(/Ca này chưa được xác nhận/)).toBeInTheDocument();
  });
  it('keeps the applied calendar accessible while a different AI draft awaits review', () => {
    fixture.state.planDraft = { input: { goal: '', tasks: [], availability: [], unavailable: [], preferred: 'evening' },
      blocks: [{ ...fixture.state.plan!.blocks[0], id: 'new' }], createdAt: '', reasons: [], assumptions: [],
      feasibility: { feasible: false, availableMin: 60, requiredMin: 600, remainingMin: -540, deficitMin: 540, shortfalls: [{ taskId: 't1', missingMin: 540 }] } };
    render(view());
    expect(fixture.board.items.some(b => b.entityId === 'b1')).toBe(true);
    act(() => { if (!fixture.board.readOnly) fixture.board.onOpenBlock('b1'); });
    expect(screen.getByRole('button', { name: 'Bắt đầu Do' })).toBeEnabled();
  });
  it('requires an explicit partial review and stores only the backend-confirmed subset with the shortfall', async () => {
    const block = { ...fixture.state.plan!.blocks[0], id: 'new' };
    const partial = { canConfirm: true, blockIds: ['new'], scheduledWorkMin: 60, shortfalls: [{ taskId: 't1', missingMin: 540 }], excludedBlocks: [], requiresAcknowledgement: true };
    const draft = { input: { goal: '', tasks: [], availability: fixture.state.availability, unavailable: [], preferred: 'evening' as const },
      blocks: [block], createdAt: 'draft-qa', reasons: [], assumptions: [],
      feasibility: { feasible: false, availableMin: 60, requiredMin: 600, remainingMin: -540, deficitMin: 540, shortfalls: partial.shortfalls },
      qualityEvaluation: { canConfirm: false, partialConfirmation: partial, releaseReady: false, score: 80, checks: {},
        metrics: { hardViolationCount: 0, rubricCoverage: 1, provenanceCoverage: 1, robustCapacity: false }, violations: [], missingRubricCriteria: [], limitations: [] } };
    fixture.state.planDraft = draft;
    fixture.confirm.mockResolvedValue({ ...draft, confirmation: { ...partial, mode: 'partial', acknowledgedShortfall: true } });
    render(view()); fireEvent.click(screen.getByRole('button', { name: 'Xem bản nháp' }));
    act(() => { if (!fixture.board.readOnly) fixture.board.onOpenBlock('new'); });
    fireEvent.click(screen.getByRole('button', { name: 'Xem và xác nhận phần lịch hợp lệ' }));
    expect(fixture.confirm).not.toHaveBeenCalled();
    expect(screen.getByRole('dialog', { name: 'Xác nhận phần lịch hợp lệ' })).toHaveTextContent('không giảm estimate');
    fireEvent.click(screen.getByRole('button', { name: 'Xác nhận 1 giờ đã xếp' }));
    await waitFor(() => expect(fixture.confirm).toHaveBeenCalledWith('draft-qa', ['new']));
    await waitFor(() => expect(fixture.state.plan?.confirmation?.mode).toBe('partial'));
    expect(fixture.state.plan?.feasibility?.deficitMin).toBe(540);
    expect(fixture.state.tasks[0].estimateMin).toBe(240);
  });
});
