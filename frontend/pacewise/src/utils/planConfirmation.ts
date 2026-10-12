import type { PartialPlanPreview, PlanDraft } from '../types';
import { blockTimestamp } from './calendarEditing';
import { durationMin } from './time';

/** User-facing explanations for server exclusions; never hide an unknown error. */
export function planBlockIssueLabel(code: unknown): string {
  const labels: Record<string, string> = {
    AFTER_DEADLINE: 'kết thúc sau deadline', PAST_BLOCK: 'nằm trong quá khứ',
    BLOCK_OVERLAP: 'trùng một ca tự học khác', UNAVAILABLE_OVERLAP: 'trùng lịch LMS hoặc lịch cá nhân',
    OUTSIDE_AVAILABILITY: 'nằm ngoài khung giờ học đã chọn', UNKNOWN_TASK: 'nhiệm vụ không còn tồn tại',
    TASK_COMPLETED: 'nhiệm vụ đã hoàn thành hoặc đã nộp', INVALID_BLOCK_TIME: 'ngày hoặc giờ không hợp lệ',
    INVALID_BLOCK_DURATION: 'thời lượng không hợp lệ', INVALID_BLOCK_ID: 'mã ca thiếu hoặc trùng',
    UNKNOWN_DEPENDENCY: 'không tìm thấy bước tiên quyết', DEPENDENCY_ORDER: 'sai thứ tự bước tiên quyết',
    DEPENDENCY_UNSCHEDULED: 'bước tiên quyết chưa được xếp', DEPENDENCY_INCOMPLETE: 'bước tiên quyết chưa được xếp đủ',
    DEPENDENCY_CYCLE: 'các bước phụ thuộc vòng lặp', DEPENDENCY_UNAVAILABLE: 'bước tiên quyết không hợp lệ',
  };
  return labels[String(code)] ?? `lỗi dữ liệu ca học (${String(code ?? 'unknown')})`;
}

/** Hard constraints block confirmation; P80/coverage warnings are reviewable. */
export function canConfirmPlan(draft: PlanDraft | null | undefined): boolean {
  if (!draft || !draft.feasibility.feasible) return false;
  const quality = draft.qualityEvaluation;
  return quality?.canConfirm ?? (quality?.violations.length === 0 || !quality);
}

/** Legacy previews with only capacity errors can be reviewed; the server still
 * revalidates every ID and constraint before committing anything. */
export function partialPlanPreview(draft: PlanDraft | null | undefined): PartialPlanPreview | undefined {
  if (!draft) return;
  if (draft.qualityEvaluation?.partialConfirmation) return draft.qualityEvaluation.partialConfirmation;
  const quality = draft.qualityEvaluation;
  if (!quality || quality.violations.length || quality.blockingErrors?.some(e => e.code !== 'DEADLINE_CAPACITY_SHORTFALL')) return;
  const blocks = draft.blocks.filter(b => b.status !== 'history' && b.status !== 'tentative' && blockTimestamp(b.date, b.start) >= Date.now());
  return { canConfirm: blocks.length > 0, blockIds: blocks.map(b => b.id), scheduledWorkMin: blocks.reduce((n, b) => n + (b.workMinutes ?? durationMin(b.start, b.end)), 0),
    excludedBlocks: [], shortfalls: draft.feasibility.shortfalls, requiresAcknowledgement: true };
}
