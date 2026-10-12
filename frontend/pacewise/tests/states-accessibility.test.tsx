import { render, screen } from '@testing-library/react';
import axe from 'axe-core';
import { describe, expect, it } from 'vitest';

import { EmptyState, ErrorState } from '../src/components/ui/States';

describe('shared UI states', () => {
  it('renders an actionable error state', () => {
    render(
      <ErrorState
        title="Không thể đồng bộ"
        description="Thử lại sau."
        requestId="REQ-1"
        onRetry={() => undefined}
      />,
    );
    expect(screen.getByRole('alert')).toHaveTextContent('Không thể đồng bộ');
    expect(screen.getByRole('button', { name: 'Thử lại' })).toBeEnabled();
  });

  it('has no detectable accessibility violations in the empty state', async () => {
    const { container } = render(
      <EmptyState title="Chưa có kế hoạch" description="Hãy tạo kế hoạch đầu tiên." />,
    );
    const result = await axe.run(container, {
      rules: { 'color-contrast': { enabled: false } },
    });
    expect(result.violations).toEqual([]);
  });
});
