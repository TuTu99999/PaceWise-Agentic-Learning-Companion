import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { RecoveryCalendarPreview } from '../src/components/domain/RecoveryCalendarPreview';
import type { PlanTimelineItem } from '../src/utils/planTimeline';

describe('RecoveryCalendarPreview', () => {
  it('shows the current and next week with LMS and proposed study blocks', () => {
    const items: PlanTimelineItem[] = [
      {
        id: 'lms:event:1', source: 'lms', title: 'Quiz CS101', date: '2026-10-01', start: '09:00', end: '09:30',
        durationMin: 30, courseCode: 'CS101', kind: 'quiz', kindLabel: 'Quiz', readOnly: true,
      },
      {
        id: 'pacewise:block-1', source: 'pacewise', title: 'Ôn quiz', date: '2026-10-06', start: '19:00', end: '20:00',
        durationMin: 60, courseCode: 'CS101', kind: 'study_block', kindLabel: 'Study block', readOnly: false,
      },
    ];

    render(
      <RecoveryCalendarPreview
        from="2026-09-28"
        items={items}
        proposedStatus={new Map([['block-1', 'moved']])}
      />,
    );

    expect(screen.getByText('Tuần này · áp dụng khi xác nhận')).toBeInTheDocument();
    expect(screen.getByText('Tuần sau · dự kiến')).toBeInTheDocument();
    expect(screen.getAllByRole('gridcell')).toHaveLength(14);
    expect(screen.getByText('Quiz CS101')).toBeInTheDocument();
    expect(screen.getByText('Ôn quiz')).toBeInTheDocument();
    expect(screen.getByText('Đề xuất dời')).toBeInTheDocument();
    expect(screen.getByText('Dự kiến tuần sau')).toBeInTheDocument();
  });
});
