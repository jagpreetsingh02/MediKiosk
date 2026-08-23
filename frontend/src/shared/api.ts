/**
 * The single place the frontend talks to the backend.
 *
 * Every response the API sends is camelCase (the backend applies that at its boundary), so
 * nothing here renames anything. If a field arrives snake_case, that is a backend bug, not a
 * mapping to add here — a translation layer is where casing drift goes to hide.
 */

export type Tier = 'stated' | 'confirmed' | 'document';
export type Priority = 'routine' | 'urgent' | 'immediate';

export interface Option {
  value: string;
  label: string;
  labelEn: string;
  icon: string | null;
  exclusive: boolean;
}

export interface Scale {
  min: number;
  max: number;
  faces: boolean;
  anchors_en: string[];
  anchors_hi: string[];
}

export interface Question {
  turnId: string;
  questionId: string;
  path: string;
  kind: 'open_text' | 'single_choice' | 'multi_choice' | 'boolean' | 'scale' | 'duration' | 'derived';
  prompt: string;
  help: string | null;
  language: string;
  translationMissing: boolean;
  sectionId: string;
  sectionTitle: string;
  socrates: string | null;
  options: Option[];
  scale: Scale | null;
  required: boolean;
  touchOnly: boolean;
  progress: Progress;
}

export interface Progress {
  answered: number;
  askable: number;
  percent: number;
  sections: number;
}

export interface SectionProgress {
  sectionId: string;
  title: string;
  answered: number;
  total: number;
  complete: boolean;
}

export interface StepResponse {
  complete: boolean;
  question: Question | null;
  progress: Progress;
  sections: SectionProgress[];
  voice?: VoiceOutcome;
  escalation?: Escalation;
  recorded?: { factId: string; path: string; tier: Tier }[];
}

export interface VoiceOutcome {
  accepted: boolean;
  degradedToTouch: boolean;
  reason: 'unclear' | 'silence' | null;
  transcript: { text: string; confidence: number; reliable: boolean; threshold: number };
  factsRecorded: number;
  prompt: string | null;
}

export interface RedFlag {
  ruleId: string;
  label: string;
  level: 'urgent' | 'immediate';
  rationale: string;
  triggeringFactIds: string[];
}

export interface Escalation {
  priority: Priority;
  flags: RedFlag[];
  immediateCount: number;
  urgentCount: number;
}

export interface ConsentScope {
  id: string;
  required: boolean;
  title: string;
  audio: string;
}

export interface ConsentPresentation {
  policyVersion: string;
  preamble: string;
  scopes: ConsentScope[];
}

export interface Source {
  factId: string;
  tier: Tier;
  confidence: number;
  verbatim: string;
  language: string;
  kind: 'utterance' | 'document';
  questionId: string | null;
  modality: string | null;
  asrConfidence: number | null;
  documentId: string | null;
  page: number | null;
  bbox: { x: number; y: number; width: number; height: number } | null;
  handwritten: boolean | null;
}

export interface SummaryLine {
  sectionId: string;
  text: string;
  kind: 'fact' | 'structural';
  emphasis: 'immediate' | 'urgent' | 'unverified' | null;
  sources: Source[];
}

export interface SummarySection {
  sectionId: string;
  title: string;
  lines: { text: string; factIds: string[]; kind: string; tier: string | null; emphasis: string | null }[];
}

export interface Summary {
  sessionId: string;
  generatedAt: string;
  status: string;
  completeness: number;
  sections: SummarySection[];
  warnings: string[];
  notice: string;
  traceability: { ok: boolean; factLines: number; untracedLines: string[]; unsupportedTokens: unknown[] };
  lines: SummaryLine[];
  escalation: Escalation;
  history: History;
}

export interface History {
  sessionId: string;
  contradictions: Contradiction[];
  demographics: { abhaRef: string | null; ageYears: number | null; gender: string | null; language: string };
  documents: { documentId: string; filename: string; pages: number; ocrBackend: string; meanConfidence: number; lowConfidencePages: number[] }[];
  medications: { entryId: string; name: Slot; dose: Slot; frequency: Slot; coding: Coding | null }[];
  problems: { entryId: string; reportedTerm: Slot; coding: Coding | null; unmapped: boolean }[];
  declined: string[];
  notAsked: string[];
  overallCompleteness: number;
}

export interface Slot {
  path: string;
  label: string;
  value: unknown;
  status: 'recorded' | 'not_asked' | 'declined';
  tier: Tier | null;
  confidence: number | null;
  factIds: string[];
  verbatim: string | null;
  superseded: { value: unknown; verbatim: string; recordedAt: string; factId: string }[];
}

export interface Coding {
  system: string;
  version: string;
  code: string;
  display: string;
}

export interface DemoCase {
  id: string;
  title: string;
  shows: string;
  language: string;
  ayush: boolean;
  document: string | null;
  watchFor: string[];
}

export interface DemoLoadResult {
  case: DemoCase;
  sessionRef: string;
  answered: number;
  spokenTurns: number;
  degradedToTouch: number;
  factsRecorded: number;
  priority: Priority;
  redFlags: string[];
  contradictions: number;
  document: { documentId: string; factsRecorded: number; needsVerification: number } | null;
}

export interface Contradiction {
  contradictionId: string;
  ruleId: string;
  label: string;
  patientSide: ContradictionSide;
  documentSide: ContradictionSide;
  clarifyingQuestion: string | null;
  status: string;
}

export interface ContradictionSide {
  factId: string;
  path: string;
  value: unknown;
  tier: Tier;
  verbatim: string;
  confidence: number;
  origin: string;
}

export interface ReviewAnswer {
  questionId: string;
  sectionTitle: string;
  question: string;
  answer: string;
  tier: Tier;
  canCorrect: boolean;
}

export interface Inspect {
  sessionRef: string;
  stateMachine: {
    currentNode: string; currentSection: string | null; turnsTaken: number;
    askable: number; declined: number; degradedToTouch: number; note: string;
  };
  facts: {
    active: number; superseded: number; byTier: Record<string, number>;
    withoutSource: number; absences: number;
  };
  redFlags: { rulesEvaluated: number; fired: string[]; priority: string; note: string };
  contradictions: number;
  consent: { scopes: string[]; ref: string | null };
  backends: {
    llm: { name: string; offline: boolean };
    speech: { name: string; offline: boolean };
    ocr: string;
  };
  audit: { intact: boolean; events: number };
  inspectLatencyMs: number;
}

export interface QueueEntry {
  sessionRef: string;
  priority: Priority;
  status: string;
  language: string;
  ayushMode: boolean;
  createdAt: string;
  waitingMinutes: number;
}

export interface TimelinePeriod {
  period: string;
  label: string;
  events: {
    eventId: string;
    occurredOn: string | null;
    datePrecision: string;
    kind: string;
    label: string;
    detail: string | null;
    lowConfidence: boolean;
    factIds: string[];
  }[];
}

let token: string | null = sessionStorage.getItem('medikiosk.token');

export function setToken(next: string | null): void {
  token = next;
  if (next) sessionStorage.setItem('medikiosk.token', next);
  else sessionStorage.removeItem('medikiosk.token');
}

export function getToken(): string | null {
  return token;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly issueCode?: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (!(init.body instanceof FormData)) headers.set('Content-Type', 'application/json');
  if (token) headers.set('Authorization', `Bearer ${token}`);

  const response = await fetch(path, { ...init, headers });
  const text = await response.text();
  const body = text ? JSON.parse(text) : null;

  if (!response.ok) {
    // The backend returns a FHIR OperationOutcome for every domain error. Surfacing its
    // diagnostics verbatim is the whole point of that choice — the messages are written to
    // be read by a person.
    const issue = body?.issue?.[0];
    throw new ApiError(
      issue?.diagnostics ?? `Request failed (${response.status})`,
      response.status,
      issue?.code,
    );
  }
  return body as T;
}

export const api = {
  about: () => request<Record<string, unknown>>('/about'),
  languages: () => request<{ languages: { code: string; name: string }[] }>('/api/v1/languages'),
  consentPresentation: (language: string) =>
    request<ConsentPresentation>(`/api/v1/consent/presentation?language=${language}`),

  requestOtp: (abhaAddress: string) =>
    request<{ txnId: string; demoOtp: string; otpSentTo: string }>('/mock-idp/abha/request-otp', {
      method: 'POST',
      body: JSON.stringify({ abha_address: abhaAddress }),
    }),
  verifyOtp: (abhaAddress: string, otp: string) =>
    request<{ access_token: string; abhaRef: string; demographics: Record<string, unknown> }>(
      '/mock-idp/abha/verify-otp',
      { method: 'POST', body: JSON.stringify({ abha_address: abhaAddress, otp }) },
    ),
  staffToken: (role: string, sub: string) =>
    request<{ access_token: string }>('/mock-idp/token', {
      method: 'POST',
      body: JSON.stringify({ role, sub }),
    }),

  createSession: (language: string, consentScopes: string[], audioExplained: boolean) =>
    request<{ sessionRef: string; consentRef: string; ayushMode: boolean; demographics: Record<string, unknown> | null }>(
      '/api/v1/sessions',
      { method: 'POST', body: JSON.stringify({ language, consentScopes, audioExplained }) },
    ),
  sessionState: (ref: string) => request<Record<string, unknown>>(`/api/v1/sessions/${ref}`),

  next: (ref: string) => request<StepResponse>(`/api/v1/sessions/${ref}/dialogue/next`),
  answer: (ref: string, turnId: string, questionId: string, value: unknown) =>
    request<StepResponse>(`/api/v1/sessions/${ref}/dialogue/answer`, {
      method: 'POST',
      body: JSON.stringify({ turnId, questionId, value, modality: 'touch' }),
    }),
  answerTyped: (ref: string, turnId: string, questionId: string, value: string) =>
    request<StepResponse>(`/api/v1/sessions/${ref}/dialogue/answer`, {
      method: 'POST',
      body: JSON.stringify({ turnId, questionId, value, modality: 'typed' }),
    }),
  answerVoice: (
    ref: string,
    turnId: string,
    questionId: string,
    transcript: string,
    confidence: number,
    bargeIn: boolean,
  ) =>
    request<StepResponse>(`/api/v1/sessions/${ref}/dialogue/answer/voice`, {
      method: 'POST',
      body: JSON.stringify({ turnId, questionId, transcript, confidence, bargeIn }),
    }),
  review: (ref: string) =>
    request<{ answers: ReviewAnswer[]; language: string }>(
      `/api/v1/sessions/${ref}/dialogue/review`,
    ),
  reopen: (ref: string, questionId: string) =>
    request<StepResponse & { reopened: string }>(`/api/v1/sessions/${ref}/dialogue/reopen`, {
      method: 'POST',
      body: JSON.stringify({ questionId }),
    }),
  skip: (ref: string, questionId: string) =>
    request<StepResponse>(`/api/v1/sessions/${ref}/dialogue/skip`, {
      method: 'POST',
      body: JSON.stringify({ questionId }),
    }),
  speak: (ref: string, text: string) =>
    request<{ audioBase64: string | null; clientFallback: boolean; backend: string }>(
      `/api/v1/sessions/${ref}/dialogue/speak`,
      { method: 'POST', body: JSON.stringify({ text }) },
    ),

  upload: (ref: string, file: File) => {
    const form = new FormData();
    form.append('file', file);
    return request<{
      documentId: string;
      filename: string;
      backend: string;
      meanConfidence: number;
      factsRecorded: number;
      lowConfidenceCount: number;
      needsVerification: { entityIndex: number; kind: string; text: string; confidence: number; sourceText: string; page: number }[];
    }>(`/api/v1/sessions/${ref}/documents`, { method: 'POST', body: form });
  },
  timeline: (ref: string) =>
    request<{ documents: unknown[]; periods: TimelinePeriod[]; eventCount: number }>(
      `/api/v1/sessions/${ref}/documents/timeline`,
    ),
  verifyEntity: (ref: string, documentId: string, entityIndex: number, accepted: boolean, correctedText?: string) =>
    request<Record<string, unknown>>(`/api/v1/sessions/${ref}/documents/${documentId}/verify`, {
      method: 'POST',
      body: JSON.stringify({ entityIndex, accepted, correctedText }),
    }),

  queue: () => request<{ queue: QueueEntry[]; count: number }>('/api/v1/queue'),
  contradictions: (ref: string) =>
    request<{ count: number; contradictions: Contradiction[]; note: string }>(
      `/api/v1/sessions/${ref}/contradictions`,
    ),

  inspect: (ref: string) => request<Inspect>(`/api/v1/sessions/${ref}/inspect`),

  demoCases: () => request<{ cases: DemoCase[]; notice: string }>('/api/v1/demo/cases'),
  loadDemoCase: (caseId: string, sessionRef: string) =>
    request<DemoLoadResult>(`/api/v1/demo/cases/${caseId}/load`, {
      method: 'POST',
      body: JSON.stringify({ sessionRef }),
    }),
  summary: (ref: string, prose = false) =>
    request<Summary>(`/api/v1/sessions/${ref}/summary?prose=${prose}`),
  factDetail: (ref: string, factId: string) =>
    request<{ explanation: string; source: Record<string, unknown>; value: unknown; tier: Tier }>(
      `/api/v1/sessions/${ref}/facts/${factId}`,
    ),
  editFact: (ref: string, path: string, value: unknown, reason: string) =>
    request<Record<string, unknown>>(`/api/v1/sessions/${ref}/summary/edit`, {
      method: 'POST',
      body: JSON.stringify({ path, value, reason }),
    }),
  commit: (ref: string) =>
    request<{ committed: boolean; bundleId: string; entries: number; hisPush: { status: string; detail: string }; purge: Record<string, unknown> | null }>(
      `/api/v1/sessions/${ref}/commit`,
      { method: 'POST', body: JSON.stringify({ confirmed: true }) },
    ),
  revokeConsent: (ref: string, scopes?: string[]) =>
    request<Record<string, unknown>>(`/api/v1/sessions/${ref}/consent/revoke`, {
      method: 'POST',
      body: JSON.stringify(scopes ? { scopes } : {}),
    }),
};
