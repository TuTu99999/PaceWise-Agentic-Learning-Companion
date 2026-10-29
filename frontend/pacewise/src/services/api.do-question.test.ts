import { afterEach, describe, expect, it, vi } from 'vitest';
import { askDoQuestion, askQuestion } from './api';

describe('askDoQuestion', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('sends only the learner question through safety classification', async () => {
    const final = {
      workflow: 'qa', status: 'completed', response: 'CSDL là tập hợp dữ liệu có tổ chức.',
      mode: 'grounded', source_refs: [],
    };
    const fetchMock = vi.fn().mockResolvedValue(new Response([
      JSON.stringify({ type: 'delta', text: 'CSDL là ' }),
      JSON.stringify({ type: 'delta', text: 'tập hợp dữ liệu có tổ chức.' }),
      JSON.stringify({ type: 'final', result: final }),
      '',
    ].join('\n'), { status: 200, headers: { 'Content-Type': 'application/x-ndjson' } }));
    vi.stubGlobal('fetch', fetchMock);

    const deltas: string[] = [];
    await askDoQuestion({
      courseId: '8',
      blockId: 'block-1',
      taskTitle: 'Bài tập cần nộp',
      objective: 'Hoàn thành bài tập',
      question: 'CSDL là gì?',
    }, (delta) => deltas.push(delta), 'en');

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain('/chat/stream');
    const body = JSON.parse(String(init.body));
    expect(body.message).toBe('CSDL là gì?');
    expect(body.message).not.toContain('Bài tập cần nộp');
    expect(body.context).toMatchObject({
      do_course_id: '8',
      do_block_id: 'block-1',
      do_task_title: 'Bài tập cần nộp',
      do_objective: 'Hoàn thành bài tập',
    });
    expect(body.qa_history).toEqual([]);
    expect(body.locale).toBe('en');
    expect(deltas.join('')).toBe(final.response);
  });

  it('gives every provider delta a paint boundary before resolving the final answer', async () => {
    const final = {
      workflow: 'qa', status: 'completed', response: 'Binary search halves the range.',
      mode: 'grounded', source_refs: [],
    };
    const animationFrames: FrameRequestCallback[] = [];
    vi.spyOn(window, 'requestAnimationFrame').mockImplementation((callback) => {
      animationFrames.push(callback);
      return animationFrames.length;
    });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response([
      JSON.stringify({ type: 'delta', text: 'Binary search ' }),
      JSON.stringify({ type: 'delta', text: 'halves the range.' }),
      JSON.stringify({ type: 'final', result: final }),
      '',
    ].join('\n'), { status: 200, headers: { 'Content-Type': 'application/x-ndjson' } })));

    const deltas: string[] = [];
    let resolved = false;
    const answer = askQuestion('How does binary search work?', [], undefined, (delta) => deltas.push(delta))
      .then((value) => { resolved = true; return value; });

    await Promise.resolve();
    await Promise.resolve();
    expect(deltas).toEqual(['Binary search ']);
    expect(resolved).toBe(false);
    animationFrames.shift()?.(performance.now());
    await new Promise((resolve) => window.setTimeout(resolve, 0));
    expect(deltas).toEqual(['Binary search ', 'halves the range.']);
    expect(resolved).toBe(false);
    animationFrames.shift()?.(performance.now());

    await expect(answer).resolves.toMatchObject({ text: final.response });
    expect(resolved).toBe(true);
  });

  it('preserves the structured AI quota message and retry delay', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      detail: {
        code: 'AI_DAILY_QUOTA_EXCEEDED',
        message: 'Bạn đã sử dụng hết hạn mức AI trong ngày.',
        retry_after_seconds: 90,
      },
    }), {
      status: 429,
      headers: { 'Content-Type': 'application/json', 'Retry-After': '90', 'X-Request-ID': 'req-quota' },
    })));

    await expect(askQuestion('SQL là gì?', [])).rejects.toMatchObject({
      code: 'RATE_LIMITED',
      message: 'Bạn đã sử dụng hết hạn mức AI trong ngày.',
      requestId: 'req-quota',
      retryAfterSeconds: 90,
    });
  });
});
