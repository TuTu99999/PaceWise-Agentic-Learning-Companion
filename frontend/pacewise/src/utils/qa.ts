import type { QAKind, Source } from '../types';

export interface QAResult {
  kind: QAKind;
  text: string;
  citations: string[];
  sources: Source[];
  suggestions: string[];
}
