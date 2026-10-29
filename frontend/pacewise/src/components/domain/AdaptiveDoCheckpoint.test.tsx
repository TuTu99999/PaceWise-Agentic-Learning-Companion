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
  stage_number: 1, stage_total: 5,
  hint_level: 0, hint: '', attempts: 0, reason: '', question: { id: 'Q-42', text: 'Recall question', source: 'Slide', version: 1 } };

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(startAdaptiveCheckpoint).mockResolvedValue(initial);
  vi.mocked(getDueAssessmentProbes).mockResolvedValue([]);
});

describe('Adaptive Do checkpoint', () => {
  it('does not expose internal assessment stages or a fixed five-step ladder', async () => {
    vi.mocked(startAdaptiveCheckpoint).mockResolvedValue({ ...initial, stage: 'application', stage_number: 1, stage_total: 1,
      question: { ...initial.question!, text: 'Application question' } });
    render(<AdaptiveDoCheckpoint courseId="7" blockId="b1" assessment={assessment} />);
    expect(await screen.findByText('Câu hỏi kiểm tra mức hiểu')).toBeVisible();
    expect(screen.queryByText(/Thử áp dụng/)).toBeNull();
    expect(screen.queryByText(/Câu 1\/1/)).toBeNull();
    expect(screen.queryByText(/Câu 4\/5/)).toBeNull();
  });

  it('marks a generated LLM follow-up as formative rather than certified understanding', async () => {
    vi.mocked(startAdaptiveCheckpoint).mockResolvedValue({ ...initial,
      question: { ...initial.question!, origin: 'llm_formative', formative_only: true } });
    render(<AdaptiveDoCheckpoint courseId="7" blockId="b1" assessment={assessment} />);
    expect(await screen.findByRole('status')).toHaveTextContent('Chỉ là câu luyện tập');
    expect(screen.getByRole('status')).toHaveTextContent('câu đã duyệt');
  });

  it('does not reveal the assessment source before the learner answers', async () => {
    render(<AdaptiveDoCheckpoint courseId="7" blockId="b1" assessment={assessment} />);
    await screen.findByText('Recall question');
    expect(screen.queryByText(/Đánh giá dựa trên câu hỏi được giảng viên duyệt/)).not.toBeInTheDocument();
  });

  it('offers a concise bounded verification prompt without exposing internal grading', async () => {
    vi.mocked(startAdaptiveCheckpoint).mockResolvedValue({ ...initial, status: 'verification_required', verification_count: 1,
      review: { status: 'verifying', reason: 'uncertain_evidence' },
      last_result: { feedback: 'Try another question', confidence: 'low', demonstrated_level: 'conceptual', provisional: true,
        requires_instructor_review: false, evidence_ids: ['ev1'], criterion_scores: [] } });
    render(<AdaptiveDoCheckpoint courseId="7" blockId="b1" assessment={assessment} />);
    expect(await screen.findByText(/chưa khớp đủ các ý cần kiểm tra/)).toBeTruthy();
    expect(screen.queryByText(/Mức tạm thời/)).toBeNull();
    expect(screen.queryByText(/giảng viên xem lại/)).toBeNull();
    expect(screen.queryByText(/Try another question/)).toBeNull();
    await waitFor(() => expect(screen.getByLabelText('Trả lời bằng lời của bạn')).not.toBeDisabled());
  });

  it('explains that a correct hinted answer needs an unhinted confirmation', async () => {
    vi.mocked(startAdaptiveCheckpoint).mockResolvedValue({ ...initial, status: 'verification_required',
      reason: 'need_unseen_item_without_hint', hint_level: 1,
      last_result: { feedback: 'Accepted', status: 'đã thể hiện được', confidence: 'high',
        demonstrated_level: 'conceptual', provisional: false, requires_instructor_review: false,
        evidence_ids: ['ev1'], criterion_scores: [] } });
    render(<AdaptiveDoCheckpoint courseId="7" blockId="b1" assessment={assessment} />);
    expect(await screen.findByText(/Câu trả lời đã đạt các ý cần thiết/)).toBeVisible();
    expect(screen.getByText(/đã dùng gợi ý/)).toBeVisible();
    expect(screen.queryByText(/Chưa đủ tín hiệu/)).toBeNull();
  });

  it('keeps a legacy review state out of the instructor-facing student copy', async () => {
    vi.mocked(startAdaptiveCheckpoint).mockResolvedValue({ ...initial, status: 'review_required',
      review: { status: 'pending_review', reason: 'verification_limit', case_id: 'case1' },
      last_result: { feedback: 'Pending', confidence: 'low', demonstrated_level: 'conceptual', provisional: true,
        requires_instructor_review: true, evidence_ids: ['ev1'], criterion_scores: [] } });
    render(<AdaptiveDoCheckpoint courseId="7" blockId="b1" assessment={assessment} />);
    expect(await screen.findByText(/tín hiệu chưa xác định/)).toBeTruthy();
    expect(screen.queryByText(/giảng viên xem lại/)).toBeNull();
    expect(screen.getByRole('button', { name: 'Thử câu đã duyệt khác' })).toBeTruthy();
  });

  it('invalid grading is represented as an unknown planning signal', async () => {
    vi.mocked(startAdaptiveCheckpoint).mockResolvedValue({ ...initial, status: 'stopped',
      review: { status: 'abstained', reason: 'invalid_evaluation' } });
    render(<AdaptiveDoCheckpoint courseId="7" blockId="b1" assessment={assessment} />);
    expect(await screen.findByText(/tín hiệu chưa xác định/)).toBeVisible();
  });
  it('shows the next approved question without exposing diagnostic rubric internals', async () => {
    vi.mocked(adaptiveCheckpointAction).mockResolvedValue({ ...initial, stage: 'explain',
      question: { ...initial.question!, id: 'Q-43', text: 'Explain question' },
      last_result: { feedback: 'Accepted', confidence: 'high', demonstrated_level: 'recognition',
        requires_instructor_review: false, evidence_ids: ['ev1'],
        criterion_scores: [{ criterion_id: 'c1', criterion_text: 'Lập luận đúng', score: 3, evidence_quote: 'my answer' }] } });
    render(<AdaptiveDoCheckpoint courseId="7" blockId="b1" assessment={assessment} />);
    await screen.findByText('Recall question');
    await waitFor(() => expect(screen.getByRole('button', { name: 'Nhận gợi ý' })).not.toBeDisabled());
    fireEvent.change(screen.getByLabelText('Trả lời bằng lời của bạn'), { target: { value: 'my answer' } });
    fireEvent.click(screen.getByRole('button', { name: 'Gửi câu trả lời' }));
    expect(await screen.findByText('Explain question')).toBeTruthy();
    expect(screen.getByLabelText('Trả lời bằng lời của bạn')).toHaveValue('');
    expect(screen.getByText('Đã ghi nhận câu trả lời. Tiếp tục với câu tiếp theo.')).toBeVisible();
    expect(screen.queryByText('Lập luận đúng')).toBeNull();
    expect(screen.queryByText('Đạt tiêu chí')).toBeNull();
    expect(screen.queryByText('Đánh giá mức hiểu dựa trên bằng chứng')).toBeNull();
    expect(vi.mocked(adaptiveCheckpointAction).mock.calls[0][0].locale).toBe('vi');
  });

  it('reuses retry key after network failure and takes hint count from server', async () => {
    vi.mocked(adaptiveCheckpointAction).mockRejectedValueOnce(new Error('Offline')).mockResolvedValueOnce({ ...initial, hint_level: 2, hint: 'H2: prerequisite' });
    render(<AdaptiveDoCheckpoint courseId="7" blockId="b1" assessment={assessment} />);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Nhận gợi ý' })).not.toBeDisabled());
    fireEvent.click(screen.getByRole('button', { name: 'Nhận gợi ý' }));
    await screen.findByRole('alert');
    fireEvent.click(screen.getByRole('button', { name: 'Nhận gợi ý' }));
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
    const button = await screen.findByRole('button', { name: 'Kiểm tra ghi nhớ đến hạn' });
    await waitFor(() => expect(button).not.toBeDisabled());
    fireEvent.click(button);
    expect(await screen.findByText('Kiểm tra ghi nhớ')).toBeTruthy();
    expect(vi.mocked(startAdaptiveCheckpoint).mock.calls[1][0].probeId).toBe('DP-1');
  });

  it('uses natural learning labels and reports completion to the session page', async () => {
    const onStatusChange = vi.fn();
    vi.mocked(startAdaptiveCheckpoint).mockResolvedValue({ ...initial, status: 'completed', stage: 'transfer' });
    render(<AdaptiveDoCheckpoint courseId="7" blockId="b1" assessment={assessment} onStatusChange={onStatusChange} />);
    expect(await screen.findByText(/Đã ghi nhận cho Plan/)).toBeVisible();
    expect(screen.getByRole('heading', { name: 'Kiểm tra mình' })).toBeVisible();
    await waitFor(() => expect(onStatusChange).toHaveBeenCalledWith(expect.objectContaining({ status: 'completed' })));
  });

  it('keeps the question, student answer, concise planning notice and next question in one transcript', async () => {
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
    expect(screen.getByText('Đã ghi nhận câu trả lời. Tiếp tục với câu tiếp theo.')).toBeVisible();
    expect(screen.queryByText('Đúng ý chính, hãy giải thích sâu hơn.')).toBeNull();
    expect(screen.getByText('Explain it in your own words')).toBeVisible();
  });

  it('does not imply success when the answer needs support', async () => {
    vi.mocked(adaptiveCheckpointAction).mockResolvedValue({ ...initial, status: 'needs_support',
      reason: 'checkpoint_not_passed',
      last_result: { feedback: 'Developing', status: 'đang hình thành', confidence: 'high',
        demonstrated_level: 'no_evidence', requires_instructor_review: false, evidence_ids: ['ev1'],
        criterion_scores: [] } });
    render(<AdaptiveDoCheckpoint courseId="7" blockId="b1" assessment={assessment} />);
    const input = await screen.findByLabelText('Trả lời bằng lời của bạn');
    fireEvent.change(input, { target: { value: 'An answer about another question' } });
    fireEvent.click(screen.getByRole('button', { name: 'Gửi câu trả lời' }));
    expect(await screen.findByText(/chưa đáp ứng đủ ý của câu hỏi này/)).toBeVisible();
    expect(screen.queryByText('Đã ghi nhận cho Plan.')).toBeNull();
  });

  it('pauses only the assessment conversation and keeps its transcript', async () => {
    render(<AdaptiveDoCheckpoint courseId="7" blockId="b1" assessment={assessment} />);
    await screen.findByText('Recall question');
    fireEvent.click(screen.getByRole('button', { name: 'Tạm dừng' }));
    expect(screen.getByText('Đã tạm dừng')).toBeVisible();
    expect(screen.getByText('Recall question')).toBeVisible();
    fireEvent.click(screen.getAllByRole('button', { name: 'Tiếp tục' })[0]);
    expect(screen.getByLabelText('Trả lời bằng lời của bạn')).toBeEnabled();
  });
});
