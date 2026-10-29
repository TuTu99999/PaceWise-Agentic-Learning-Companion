import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { StudySessionPage } from './StudySessionPage';

const mocks = vi.hoisted(() => ({ state: {} as Record<string, unknown>, timer: {} as Record<string, unknown>,
  preparation: null as unknown, task: undefined as Record<string, unknown> | undefined, start: vi.fn(),
  dispatch: vi.fn(), timerArgs: [] as unknown[] }));
vi.mock('../../store/AppStore', () => ({ useAppStore: () => ({ state: mocks.state, dispatch: mocks.dispatch }) }));
vi.mock('../../hooks/useDerived', () => ({ useDerived: () => ({ taskById: mocks.task ? new Map([['1:7', mocks.task]]) : new Map(),
  courseOf: () => ({ id: '1', code: 'CS101', name: 'Programming' }) }) }));
vi.mock('../../hooks/useDurableStudyTimer', () => ({ useDurableStudyTimer: (...args: unknown[]) => {
  mocks.timerArgs = args;
  return mocks.timer;
} }));
vi.mock('../../hooks/useDoPreparation', () => ({ materialRevision: () => 'version-1',
  useDoPreparation: () => ({ preparation: mocks.preparation, loading: false, error: '', retry: vi.fn() }) }));
vi.mock('../../components/domain/DoSessionSupport', () => ({
  DoSessionSupport: () => <section data-testid="session-materials">Tài liệu phiên học</section>,
}));
vi.mock('../../components/domain/DoSessionAssistant', () => ({
  DoSessionAssistant: ({ assessment, mode, onModeChange, onAssessmentStatusChange }: { assessment?: { question: string }; mode?: 'learn' | 'assess'; onModeChange?: (mode: 'learn' | 'assess') => void; onAssessmentStatusChange?: (checkpoint: { last_result?: object }) => void }) => (
    <section data-testid="session-assistant">
      <h2>Trợ lý trong phiên</h2>
      <button onClick={() => onModeChange?.('learn')}>Hỏi để học</button><button onClick={() => onModeChange?.('assess')}>Kiểm tra mình</button>
      <span data-testid="assistant-mode">{mode}</span>
      {assessment ? `Assessment panel: ${assessment.question}` : 'Chatbot kiểm tra chưa thể bắt đầu'}
      {assessment && <button onClick={() => onAssessmentStatusChange?.({ last_result: {} })}>Ghi assessment signal</button>}
    </section>
  ),
}));
vi.mock('../../components/ui/Toast', () => ({ useToast: () => vi.fn() }));
vi.mock('../../utils/routine', () => ({ routineSleepSlots: () => [] }));
vi.mock('../../utils/lmsPlanning', () => ({ lmsUnavailableSlots: () => [], mergeUnavailable: () => [] }));

beforeEach(() => {
  sessionStorage.clear();
  mocks.task = { id: '1:7', courseId: '1', title: 'Assignment', objective: 'Whole assignment description. Estimate 144 minutes.',
    deadline: '2099-10-11', estimateMin: 144, estimateIsAssumption: true, loggedMin: 0, status: 'todo' };
  mocks.state = { user: { id: 'u1' }, workspaceReady: true, courseSourceStatus: 'ready', courseData: {}, unavailable: [], assessments: [],
    activeSession: null, tasks: [mocks.task], plan: { blocks: [{ id: 'b1', taskId: '1:7', status: 'confirmed',
      date: '2099-10-10', start: '16:00', end: '16:30', milestoneTitle: 'Read rubric',
      rhythm: { sessionMinutes: 90, breakMinutes: 10 } }] } };
  mocks.timer = { session: null, elapsed: 0, busy: false, error: '', start: mocks.start };
  mocks.preparation = { objective: 'Read rubric', scope: { module_names: ['Chapter 3'] } };
  vi.clearAllMocks();
  mocks.timerArgs = [];
});

function setup() {
  return render(<MemoryRouter initialEntries={['/study/1:7/session?blockId=b1']}><Routes>
    <Route path="/study/:taskId/session" element={<StudySessionPage />} />
  </Routes></MemoryRouter>);
}

describe('focused Do session UI', () => {
  it('waits for the first course sync on a direct reload instead of claiming the task is missing', () => {
    mocks.task = undefined;
    mocks.state.workspaceReady = false;
    mocks.state.courseSourceStatus = 'loading';
    setup();
    expect(screen.getByRole('heading', { name: 'Đang khôi phục phiên Do' })).toBeVisible();
    expect(screen.queryByRole('heading', { name: 'Không tìm thấy nhiệm vụ' })).not.toBeInTheDocument();
  });

  it('shows a recoverable source error rather than a false missing-task message', () => {
    mocks.task = undefined;
    mocks.state.courseSourceStatus = 'error';
    setup();
    expect(screen.getByRole('heading', { name: 'Chưa tải được dữ liệu phiên Do' })).toBeVisible();
    expect(screen.queryByRole('heading', { name: 'Không tìm thấy nhiệm vụ' })).not.toBeInTheDocument();
  });

  it('reconciles a removed requested block so its stale timer cannot block the next Do session', () => {
    (mocks.state.plan as { blocks: unknown[] }).blocks = [];
    setup();
    expect(screen.getByRole('heading', { name: 'Ca tự học không còn hiệu lực' })).toBeVisible();
    expect(screen.getByText(/Ca cũ đã được tự hủy/)).toBeVisible();
    expect(mocks.timerArgs[1]).toBe('b1');
  });

  it('uses the confirmed milestone and separates session duration from whole-task estimates', () => {
    setup();
    expect(screen.getByText('Read rubric')).toBeVisible();
    expect(screen.getByText('30 phút')).toBeVisible();
    expect(screen.queryByText('Whole assignment description. Estimate 144 minutes.')).not.toBeInTheDocument();
    expect(screen.queryByText(/Ước lượng nền dựa trên điểm tối đa/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Nhịp đã xác nhận/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Hoạt động: Chưa xác định/)).not.toBeInTheDocument();
    expect(screen.queryByText('ⓘ Cách ghi nhận thời gian')).not.toBeInTheDocument();
    expect(screen.queryByText('Chi tiết nhiệm vụ')).not.toBeInTheDocument();
    expect(screen.queryByText('Thông tin phiên')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Bắt đầu học' }));
    expect(mocks.start).toHaveBeenCalledOnce();
  });

  it('does not invent a session objective if no milestone is available', () => {
    (mocks.state.plan as { blocks: Array<{ milestoneTitle?: string }> }).blocks[0].milestoneTitle = undefined;
    mocks.preparation = null;
    setup();
    expect(screen.getByText('Ca tự học cho nhiệm vụ này')).toBeVisible();
    expect(screen.queryByText('Whole assignment description. Estimate 144 minutes.')).not.toBeInTheDocument();
  });

  it('labels ending a session without claiming the whole assignment or understanding is complete', () => {
    mocks.timer = { ...mocks.timer, session: { status: 'running', interruption_reason: 'none', unobserved_gap: true }, elapsed: 180000 };
    setup();
    expect(screen.getByRole('button', { name: 'Kết thúc phiên' })).toBeEnabled();
    expect(screen.queryByRole('button', { name: /^Hoàn thành$/ })).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Ghi chú cho phiên này')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Nguyên nhân gián đoạn')).not.toBeInTheDocument();
    expect(screen.queryByText(/Có khoảng chưa quan sát/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Bận đột xuất không làm giảm mức hiểu/)).not.toBeInTheDocument();
  });

  it('records concrete follow-up minutes instead of asking the learner for a completion percentage', async () => {
    const act = vi.fn(async (action: string) => action === 'complete'
      ? {
          status: 'completed',
          evaluation: {
            actual_minutes: 3,
            status: 'needs_more_time',
            remaining_minutes: 30,
            work_result: 'needs_more_time',
            needs_recovery: true,
            next_action: 'Mở Recover',
          },
        }
      : { status: 'paused' });
    mocks.timer = {
      ...mocks.timer,
      session: { status: 'running', interruption_reason: 'none', unobserved_gap: false },
      elapsed: 180000,
      act,
    };
    setup();

    fireEvent.click(screen.getByRole('button', { name: 'Kết thúc phiên' }));
    expect(await screen.findByRole('heading', { name: 'Kết thúc phiên học' })).toBeVisible();
    expect(screen.queryByText('25%')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Chưa xong, cần học tiếp/ }));
    fireEvent.change(screen.getByLabelText('Cần thêm khoảng bao nhiêu phút?'), { target: { value: '30' } });
    fireEvent.click(screen.getByRole('button', { name: 'Kết thúc và phản tư' }));

    await waitFor(() => expect(act).toHaveBeenCalledWith('complete', expect.objectContaining({
      workResult: 'needs_more_time',
      additionalMinutes: 30,
    })));
    expect(act).not.toHaveBeenCalledWith('complete', expect.objectContaining({ completionPercent: expect.anything() }));
  });

  it('shows one assessment chatbot automatically after the timed session starts', () => {
    mocks.state.assessments = [{
      id: 'assessment-1', assessmentSetId: 'set-1', sourceResourceId: 11, sourceChapter: 'Chapter 3',
      topic: 'Assignment', question: 'Giải thích nội dung assignment', rubric: ['Đúng'], status: 'approved',
    }];
    const view = setup();
    expect(screen.queryByText(/Assessment panel: Giải thích/)).not.toBeInTheDocument();
    mocks.timer = { ...mocks.timer, session: { status: 'running', interruption_reason: 'none' }, elapsed: 60000 };
    view.rerender(<MemoryRouter initialEntries={['/study/1:7/session?blockId=b1']}><Routes>
      <Route path="/study/:taskId/session" element={<StudySessionPage />} />
    </Routes></MemoryRouter>);
    expect(screen.getByText('Assessment panel: Giải thích nội dung assignment')).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: 'Ghi assessment signal' }));
    expect(mocks.dispatch).toHaveBeenCalledWith({ type: 'MARK_PLAN_NEEDS_ANALYSIS' });
    expect(screen.queryByText('Kiểm tra nhanh mức hiểu')).not.toBeInTheDocument();
  });

  it('offers the chapter self-check in every Do block of the same assignment', () => {
    mocks.state.assessments = [{
      id: 'assessment-chapter-3', assessmentSetId: 'set-chapter-3', sourceResourceId: 11,
      courseId: '1', topic: 'Unrelated wording', question: 'Explain the key idea',
      sourceChapter: 'Chương 3: Cấu trúc dữ liệu', rubric: ['Ý chính'], status: 'approved',
    }];
    mocks.state.plan = { blocks: [
      { id: 'b1', taskId: '1:7', status: 'confirmed', date: '2099-10-10', start: '16:00', end: '16:30', milestoneTitle: 'Part 1' },
      { id: 'b2', taskId: '1:7', status: 'confirmed', date: '2099-10-10', start: '17:00', end: '17:30', milestoneTitle: 'Part 2' },
    ] };
    mocks.preparation = { objective: 'Different objective', scope: {
      module_ids: ['module-3'], module_names: ['Chapter 3'], assignment_id: '7', status: 'mapped',
    } };
    mocks.timer = { ...mocks.timer, session: { status: 'running', interruption_reason: 'none' }, elapsed: 60000 };

    const first = setup();
    expect(screen.getByText('Assessment panel: Explain the key idea')).toBeVisible();
    first.unmount();
    render(<MemoryRouter initialEntries={['/study/1:7/session?blockId=b2']}><Routes>
      <Route path="/study/:taskId/session" element={<StudySessionPage />} />
    </Routes></MemoryRouter>);
    expect(screen.getByText('Assessment panel: Explain the key idea')).toBeVisible();
  });

  it('does not attach a chapter question to an assignment mapped to another chapter', () => {
    mocks.state.assessments = [{
      id: 'assessment-chapter-2', assessmentSetId: 'set-chapter-2', sourceResourceId: 11,
      courseId: '1', topic: 'Assignment', question: 'Explain the key idea',
      sourceChapter: 'Chương 2: Tìm kiếm', rubric: ['Ý chính'], status: 'approved',
    }];
    mocks.preparation = { objective: 'Assignment', scope: {
      module_ids: ['module-3'], module_names: ['Chapter 3'], assignment_id: '7', status: 'mapped',
    } };
    mocks.timer = { ...mocks.timer, session: { status: 'running', interruption_reason: 'none' }, elapsed: 60000 };
    setup();
    expect(screen.getByText('Chatbot kiểm tra chưa thể bắt đầu')).toBeVisible();
  });

  it('keeps the assistant directly below suggested materials in the same sidebar', () => {
    mocks.timer = { ...mocks.timer, session: { status: 'running', interruption_reason: 'none' }, elapsed: 60000 };
    setup();
    const sidebar = screen.getByTestId('do-session-sidebar');
    const scoped = within(sidebar);
    const materials = scoped.getByTestId('session-materials');
    const assistant = scoped.getByTestId('session-assistant');
    expect(materials.compareDocumentPosition(assistant) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('restores the selected assistant tab after leaving and reopening the same Do block', async () => {
    mocks.timer = { ...mocks.timer, session: { status: 'running', interruption_reason: 'none' }, elapsed: 60000 };
    const first = setup();
    fireEvent.click(screen.getByRole('button', { name: 'Kiểm tra mình' }));
    expect(screen.getByTestId('assistant-mode')).toHaveTextContent('assess');
    first.unmount();
    setup();
    await waitFor(() => expect(screen.getByTestId('assistant-mode')).toHaveTextContent('assess'));
  });

  it('shows a clear empty assessment state without restoring the support chatbot', () => {
    mocks.timer = { ...mocks.timer, session: { status: 'paused', interruption_reason: 'none' }, elapsed: 60000 };
    setup();
    expect(screen.getByRole('heading', { name: 'Trợ lý trong phiên' })).toBeVisible();
    expect(screen.getByRole('button', { name: 'Hỏi để học' })).toBeVisible();
    expect(screen.getByRole('button', { name: 'Kiểm tra mình' })).toBeVisible();
    expect(screen.getByText('Chatbot kiểm tra chưa thể bắt đầu')).toBeVisible();
  });

  it('never borrows an approved assessment from another course', () => {
    mocks.state.assessments = [{
      id: 'assessment-2', assessmentSetId: 'set-2', sourceResourceId: 11, sourceChapter: 'Chapter 3',
      courseId: '2', topic: 'Assignment', question: 'Giải thích nội dung assignment',
      rubric: ['Đúng'], status: 'approved',
    }];
    mocks.timer = { ...mocks.timer, session: { status: 'running', interruption_reason: 'none' }, elapsed: 60000 };
    setup();
    expect(screen.getByText('Chatbot kiểm tra chưa thể bắt đầu')).toBeVisible();
    expect(screen.queryByText(/Assessment panel/)).not.toBeInTheDocument();
  });

  it('does not expose legacy questions that have no approved chapter question set', () => {
    mocks.state.assessments = [{
      id: 'Q-63', courseId: '1', topic: 'Assignment', question: 'Legacy database-model question',
      rubric: ['Đúng'], status: 'approved',
    }];
    mocks.timer = { ...mocks.timer, session: { status: 'running', interruption_reason: 'none' }, elapsed: 60000 };
    setup();
    expect(screen.getByText('Chatbot kiểm tra chưa thể bắt đầu')).toBeVisible();
    expect(screen.queryByText(/Legacy database-model question/)).not.toBeInTheDocument();
  });

  it('shows save errors immediately even while operational explanations are collapsed', () => {
    mocks.timer = { ...mocks.timer, error: 'Checkpoint not saved', retry: vi.fn() };
    setup();
    expect(screen.getByRole('alert')).toHaveTextContent('Checkpoint not saved');
    expect(screen.getByRole('button', { name: 'Thử lưu lại checkpoint' })).toBeVisible();
  });
});
