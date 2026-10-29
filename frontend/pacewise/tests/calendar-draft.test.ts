import { describe, expect, it } from 'vitest';
import { initialState, reducer } from '../src/store/AppStore';
import type { Plan, PlanDraft } from '../src/types';
const block = { id: 'b', taskId: 't', date: '2026-10-10', start: '19:00', end: '20:00' };
const plan: Plan = { id: 'p', blocks: [block], weekStart: '2026-10-05', savedAt: '2026-10-05T00:00:00Z', version: 1 };
describe('calendar draft persistence', () => {
  it('round-trips add/move/delete drafts without changing the applied schedule', () => {
    let state = { ...initialState, plan };
    const edited = [{ ...block, start: '19:15', end: '20:15' }, { ...block, id: 'new' }];
    state = reducer(state, { type: 'SAVE_CALENDAR_DRAFT', blocks: edited });
    const reloaded = reducer(initialState, { type: 'HYDRATE_WORKSPACE', state: JSON.parse(JSON.stringify({ plan: state.plan, calendarDraft: state.calendarDraft })) });
    expect(reloaded.calendarDraft?.blocks).toEqual(edited);
    expect(reloaded.calendarDraft?.needsAnalysis).toBe(true);
    expect(state.plan?.blocks).toEqual([block]);
    state = reducer(state, { type: 'SAVE_CALENDAR_DRAFT', blocks: [] });
    expect(state.calendarDraft?.blocks).toEqual([]);
    expect(state.plan).toEqual(plan);
  });
  it('a new AI proposal clears the raw draft but does not apply itself', () => {
    const editing = reducer({ ...initialState, plan }, { type: 'SAVE_CALENDAR_DRAFT', blocks: [] });
    const draft: PlanDraft = { blocks: [block], input: { goal: 'Học', tasks: [], availability: [], unavailable: [], preferred: ['morning'] },
      feasibility: { availableMin: 60, requiredMin: 60, remainingMin: 0, feasible: true, deficitMin: 0, shortfalls: [] }, reasons: [], assumptions: [], createdAt: '2026-10-10T00:00:00Z' };
    const updated = reducer(editing, { type: 'SET_DRAFT', draft });
    expect(updated.calendarDraft).toBeNull();
    expect(updated.plan).toEqual(plan);
    expect(updated.planDraft).toEqual(draft);
  });

  it('marks the future plan for re-analysis after learning or self-check evidence', () => {
    const marked = reducer({ ...initialState, plan }, { type: 'MARK_PLAN_NEEDS_ANALYSIS' });
    expect(marked.plan).toEqual(plan);
    expect(marked.calendarDraft).toMatchObject({ blocks: plan.blocks, needsAnalysis: true });
  });
});
