// @vitest-environment jsdom

import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { PlanTimelineItem } from '../../utils/planTimeline';
import { addDays, DEMO_TODAY } from '../../utils/time';
import { CombinedSchedule } from './CombinedSchedule';

const studyItem: PlanTimelineItem = {
  id: 'pacewise:block-1',
  source: 'pacewise',
  title: 'Ôn tập vòng lặp',
  date: DEMO_TODAY,
  start: '19:00',
  end: '20:00',
  durationMin: 60,
  courseCode: 'CS101',
  kind: 'study_block',
  kindLabel: 'Study block',
  deadline: addDays(DEMO_TODAY, 2),
  readOnly: false,
};

describe('CombinedSchedule', () => {
  it('keeps the agenda compact and lets the learner open another day', () => {
    const tomorrow = addDays(DEMO_TODAY, 1);
    render(<CombinedSchedule items={[studyItem]} dates={[DEMO_TODAY, tomorrow]} nextItemId={studyItem.id} />);

    expect(screen.getByText('Ôn tập vòng lặp')).toBeTruthy();
    expect(screen.getByText('Sắp tới')).toBeTruthy();

    const tomorrowButton = screen.getByRole('button', { name: /Ngày mai.*Chưa có lịch/i });
    expect(tomorrowButton.getAttribute('aria-expanded')).toBe('false');
    fireEvent.click(tomorrowButton);
    expect(tomorrowButton.getAttribute('aria-expanded')).toBe('true');
    expect(screen.getByText('Bạn chưa có buổi học hoặc mốc LMS trong ngày này.')).toBeTruthy();
  });

  it('keeps filters behind an optional details control', () => {
    render(<CombinedSchedule items={[studyItem]} dates={[DEMO_TODAY]} />);

    const filter = screen.getByText('Lọc nội dung · 1 mục').closest('details');
    expect(filter?.open).toBe(false);
  });
});
