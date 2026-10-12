import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { DoSessionPreparation } from '../../types';
import { DoSessionSupport } from './DoSessionSupport';

const preparation: DoSessionPreparation = {
  action: 'prepare', status: 'ready', block_id: 'b1', task_id: 't1', title: 'Vòng lặp',
  objective: 'Hiểu vòng lặp for', planned_minutes: 45, opening_prompt: 'Hãy hỏi khi cần.',
  recommended_resources: [{ id: 'r1', title: 'Slide vòng lặp', kind: 'file', module: 'Tuần 2', citation: '[Tuần 2 · Slide vòng lặp]', url: '/mock.pdf' }],
};

describe('DoSessionSupport', () => {
  afterEach(() => {
    vi.clearAllMocks();
    vi.unstubAllEnvs();
  });

  it('makes inline assignment requirements readable without expanding them by default', () => {
    render(<DoSessionSupport loading={false} preparation={{
      ...preparation,
      recommended_resources: [{
        id: 'assignment:1:7', title: 'Yêu cầu bài tập', kind: 'assignment', module: 'Chương 3',
        citation: '[Yêu cầu]', excerpt: 'Trình bày lập luận của bạn.',
      }],
    }} />);
    expect(screen.getByText('Xem nội dung')).toBeVisible();
    expect(screen.getByText('Trình bày lập luận của bạn.').closest('details')).not.toHaveAttribute('open');
  });

  it('keeps resources visible while updating', () => {
    render(<DoSessionSupport preparation={preparation} loading />);
    expect(screen.getByText('Slide vòng lặp')).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('Đang cập nhật');
  });

  it('explains a missing chapter mapping instead of recommending another chapter', () => {
    render(<DoSessionSupport preparation={{
      ...preparation,
      recommended_resources: [],
      scope: { status: 'unmapped', module_ids: [], module_names: [], assignment_id: '7' },
    }} loading={false} />);
    expect(screen.getByText('Chưa xác định được học liệu đúng chương cho nhiệm vụ này.')).toBeInTheDocument();
    expect(screen.queryByText('Slide vòng lặp')).not.toBeInTheDocument();
  });

  it('keeps authenticated PDF links but hides legacy LMS-relative links in API-only mode', () => {
    vi.stubEnv('VITE_LMS_WEB_ENABLED', 'false');
    render(<DoSessionSupport preparation={{
      ...preparation,
      recommended_resources: [
        preparation.recommended_resources[0],
        { ...preparation.recommended_resources[0], id: 'r2', title: 'PDF proxy', url: '/api/v1/lms-files/1/2/download' },
      ],
    }} loading={false} />);
    expect(screen.queryByRole('link', { name: /Slide vòng lặp/i })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: /PDF proxy/i })).toHaveAttribute('href', '/api/v1/lms-files/1/2/download');
  });

  it('opens resources in a new tab and no longer contains a support chatbot', () => {
    render(<DoSessionSupport preparation={preparation} loading={false} />);
    const resourceLink = screen.getByRole('link', { name: /Slide vòng lặp/i });
    expect(resourceLink).toHaveAttribute('target', '_blank');
    expect(resourceLink).toHaveAttribute('href', 'http://localhost:8010/mock.pdf');
    expect(screen.queryByRole('heading', { name: 'Hỏi đáp trong phiên' })).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText('Hỏi về khái niệm đang học…')).not.toBeInTheDocument();
  });
});
