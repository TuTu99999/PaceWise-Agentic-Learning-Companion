import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { LearningCycleMetrics } from '../../types';
import { LearningCycleKpis } from './LearningCycleKpis';

const metrics: LearningCycleMetrics = {
  periodStart: '2026-10-05', periodEnd: '2026-10-12',
  originalPlan: { status: 'available', n: 5, count: 20, total: 30, rate: 2 / 3, removedCount: 10, unverifiedCount: 10 },
  currentPlan: { status: 'available', n: 5, count: 20, total: 20, rate: 1, removedCount: 0, unverifiedCount: 0 },
  learningEvidence: { status: 'available', n: 5, total: 30, satisfied: 15, rate: 0.5, missing: 5, belowRequirement: 5, unmapped: 5,
    retention: { due: 5, checked: 0, passed: 0 } },
};

describe('evidence-backed learning cycle metrics', () => {
  it('separates original attainment, revised attainment and evidence quality', () => {
    render(<LearningCycleKpis metrics={metrics} />);
    expect(screen.getByText('67%')).toBeInTheDocument();
    expect(screen.getByText('100%')).toBeInTheDocument();
    expect(screen.getByText('50%')).toBeInTheDocument();
    expect(screen.getByText(/10 mốc ban đầu không còn/)).toBeInTheDocument();
    expect(screen.getByText(/0\/5 đã kiểm tra/)).toBeInTheDocument();
    expect(screen.getByText(/không tạo so sánh tiến độ trước\/sau giả/)).toBeInTheDocument();
  });

  it('does not turn missing history into a failing zero percent', () => {
    render(<LearningCycleKpis />);
    expect(screen.getAllByText('Chưa đủ dữ liệu')).toHaveLength(3);
    expect(screen.queryByText('0%')).not.toBeInTheDocument();
  });

  it('does not render suppressed small-cohort values', () => {
    render(<LearningCycleKpis metrics={{ ...metrics,
      originalPlan: { ...metrics.originalPlan, status: 'insufficient_data', rate: null },
      currentPlan: { ...metrics.currentPlan, status: 'insufficient_data', rate: null },
      learningEvidence: { ...metrics.learningEvidence, status: 'insufficient_data', rate: null },
    }} />);
    expect(screen.getAllByText('Chưa đủ dữ liệu')).toHaveLength(3);
    expect(screen.queryByText('50%')).not.toBeInTheDocument();
  });
});
