import { describe, expect, it } from 'vitest';
import type { PlanDraft } from '../types';
import { canConfirmPlan, planBlockIssueLabel } from './planConfirmation';

const draft = (feasible: boolean, quality?: Partial<NonNullable<PlanDraft['qualityEvaluation']>>) => ({
  feasibility: { feasible },
  qualityEvaluation: quality ? { violations: [], ...quality } : undefined,
}) as PlanDraft;

describe('plan confirmation gates', () => {
  it('requires a draft', () => expect(canConfirmPlan(null)).toBe(false));
  it('blocks capacity shortfall', () => expect(canConfirmPlan(draft(false, { canConfirm: true }))).toBe(false));
  it('blocks hard errors even with enough capacity', () => expect(canConfirmPlan(draft(true, { canConfirm: false }))).toBe(false));
  it('allows P80 warnings for explicit student review', () => expect(canConfirmPlan(draft(true, { canConfirm: true, releaseReady: false }))).toBe(true));
  it('blocks legacy drafts containing violations', () => expect(canConfirmPlan(draft(true, { violations: [{ code: 'AFTER_DEADLINE' }] }))).toBe(false));
  it('retains compatible capacity-only legacy drafts', () => expect(canConfirmPlan(draft(true))).toBe(true));
  it('explains excluded blocks without exposing only internal reason codes', () => {
    expect(planBlockIssueLabel('AFTER_DEADLINE')).toBe('kết thúc sau deadline');
    expect(planBlockIssueLabel('DEPENDENCY_INCOMPLETE')).toContain('tiên quyết chưa được xếp đủ');
    expect(planBlockIssueLabel('OUTSIDE_AVAILABILITY')).toContain('khung giờ học đã chọn');
    expect(planBlockIssueLabel('NEW_ERROR')).toContain('NEW_ERROR');
  });
});
