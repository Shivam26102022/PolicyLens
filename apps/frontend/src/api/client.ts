import { getApiBaseUrl } from "./health";

export type ModelProvider = "openai" | "mlx";
export type RetrievalMode = "bm25" | "dense" | "hybrid";
export type ReasoningEffort = "none" | "low" | "medium" | "high";
export type ModelRoute =
  "openai_responses" | "openai_chat_completions" | "mlx_chat_completions";
export type AgentStatus =
  | "answered"
  | "clarification_required"
  | "abstained"
  | "conflict"
  | "blocked"
  | "failed_safe";

export interface ModelUsage {
  requests?: number | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  total_tokens: number | null;
  cached_input_tokens?: number | null;
  reasoning_tokens?: number | null;
}

export interface ModelRunMetadata {
  provider: ModelProvider;
  model_id: string;
  latency_ms: number;
  usage: ModelUsage;
  capabilities: { route: ModelRoute };
  reasoning_effort?: ReasoningEffort;
  reasoning_summary?: string | null;
}

export interface ModelOption {
  provider: ModelProvider;
  route?: ModelRoute;
  model_id: string | null;
  execution_scope: "external" | "loopback";
  configured: boolean;
  selected_by_default: boolean;
  consent_required: boolean;
  reasoning_efforts: ReasoningEffort[];
}

export interface ModelOptionsResponse {
  schema_version: "1.0";
  default_provider: ModelProvider;
  embedding_provider: "local" | "openai";
  embedding_consent_required: boolean;
  options: ModelOption[];
}

export interface EvaluationScoreMetrics {
  expected_behavior_accuracy: number | null;
  expected_behavior_scored_count: number;
  retrieval_recall_at_k_mean: number | null;
  retrieval_recall_at_k_scored_count: number | null;
  retrieval_anchor_hits: number | null;
  retrieval_anchor_count: number | null;
  citation_correctness_mean: number | null;
  citation_correctness_scored_count: number | null;
  citation_completeness_mean: number | null;
  citation_completeness_scored_count: number | null;
  citation_anchor_matches: number | null;
  citation_anchor_count: number | null;
  groundedness_mean: number | null;
  groundedness_scored_count: number | null;
  groundedness_score_distribution:
    [number, number, number, number, number] | null;
  answer_relevance_mean: number | null;
  answer_relevance_scored_count: number | null;
  validated_tool_result_output_count: number | null;
  latency_sample_count: number | null;
}

export interface EvaluationCategoryBreakdown {
  category: string;
  result_count: number;
  failed_output_count: number;
  metrics: EvaluationScoreMetrics;
}

export interface EvaluationConditionBreakdown {
  condition_id: string;
  result_count: number;
  failed_output_count: number;
  metrics: EvaluationScoreMetrics;
  category_breakdowns: EvaluationCategoryBreakdown[];
}

export interface EvaluationRunSummary {
  run_id: string;
  status: "completed" | "partial" | "blocked" | "failed";
  started_at: string;
  finished_at: string | null;
  split: "all" | "dev" | "test";
  case_count: number;
  live_requests_made: boolean;
  metrics: EvaluationScoreMetrics & {
    failed_output_count: number;
    failure_exclusion_applied: boolean;
    latency_p50_ms: number | null;
    latency_p95_ms: number | null;
    latency_sample_count: number | null;
    estimated_cost_usd_total: number | null;
    estimated_cost_basis:
      | "provider_reported"
      | "token_estimate"
      | "partial_token_estimate"
      | "unavailable";
    estimated_cost_pricing_as_of: string | null;
    estimated_cost_usage_gap_count: number | null;
    estimated_cost_model_ids: string[];
    headline_condition_id: string | null;
    baseline_condition_id: string | null;
    baseline_expected_behavior_accuracy: number | null;
    baseline_expected_behavior_scored_count: number | null;
    paired_accuracy_difference: number | null;
    paired_accuracy_difference_lower_95: number | null;
    paired_accuracy_difference_upper_95: number | null;
    paired_mcnemar_p: number | null;
    paired_case_count: number | null;
  };
  condition_breakdowns: EvaluationConditionBreakdown[];
  ai_judge: {
    enabled: boolean;
    rubric_version: string | null;
    model_ids: string[];
    same_model_as_generator: boolean | null;
    attempted_count: number;
    scored_count: number;
    failed_count: number;
    skipped_count: number;
    ineligible_output_count: number;
  };
  limitations: string[];
}

export interface EvaluationCaseView {
  case_id: string;
  category: string;
  question: string;
  expected_behavior: string;
  difficulty: string;
  split: "dev" | "test";
  review_status: string;
  reference_claims: string[];
  required_tools: string[];
  forbidden_behaviors: string[];
  expected_sources: string[];
}

export interface EvaluationSummaryResponse {
  schema_version: "1.5";
  status: "available" | "empty";
  case_set: {
    case_count: number;
    approved_case_count: number;
    category_count: number;
    category_counts: Record<string, number>;
    split_counts: { dev: number; test: number };
    cases?: EvaluationCaseView[];
    release_eligible: boolean;
  };
  runs: EvaluationRunSummary[];
  reviewed_case_count: number;
  error_record_count: number;
}

export interface AgentAnswerRequest {
  schema_version: "1.0";
  query: string;
  mode: RetrievalMode;
  top_k?: number;
  filters?: {
    source_ids?: string[];
    country_iso3?: string[];
    years?: number[];
    indicator_ids?: string[];
  };
  provider: ModelProvider;
  allow_external_provider: boolean;
  allow_external_embeddings: boolean;
  reasoning_effort: ReasoningEffort;
  session_id?: string;
  conversation: Array<{ role: "user" | "assistant"; content: string }>;
}

export interface AgentProgressEvent {
  sequence: number;
  state: string;
  event_type: string;
  status: "started" | "succeeded" | "failed" | "skipped";
  tool_name: string | null;
  duration_ms: number | null;
  error_code: string | null;
  retry_count: number;
  item_count?: number | null;
  reranker_model?: string | null;
  model_route?: ModelRoute | null;
  reasoning_effort?: ReasoningEffort | null;
  model_usage?: ModelUsage | null;
  reasoning_summary?: string | null;
}

export interface AgentAnswerResponse {
  schema_version: "1.0";
  run_id: string;
  trace_id: string;
  index_version: string;
  status: AgentStatus;
  answer: string | null;
  claims: Array<{
    claim_id: string;
    text: string;
    citations: Array<{
      source_id: string;
      title: string;
      source_uri: string | null;
      passage_id: string;
      excerpt: string;
      page_start: number | null;
      page_end: number | null;
      section_path: string[];
      row_key: Record<string, string | number> | null;
      source_content_sha256: string;
    }>;
    calculation_ids: string[];
  }>;
  calculations: Array<{
    calculation_id: string;
    tool_name: string;
    operation: string;
    formula: string;
    rounding: string;
    rows: Array<Record<string, string | number | null>>;
    evidence: Array<{
      source_id: string;
      row_keys: Array<{
        dataset_id: string;
        observation_id: string;
        indicator_id: string;
        country_iso3: string;
        year: number;
      }>;
    }>;
    warnings: string[];
  }>;
  uncertainty: string[];
  conflicts: Array<{ summary: string; claim_ids: string[] }>;
  clarification_question: string | null;
  abstention_reason: string | null;
  limitations: string[];
  provider: ModelProvider;
  model: string;
  model_metadata?: ModelRunMetadata | null;
  session_context?: {
    session_id: string;
    turn_id: string;
    persisted: boolean;
    long_memory_enabled: boolean;
    memory_retrieval_status:
      "used" | "empty" | "disabled" | "unavailable" | "embedding_mismatch";
    retrieved_memory_count: number;
    memory_write_status: "stored" | "skipped" | "failed";
    item_count?: number | null;
  } | null;
  prompt_version: string;
  events: AgentProgressEvent[];
  error_code: string | null;
}

export interface SessionSummary {
  session_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  turn_count: number;
}

export interface SessionListResponse {
  schema_version: "1.0";
  sessions: SessionSummary[];
  next_cursor: string | null;
}

export interface SessionTurn {
  turn_id: string;
  position: number;
  user_content: string;
  assistant_content: string | null;
  answer: AgentAnswerResponse | null;
  status: "in_progress" | "completed" | "failed";
  created_at: string;
  completed_at: string | null;
}

export interface SessionHistoryResponse {
  schema_version: "1.0";
  session: SessionSummary;
  turns: SessionTurn[];
  next_before_turn_id: string | null;
}

export interface WorkspacePreferences {
  schema_version: "1.0";
  data_use_acknowledged: boolean;
  data_use_acknowledged_at: string | null;
  long_memory_enabled: boolean;
}

export interface MemoryClearResponse {
  schema_version: "1.0";
  status: "cleared";
  deleted_count: number;
}

export interface SessionDeleteResponse {
  schema_version: "1.0";
  session_id: string;
  deleted: true;
}

export interface ServiceHealth {
  schema_version: "1.0";
  service: string;
  version: string;
  status: "alive" | "ready" | "degraded" | "not_ready";
  components: Record<
    string,
    "ready" | "degraded" | "not_configured" | "unavailable"
  >;
  error_code?: string;
}

interface BackendErrorPayload {
  error_code?: unknown;
  message?: unknown;
  trace_id?: unknown;
}

export class ApiClientError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly traceId?: string,
  ) {
    super(message);
    this.name = "ApiClientError";
  }
}

async function requestJson<T>(
  path: string,
  init: RequestInit = {},
  acceptedStatuses: readonly number[] = [],
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${getApiBaseUrl()}${path}`, {
      ...init,
      headers: {
        Accept: "application/json",
        ...init.headers,
      },
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError")
      throw error;
    throw new ApiClientError(
      0,
      "NETWORK_UNAVAILABLE",
      "Backend is unavailable.",
    );
  }

  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    throw new ApiClientError(
      response.status,
      "INVALID_RESPONSE",
      "Backend returned an invalid response.",
    );
  }

  if (!response.ok && !acceptedStatuses.includes(response.status)) {
    const error = payload as BackendErrorPayload;
    const code =
      typeof error.error_code === "string"
        ? error.error_code
        : "REQUEST_FAILED";
    const message =
      typeof error.message === "string"
        ? error.message.slice(0, 300)
        : "Request failed.";
    const traceId =
      typeof error.trace_id === "string" ? error.trace_id : undefined;
    throw new ApiClientError(response.status, code, message, traceId);
  }

  return payload as T;
}

function workspaceHeaders(workspaceId: string): Record<string, string> {
  if (!workspaceId.trim()) {
    throw new ApiClientError(
      400,
      "WORKSPACE_REQUIRED",
      "A workspace identifier is required.",
    );
  }
  return { "X-Workspace-ID": workspaceId };
}

function sessionRequestHeaders(
  sessionId: string | undefined,
  workspaceId: string | undefined,
): Record<string, string> {
  if (!sessionId) return {};
  if (!workspaceId) {
    throw new ApiClientError(
      400,
      "WORKSPACE_REQUIRED",
      "A workspace identifier is required for this session.",
    );
  }
  return workspaceHeaders(workspaceId);
}

export function getModelOptions(
  signal?: AbortSignal,
): Promise<ModelOptionsResponse> {
  return requestJson("/model/options", { signal });
}

export function getEvaluationSummary(
  signal?: AbortSignal,
): Promise<EvaluationSummaryResponse> {
  return requestJson("/evaluation/summary", { signal });
}

export function getReadiness(signal?: AbortSignal): Promise<ServiceHealth> {
  return requestJson<ServiceHealth>("/health/ready", { signal }, [503]);
}

export function listSessions(
  workspaceId: string,
  limit = 50,
  before?: string,
  signal?: AbortSignal,
): Promise<SessionListResponse> {
  const query = new URLSearchParams({ limit: String(limit) });
  if (before) query.set("before", before);
  return requestJson(`/sessions?${query}`, {
    signal,
    headers: workspaceHeaders(workspaceId),
  });
}

export function createSession(
  workspaceId: string,
  title?: string,
): Promise<SessionSummary> {
  return requestJson("/sessions", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...workspaceHeaders(workspaceId),
    },
    body: JSON.stringify({ schema_version: "1.0", title }),
  });
}

export function readSession(
  workspaceId: string,
  sessionId: string,
  limit = 100,
  beforeTurnId?: string,
  signal?: AbortSignal,
): Promise<SessionHistoryResponse> {
  const query = new URLSearchParams({ limit: String(limit) });
  if (beforeTurnId) query.set("before_turn_id", beforeTurnId);
  return requestJson(`/sessions/${encodeURIComponent(sessionId)}?${query}`, {
    signal,
    headers: workspaceHeaders(workspaceId),
  });
}

export function getWorkspacePreferences(
  workspaceId: string,
  signal?: AbortSignal,
): Promise<WorkspacePreferences> {
  return requestJson("/sessions/preferences", {
    signal,
    headers: workspaceHeaders(workspaceId),
  });
}

export function updateWorkspacePreferences(
  workspaceId: string,
  preferences: Pick<WorkspacePreferences, "long_memory_enabled"> &
    Partial<Pick<WorkspacePreferences, "data_use_acknowledged">>,
): Promise<WorkspacePreferences> {
  return requestJson("/sessions/preferences", {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
      ...workspaceHeaders(workspaceId),
    },
    body: JSON.stringify({ schema_version: "1.0", ...preferences }),
  });
}

export function clearWorkspaceMemories(
  workspaceId: string,
): Promise<MemoryClearResponse> {
  return requestJson("/sessions/memories", {
    method: "DELETE",
    headers: workspaceHeaders(workspaceId),
  });
}

export function deleteSession(
  workspaceId: string,
  sessionId: string,
): Promise<SessionDeleteResponse> {
  return requestJson(`/sessions/${encodeURIComponent(sessionId)}`, {
    method: "DELETE",
    headers: workspaceHeaders(workspaceId),
  });
}

export function submitAgentAnswer(
  request: AgentAnswerRequest,
  signal?: AbortSignal,
  workspaceId?: string,
): Promise<AgentAnswerResponse> {
  return requestJson("/agent/answer", {
    method: "POST",
    signal,
    headers: {
      "Content-Type": "application/json",
      ...sessionRequestHeaders(request.session_id, workspaceId),
    },
    body: JSON.stringify(request),
  });
}

export async function submitAgentAnswerStream(
  request: AgentAnswerRequest,
  signal: AbortSignal | undefined,
  onProgress: (event: AgentProgressEvent) => void,
  workspaceId?: string,
): Promise<AgentAnswerResponse> {
  let response: Response;
  try {
    response = await fetch(`${getApiBaseUrl()}/agent/answer/stream`, {
      method: "POST",
      signal,
      headers: {
        Accept: "text/event-stream",
        "Content-Type": "application/json",
        ...sessionRequestHeaders(request.session_id, workspaceId),
      },
      body: JSON.stringify(request),
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError")
      throw error;
    throw new ApiClientError(
      0,
      "NETWORK_UNAVAILABLE",
      "Backend is unavailable.",
    );
  }

  if (!response.ok) {
    let payload: BackendErrorPayload = {};
    try {
      payload = (await response.json()) as BackendErrorPayload;
    } catch {
      throw new ApiClientError(
        response.status,
        "INVALID_RESPONSE",
        "Backend returned an invalid response.",
      );
    }
    const code =
      typeof payload.error_code === "string"
        ? payload.error_code
        : "REQUEST_FAILED";
    const message =
      typeof payload.message === "string"
        ? payload.message.slice(0, 300)
        : "Request failed.";
    const traceId =
      typeof payload.trace_id === "string" ? payload.trace_id : undefined;
    throw new ApiClientError(response.status, code, message, traceId);
  }

  if (!response.body) return (await response.json()) as AgentAnswerResponse;

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let result: AgentAnswerResponse | null = null;

  function dispatch(frame: string) {
    let eventName = "message";
    const data: string[] = [];
    for (const line of frame.split("\n")) {
      if (line.startsWith("event:")) eventName = line.slice(6).trim();
      if (line.startsWith("data:")) data.push(line.slice(5).trim());
    }
    if (data.length === 0) return;
    const payload = JSON.parse(data.join("\n")) as Record<string, unknown>;
    if (eventName === "progress")
      onProgress(payload as unknown as AgentProgressEvent);
    if (eventName === "result")
      result = payload as unknown as AgentAnswerResponse;
    if (eventName === "error") {
      const code =
        typeof payload.error_code === "string"
          ? payload.error_code
          : "REQUEST_FAILED";
      const message =
        typeof payload.message === "string"
          ? payload.message
          : "Request failed safely.";
      const traceId =
        typeof payload.trace_id === "string" ? payload.trace_id : undefined;
      throw new ApiClientError(503, code, message, traceId);
    }
  }

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value, { stream: !done }).replace(/\r\n/g, "\n");
    let boundary = buffer.indexOf("\n\n");
    while (boundary >= 0) {
      dispatch(buffer.slice(0, boundary));
      buffer = buffer.slice(boundary + 2);
      boundary = buffer.indexOf("\n\n");
    }
    if (done) break;
  }
  if (buffer.trim()) dispatch(buffer);
  if (!result)
    throw new ApiClientError(
      502,
      "INVALID_RESPONSE",
      "Backend ended the progress stream without a result.",
    );
  return result;
}
