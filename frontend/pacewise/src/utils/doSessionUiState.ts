export type DoAssistantMode = 'learn' | 'assess';

function storageKey(userId: string | number | undefined, blockId: string | undefined) {
  if (userId === undefined || !blockId) return '';
  return `pacewise:do-ui:${userId}:${blockId}`;
}

export function readDoAssistantMode(
  userId: string | number | undefined,
  blockId: string | undefined,
): DoAssistantMode {
  const key = storageKey(userId, blockId);
  if (!key) return 'learn';
  try {
    return window.sessionStorage.getItem(key) === 'assess' ? 'assess' : 'learn';
  } catch {
    return 'learn';
  }
}

export function writeDoAssistantMode(
  userId: string | number | undefined,
  blockId: string | undefined,
  mode: DoAssistantMode,
) {
  const key = storageKey(userId, blockId);
  if (!key) return;
  try { window.sessionStorage.setItem(key, mode); } catch { /* UI preference can remain in memory. */ }
}

export function clearDoAssistantMode(userId: string | number | undefined, blockId: string | undefined) {
  const key = storageKey(userId, blockId);
  if (!key) return;
  try { window.sessionStorage.removeItem(key); } catch { /* Nothing sensitive is retained. */ }
}
