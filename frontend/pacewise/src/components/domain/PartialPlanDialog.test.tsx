import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { LocaleProvider } from '../../i18n/LocaleContext';
import type { PartialPlanPreview, PlanDraft, Task } from '../../types';
import { PartialPlanDialog } from './PartialPlanDialog';

const task: Task = {
  id: 'task-1', title: 'Bài tập Chương 3', courseId: 'DB201', deadline: '2026-10-20',
  estimateMin: 240, loggedMin: 0, status: 'todo', priority: 'high', objective: 'Hoàn thành bài tập',
};

const draft: PlanDraft = {
  input: { goal: '', tasks: [], availability: [], unavailable: [], preferred: 'evening' },
  blocks: [
    { id: 'block-1', taskId: task.id, milestoneTitle: 'Hoàn thành mô hình quan hệ', date: '2026-10-18', start: '19:45', end: '20:40' },
    { id: 'block-2', taskId: task.id, milestoneTitle: 'Kiểm tra lược đồ', date: '2026-10-18', start: '21:02', end: '21:57' },
  ],
  feasibility: { availableMin: 135, requiredMin: 165, remainingMin: -30, feasible: false, deficitMin: 30, shortfalls: [{ taskId: task.id, missingMin: 30 }] },
  reasons: [], assumptions: [], createdAt: 'draft-1',
};

const preview: PartialPlanPreview = {
  canConfirm: true, blockIds: ['block-1', 'block-2'], scheduledWorkMin: 135,
  shortfalls: [{ taskId: task.id, missingMin: 30 }], excludedBlocks: [], requiresAcknowledgement: true,
};

describe('PartialPlanDialog', () => {
  beforeEach(() => window.localStorage.setItem('pacewise-language', 'en'));

  it('renders the complete partial-confirmation flow in English with one scroll container', () => {
    render(<LocaleProvider><PartialPlanDialog
      open draft={draft} preview={preview} tasks={[task]} saving={false}
      onClose={vi.fn()} onConfirm={vi.fn()} onAdjust={vi.fn()}
    /></LocaleProvider>);

    const dialog = screen.getByRole('dialog', { name: 'Confirm valid scheduled sessions' });
    expect(screen.getByText(/Only the 2 valid sessions below will be confirmed/)).toBeInTheDocument();
    expect(screen.getByText('Remaining unscheduled work:')).toBeInTheDocument();
    expect(screen.getByText(/30 minutes still needs to be scheduled before the deadline/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Adjust to schedule all work' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Confirm 2 hours 15 minutes scheduled' })).toBeInTheDocument();
    expect(dialog.querySelectorAll('.overflow-y-auto')).toHaveLength(1);
  });
});
