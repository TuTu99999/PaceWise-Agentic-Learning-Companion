import { describe, expect, it } from 'vitest';

import { initialState } from '../src/store/AppStore';

describe('production initial state', () => {
  it('does not expose seeded learner activity as real data', () => {
    expect(initialState.plan).toBeNull();
    expect(initialState.sessions).toEqual([]);
    expect(initialState.quickChecks).toEqual([]);
    expect(initialState.guidance).toEqual([]);
    expect(initialState.settings.lastSync).toBe('');
  });
});
