import { webcrypto } from 'node:crypto';
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest';

const encoder = new TextEncoder();
const b64 = (buffer: ArrayBuffer | Uint8Array) => Buffer.from(buffer instanceof Uint8Array ? buffer : new Uint8Array(buffer)).toString('base64');
const raw = (value: string) => Uint8Array.from(Buffer.from(value, 'base64'));
const info = encoder.encode('pacewise-private-api-v1');

beforeEach(() => { vi.resetModules(); vi.stubGlobal('crypto', webcrypto); });
afterEach(() => vi.unstubAllGlobals());

describe('encrypted API transport', () => {
  it('hides identity, credentials, IDs and target path on the wire, then decrypts an authenticated response', async () => {
    const server = await webcrypto.subtle.generateKey({ name: 'ECDH', namedCurve: 'P-256' }, false, ['deriveBits']);
    const publicKey = b64(await webcrypto.subtle.exportKey('raw', server.publicKey));
    const wire: string[] = [];
    const fetchMock = vi.fn(async (url: string, options?: RequestInit) => {
      if (url.endsWith('/private/config')) return new Response(JSON.stringify({ publicKey }));
      expect(url).toBe('/api/v1/private/dispatch');
      wire.push(String(options?.body));
      const packet = JSON.parse(String(options?.body));
      const client = await webcrypto.subtle.importKey('raw', raw(packet.publicKey), { name: 'ECDH', namedCurve: 'P-256' }, false, []);
      const shared = await webcrypto.subtle.deriveBits({ name: 'ECDH', public: client }, server.privateKey, 256);
      const material = await webcrypto.subtle.importKey('raw', shared, 'HKDF', false, ['deriveKey']);
      const key = await webcrypto.subtle.deriveKey({ name: 'HKDF', hash: 'SHA-256', salt: raw(packet.salt), info }, material,
        { name: 'AES-GCM', length: 256 }, false, ['encrypt', 'decrypt']);
      const request = JSON.parse(new TextDecoder().decode(await webcrypto.subtle.decrypt({ name: 'AES-GCM', iv: raw(packet.nonce),
        additionalData: encoder.encode('pacewise-private-api-v1:request') }, key, raw(packet.ciphertext))));
      expect(request.path).toBe('/api/v1/auth/lms-login');
      expect(JSON.parse(request.body)).toEqual({ email: 'private@example.edu', password: 'SECRET', course_id: 7 });
      const nonce = webcrypto.getRandomValues(new Uint8Array(12));
      const aad = Buffer.concat([Buffer.from('pacewise-private-api-v1:response:'), Buffer.from(raw(packet.nonce)), Buffer.from('429')]);
      const cipher = await webcrypto.subtle.encrypt({ name: 'AES-GCM', iv: nonce, additionalData: aad }, key,
        encoder.encode(JSON.stringify({ type: 'json', body: { user: { id: '42', courseId: '7' } }, headers: { 'retry-after': '60' } })));
      return new Response(JSON.stringify({ version: 1, nonce: b64(nonce), ciphertext: b64(cipher) }), { status: 429 });
    });
    vi.stubGlobal('fetch', fetchMock);
    const { encryptedFetch } = await import('../src/services/privateApi');
    const result = await encryptedFetch('/api/v1', '/auth/lms-login', { method: 'POST',
      body: JSON.stringify({ email: 'private@example.edu', password: 'SECRET', course_id: 7 }) });
    expect(await result.json()).toEqual({ user: { id: '42', courseId: '7' } });
    expect(result.headers.get('retry-after')).toBe('60');
    expect(wire[0]).not.toContain('SECRET');
    expect(wire[0]).not.toContain('private@example.edu');
    expect(wire[0]).not.toContain('course_id');
    expect(wire[0]).not.toContain('/auth/lms-login');
  });

  it('fails closed on a successful plaintext response instead of silently falling back', async () => {
    const server = await webcrypto.subtle.generateKey({ name: 'ECDH', namedCurve: 'P-256' }, false, ['deriveBits']);
    const publicKey = b64(await webcrypto.subtle.exportKey('raw', server.publicKey));
    vi.stubGlobal('fetch', vi.fn(async (url: string) => new Response(JSON.stringify(url.endsWith('/config') ? { publicKey } : { user: { id: 1 } }))));
    const { encryptedFetch } = await import('../src/services/privateApi');
    await expect(encryptedFetch('/api/v1', '/auth/me')).rejects.toThrow('Unencrypted API response rejected');
  });

  it('refreshes a stale server key once after a backend restart', async () => {
    const staleServer = await webcrypto.subtle.generateKey({ name: 'ECDH', namedCurve: 'P-256' }, false, ['deriveBits']);
    const currentServer = await webcrypto.subtle.generateKey({ name: 'ECDH', namedCurve: 'P-256' }, false, ['deriveBits']);
    const stalePublicKey = b64(await webcrypto.subtle.exportKey('raw', staleServer.publicKey));
    const currentPublicKey = b64(await webcrypto.subtle.exportKey('raw', currentServer.publicKey));
    let configRequests = 0;
    let dispatchRequests = 0;
    const fetchMock = vi.fn(async (url: string, options?: RequestInit) => {
      if (url.endsWith('/private/config')) {
        configRequests += 1;
        return new Response(JSON.stringify({ publicKey: configRequests === 1 ? stalePublicKey : currentPublicKey }));
      }
      dispatchRequests += 1;
      if (dispatchRequests === 1) {
        return new Response(JSON.stringify({ detail: 'Invalid encrypted request' }), {
          status: 400,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      const packet = JSON.parse(String(options?.body));
      const client = await webcrypto.subtle.importKey('raw', raw(packet.publicKey), { name: 'ECDH', namedCurve: 'P-256' }, false, []);
      const shared = await webcrypto.subtle.deriveBits({ name: 'ECDH', public: client }, currentServer.privateKey, 256);
      const material = await webcrypto.subtle.importKey('raw', shared, 'HKDF', false, ['deriveKey']);
      const key = await webcrypto.subtle.deriveKey({ name: 'HKDF', hash: 'SHA-256', salt: raw(packet.salt), info }, material,
        { name: 'AES-GCM', length: 256 }, false, ['encrypt', 'decrypt']);
      const nonce = webcrypto.getRandomValues(new Uint8Array(12));
      const aad = Buffer.concat([Buffer.from('pacewise-private-api-v1:response:'), Buffer.from(raw(packet.nonce)), Buffer.from('200')]);
      const cipher = await webcrypto.subtle.encrypt({ name: 'AES-GCM', iv: nonce, additionalData: aad }, key,
        encoder.encode(JSON.stringify({ type: 'json', body: { configured: true }, headers: {} })));
      return new Response(JSON.stringify({ version: 1, nonce: b64(nonce), ciphertext: b64(cipher) }), { status: 200 });
    });
    vi.stubGlobal('fetch', fetchMock);
    const { encryptedFetch } = await import('../src/services/privateApi');

    const result = await encryptedFetch('/api/v1', '/auth/google/status');

    expect(await result.json()).toEqual({ configured: true });
    expect(configRequests).toBe(2);
    expect(dispatchRequests).toBe(2);
  });
});
