import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useChatAutoScroll } from './useChatAutoScroll';

function Harness() {
  const [revision, setRevision] = useState(0);
  const { containerRef, handleScroll, followLatest } = useChatAutoScroll(revision);
  return (
    <>
      <div ref={containerRef} onScroll={handleScroll} data-testid="chat-viewport" />
      <button type="button" onClick={() => setRevision((value) => value + 1)}>append</button>
      <button type="button" onClick={followLatest}>follow</button>
    </>
  );
}

function setDimensions(element: HTMLElement, scrollHeight: number, clientHeight: number) {
  Object.defineProperties(element, {
    scrollHeight: { configurable: true, value: scrollHeight },
    clientHeight: { configurable: true, value: clientHeight },
  });
}

describe('useChatAutoScroll', () => {
  afterEach(() => vi.restoreAllMocks());

  it('follows new chat content while the reader remains near the bottom', () => {
    render(<Harness />);
    const viewport = screen.getByTestId('chat-viewport');
    setDimensions(viewport, 900, 300);

    fireEvent.click(screen.getByRole('button', { name: 'append' }));

    expect(viewport.scrollTop).toBe(900);
  });

  it('preserves an intentional history position until a new outgoing message forces follow mode', () => {
    render(<Harness />);
    const viewport = screen.getByTestId('chat-viewport');
    setDimensions(viewport, 900, 300);
    viewport.scrollTop = 200;
    fireEvent.scroll(viewport);

    fireEvent.click(screen.getByRole('button', { name: 'append' }));
    expect(viewport.scrollTop).toBe(200);

    fireEvent.click(screen.getByRole('button', { name: 'follow' }));
    expect(viewport.scrollTop).toBe(900);
  });

  it('re-applies the latest position after the browser finishes laying out a reply', () => {
    let scheduled: FrameRequestCallback | undefined;
    vi.spyOn(window, 'requestAnimationFrame').mockImplementation((callback) => {
      scheduled = callback;
      return 1;
    });
    vi.spyOn(window, 'cancelAnimationFrame').mockImplementation(() => undefined);
    render(<Harness />);
    const viewport = screen.getByTestId('chat-viewport');
    setDimensions(viewport, 900, 300);

    fireEvent.click(screen.getByRole('button', { name: 'append' }));
    viewport.scrollTop = 500;
    setDimensions(viewport, 1200, 300);
    scheduled?.(0);

    expect(viewport.scrollTop).toBe(1200);
  });
});
