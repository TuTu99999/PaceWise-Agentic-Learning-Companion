// Wire privacy only: the browser owner can still inspect decrypted application data.
const encoder = new TextEncoder();
const info = encoder.encode('pacewise-private-api-v1');
let configuration: Promise<{ publicKey: string }> | undefined;
const join = (...items: Uint8Array[]) => {
  const result = new Uint8Array(items.reduce((size, item) => size + item.length, 0));
  let offset = 0;
  for (const item of items) { result.set(item, offset); offset += item.length; }
  return result;
};
const encode = (value: Uint8Array) => {
  // Avoid spreading large payloads into a function's argument list.
  let text = '';
  for (let offset = 0; offset < value.length; offset += 8192) text += String.fromCharCode(...value.subarray(offset, offset + 8192));
  return btoa(text);
};
const decode = (value: string) => Uint8Array.from(atob(value), (char) => char.charCodeAt(0));

async function encryptedFetchAttempt(base: string, path: string, init: RequestInit, retryConfig: boolean): Promise<Response> {
  if (!globalThis.crypto?.subtle) throw new Error('Private API requires HTTPS or localhost.');
  if (!configuration) {
    configuration = fetch(`${base}/private/config`, { credentials: 'include', cache: 'no-store' })
      .then(async (response) => { if (!response.ok) throw new Error('Private API unavailable'); return response.json(); })
      .catch((error) => { configuration = undefined; throw error; });
  }
  const server = await configuration;
  const pair = await crypto.subtle.generateKey({ name: 'ECDH', namedCurve: 'P-256' }, false, ['deriveBits']);
  const remote = await crypto.subtle.importKey('raw', decode(server.publicKey), { name: 'ECDH', namedCurve: 'P-256' }, false, []);
  const shared = await crypto.subtle.deriveBits({ name: 'ECDH', public: remote }, pair.privateKey, 256);
  const salt = crypto.getRandomValues(new Uint8Array(32));
  const nonce = crypto.getRandomValues(new Uint8Array(12));
  const material = await crypto.subtle.importKey('raw', shared, 'HKDF', false, ['deriveKey']);
  const key = await crypto.subtle.deriveKey({ name: 'HKDF', hash: 'SHA-256', salt, info }, material,
    { name: 'AES-GCM', length: 256 }, false, ['encrypt', 'decrypt']);
  if (init.body != null && typeof init.body !== 'string') throw new Error('Unsupported encrypted request body');
  const target = new URL(`${base}${path}`, globalThis.location?.origin || 'http://localhost');
  const body = JSON.stringify({ method: (init.method || 'GET').toUpperCase(), path: target.pathname + target.search, body: init.body ?? null, sentAt: Date.now() });
  const ciphertext = await crypto.subtle.encrypt({ name: 'AES-GCM', iv: nonce, additionalData: join(info, encoder.encode(':request')) }, key, encoder.encode(body));
  const publicKey = await crypto.subtle.exportKey('raw', pair.publicKey);
  const headers = new Headers(init.headers);
  headers.set('Content-Type', 'application/json');
  const response = await fetch(`${base}/private/dispatch`, { method: 'POST', headers, credentials: 'include', signal: init.signal,
    body: JSON.stringify({ publicKey: encode(new Uint8Array(publicKey)), salt: encode(salt), nonce: encode(nonce), ciphertext: encode(new Uint8Array(ciphertext)) }) });
  const envelope = await response.json();
  if (!envelope.ciphertext || envelope.version !== 1) {
    if (retryConfig && response.status === 400 && envelope.detail === 'Invalid encrypted request') {
      // A long-lived browser tab may still hold the previous public key after a
      // backend restart or key rotation. Refresh the public configuration and
      // retry once; encrypted transport remains mandatory on the retry.
      configuration = undefined;
      return encryptedFetchAttempt(base, path, init, false);
    }
    if (response.ok) throw new Error('Unencrypted API response rejected');
    return new Response(JSON.stringify({ detail: 'Không thể xác minh dữ liệu API.' }), { status: response.status, headers: { 'Content-Type': 'application/json' } });
  }
  const plaintext = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: decode(envelope.nonce),
    additionalData: join(info, encoder.encode(':response:'), nonce, encoder.encode(String(response.status))) }, key, decode(envelope.ciphertext));
  const result = JSON.parse(new TextDecoder().decode(plaintext));
  const returnedHeaders = new Headers(result.headers);
  returnedHeaders.set('Content-Type', result.type === 'json' ? 'application/json' : result.contentType || 'application/octet-stream');
  return new Response(result.type === 'json' ? JSON.stringify(result.body) : decode(result.body), { status: response.status, headers: returnedHeaders });
}

export async function encryptedFetch(base: string, path: string, init: RequestInit = {}): Promise<Response> {
  return encryptedFetchAttempt(base, path, init, true);
}

export const privateApiEnabled = import.meta.env.MODE !== 'test' && import.meta.env.VITE_PRIVATE_API !== 'false';
