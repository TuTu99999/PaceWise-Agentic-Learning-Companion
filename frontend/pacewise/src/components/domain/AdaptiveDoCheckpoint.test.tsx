import '@testing-library/jest-dom/vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { adaptiveCheckpointAction, getDueAssessmentProbes, startAdaptiveCheckpoint } from '../../services/api';
import type { AssessmentItem } from '../../types';
import type { AdaptiveCheckpoint } from '../../types/adaptiveAssessment';
import { AdaptiveDoCheckpoint } from './AdaptiveDoCheckpoint';

vi.mock('../../services/api', () => ({
  adaptiveCheckpointAction: vi.fn(), getDueAssessmentProbes: vi.fn(), startAdaptiveCheckpoint: vi.fn(),
}));

const assessment: AssessmentItem = { id: 'Q-42', topic: 'Relations', question: 'Seed', rubric: ['Concept'], status: 'approved', knowledgeComponentIds: ['kc'] };
const initial: AdaptiveCheckpoint = { session_id: 'AS-1', status: 'active', stage: 'recall', mode: 'learning', kc_id: 'kc',
  hint_level: 0, hint: '', attempts: 0, reason: '', question: { id: 'Q-42', text: 'Recall question', source: 'Slide', version: 1 } };

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(startAdaptiveCheckpoint).mockResolvedValue(initial);
  vi.mocked(getDueAssessmentProbes).mockResolvedValue([]);
});

describe('Adaptive Do checkpoint', () => {
  it('marks a generated LLM follow-up as formative rather than certified understanding', async () => {
    vi.mocked(startAdaptiveCheckpoint).mockResolvedValue({ ...initial,
      question: { ...initial.question!, origin: 'llm_formative', formative_only: true } });
    render(<AdaptiveDoCheckpoint courseId="7" blockId="b1" assessment={assessment} />);
    expect(await screen.findByRole('status')).toHaveTextContent('không dùng để nâng mức hiểu');
    expect(screen.getByRole('status')).toHaveTextContent('kiểm chứng bằng câu đã duyệt');
  });

  it('does not reveal the assessment source before the learner answers', async () => {
    render(<AdaptiveDoCheckpoint courseId="7" blockId="b1" assessment={assessment} />);
    await screen.findByText('Recall question');
    expect(screen.queryByText(/Đánh giá dựa trên câu hỏi được giảng viên duyệt/)).not.toBeInTheDocument();
  });

  it('offers bounded verification without claiming teacher review or confirmed understanding', async () => {
    vi.mocked(startAdaptiveCheckpoint).mockResolvedValue({ ...initial, status: 'verification_required', verification_count: 1,
      review: { status: 'verifying', reason: 'uncertain_evidence' },
      last_result: { feedback: 'Try another question', confidence: 'low', demonstrated_level: 'conceptual', provisional: true,
        requires_instructor_review: false, evidence_ids: ['ev1'], criterion_scores: [] } });
    render(<AdaptiveDoCheckpoint courseId="7" blockId="b1" assessment={assessment} />);
    expect(await screen.findByText(/Câu kiểm chứng bổ sung 1\/2/)).toBeTruthy();
    expect(screen.getByText(/Mức tạm thời \(chưa xác nhận\)/)).toBeTruthy();
    expect(screen.queryByText(/Đang chờ giảng viên xem lại/)).toBeNull();
    await waitFor(() => expect(screen.getByLabelText('Trả lời bằng lời của bạn')).not.toBeDisabled());
  });

  it('pending human review explicitly permits learning reflection and planning', async () => {
    vi.mocked(startAdaptiveCheckpoint).mockResolvedValue({ ...initial, status: 'review_required',
      review: { status: 'pending_review', reason: 'verification_limit', case_id: 'case1' },
      last_result: { feedback: 'Pending', confidence: 'low', demonstrated_level: 'conceptual', provisional: true,
        requires_instructor_review: true, evidence_ids: ['ev1'], criterion_scores: [] } });
    render(<AdaptiveDoCheckpoint courseId="7" blockId="b1" assessment={assessment} />);
    expect(await screen.findByText(/không cần chờ duyệt/)).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Kiểm tra lại bằng câu đã duyệt' })).toBeTruthy();
  });

  it('invalid grading is not presented as student weakness', async () => {
    vi.mocked(startAdaptiveCheckpoint).mockResolvedValue({ ...initial, status: 'stopped',
      review: { status: 'abstained', reason: 'invalid_evaluation' } });
    render(<AdaptiveDoCheckpoint courseId="7" blockId="b1" assessment={assessment} />);
    expect(await screen.findByRole('status')).toHaveTextContent('không coi là bạn chưa hiểu');
  });
  it('shows next approved question and grounded diagnostic rubric', async () => {
    vi.mocked(adaptiveCheckpointAction).mockResolvedValue({ ...initial, stage: 'explain',
      question: { ...initial.question!, id: 'Q-43', text: 'Explain question' },
      last_result: { feedback: 'Accepted', confidence: 'high', demonstrated_level: 'recognition',
        requires_instructor_review: false, evidence_ids: ['ev1'],
        criterion_scores: [{ criterion_id: 'c1', score: 3, evidence_quote: 'my answer' }] } });
    render(<AdaptiveDoCheckpoint courseId="7" blockId="b1" assessment={assessment} />);
    await screen.findByText('Recall question');
    await waitFor(() => expect(screen.getByRole('button', { name: 'Nhận một gợi ý' })).not.toBeDisabled());
    fireEvent.change(screen.getByLabelText('Trả lời bằng lời của bạn'), { target: { value: 'my answer' } });
    fireEvent.click(screen.getByRole('button', { name: 'Gửi câu trả lời' }));
    expect(await screen.findByText('Explain question')).toBeTruthy();
    expect(screen.getByLabelText('Trả lời bằng lời của bạn')).toHaveValue('');
    expect(screen.getByText(/c1: mức 3\/4/)).toBeTruthy();
    expect(screen.getByText(/Đánh giá dựa trên câu hỏi được giảng viên duyệt/)).toBeVisible();
  });

  it('reuses retry key after network failure and takes hint count from server', async () => {
    vi.mocked(adaptiveCheckpointAction).mockRejectedValueOnce(new Error('Offline')).mockResolvedValueOnce({ ...initial, hint_level: 2, hint: 'H2: prerequisite' });
    render(<AdaptiveDoCheckpoint courseId="7" blockId="b1" assessment={assessment} />);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Nhận một gợi ý' })).not.toBeDisabled());
    fireEvent.click(screen.getByRole('button', { name: 'Nhận một gợi ý' }));
    await screen.findByRole('alert');
    fireEvent.click(screen.getByRole('button', { name: 'Nhận một gợi ý' }));
    await screen.findByText(/H2: prerequisite/);
    const calls = vi.mocked(adaptiveCheckpointAction).mock.calls;
    expect(calls[0][0].eventKey).toBe(calls[1][0].eventKey);
  });

  it('reports missing approved coverage and disables answer rather than fabricating a pass', async () => {
    vi.mocked(startAdaptiveCheckpoint).mockResolvedValue({ ...initial, status: 'coverage_gap', stage: 'transfer', question: null });
    render(<AdaptiveDoCheckpoint courseId="7" blockId="b1" assessment={assessment} />);
    expect(await screen.findByRole('status')).toHaveTextContent('Chưa có câu hỏi được duyệt');
    expect(screen.getByRole('button', { name: 'Gửi câu trả lời' })).toBeDisabled();
  });

  it('opens a due probe inside Do, without adding a phase', async () => {
    vi.mocked(getDueAssessmentProbes).mockResolvedValue([{ id: 'DP-1', kc_id: 'kc', due_at: '2026-10-08T10:00:00Z' }]);
    vi.mocked(startAdaptiveCheckpoint).mockResolvedValueOnce(initial).mockResolvedValueOnce({ ...initial, mode: 'retention', stage: 'application' });
    render(<AdaptiveDoCheckpoint courseId="7" blockId="b1" assessment={assessment} />);
    const button = await screen.findByRole('button', { name: 'Kiểm tra nhớ đến hạn' });
    await waitFor(() => expect(button).not.toBeDisabled());
    fireEvent.click(button);
    expect(await screen.findByText('Kiểm tra lại khả năng ghi nhớ')).toBeTruthy();
    expect(vi.mocked(startAdaptiveCheckpoint).mock.calls[1][0].probeId).toBe('DP-1');
  });

  it('uses natural learning labels and reports completion to the session page', async () => {
    const onStatusChange = vi.fn();
    vi.mocked(startAdaptiveCheckpoint).mockResolvedValue({ ...initial, status: 'completed', stage: 'transfer' });
    render(<AdaptiveDoCheckpoint courseId="7" blockId="b1" assessment={assessment} onStatusChange={onStatusChange} />);
    expect(await screen.findByText(/Bước 5\/5 · Thử tình huống khác/)).toBeVisible();
    expect(screen.getByRole('heading', { name: 'Kiểm tra mình' })).toBeVisible();
    await waitFor(() => expect(onStatusChange).toHaveBeenCalledWith(expect.objectContaining({ status: 'completed' })));
  });

  it('keeps the question, student answer, feedback and next question in one transcript', async () => {
    vi.mocked(adaptiveCheckpointAction).mockResolvedValue({ ...initial, stage: 'explain',
      question: { ...initial.question!, id: 'Q-43', text: 'Explain it in your own words' },
      last_result: { feedback: 'Đúng ý chính, hãy giải thích sâu hơn.', confidence: 'high', demonstrated_level: 'recognition',
        requires_instructor_review: false, evidence_ids: ['ev1'], criterion_scores: [] } });
    render(<AdaptiveDoCheckpoint courseId="7" blockId="b1" assessment={assessment} />);
    const input = await screen.findByLabelText('Trả lời bằng lời của bạn');
    fireEvent.change(input, { target: { value: 'My explanation' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(await screen.findByText('My explanation')).toBeVisible();
    expect(screen.getByText('Recall question')).toBeVisible();
    expect(screen.getByText('Đúng ý chính, hãy giải thích sâu hơn.')).toBeVisible();
    expect(screen.getByText('Explain it in your own words')).toBeVisible();
  });

  it('pauses only the assessment conversation and keeps its transcript', async () => {
    render(<AdaptiveDoCheckpoint courseId="7" blockId="b1" assessment={assessment} />);
    await screen.findByText('Recall question');
    fireEvent.click(screen.getByRole('button', { name: 'Dừng kiểm tra' }));
    expect(screen.getByText('Đã dừng kiểm tra tạm thời')).toBeVisible();
    expect(screen.getByText('Recall question')).toBeVisible();
    fireEvent.click(screen.getAllByRole('button', { name: 'Tiếp tục kiểm tra' })[0]);
    expect(screen.getByLabelText('Trả lời bằng lời của bạn')).toBeEnabled();
  });
});
