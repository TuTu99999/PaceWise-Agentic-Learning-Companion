import type {
  AssessmentItem,
  AvailabilityDay,
  AuditEntry,
  CanvasSyncResult,
  ClassGuidance,
  ClassGroup,
  GroupStats,
  LMSInstructorSummary,
  Drift,
  DoBlocker,
  DoCheckpointResult,
  DoSessionEvaluation,
  DoSessionPreparation,
  Plan,
  PlanDraft,
  PlanImpact,
  PlanInput,
  ReviewItem,
  RecoveryOption,
  Source,
  StudySession,
  Task,
  UnavailableSlot,
  User,
  WeeklyGoal,
  CourseMaterialSummary,
  MaterialPreview,
  InstructorWorkspace,
  DurableStudySession, InterruptionReason, LengthFeeling, RhythmReport,
  DoWorkResult, UnderstandingSelfReport,
} from '../types';
import type { QAResult } from '../utils/qa';
import type { AdaptiveCheckpoint, DelayedProbe } from '../types/adaptiveAssessment';
import { encryptedFetch, privateApiEnabled } from './privateApi';
import { standaloneCourses } from './courseSource';
export { standaloneCourses, coursePdfMaxMb } from './courseSource';

const API_BASE = (import.meta.env.VITE_API_URL || '/api/v1').replace(/\/$/, '');

export interface PdfUploadReceipt { fileId: number; duplicate: boolean }
export type CourseDocumentRole = 'learning_material' | 'student_assignment_brief' | 'student_rubric' | 'mixed_assignment_package' | 'teacher_solution';

type UploadTicket = {
  uploadMode: 'proxy' | 's3';
  receiptToken: string;
  uploadPath?: string;
  uploadUrl?: string;
  uploadHeaders?: Record<string, string>;
};

async function sha256Hex(file: File) {
  const digest = await crypto.subtle.digest('SHA-256', await file.arrayBuffer());
  return [...new Uint8Array(digest)].map((part) => part.toString(16).padStart(2, '0')).join('');
}

export async function uploadTeacherDocument(courseId: string, file: File, chapter: string, contentRole: CourseDocumentRole): Promise<PdfUploadReceipt | undefined> {
  if (!standaloneCourses) {
    if (!file.name.toLowerCase().endsWith('.pdf')) throw new Error('Nguồn LMS ngoài hiện chỉ hỗ trợ PDF.');
    const bytes = new Uint8Array(await file.arrayBuffer()); let binary = '';
    for (let offset = 0; offset < bytes.length; offset += 8192) binary += String.fromCharCode(...bytes.subarray(offset, offset + 8192));
    await writeTeacherManagement(courseId, 'pdf', { filename: file.name, data_base64: btoa(binary), chapter });
    return;
  }
  const checksumSha256 = await sha256Hex(file);
  const ticket = await request<UploadTicket>(`/instructor/manage/courses/${encodeURIComponent(courseId)}/document-ticket`, {
    method: 'POST', body: JSON.stringify({ filename: file.name, chapter, size: file.size, checksumSha256, content_role: contentRole }),
  });
  const contentType = file.name.toLowerCase().endsWith('.docx')
    ? 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    : 'application/pdf';
  let response: Response;
  if (ticket.uploadMode === 's3') {
    const target = new URL(ticket.uploadUrl ?? '');
    if (target.protocol !== 'https:' || target.username || target.password) throw new Error('Lượt tải S3 không hợp lệ.');
    response = await fetch(target, {
      method: 'PUT',
      body: file,
      headers: ticket.uploadHeaders ?? { 'Content-Type': contentType },
      credentials: 'omit',
    });
  } else {
    // Only the exact same-origin binary capability path is allowed, never a URL
    // supplied by a course record. Metadata/ticket requests remain encrypted.
    if (!/^\/api\/v1\/private\/uploads\/[A-Za-z0-9_-]{40,100}$/.test(ticket.uploadPath ?? '')) throw new Error('Lượt tải không hợp lệ.');
    const csrf = cookie('pacewise_csrf');
    response = await fetch(ticket.uploadPath!, { method: 'PUT', credentials: 'include', body: file,
      headers: { 'Content-Type': contentType, ...(csrf ? { 'X-CSRF-Token': decodeURIComponent(csrf) } : {}) } });
  }
  if (!response.ok) {
    if (response.status === 429) throw new ApiError('RATE_LIMITED', 'Hàng chờ tải đang đầy. Hãy thử lại sau.', undefined, Number(response.headers.get('Retry-After')) || 5);
    throw new Error(response.status === 413 ? 'File vượt giới hạn dung lượng.' : 'Không tải được tài liệu. Hãy thử lại.');
  }
  return request<PdfUploadReceipt>(`/instructor/manage/courses/${encodeURIComponent(courseId)}/document-receipt`, {
    method: 'POST', body: JSON.stringify({ token: ticket.receiptToken }),
  });
}

export const uploadTeacherPdf = (courseId: string, file: File, chapter: string) =>
  uploadTeacherDocument(courseId, file, chapter, 'learning_material');

export interface StudyTimerCommand {
  action: 'checkpoint' | 'pause' | 'resume' | 'recover' | 'complete' | 'cancel';
  eventKey: string; expectedVersion: number; interruptionReason?: InterruptionReason;
  completionPercent?: number; lengthFeeling?: LengthFeeling; blocker?: DoBlocker; note?: string; outsideMinutes?: number;
  workResult?: DoWorkResult; additionalMinutes?: number; understandingSelfReport?: UnderstandingSelfReport;
}
export const getStudyTimer = (blockId: string) => request<{ session: DurableStudySession | null; activeSession?: DurableStudySession | null }>(`/study-sessions/current?blockId=${encodeURIComponent(blockId)}`);
export const startStudyTimer = (courseId: string, blockId: string) => request<DurableStudySession>('/study-sessions', { method: 'POST', body: JSON.stringify({ courseId: Number(courseId), blockId }) });
export const updateStudyTimer = (id: string, command: StudyTimerCommand) => request<DurableStudySession>(`/study-sessions/${encodeURIComponent(id)}/events`, { method: 'POST', body: JSON.stringify(command) });
export const getRhythmProposal = () => request<RhythmReport>('/study-sessions/rhythm/proposal');
export const confirmRhythmProposal = (proposalId: string) => request<{ preferences: RhythmReport['current']; scope: { courseId: number; activityType: NonNullable<RhythmReport['proposal']>['activityType'] }; planChanged: false }>('/study-sessions/rhythm/confirm', { method: 'POST', body: JSON.stringify({ proposalId }) });

export interface LmsFileIndexStatus {
  id: number;
  title: string;
  status: string;
  chunk_count: number;
  error: string;
  updated_at: string;
  version?: string;
  view_url?: string;
}

export function fetchLmsFileIndexStatus(courseId: string, signal?: AbortSignal) {
  return request<{ files: LmsFileIndexStatus[] }>(`/instructor/lms-files/status?course_id=${encodeURIComponent(courseId)}`, { signal });
}
export const retryLmsFileIndex = (courseId: string, fileId: number, expectedVersion: string) =>
  request<{ status: string }>(`/instructor/lms-files/${encodeURIComponent(courseId)}/${fileId}/retry`, {
    method: 'POST', body: JSON.stringify({ expectedVersion }),
  });

export class ApiError extends Error {
  constructor(
    public code: 'AI_UNAVAILABLE' | 'TIMEOUT' | 'INVALID_CREDENTIALS' | 'UNAUTHENTICATED' | 'FORBIDDEN' | 'CONFLICT' | 'RATE_LIMITED' | 'UPSTREAM' | 'UNKNOWN',
    message: string,
    public requestId = `PW-REQ-${Math.random().toString(16).slice(2, 8).toUpperCase()}`,
    public retryAfterSeconds?: number,
  ) {
    super(message);
  }
}

function cookie(name: string) {
  return document.cookie
    .split('; ')
    .find((item) => item.startsWith(`${name}=`))
    ?.split('=')
    .slice(1)
    .join('=');
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method || 'GET').toUpperCase();
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json');
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    const csrf = cookie('pacewise_csrf');
    if (csrf) headers.set('X-CSRF-Token', decodeURIComponent(csrf));
  }
  let response: Response;
  try {
    response = privateApiEnabled
      ? await encryptedFetch(API_BASE, path, { ...init, headers })
      : await fetch(`${API_BASE}${path}`, { ...init, headers, credentials: 'include' });
  } catch (error) {
    if (init.signal?.aborted) throw error;
    throw new ApiError('UPSTREAM', 'Không thể kết nối PaceWise API.');
  }
  if (!response.ok) {
    const payload = (await response.json().catch(() => ({}))) as { detail?: string | { message?: string; retry_after_seconds?: number } };
    const code = response.status === 401
      ? ['/auth/login', '/auth/lms-login'].includes(path) ? 'INVALID_CREDENTIALS' : 'UNAUTHENTICATED'
      : response.status === 403 ? 'FORBIDDEN'
      : response.status === 409 ? 'CONFLICT'
      : response.status === 429 || (response.status === 503 && response.headers.has('Retry-After')) ? 'RATE_LIMITED'
      : response.status >= 502 ? 'UPSTREAM'
      : 'UNKNOWN';
    const message = response.status >= 500 ? 'Dịch vụ tạm thời chưa sẵn sàng. Vui lòng thử lại.'
      : code === 'INVALID_CREDENTIALS' ? 'Email hoặc mật khẩu không đúng.'
      : typeof payload.detail === 'string' ? payload.detail
      : payload.detail?.message ? payload.detail.message : 'Dữ liệu yêu cầu không hợp lệ.';
    const retry = Number(response.headers.get('Retry-After')) || (typeof payload.detail === 'object' ? payload.detail.retry_after_seconds : undefined) || 0;
    throw new ApiError(code, message, response.headers.get('X-Request-ID') || undefined,
      code === 'RATE_LIMITED' && Number.isFinite(retry) && retry > 0 ? retry : undefined);
  }
  return (await response.json()) as T;
}

async function requestBlob(path: string, body: unknown): Promise<Blob> {
  const headers = new Headers({ 'Content-Type': 'application/json' });
  const csrf = cookie('pacewise_csrf');
  if (csrf) headers.set('X-CSRF-Token', decodeURIComponent(csrf));
  let response: Response;
  try {
    const options: RequestInit = {
      method: 'POST',
      headers,
      credentials: 'include',
      body: JSON.stringify(body),
    };
    response = privateApiEnabled ? await encryptedFetch(API_BASE, path, options) : await fetch(`${API_BASE}${path}`, options);
  } catch {
    throw new ApiError('UPSTREAM', 'Không thể kết nối PaceWise API.');
  }
  if (!response.ok) {
    const payload = (await response.json().catch(() => ({}))) as { detail?: string };
    throw new ApiError('UNKNOWN', response.status >= 500 ? 'Dịch vụ tạm thời chưa sẵn sàng.'
      : typeof payload.detail === 'string' ? payload.detail : 'Dữ liệu yêu cầu không hợp lệ.');
  }
  return response.blob();
}

export async function login(email: string, password: string, courseId?: number): Promise<User> {
  const result = await request<{ user: User }>(standaloneCourses ? '/auth/login' : '/auth/lms-login', {
    method: 'POST',
    body: JSON.stringify({ email, password, course_id: courseId }),
  });
  announceAuthChange();
  return result.user;
}

export function getGoogleSignInStatus(): Promise<{ configured: boolean }> {
  return request('/auth/google/status');
}

export function startGoogleSignIn(): Promise<{ authorizationUrl: string }> {
  return request('/auth/google/start', { method: 'POST', body: JSON.stringify({}) });
}

export async function loginWithLaunch(token: string): Promise<User> {
  const result = await request<{ user: User }>('/auth/lms-launch', {
    method: 'POST',
    body: JSON.stringify({ token }),
  });
  announceAuthChange();
  return result.user;
}

export async function getCurrentSession(): Promise<User | null> {
  try {
    return (await request<{ user: User }>('/auth/me')).user;
  } catch (error) {
    if (error instanceof ApiError && error.code === 'UNAUTHENTICATED') return null;
    throw error;
  }
}

export async function logout(): Promise<{ linkedLmsRevoked: boolean; studySessionPaused?: boolean } | undefined> {
  try {
    const result = await request<{ ok: boolean; linkedLmsRevoked: boolean; studySessionPaused: boolean }>('/auth/logout', { method: 'POST' });
    announceAuthChange();
    return result;
  } catch (error) {
    if (!(error instanceof ApiError) || error.code !== 'UNAUTHENTICATED') throw error;
  }
}

function announceAuthChange() {
  try { window.localStorage.setItem('pacewise:auth-change', `${Date.now()}:${Math.random()}`); }
  catch { /* Session correctness does not depend on optional browser storage. */ }
}

export function createLmsBrowserBridge(): Promise<{ code: string; expires_in: number }> {
  return request('/auth/lms-bridge', { method: 'POST' });
}

export async function switchCourse(courseId: string): Promise<{ courseId: string }> {
  return request<{ courseId: string }>('/auth/course', {
    method: 'POST',
    body: JSON.stringify({ courseId: Number(courseId) }),
  });
}

export async function loadWorkspace(): Promise<{ state: Record<string, unknown>; version: number; updatedAt: string | null }> {
  return request<{ state: Record<string, unknown>; version: number; updatedAt: string | null }>('/workspace');
}

export async function saveWorkspace(state: Record<string, unknown>, expectedVersion: number): Promise<{ version: number; updatedAt: string }> {
  return request<{ version: number; updatedAt: string }>('/workspace', {
    method: 'PUT',
    body: JSON.stringify({ state, expectedVersion }),
  });
}

export async function saveInstructorAction(
  actionType: 'review' | 'assessment' | 'guidance' | 'schedule' | 'course_structure' | 'feedback' | 'settings',
  entityId: string,
  payload: Record<string, unknown>,
): Promise<{ id: string; createdAt: string; payload: Record<string, unknown> }> {
  return request('/instructor/actions', {
    method: 'POST',
    body: JSON.stringify({ actionType, entityId, payload }),
  });
}

export function deleteAssessmentDesign(entityId: string): Promise<{ entityId: string; deleted: boolean; retainedAudit: boolean }> {
  return request(`/instructor/assessment/${encodeURIComponent(entityId)}`, { method: 'DELETE' });
}

export interface GoogleCalendarStatus {
  health?: 'connected' | 'disconnected' | 'degraded' | 'not_configured';
  error?: string | null;
  configured: boolean;
  connected: boolean;
  calendarId: string | null;
  connectedAt: string | null;
  lastFreeBusySyncAt: string | null;
  accountEmail: string | null;
}

export interface PushStatus {
  configured: boolean;
  publicKey: string | null;
  subscribed: boolean;
}
export function getPushStatus(): Promise<PushStatus> { return request('/notifications/push'); }
export function registerPush(subscription: PushSubscriptionJSON): Promise<{ ok: boolean }> {
  return request('/notifications/push', { method: 'POST', body: JSON.stringify(subscription) });
}
export function unregisterPush(): Promise<{ ok: boolean }> {
  return request('/notifications/push', { method: 'DELETE' });
}
export function claimReminders(ids: string[]): Promise<{ ids: string[] }> {
  return request('/notifications/claim', { method: 'POST', body: JSON.stringify({ ids }) });
}

export async function previewQuestionDesign(design: NonNullable<AssessmentItem['questionDesign']>, rubric: string[], source: string): Promise<{ saved: boolean; course_id: number; examples: Array<{ stage: string; question: string; expected_facts: { holds: boolean; minimal_additions: string[][] } }> }> {
  return request('/instructor/assessment/design-preview', { method: 'POST', body: JSON.stringify({ design, rubric, source }) });
}

export interface GoogleBusyResult {
  busy: { start: string; end: string }[];
  unavailableSlots: UnavailableSlot[];
}

export interface CalendarExportBlock {
  blockId: string;
  title: string;
  start: string;
  end: string;
}

export async function getGoogleCalendarStatus(): Promise<GoogleCalendarStatus> {
  return request<GoogleCalendarStatus>('/integrations/google-calendar/status');
}

export async function connectGoogleCalendar(): Promise<{ authorizationUrl: string }> {
  return request<{ authorizationUrl: string }>('/integrations/google-calendar/connect', { method: 'POST' });
}

export async function syncGoogleCalendarBusy(timeMin: string, timeMax: string): Promise<GoogleBusyResult> {
  return request<GoogleBusyResult>('/integrations/google-calendar/freebusy', {
    method: 'POST',
    body: JSON.stringify({ timeMin, timeMax, timeZone: 'Asia/Ho_Chi_Minh' }),
  });
}

export async function exportPlanToGoogleCalendar(
  blocks: CalendarExportBlock[],
): Promise<{ created: Array<{ blockId: string; eventId: string; htmlLink?: string }>; skipped: string[] }> {
  return request('/integrations/google-calendar/events', {
    method: 'POST',
    body: JSON.stringify({ confirmed: true, timeZone: 'Asia/Ho_Chi_Minh', blocks }),
  });
}

export async function downloadPlanIcs(blocks: CalendarExportBlock[]): Promise<Blob> {
  return requestBlob('/calendar/pacewise-study-plan.ics', {
    calendarName: 'PaceWise Study Plan',
    blocks,
  });
}

export async function disconnectGoogleCalendar(): Promise<void> {
  await request('/integrations/google-calendar', { method: 'DELETE' });
}

export interface AgentResponse {
  response: string;
  workflow: 'plan' | 'do' | 'tracking' | 'qa' | 'understanding' | 'recover' | 'reflect';
  mode?: string;
  status: string;
  pending_action?: Record<string, unknown> | null;
  proposed_milestones?: Array<Record<string, unknown>>;
  output?: {
    replan_decision?: { action: 'keep' | 'propose_draft'; reasons: string[]; requires_confirmation: boolean; auto_apply: false };
    plan_validation?: { valid: boolean; errors: { code: string }[] };
    plan_draft?: PlanDraft;
    confirmed_plan?: PlanDraft;
    weekly_goals?: WeeklyGoal[];
    do_session?: DoSessionPreparation | DoSessionEvaluation;
    citation_dispute?: { dispute_id: string };
    learning_evidence?: Record<string, unknown>;
    knowledge_state?: Array<Record<string, unknown>>;
  } | null;
  progress_metrics?: Record<string, unknown>;
  risk_signals?: Array<Record<string, unknown>>;
  assessment_result?: {
    assessment_id?: string;
    status?: string;
    confidence?: string;
    evidence_quotes?: string[];
    rubric_version?: number;
    demonstrated_level?: string;
    knowledge_component_ids?: string[];
    evidence_ids?: string[];
    provisional?: boolean;
  } | null;
  review_case_id?: string | null;
  recovery_options?: Array<Record<string, unknown>>;
  reflection_draft?: Record<string, unknown> | null;
  source_refs: Array<{
    id?: string;
    citation: string;
    document_title?: string;
    page?: number | string;
    paragraph?: number | string;
    excerpt?: string;
    material_id?: string;
    download_url?: string;
    preview_url?: string;
    section_title?: string;
    location_detail?: string;
    file_name?: string;
  }>;
}

async function runAgent(
  message: string,
  workflow: AgentResponse['workflow'],
  context: Record<string, unknown> = {},
  options?: {
    signal?: AbortSignal;
    history?: Array<{ role: 'user' | 'assistant'; content: string }>;
    locale?: 'vi' | 'en';
  },
): Promise<AgentResponse> {
  return request<AgentResponse>('/chat', {
    method: 'POST',
    body: JSON.stringify({ message, workflow, locale: options?.locale ?? 'vi', context, qa_history: options?.history ?? [] }),
    signal: options?.signal,
  });
}

interface QAStreamOptions {
  signal?: AbortSignal;
  history?: Array<{ role: 'user' | 'assistant'; content: string }>;
  onDelta?: (delta: string) => void;
  onStatus?: (message: string) => void;
  locale?: 'vi' | 'en';
}

async function runStreamingQA(
  message: string,
  context: Record<string, unknown>,
  options: QAStreamOptions = {},
): Promise<AgentResponse> {
  const headers = new Headers({ 'Content-Type': 'application/json', Accept: 'application/x-ndjson' });
  const csrf = cookie('pacewise_csrf');
  if (csrf) headers.set('X-CSRF-Token', decodeURIComponent(csrf));
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/chat/stream`, {
      method: 'POST',
      headers,
      credentials: 'include',
      signal: options.signal,
      body: JSON.stringify({ message, workflow: 'qa', locale: options.locale ?? 'vi', context, qa_history: options.history ?? [] }),
    });
  } catch (error) {
    if (options.signal?.aborted) throw error;
    throw new ApiError('UPSTREAM', 'Không thể kết nối PaceWise API.');
  }
  if (!response.ok || !response.body) {
    const payload = (await response.json().catch(() => ({}))) as {
      detail?: string | { message?: string; retry_after_seconds?: number };
    };
    const code = response.status === 401 ? 'UNAUTHENTICATED'
      : response.status === 403 ? 'FORBIDDEN'
      : response.status === 429 || response.status === 503 ? 'RATE_LIMITED'
      : response.status >= 500 ? 'UPSTREAM' : 'UNKNOWN';
    const message = typeof payload.detail === 'string'
      ? payload.detail
      : payload.detail?.message || 'Chưa thể mở luồng trả lời.';
    const retry = Number(response.headers.get('Retry-After'))
      || (typeof payload.detail === 'object' ? payload.detail.retry_after_seconds : undefined)
      || 0;
    throw new ApiError(code, message, response.headers.get('X-Request-ID') || undefined,
      code === 'RATE_LIMITED' && retry > 0 ? retry : undefined);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let pending = '';
  let finalResult: AgentResponse | undefined;
  // A provider may place several model deltas in one TCP packet. Without a
  // paint boundary React batches every setState from that packet and the user
  // sees the whole answer appear at once even though the server did stream it.
  // Preserve the provider's text exactly, but give each received delta one
  // frame to become visible before accepting the final event.
  const paintBoundary = () => new Promise<void>((resolve) => {
    if (typeof window !== 'undefined' && typeof window.requestAnimationFrame === 'function'
      && document.visibilityState !== 'hidden') {
      window.requestAnimationFrame(() => resolve());
      return;
    }
    window.setTimeout(resolve, 0);
  });
  const consume = async (line: string) => {
    if (!line.trim()) return;
    const event = JSON.parse(line) as {
      type: 'status' | 'delta' | 'final' | 'error'; message?: string; text?: string;
      result?: AgentResponse; status?: number; detail?: string;
    };
    if (event.type === 'delta' && event.text) {
      options.onDelta?.(event.text);
      if (options.onDelta) await paintBoundary();
    }
    if (event.type === 'status' && event.message) options.onStatus?.(event.message);
    if (event.type === 'final' && event.result) finalResult = event.result;
    if (event.type === 'error') {
      throw new ApiError(event.status === 429 ? 'RATE_LIMITED' : event.status === 403 ? 'FORBIDDEN' : 'UPSTREAM',
        event.detail || 'Dịch vụ AI tạm thời chưa sẵn sàng.');
    }
  };
  while (true) {
    const { value, done } = await reader.read();
    pending += decoder.decode(value, { stream: !done });
    const lines = pending.split('\n');
    pending = lines.pop() ?? '';
    for (const line of lines) await consume(line);
    if (done) break;
  }
  await consume(pending);
  if (!finalResult) throw new ApiError('UPSTREAM', 'Luồng trả lời kết thúc trước khi được kiểm tra.');
  return finalResult;
}

function fold(value: string) {
  return value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
}

export async function trackProgress(
  plan: Plan | null,
  availability: AvailabilityDay[],
  unavailable: UnavailableSlot[],
  tasks: Task[] = [],
  sessions: StudySession[] = [],
): Promise<AgentResponse> {
  return runAgent('Kiểm tra tiến độ hiện tại và cảnh báo deadline có rủi ro.', 'tracking', {
    current_plan: plan,
    availability,
    unavailable_slots: unavailable,
    progress_metrics: {
      tasks: tasks.map((task) => ({
        id: task.id,
        estimate_min: task.estimateMin,
        logged_min: task.loggedMin,
        status: task.status,
      })),
      session_count: sessions.length,
      studied_minutes: sessions.reduce((total, session) => total + session.minutes, 0),
    },
  });
}

export interface UnderstandingResult {
  evidenceState: 'demonstrated' | 'developing' | 'misconception' | 'abstained';
  confidence: 'high' | 'medium' | 'low';
  feedback: string;
  requiresInstructorReview: boolean;
  evidenceQuotes: string[];
  rubricVersion?: number;
  reviewCaseId?: string;
}

export async function assessUnderstanding(assessment: AssessmentItem, answer: string): Promise<UnderstandingResult> {
  const result = await runAgent(answer, 'understanding', {
    assessment_id: assessment.id,
  });
  const assessmentResult = result.assessment_result ?? {};
  const status = fold(assessmentResult.status ?? '');
  const confidence = fold(assessmentResult.confidence ?? '');
  const requiresInstructorReview = result.status === 'awaiting_teacher';
  return {
    evidenceState: requiresInstructorReview
      ? 'abstained'
      : status.includes('the hien')
      ? 'demonstrated'
      : status.includes('hinh thanh')
        ? 'developing'
        : status.includes('nham lan')
          ? 'misconception'
          : 'abstained',
    confidence: confidence.includes('cao') || confidence.includes('high')
      ? 'high'
      : confidence.includes('trung') || confidence.includes('medium')
        ? 'medium'
        : 'low',
    feedback: result.response,
    requiresInstructorReview,
    evidenceQuotes: assessmentResult.evidence_quotes ?? [],
    rubricVersion: assessmentResult.rubric_version,
    reviewCaseId: result.review_case_id ?? undefined,
  };
}

export async function generateRecoveryOptions(
  plan: Plan,
  tasks: Task[],
  drift: Drift,
  availability: AvailabilityDay[],
  unavailable: UnavailableSlot[],
  impact?: PlanImpact,
): Promise<RecoveryOption[]> {
  const result = await runAgent(
    `Kế hoạch đang thiếu ${drift.deficitMin} phút cho nhiệm vụ ${drift.taskId} trước deadline ${drift.deadline}.`,
    'recover',
    {
      current_plan: plan,
      progress_metrics: { drift, plan_impact: impact },
      availability,
      unavailable_slots: unavailable,
      proposed_milestones: tasks.map((task) => ({
        milestone_id: task.id,
        title: task.title,
        course_id: task.courseId,
        priority: task.priority,
        assignment_group: task.assignmentGroup
          ? {
              id: task.assignmentGroup.id,
              name: task.assignmentGroup.name,
              weight: task.assignmentGroup.weight,
            }
          : null,
        points_possible: task.pointsPossible ?? 0,
        estimated_minutes: Math.max(0, task.estimateMin - task.loggedMin),
        deadline: task.deadline,
      })),
    },
  );
  return (result.recovery_options ?? []).map((raw, index) => ({
    id: String(raw.id ?? String.fromCharCode(65 + index)) as RecoveryOption['id'],
    title: String(raw.title ?? raw.option_name ?? `Phương án ${index + 1}`),
    summary: String(raw.summary ?? raw.remaining_risks ?? ''),
    changes: Array.isArray(raw.changes) ? raw.changes.map(String) : [],
    impact: String(raw.impact ?? raw.remaining_risks ?? ''),
    time: String(raw.time ?? `${raw.hours_short_or_free ?? 0} giờ`),
    tradeoff: String(raw.tradeoff ?? raw.remaining_risks ?? ''),
    newBlocks: Array.isArray(raw.new_blocks) ? raw.new_blocks as RecoveryOption['newBlocks'] : plan.blocks,
    assumptions: Array.isArray(raw.assumptions) ? raw.assumptions.map(String) : [],
    fullyRecovers: Boolean(raw.fully_recovers),
    workloadMinutes: typeof raw.workload_minutes === 'number' ? raw.workload_minutes : undefined,
    scheduledMinutes: typeof raw.scheduled_minutes === 'number' ? raw.scheduled_minutes : undefined,
    missingMinutes: typeof raw.missing_minutes === 'number' ? raw.missing_minutes : undefined,
    shortfalls: Array.isArray(raw.shortfalls)
      ? raw.shortfalls.flatMap((item) => {
          if (!item || typeof item !== 'object') return [];
          const value = item as Record<string, unknown>;
          const taskId = String(value.taskId ?? value.task_id ?? '');
          const missingMin = Number(value.missingMin ?? value.missing_min ?? 0);
          return taskId && Number.isFinite(missingMin) && missingMin > 0 ? [{ taskId, missingMin }] : [];
        })
      : [],
  }));
}

export async function confirmRecovery(optionId: string): Promise<void> {
  await runAgent(`Tôi xác nhận phương án ${optionId}.`, 'recover');
}

export async function createReflection(
  answers: [string, string, string],
  progressMetrics: Record<string, unknown>,
  locale: 'vi' | 'en' = 'vi',
): Promise<AgentResponse> {
  const activityReflection = progressMetrics.reflection_scope === 'activity';
  return runAgent(
    locale === 'en'
      ? activityReflection
        ? `Activity outcome: ${answers[0]}\nWhat helped or caused difficulty: ${answers[1]}\nNext step: ${answers[2]}`
        : `What worked: ${answers[0]}\nReason for plan drift: ${answers[1]}\nAdjustment for next week: ${answers[2]}`
      : activityReflection
        ? `Kết quả sau hoạt động: ${answers[0]}\nĐiều hỗ trợ hoặc gây khó khăn: ${answers[1]}\nBước tiếp theo: ${answers[2]}`
        : `Điều hiệu quả: ${answers[0]}\nNguyên nhân lệch: ${answers[1]}\nĐiều chỉnh tuần sau: ${answers[2]}`,
    'reflect',
    { progress_metrics: progressMetrics, reflection_course_id: (progressMetrics.activity as { course_id?: string } | undefined)?.course_id },
    { locale },
  );
}

export async function confirmReflection(scope: 'weekly' | 'activity' = 'weekly', courseId?: string, locale: 'vi' | 'en' = 'vi'): Promise<AgentResponse> {
  return runAgent(
    scope === 'activity' ? 'Tôi xác nhận và lưu ghi nhận sau hoạt động này.' : 'Tôi xác nhận điều chỉnh cho tuần sau.',
    'reflect',
    { reflection_course_id: courseId },
    { locale },
  );
}

export async function generatePlan(input: PlanInput, tasks: Task[]): Promise<PlanDraft> {
  const selected = input.tasks
    .map((item) => tasks.find((task) => task.id === item.taskId)?.title)
    .filter(Boolean)
    .join(', ');
  const agentResult = await runAgent(
    `Lập kế hoạch từ hiện tại đến hết tuần sau cho các mục tiêu đã xác nhận. Các nhiệm vụ đã chọn: ${selected}.`,
    'plan',
    {
      availability: input.availability
        .filter((item) => item.enabled)
        .map((item) => ({ day: String(item.weekday), start: item.start, end: item.end })),
      unavailable_slots: input.unavailable.map((item) => ({
        id: item.id,
        label: item.label,
        day: String(item.weekday),
        date: item.date,
        start: item.start,
        end: item.end,
        source: item.source,
        category: item.category,
      })),
      goals: input.tasks.map((item) => {
        const task = tasks.find((candidate) => candidate.id === item.taskId);
        return {
          task_id: item.taskId,
          title: task?.title ?? item.taskId,
          course_id: task?.courseId,
          deadline: task?.deadline,
          remaining_minutes: item.remainingMin,
          weekly_goal_id: item.weeklyGoalId,
          weekly_goal: input.weeklyGoals?.find((goal) => goal.id === item.weeklyGoalId)?.title ?? input.goal,
        };
      }),
      plan_input: input,
    },
  );
  const draft = agentResult.output?.plan_draft;
  if (!draft) {
    throw new ApiError('UPSTREAM', 'Backend không trả về lịch học chuẩn hóa.');
  }
  return {
    ...draft,
    reasons: [agentResult.response, ...draft.reasons],
  };
}

export async function proposeWeeklyGoals(tasks: Task[]): Promise<WeeklyGoal[]> {
  const candidates = tasks
    .filter((task) => task.status !== 'done')
    .map((task) => ({
      task_id: task.id,
      title: task.title,
      course_id: task.courseId,
      deadline: task.deadline,
      assignment_group_weight: task.assignmentGroup?.weight ?? 0,
      points_possible: task.pointsPossible ?? 0,
    }));
  const result = await runAgent(
    'Đề xuất mục tiêu tự học cho tuần này từ các deadline đang mở.',
    'plan',
    { planning_stage: 'goal_proposal', goals: candidates },
  );
  return result.output?.weekly_goals ?? [];
}

function toQAKind(result: AgentResponse): QAResult['kind'] {
  if (result.mode === 'integrity') return 'integrity';
  if (result.mode === 'conversation') return 'conversation';
  if (result.mode === 'out_of_scope') return 'out_of_scope';
  return result.source_refs.length ? 'grounded' : 'abstained';
}

export async function askQuestion(
  question: string,
  history: Array<{ role: 'user' | 'assistant'; content: string }> = [],
  signal?: AbortSignal,
  onDelta?: (delta: string) => void,
  locale: 'vi' | 'en' = 'vi',
): Promise<QAResult> {
  const result = await runStreamingQA(question, {}, {
    history: history.slice(-4).map((turn) => ({ ...turn, content: turn.content.slice(0, 1000) })),
    signal,
    onDelta,
    locale,
  });
  const sources = result.source_refs.map(toSource);
  return {
    kind: toQAKind(result),
    text: result.response,
    citations: sources.map((item) => item.id),
    sources,
    suggestions: [],
  };
}

export async function prepareDoSession(input: {
  courseId: string;
  blockId: string;
}, signal?: AbortSignal): Promise<DoSessionPreparation> {
  return request('/study-sessions/prepare', {
    method: 'POST', signal, body: JSON.stringify({ courseId: Number(input.courseId), blockId: input.blockId }),
  });
}

export async function evaluateDoSession(input: {
  courseId: string;
  blockId: string;
  taskId: string;
  plannedMinutes: number;
  actualMinutes: number;
  completionPercent: number;
  blocker: DoBlocker;
  blockerNote?: string;
}): Promise<DoSessionEvaluation> {
  const result = await runAgent('Đánh giá kết quả phiên tự học vừa kết thúc.', 'do', {
    do_course_id: input.courseId,
    do_block_id: input.blockId,
    progress_metrics: {
      do_session: {
        action: 'complete',
        course_id: input.courseId,
        block_id: input.blockId,
        task_id: input.taskId,
        planned_minutes: input.plannedMinutes,
        actual_minutes: input.actualMinutes,
        completion_percent: input.completionPercent,
        blocker: input.blocker,
        blocker_note: input.blockerNote ?? '',
      },
    },
  });
  const evaluation = result.output?.do_session;
  if (!evaluation || evaluation.action !== 'complete') throw new ApiError('UPSTREAM', 'Do Agent chưa đánh giá được phiên học.');
  return evaluation;
}

export async function askDoQuestion(input: {
  courseId: string;
  blockId: string;
  taskTitle: string;
  objective: string;
  question: string;
}, onDelta?: (delta: string) => void, locale: 'vi' | 'en' = 'vi'): Promise<QAResult> {
  const result = await runStreamingQA(
    input.question,
    {
      do_course_id: input.courseId,
      do_block_id: input.blockId,
      do_task_title: input.taskTitle,
      do_objective: input.objective,
    },
    { onDelta, locale },
  );
  const sources = result.source_refs.map(toSource);
  return {
    kind: toQAKind(result),
    text: result.response,
    citations: sources.map((item) => item.id),
    sources,
    suggestions: [],
  };
}

export interface DurableDoChatMessage {
  id: string;
  role: 'student' | 'assistant';
  text: string;
  result?: QAResult;
}

export async function getDoChatHistory(courseId: string, blockId: string): Promise<DurableDoChatMessage[]> {
  const payload = await request<{ messages: Array<{
    id: string;
    role: 'student' | 'assistant';
    text: string;
    kind?: QAResult['kind'];
    sourceRefs?: AgentResponse['source_refs'];
  }> }>(`/study-sessions/chat?courseId=${encodeURIComponent(courseId)}&blockId=${encodeURIComponent(blockId)}`);
  return payload.messages.map((message) => {
    if (message.role === 'student') return message;
    const sources = (message.sourceRefs ?? []).map(toSource);
    return {
      ...message,
      result: {
        kind: message.kind ?? (sources.length ? 'grounded' : 'abstained'),
        text: message.text,
        citations: sources.map((source) => source.id),
        sources,
        suggestions: [],
      },
    };
  });
}

export async function assessDoCheckpoint(input: {
  courseId: string;
  blockId: string;
  assessmentId: string;
  answer: string;
  hintLevel: number;
  firstAttempt: boolean;
  eventKey: string;
}): Promise<DoCheckpointResult> {
  const result = await runAgent(input.answer, 'do', {
    assessment_id: input.assessmentId,
    do_course_id: input.courseId,
    do_block_id: input.blockId,
    progress_metrics: {
      do_session: {
        action: 'assess',
        course_id: input.courseId,
        block_id: input.blockId,
        assessment_attempt: {
          response: input.answer,
          first_attempt: input.firstAttempt,
          hint_level: input.hintLevel,
          block_id: input.blockId,
          event_key: input.eventKey,
        },
      },
    },
  });
  const assessment = result.assessment_result ?? {};
  const status = fold(assessment.status ?? '');
  const confidence = fold(assessment.confidence ?? '');
  const requiresInstructorReview = result.status === 'awaiting_teacher';
  return {
    evidenceState: requiresInstructorReview
      ? 'abstained'
      : status.includes('the hien')
        ? 'demonstrated'
        : status.includes('hinh thanh')
          ? 'developing'
          : status.includes('nham lan')
            ? 'misconception'
            : 'abstained',
    confidence: confidence.includes('cao') || confidence.includes('high')
      ? 'high'
      : confidence.includes('trung') || confidence.includes('medium')
        ? 'medium'
        : 'low',
    feedback: result.response,
    evidenceQuotes: assessment.evidence_quotes ?? [],
    demonstratedLevel: assessment.demonstrated_level,
    knowledgeComponentIds: assessment.knowledge_component_ids ?? [],
    evidenceIds: assessment.evidence_ids ?? [],
    provisional: assessment.provisional ?? true,
    requiresInstructorReview,
    reviewCaseId: result.review_case_id ?? undefined,
  };
}

export function startAdaptiveCheckpoint(input: { courseId: string; blockId: string; assessmentId: string; probeId?: string; restart?: boolean }) {
  return request<AdaptiveCheckpoint>('/do/assessment/start', {
    method: 'POST', body: JSON.stringify({ course_id: Number(input.courseId), block_id: input.blockId,
      assessment_id: input.assessmentId, probe_id: input.probeId, restart: input.restart }),
  });
}

export function getDueAssessmentProbes(courseId: string) {
  return request<DelayedProbe[]>(`/do/assessment/due?course_id=${encodeURIComponent(courseId)}`);
}

export function adaptiveCheckpointAction(input: { sessionId: string; courseId: string; action: 'hint' | 'answer'; eventKey: string; answer?: string; locale?: 'vi' | 'en' }) {
  return request<AdaptiveCheckpoint>(`/do/assessment/${encodeURIComponent(input.sessionId)}/${input.action}`, {
    method: 'POST', body: JSON.stringify({ course_id: Number(input.courseId), event_key: input.eventKey,
      answer: input.answer ?? '', locale: input.locale ?? 'vi' }),
  });
}

export async function askHint(
  history: Array<{ role: 'user' | 'assistant'; content: string }> = [],
  locale: 'vi' | 'en' = 'vi',
): Promise<QAResult> {
  const result = await runAgent(
    'Hãy gợi ý từng bước và đặt câu hỏi Socratic để tôi tự làm, không đưa đáp án hoàn chỉnh.',
    'qa',
    {},
    { history: history.slice(-4).map((turn) => ({ ...turn, content: turn.content.slice(0, 1000) })), locale },
  );
  const sources = result.source_refs.map(toSource);
  return {
    kind: 'hint',
    text: result.response,
    citations: sources.map((item) => item.id),
    sources,
    suggestions: [],
  };
}

function toSource(item: AgentResponse['source_refs'][number]): Source {
  const position = item.location_detail || [
    item.section_title ? `Mục: ${item.section_title}` : '',
    item.page !== undefined ? `Trang ${item.page}` : '',
    item.paragraph !== undefined ? `Đoạn ${item.paragraph}` : '',
  ].filter(Boolean).join(' · ');

  // Nếu item có material_id nhưng chưa có download_url, tự tạo download_url
  const downloadUrl = item.download_url || (item.material_id ? `/api/v1/materials/${item.material_id}/download` : undefined);

  return {
    id: item.id || item.citation,
    name: item.document_title || item.citation,
    location: position || item.citation,
    excerpt: item.excerpt || 'Đoạn nguồn được truy xuất từ học liệu đã duyệt của môn học.',
    materialId: item.material_id,
    downloadUrl,
    previewUrl: item.preview_url,
    sectionTitle: item.section_title,
    locationDetail: item.location_detail,
    fileName: item.file_name,
  };
}

export async function confirmPlan(draftId?: string, partialBlockIds?: string[]): Promise<PlanDraft> {
  const result = await runAgent('Tôi xác nhận kế hoạch này.', 'plan', {
    ...(draftId ? { plan_confirmation_id: draftId } : {}),
    ...(partialBlockIds ? { accept_partial_plan: true, partial_block_ids: partialBlockIds } : {}),
  });
  if (!result.output?.confirmed_plan) throw new Error('Backend chưa trả lại kế hoạch đã xác nhận. Bản nháp vẫn được giữ.');
  return result.output.confirmed_plan;
}

export async function syncCanvas(): Promise<CanvasSyncResult> {
  return request<CanvasSyncResult>('/lms/sync');
}

export function lmsEventStreamUrl(): string {
  return `${API_BASE}/lms/events/stream`;
}

export async function reportCitation(sourceId: string): Promise<{ disputeId: string }> {
  const result = await runAgent(`Khiếu nại trích dẫn [${sourceId}] vì nguồn có thể không chính xác.`, 'qa');
  const disputeId = result.output?.citation_dispute?.dispute_id;
  if (!disputeId) {
    throw new ApiError('UPSTREAM', 'Hệ thống chưa thể ghi nhận phản ánh nguồn.');
  }
  return { disputeId };
}

export interface InstructorData {
  classGroups: ClassGroup[];
  groupStats: Record<string, GroupStats>;
  reviewQueue: ReviewItem[];
  assessments: AssessmentItem[];
  audit: AuditEntry[];
  guidance: ClassGuidance[];
  privacy: { minimumGroupSize: number; containsDirectIdentifiers: boolean };
  lmsSummary: LMSInstructorSummary | null;
  teacherWorkspace: InstructorWorkspace;
}

export async function fetchInstructorData(): Promise<InstructorData> {
  return request<InstructorData>('/instructor/assessment-designs');
}

export async function fetchInstructorDashboard(courseId: string): Promise<import('../types').InstructorDashboard> {
  return request<import('../types').InstructorDashboard>(`/instructor/dashboard?course_id=${encodeURIComponent(courseId)}`);
}

export function fetchTeacherManagement(courseId: string) {
  return request<import('../types/teacherManagement').TeacherManagementData>(`/instructor/manage/courses/${encodeURIComponent(courseId)}`);
}
export const fetchManagedCourses = () => request<import('../types/teacherManagement').ManagedCourse[]>('/instructor/manage/courses');
export const fetchTeacherRoster = () => request<{ id: number; name: string }[]>('/instructor/manage/roster');
export interface CourseInvite {
  id: string; email: string; status: 'pending' | 'accepted' | 'expired' | 'revoked'; expiresAt: string;
}
export interface CourseMembers { students: { id: number; name: string }[]; invitations: CourseInvite[] }
export const fetchCourseMembers = (id: string) => request<CourseMembers>(`/instructor/manage/courses/${encodeURIComponent(id)}/members`);
export const inviteCourseStudents = (id: string, emails: string[]) => request<{ invitations: CourseInvite[]; emailSent: boolean }>(
  `/instructor/manage/courses/${encodeURIComponent(id)}/invitations`, { method: 'POST', body: JSON.stringify({ emails }) });
export const revokeCourseInvitation = (id: string, inviteId: string) => request(
  `/instructor/manage/courses/${encodeURIComponent(id)}/invitations/${encodeURIComponent(inviteId)}/revoke`, { method: 'POST' });
export const removeCourseStudent = (id: string, studentId: number) => request(
  `/instructor/manage/courses/${encodeURIComponent(id)}/members/${studentId}/remove`, { method: 'POST' });
export const addKnownCourseStudents = (id: string, studentIds: number[]) => request<{ added: number }>(
  `/instructor/manage/courses/${encodeURIComponent(id)}/members/add`, { method: 'POST', body: JSON.stringify({ student_ids: studentIds }) });
export interface MyCourseInvitation {
  id: string; courseId: number; code: string; name: string; term: string; teacher: string; expiresAt: string;
}
export const fetchMyCourseInvitations = () => request<{ invitations: MyCourseInvitation[] }>('/membership/invitations');
export const acceptMyCourseInvitation = (inviteId: string) => request<{ courseId: number; joined: boolean }>(
  `/membership/invitations/${encodeURIComponent(inviteId)}/accept`, { method: 'POST' });
export function manageCourse(target: string, payload: object, method: 'POST' | 'PUT' = 'POST') {
  return request<import('../types/teacherManagement').ManagedCourse>(`/instructor/manage/courses${target}`, { method, body: JSON.stringify(payload) });
}
export function teacherScheduleAction(action: 'preview' | 'demo-preview' | 'series-preview' | 'import-preview' | 'confirm' | 'restore', payload: object) {
  return request<import('../types/teacherManagement').SchedulePreview>(`/instructor/manage/schedule/${action}`, { method: 'POST', body: JSON.stringify(payload) });
}
export const fetchTeacherScheduleHistory = () => request<import('../types/teacherManagement').SchedulePreview[]>('/instructor/manage/schedule/history');
export function writeTeacherManagement(courseId: string, target: string, payload: object, method: 'POST' | 'PUT' = 'POST') {
  return request(`/instructor/manage/courses/${encodeURIComponent(courseId)}/${target}`, { method, body: JSON.stringify(payload) });
}
export function deleteTeacherResource(courseId: string, resourceId: number) {
  return request(`/instructor/manage/courses/${encodeURIComponent(courseId)}/resources/${resourceId}`, { method: 'DELETE' });
}
export function fetchTeacherProfile() {
  return request<import('../types/teacherManagement').TeacherProfileData>('/instructor/manage/profile');
}
export function saveTeacherProfile(payload: object) {
  return request<import('../types/teacherManagement').TeacherProfileData>('/instructor/manage/profile', { method: 'PUT', body: JSON.stringify(payload) });
}

export async function fetchCourseMaterials(courseId: string | number): Promise<CourseMaterialSummary[]> {
  return request<CourseMaterialSummary[]>(`/materials/course/${courseId}`);
}

export async function fetchInstructorMaterials(courseId: string | number): Promise<CourseMaterialSummary[]> {
  return request<CourseMaterialSummary[]>(`/instructor/materials?course_id=${courseId}`);
}

export async function uploadCourseMaterial(
  courseId: string | number,
  file: File,
  title?: string,
  moduleName?: string,
): Promise<{ status: string; message: string; material: CourseMaterialSummary }> {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('course_id', String(courseId));
  if (title) formData.append('title', title);
  if (moduleName) formData.append('module_name', moduleName);

  return request('/instructor/materials/upload', {
    method: 'POST',
    body: formData,
  });
}

export async function deleteCourseMaterial(materialId: string): Promise<void> {
  await request(`/instructor/materials/${materialId}`, {
    method: 'DELETE',
  });
}

export async function previewCourseMaterial(materialId: string): Promise<MaterialPreview> {
  return request<MaterialPreview>(`/materials/${materialId}/preview`);
}

export function getMaterialDownloadUrl(materialId: string): string {
  return `${API_BASE}/materials/${materialId}/download`;
}

