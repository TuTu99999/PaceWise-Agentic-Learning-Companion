import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { ThemeToggle } from './ThemeToggle';

describe('ThemeToggle', () => {
  afterEach(() => {
    document.documentElement.dataset.theme = 'light';
    window.localStorage.removeItem('pacewise-theme');
  });

  it('switches the global theme and persists the preference', () => {
    document.documentElement.dataset.theme = 'light';
    render(<ThemeToggle />);

    fireEvent.click(screen.getByRole('button', { name: 'Chuyển sang giao diện tối' }));

    expect(document.documentElement.dataset.theme).toBe('dark');
    expect(window.localStorage.getItem('pacewise-theme')).toBe('dark');
    expect(screen.getByRole('button', { name: 'Chuyển sang giao diện sáng' })).toBeTruthy();
  });
  it('synchronizes the desktop and mobile controls', async () => {
    document.documentElement.dataset.theme = 'light';
    render(<><ThemeToggle sidebar /><ThemeToggle /></>);
    fireEvent.click(screen.getAllByRole('button', { name: 'Chuyển sang giao diện tối' })[1]);
    await waitFor(() => expect(screen.getAllByRole('button', { name: 'Chuyển sang giao diện sáng' })).toHaveLength(2));
    fireEvent.click(screen.getAllByRole('button', { name: 'Chuyển sang giao diện sáng' })[0]);
    await waitFor(() => expect(screen.getAllByRole('button', { name: 'Chuyển sang giao diện tối' })).toHaveLength(2));
  });
});
