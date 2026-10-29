import { describe, expect, it } from 'vitest';
import { replanHref } from './replanNavigation';

describe('replanHref', () => {
  it('hands a confirmed activity reflection back to Plan', () => {
    expect(replanHref('reflection', { scope: 'activity' })).toBe(
      '/plan?reanalyze=reflection&scope=activity',
    );
  });

  it('keeps contextual values encoded', () => {
    expect(replanHref('lms', { taskId: 'course:task 1', impactId: 'new?item' })).toBe(
      '/plan?reanalyze=lms&taskId=course%3Atask+1&impactId=new%3Fitem',
    );
  });

  it('routes changed study preferences through weekly Plan review', () => {
    expect(replanHref('preferences', { scope: 'weekly' })).toBe(
      '/plan?reanalyze=preferences&scope=weekly',
    );
  });
});
