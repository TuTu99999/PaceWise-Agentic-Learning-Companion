import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { TimeSelect } from '../src/components/ui/Field';

describe('TimeSelect', () => {
  it('renders a locale-independent 24-hour list including 24:00 for end time', () => {
    const onChange = vi.fn();
    render(<TimeSelect label="Kết thúc" includeEndOfDay value="18:00" onChange={onChange} />);

    const select = screen.getByLabelText('Kết thúc');
    expect(screen.getByRole('option', { name: '00:00' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: '24:00' })).toBeInTheDocument();
    expect(screen.queryByText(/SA|CH/)).not.toBeInTheDocument();

    fireEvent.change(select, { target: { value: '23:30' } });
    expect(onChange).toHaveBeenCalled();
  });

  it('preserves an existing non-standard minute value', () => {
    render(<TimeSelect label="Bắt đầu" value="18:45" onChange={() => undefined} />);
    expect(screen.getByRole('option', { name: '18:45' })).toBeInTheDocument();
  });
});
