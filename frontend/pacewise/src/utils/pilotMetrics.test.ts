import { describe, expect, it } from 'vitest';
import type { Task } from '../types';
import { addDays, DEMO_TODAY } from './time';
import { adaptiveEstimate, calculatePilotMetrics, updateEstimateProfiles } from './pilotMetrics';

const task = (patch: Partial<Task> = {}): Task => ({
  id: 't1', title: 'Assignment', courseId: 'c1', deadline: '2099-01-01', estimateMin: 60,
  loggedMin: 0, status: 'todo', priority: 'medium', objective: '', estimateIsAssumption: true, ...patch,
});

describe('pilot metrics and adaptive estimates', () => {
  it('learns a bounded course multiplier when a task is completed', () => {
    const profiles = updateEstimateProfiles({}, [task({ loggedMin: 120, status: 'in_progress' })], [task({ loggedMin: 120, status: 'done' })]);
    expect(profiles.c1).toMatchObject({ sampleCount: 1, multiplier: 2 });
    expect(adaptiveEstimate(task(), profiles)).toBe(120);
  });

  it('does not override an estimate confirmed by the student', () => {
    expect(adaptiveEstimate(task({ estimateIsAssumption: false }), { c1: { courseId: 'c1', sampleCount: 2, multiplier: 2, updatedAt: '' } })).toBe(60);
  });

  it('reports plan coverage and on-time submission rate', () => {
    const metrics = calculatePilotMetrics([
      task({ id: 'a', deadline: addDays(DEMO_TODAY, 2), submission: { state: 'graded', attempts: 1, late: false, score: 8, feedback: '', rubricAssessment: {} } }),
      task({ id: 'b', deadline: addDays(DEMO_TODAY, 3), submission: { state: 'graded', attempts: 1, late: true, score: 7, feedback: '', rubricAssessment: {} } }),
    ], { id: 'p', weekStart: '', savedAt: '', version: 1, blocks: [{ id: 'x', taskId: 'a', date: addDays(DEMO_TODAY, 1), start: '18:00', end: '19:00' }] }, [], 1);
    expect(metrics.planCoverageRate).toBe(0.5);
    expect(metrics.onTimeSubmissionRate).toBe(0.5);
    expect(metrics.recoveryCount).toBe(1);
  });

  it('counts submitted but not yet graded assignments in the on-time metric', () => {
    const metrics = calculatePilotMetrics([
      task({ submission: { state: 'submitted', submittedAt: '2026-10-02T08:00:00Z', attempts: 1, late: false, score: null, feedback: '', rubricAssessment: {} } }),
    ], null, [], 0);

    expect(metrics.gradedSubmissionCount).toBe(0);
    expect(metrics.submittedAssignmentCount).toBe(1);
    expect(metrics.onTimeSubmissionRate).toBe(1);
  });

  it('measures plan coverage only for the 14-day deadline horizon', () => {
    const metrics = calculatePilotMetrics([
      task({ id: 'near', deadline: addDays(DEMO_TODAY, 5) }),
      task({ id: 'far', deadline: addDays(DEMO_TODAY, 40) }),
    ], {
      id: 'p', weekStart: DEMO_TODAY, savedAt: '', version: 1,
      blocks: [{ id: 'x', taskId: 'near', date: addDays(DEMO_TODAY, 1), start: '18:00', end: '19:00' }],
    }, [], 0);

    expect(metrics.openDeadlineCount).toBe(1);
    expect(metrics.planCoverageRate).toBe(1);
  });

  it('excludes planned assignments outside the 14-day horizon from risk metrics', () => {
    const metrics = calculatePilotMetrics([
      task({ id: 'near', deadline: addDays(DEMO_TODAY, 5), estimateMin: 120 }),
      task({ id: 'far', deadline: addDays(DEMO_TODAY, 40), estimateMin: 120 }),
    ], {
      id: 'p', weekStart: DEMO_TODAY, savedAt: '', version: 1,
      blocks: [
        { id: 'near-block', taskId: 'near', date: addDays(DEMO_TODAY, 1), start: '18:00', end: '19:00' },
        { id: 'far-block', taskId: 'far', date: addDays(DEMO_TODAY, 2), start: '18:00', end: '19:00' },
      ],
    }, [], 0);

    expect(metrics.openDeadlineCount).toBe(1);
    expect(metrics.atRiskDeadlineCount).toBe(1);
  });
});
