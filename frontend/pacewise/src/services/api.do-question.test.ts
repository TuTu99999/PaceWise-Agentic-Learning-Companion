import { afterEach, describe, expect, it, vi } from 'vitest';
import { askDoQuestion } from './api';

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
    }, (delta) => deltas.push(delta));

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
    expect(deltas.join('')).toBe(final.response);
  });
});
