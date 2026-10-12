import { useCallback, useEffect, useLayoutEffect, useRef } from 'react';

const DEFAULT_BOTTOM_THRESHOLD_PX = 80;

/**
 * Keeps a chat viewport pinned to its newest content while the reader is at
 * the bottom. Scrolling up disables following until the caller explicitly
 * starts a new message with followLatest().
 */
export function useChatAutoScroll(revision: unknown, bottomThresholdPx = DEFAULT_BOTTOM_THRESHOLD_PX) {
  const containerRef = useRef<HTMLDivElement>(null);
  const shouldFollowLatestRef = useRef(true);
  const frameRef = useRef<number | null>(null);

  const cancelScheduledScroll = useCallback(() => {
    if (frameRef.current !== null) {
      window.cancelAnimationFrame(frameRef.current);
      frameRef.current = null;
    }
  }, []);

  const commitScroll = useCallback(() => {
    const container = containerRef.current;
    if (container) container.scrollTop = container.scrollHeight;
  }, []);

  const scheduleScrollAfterLayout = useCallback(() => {
    cancelScheduledScroll();
    frameRef.current = window.requestAnimationFrame(() => {
      frameRef.current = null;
      if (shouldFollowLatestRef.current) commitScroll();
    });
  }, [cancelScheduledScroll, commitScroll]);

  const scrollToLatest = useCallback((force = false) => {
    if (force) shouldFollowLatestRef.current = true;
    if (!shouldFollowLatestRef.current) return;
    // Scroll immediately for React's committed layout, then once more on the
    // next frame for markdown/citation blocks whose height settles afterward.
    commitScroll();
    scheduleScrollAfterLayout();
  }, [commitScroll, scheduleScrollAfterLayout]);

  const handleScroll = useCallback(() => {
    const container = containerRef.current;
    if (!container) return;

    const distanceFromBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
    shouldFollowLatestRef.current = distanceFromBottom <= bottomThresholdPx;
  }, [bottomThresholdPx]);

  useLayoutEffect(() => {
    scrollToLatest();
  }, [revision, scrollToLatest]);

  useEffect(() => cancelScheduledScroll, [cancelScheduledScroll]);

  return {
    containerRef,
    handleScroll,
    followLatest: () => scrollToLatest(true),
  };
}
