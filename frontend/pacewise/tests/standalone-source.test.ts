import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest';

beforeEach(() => { vi.resetModules(); vi.stubEnv('VITE_COURSE_SOURCE_MODE', 'standalone'); vi.stubEnv('VITE_PRIVATE_API_REQUIRED', 'false'); vi.stubGlobal('document', { cookie: 'pacewise_csrf=secure-csrf' }); });
afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); });

describe('standalone source transport', () => {
  it('logs into PaceWise, not the legacy LMS route', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ user: { id: '2', role: 'student' } })));
    vi.stubGlobal('fetch', fetchMock);
    const { login } = await import('../src/services/api');
    await login('preserved@example.test', 'preserved-password');
    expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/auth/login');
  });

  it('sends a PDF as binary to the unified opaque document ticket, never base64 JSON', async () => {
    const path = '/api/v1/private/uploads/' + 'a'.repeat(43);
    const fetchMock = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ uploadMode: 'proxy', uploadPath: path, receiptToken: 'a'.repeat(43) })))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ fileId: 12, duplicate: false })));
    vi.stubGlobal('fetch', fetchMock);
    const { uploadTeacherPdf, coursePdfMaxMb } = await import('../src/services/api');
    const file = new File(['%PDF-1.4'], 'slides.pdf', { type: 'application/pdf' });
    const readAll = vi.fn().mockResolvedValue(new TextEncoder().encode('%PDF-1.4').buffer);
    Object.defineProperty(file, 'arrayBuffer', { value: readAll });
    await uploadTeacherPdf('7', file, 'Chapter 3');
    expect(coursePdfMaxMb).toBe(50);
    const [ticketUrl, ticketInit] = fetchMock.mock.calls[0];
    expect(ticketUrl).toBe('/api/v1/instructor/manage/courses/7/document-ticket');
    expect(JSON.parse(ticketInit.body)).toEqual({
      filename: 'slides.pdf',
      size: file.size,
      chapter: 'Chapter 3',
      checksumSha256: expect.stringMatching(/^[a-f0-9]{64}$/),
      content_role: 'learning_material',
    });
    const [binaryUrl, binaryInit] = fetchMock.mock.calls[1];
    expect(binaryUrl).toBe(path); expect(binaryInit.body).toBe(file);
    expect(binaryInit.headers['X-CSRF-Token']).toBe('secure-csrf');
    expect(readAll).toHaveBeenCalledOnce();
  });

  it('rejects a ticket redirecting file contents to an external host', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ uploadMode: 'proxy', uploadPath: 'https://untrusted.invalid/upload', receiptToken: 'a'.repeat(43) })));
    vi.stubGlobal('fetch', fetchMock);
    const { uploadTeacherPdf } = await import('../src/services/api');
    const file = new File(['%PDF-'], 'slides.pdf');
    Object.defineProperty(file, 'arrayBuffer', { value: vi.fn().mockResolvedValue(new TextEncoder().encode('%PDF-').buffer) });
    await expect(uploadTeacherPdf('7', file, 'Chapter 3')).rejects.toThrow('Lượt tải không hợp lệ');
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('uploads directly to a presigned S3 URL without browser credentials', async () => {
    const token = 'b'.repeat(43);
    const url = 'https://pacewise-materials.s3.ap-southeast-1.amazonaws.com/object?signed=yes';
    const headers = { 'Content-Type': 'application/pdf', 'x-amz-checksum-sha256': 'digest' };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ uploadMode: 's3', uploadUrl: url, uploadHeaders: headers, receiptToken: token })))
      .mockResolvedValueOnce(new Response(null, { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ fileId: 18, duplicate: false })));
    vi.stubGlobal('fetch', fetchMock);
    const { uploadTeacherPdf } = await import('../src/services/api');
    const file = new File(['%PDF-1.4'], 'slides.pdf', { type: 'application/pdf' });
    Object.defineProperty(file, 'arrayBuffer', { value: vi.fn().mockResolvedValue(new TextEncoder().encode('%PDF-1.4').buffer) });

    await expect(uploadTeacherPdf('7', file, 'Chapter 3')).resolves.toEqual({ fileId: 18, duplicate: false });
    expect(fetchMock.mock.calls[1]).toEqual([new URL(url), expect.objectContaining({
      method: 'PUT', body: file, headers, credentials: 'omit',
    })]);
    expect(JSON.parse(fetchMock.mock.calls[2][1].body)).toEqual({ token });
  });
});
