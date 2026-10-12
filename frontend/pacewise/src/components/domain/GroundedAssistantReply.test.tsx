import '@testing-library/jest-dom/vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { GroundedAssistantReply } from './GroundedAssistantReply';

describe('GroundedAssistantReply', () => {
  it('keeps source cards collapsed behind one compact course-material summary', () => {
    render(<GroundedAssistantReply
      compact
      message={{
        kind: 'grounded',
        text: 'Giải thích ngắn có căn cứ.',
        sources: [
          { id: 's1', name: 'Slide chương 3', sectionTitle: 'Chương 3', location: 'Trang 4', excerpt: 'Đoạn một.' },
          { id: 's2', name: 'Bài tập chương 3', sectionTitle: 'Chương 3', location: 'Trang 6', excerpt: 'Đoạn hai.' },
        ],
      }}
      onOpen={vi.fn()}
    />);

    const summary = screen.getByText('Đã kiểm tra 2 nguồn · Chương 3 · trang 4–6');
    expect(summary).toBeVisible();
    expect(summary.closest('details')).not.toHaveAttribute('open');
    expect(screen.getByText('Giải thích ngắn có căn cứ.').closest('.max-h-72')).toBeTruthy();
  });

  it('keeps the original-file action opening in a new tab', () => {
    render(<GroundedAssistantReply
      message={{
        kind: 'grounded',
        text: 'Nội dung.',
        sources: [{ id: 's1', name: 'Slide', location: 'Trang 1', excerpt: 'Nguồn', downloadUrl: '/api/v1/materials/1/download' }],
      }}
      onOpen={vi.fn()}
    />);

    fireEvent.click(screen.getByText(/Đã kiểm tra 1 nguồn/));
    expect(screen.getByRole('link', { name: 'Xem file' })).toHaveAttribute('target', '_blank');
  });
});
