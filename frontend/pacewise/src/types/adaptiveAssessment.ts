export interface AdaptiveCheckpoint {
  session_id: string;
  status: 'active' | 'needs_support' | 'verification_required' | 'review_required' | 'stopped' | 'completed' | 'coverage_gap';
  stage: 'recall' | 'explain' | 'why' | 'application' | 'transfer';
  mode: 'learning' | 'retention';
  probe_id?: string | null;
  kc_id: string;
  hint_level: number;
  hint: string;
  attempts: number;
  reason: string;
  blocks_planning?: false;
  blocks_learning?: false;
  verification_count?: number;
  verification_limit?: number;
  review?: { status: 'accepted' | 'verifying' | 'pending_review' | 'abstained'; reason: string; case_id?: string | null; resolved_case_ids?: string[] };
  question: { id: string; text: string; source: string; version: number; origin?: 'approved_anchor' | 'verified_template' | 'llm_formative'; formative_only?: boolean } | null;
  coverage_gap?: string | null;
  delayed_probe?: { id: string; due_at: string; status: string };
  last_result?: {
    feedback: string;
    confidence: string;
    demonstrated_level: string;
    provisional?: boolean;
    requires_instructor_review: boolean;
    evidence_ids: string[];
    criterion_scores: Array<{ criterion_id: string; score: number; evidence_quote: string }>;
  };
}

export interface DelayedProbe {
  id: string;
  kc_id: string;
  due_at: string;
}
