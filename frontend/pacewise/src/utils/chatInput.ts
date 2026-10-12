import type { KeyboardEvent } from 'react';

/** Run the same send action as the button without relying on requestSubmit(). */
export function submitChatOnEnter(event: KeyboardEvent<HTMLTextAreaElement>, send: () => void) {
  if (
    event.key !== 'Enter'
    || event.shiftKey
    || event.repeat
    || event.nativeEvent.isComposing
    || event.keyCode === 229
  ) return;
  event.preventDefault();
  send();
}
