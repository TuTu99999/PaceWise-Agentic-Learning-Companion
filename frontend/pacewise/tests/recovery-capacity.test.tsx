import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { RecoveryCapacitySummary } from '../src/components/domain/RecoveryCapacitySummary';
import type { RecoveryOption } from '../src/types';

describe('RecoveryCapacitySummary', () => {
  it('explains workload, scheduled time, and unresolved capacity separately', () => {
    const option: RecoveryOption = {
      id: 'A',
      title: 'Cân bằng lại tất cả môn',
      summary: 'Rebalance',
      changes: [],
      impact: 'Vẫn thiếu thời gian',
      time: 'Xếp lại thời gian',
      tradeoff: 'Protect nearest deadlines',
      newBlocks: [],
      assumptions: [],
      fullyRecovers: false,
      workloadMinutes: 4750,
      scheduledMinutes: 2205,
      missingMinutes: 2545,
      shortfalls: [{ taskId: 'DS201:project', missingMin: 2545 }],
    };

    render(<RecoveryCapacitySummary option={option} />);

    expect(screen.getByText('Khối lượng cần sắp xếp')).toBeInTheDocument();
    expect(screen.getByText('Đã xếp được')).toBeInTheDocument();
    expect(screen.getByText('Còn thiếu capacity')).toBeInTheDocument();
    expect(screen.getByText(/4[.,]750 phút/)).toBeInTheDocument();
    expect(screen.getByText(/2[.,]205 phút/)).toBeInTheDocument();
    expect(screen.getByText(/2[.,]545 phút/)).toBeInTheDocument();
    expect(screen.getByText('DS201:project')).toBeInTheDocument();
  });
});
