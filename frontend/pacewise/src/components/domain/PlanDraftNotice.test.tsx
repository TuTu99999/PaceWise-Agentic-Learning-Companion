import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { PlanDraft, Task } from '../../types';
import { draftIssues, PlanDraftNotice } from './PlanDraftNotice';

const task: Task = { id: '1:a', courseId: '1', title: 'Quan hệ thứ tự', objective: 'Vận dụng',
  deadline: '2026-10-08', dueAt: '2026-10-08T12:00:00+07:00', estimateMin: 30, loggedMin: 0, status: 'todo', priority: 'high' };
const draft: PlanDraft = { input: { goal: 'test', tasks: [], availability: [], unavailable: [], preferred: 'evening' },
  createdAt: '', blocks: [], reasons: [], assumptions: [], feasibility: { availableMin: 30, requiredMin: 45,
    remainingMin: -15, feasible: false, deficitMin: 15, shortfalls: [{ taskId: '1:a', missingMin: 15 }] },
  durationAdjustments: [{ taskId: '1:a', studentRemainingMin: 30, baselineTargetMin: 30, proposedTargetMin: 45,
    reason: 'history', requiresConfirmation: true, sourceRefs: ['do:s1', 'do:s2', 'do:s3'], evidenceCount: 3 }],
};
beforeEach(() => { vi.useFakeTimers({ toFake: ['Date'] }); vi.setSystemTime(new Date('2026-10-05T08:00:00+07:00')); });
afterEach(() => vi.useRealTimers());
describe('truthful compact draft notices', () => {
  it('shows confirmed weekly goals, decomposed steps, deliverables and source types', () => {
    render(<PlanDraftNotice draft={{
      ...draft,
      weeklyGoals: [{ id: 'g1', title: 'Hoàn thành bản nháp', taskIds: [task.id], confirmed: true,
        rationale: 'Bài gần deadline và có rubric.', sourceRefs: ['assignment:1:a', 'rubric:r1'], analysisSource: 'model' }],
      milestones: [{ milestoneId: 'm1', taskId: task.id, title: 'Đối chiếu yêu cầu', deliverable: 'Checklist rubric',
        estimatedMin: 30, targetMin: 30, dependsOn: [], sourceRefs: ['assignment:1:a', 'rubric:r1'],
        decompositionSource: 'rubric_evidence', difficulty: 'vừa', deadline: task.deadline }],
      decompositionAnalysis: { modelOutput: { valid: true, fallbackApplied: false, source: 'model' } },
    }} tasks={[task]} />);
    expect(screen.getByRole('group', { name: 'Phân tích mục tiêu và nhiệm vụ' })).toHaveTextContent('Hoàn thành bản nháp');
    expect(screen.getByRole('group', { name: 'Phân tích mục tiêu và nhiệm vụ' })).toHaveTextContent('Checklist rubric');
    expect(screen.getByRole('group', { name: 'Phân tích mục tiêu và nhiệm vụ' })).toHaveTextContent('Assignment · Rubric');
    expect(screen.getByRole('group', { name: 'Phân tích mục tiêu và nhiệm vụ' })).toHaveTextContent('Theo rubric');
  });
  it('names the actual shortage and hour-specific deadline instead of all error categories', () => {
    render(<PlanDraftNotice draft={draft} tasks={[task]} />);
    expect(screen.getByRole('alert')).toHaveTextContent('Quan hệ thứ tự còn thiếu 15 phút trước hạn');
    expect(screen.getByRole('alert')).toHaveTextContent('12:00');
    expect(screen.getByRole('alert')).not.toHaveTextContent('dependency');
  });
  it('collapses duration proposals and shows provenance on demand', () => {
    render(<PlanDraftNotice draft={draft} tasks={[task]} />);
    const summary = screen.getByText('Có 1 đề xuất thời lượng — Xem chi tiết');
    const details = summary.closest('details')!;
    expect(details.open).toBe(false);
    fireEvent.click(summary);
    expect(screen.getByText(/Nguồn: do:s1, do:s2, do:s3/)).toBeInTheDocument();
    expect(screen.getByText(/không phải độ dài phiên tối ưu/)).toBeInTheDocument();
  });
  it('explains when observed Do progress materially changes the replan workload', () => {
    render(<PlanDraftNotice draft={{
      ...draft,
      feasibility: {
        ...draft.feasibility,
        deadlineRisks: [{
          deadline: '2026-10-08', deadlineMinute: 720, taskIds: [task.id], availableMin: 120,
          requiredP50Min: 135, requiredP80Min: 180, slackP50Min: -15, slackP80Min: -60,
          risk: 'p50_shortage',
        }],
      },
      replanAdjustments: [{
        taskId: task.id, baselineRemainingMin: 30, reconciledRemainingMin: 60, addedMin: 30,
        reason: 'observed_unfinished_work', sourceRef: 'do:block-1',
      }],
    }} tasks={[task]} />);

    expect(screen.getByText('Bản lịch mới đã dùng tiến độ Do và Reflect')).toBeInTheDocument();
    expect(screen.getByText(/còn cần thêm 30 phút/)).toBeInTheDocument();
    expect(screen.getByText(/slack P50 -15 phút, slack P80 -60 phút/)).toBeInTheDocument();
  });
  it('identifies the specific prerequisite milestone', () => {
    const issue = draftIssues({ ...draft, feasibility: { ...draft.feasibility, feasible: true, shortfalls: [] },
      milestones: [{ milestoneId: 'm2', taskId: '1:a', title: 'Vận dụng', deliverable: '', estimatedMin: 30, targetMin: 30,
        dependsOn: ['m1'], deadline: task.deadline }],
      qualityEvaluation: { releaseReady: false, score: 80, checks: {}, metrics: { hardViolationCount: 1, rubricCoverage: 1, provenanceCoverage: 1, robustCapacity: true }, violations: [], missingRubricCriteria: [], limitations: [],
        blockingErrors: [{ code: 'UNKNOWN_DEPENDENCY', milestoneId: 'm2' }] } }, [task]);
    expect(issue.join()).toContain('bước “Vận dụng”');
    expect(issue.join()).not.toContain('còn thiếu');
  });
  it('does not tell a learner to add availability before an expired deadline', () => {
    render(<PlanDraftNotice draft={draft} tasks={[task]} now={Date.parse('2026-10-10T11:00:00+07:00')} />);
    expect(screen.getByRole('alert')).toHaveTextContent('Bản nháp cũ còn chứa nhiệm vụ đã quá hạn');
    expect(screen.getByRole('alert')).toHaveTextContent('AI phân tích lại');
    expect(screen.queryByText(/còn thiếu 15 phút/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Thêm thời gian rảnh trước hạn/)).not.toBeInTheDocument();
  });
  it('keeps unresolved overdue work separate from future-capacity errors', () => {
    render(<PlanDraftNotice draft={{ ...draft, durationAdjustments: [], feasibility: { ...draft.feasibility, feasible: true, shortfalls: [] },
      expiredTasks: [{ taskId: task.id, title: task.title, deadline: task.dueAt!, status: 'overdue_unresolved' }] }} tasks={[task]} now={Date.parse('2026-10-10T11:00:00+07:00')} />);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.getByText(/không tính vào capacity tương lai/)).toBeInTheDocument();
    expect(screen.getByText(/Chưa coi là hoàn thành/)).toBeInTheDocument();
  });
});
