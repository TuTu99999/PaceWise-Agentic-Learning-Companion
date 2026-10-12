import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';

// Run the simulator's actual editor function with a DOM and a stubbed transport.
// This is not a browser screenshot or a production Canvas integration test.
const source = readFileSync(resolve(process.cwd(), '../../lms-simulator/static/app.js'), 'utf8');
const editorSource = source.slice(source.indexOf('function openModuleItemEditor('), source.indexOf('function bindFileActions('));

function mountEditor() {
  const request = vi.fn().mockResolvedValue({});
  const open = new Function('state', 'openDialog', 'escapeHtml', 'request', 'closeDialog', 'renderModulesTab', 'document',
    `${editorSource}\nreturn openModuleItemEditor;`)(
    { user: { id: 1 }, currentCourse: { course: { id: 77 }, assignments: [{ id: 9, title: 'Homework' }],
      resources: [{ id: 4, title: 'Relations.pdf' }], content: { page: [{ id: 5, title: 'Overview' }], quiz: [{ id: 6, title: 'Quiz' }] } } },
    (_title: string, html: string) => { document.body.innerHTML = html; },
    (text: string) => text.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('"', '&quot;'),
    request, vi.fn(), vi.fn(), document,
  );
  open(3);
  return request;
}

afterEach(() => { document.body.innerHTML = ''; });

describe('LMS module editor authoritative content references', () => {
  it('offers real page IDs and auto-fills the selected title', () => {
    mountEditor();
    const content = document.querySelector<HTMLSelectElement>('#module-item-content')!;
    expect(content.required).toBe(true);
    content.value = '5';
    content.dispatchEvent(new Event('change'));
    expect(document.querySelector<HTMLInputElement>('#module-item-title')!.value).toBe('Overview');
  });

  it('submits a linked quiz ID rather than an unlinked label', async () => {
    const request = mountEditor();
    const type = document.querySelector<HTMLSelectElement>('#module-item-type')!;
    type.value = 'quiz';
    type.dispatchEvent(new Event('change'));
    const content = document.querySelector<HTMLSelectElement>('#module-item-content')!;
    content.value = '6';
    content.dispatchEvent(new Event('change'));
    document.querySelector('#module-item-editor')!.dispatchEvent(new Event('submit', { cancelable: true }));
    await vi.waitFor(() => expect(request).toHaveBeenCalledOnce());
    expect(request.mock.calls[0][0]).toBe('/api/courses/77/modules/3/items');
    expect(JSON.parse(request.mock.calls[0][1].body)).toEqual({ user_id: 1, title: 'Quiz', item_type: 'quiz', content_id: 6, external_url: '' });
  });

  it('switches file references and requires a URL only for an external link', async () => {
    const request = mountEditor();
    const type = document.querySelector<HTMLSelectElement>('#module-item-type')!;
    const content = document.querySelector<HTMLSelectElement>('#module-item-content')!;
    const url = document.querySelector<HTMLInputElement>('#module-item-url')!;
    type.value = 'resource';
    type.dispatchEvent(new Event('change'));
    expect(content.options[1].value).toBe('4');
    type.value = 'external_url';
    type.dispatchEvent(new Event('change'));
    expect(content.disabled).toBe(true);
    expect(url.required).toBe(true);
    url.value = 'https://example.test';
    document.querySelector<HTMLInputElement>('#module-item-title')!.value = 'Link';
    document.querySelector('#module-item-editor')!.dispatchEvent(new Event('submit', { cancelable: true }));
    await vi.waitFor(() => expect(request).toHaveBeenCalledOnce());
    expect(JSON.parse(request.mock.calls[0][1].body).content_id).toBeNull();
  });
});
