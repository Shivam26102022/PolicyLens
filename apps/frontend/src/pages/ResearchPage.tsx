import { useCallback, useEffect, useRef, useState } from "react";
import {
  Clipboard,
  ClipboardCheck,
  ArrowDown,
  ArrowUp,
  Clock3,
  LoaderCircle,
  MessageSquarePlus,
  Square,
} from "lucide-react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

import {
  ApiClientError,
  clearWorkspaceMemories,
  createSession,
  deleteSession,
  getWorkspacePreferences,
  listSessions,
  readSession,
  submitAgentAnswerStream,
  updateWorkspacePreferences,
  type AgentAnswerResponse,
  type AgentProgressEvent,
  type ModelProvider,
  type SessionHistoryResponse,
  type SessionSummary,
} from "../api/client";
import AgentTrail from "../components/AgentTrail";
import EvidenceDrawer from "../components/EvidenceDrawer";
import PdfPreviewDialog, {
  type PdfPreviewRequest,
} from "../components/PdfPreviewDialog";
import ProviderConsentDialog from "../components/ProviderConsentDialog";
import { examplePrompts } from "../data/example-prompts";
import { pdfViewerUrl, resolvePdfSource } from "../data/pdf-sources";
import { useWorkbench } from "../state/WorkbenchContext";

interface ResearchRun {
  id: string;
  question: string;
  provider: ModelProvider;
  status: AgentAnswerResponse["status"] | "cancelled";
  response?: AgentAnswerResponse;
  message?: string;
}

type ConversationMessage = {
  role: "user" | "assistant";
  content: string;
  response?: AgentAnswerResponse;
};
type ConversationPair = {
  user?: ConversationMessage;
  assistant?: ConversationMessage;
};

const NOTICE_COPY: Partial<
  Record<
    AgentAnswerResponse["status"],
    { title: string; why: string; tips: string[] }
  >
> = {
  abstained: {
    title: "I could not find enough evidence",
    why: "PolicyLens only answers from its stored World Bank and ILO documents and statistics, so it says so instead of guessing.",
    tips: [
      "Name a country (Malaysia, Singapore, India or Indonesia), an indicator and a year, for example “Singapore unemployment 2025”.",
      "Ask about one topic at a time, such as youth unemployment, skills programmes or informal work.",
      "Say what you want to compare, and the period, for calculations.",
    ],
  },
  clarification_required: {
    title: "One quick question",
    why: "Your question could mean more than one thing, so I would rather check than answer the wrong one.",
    tips: [
      "Reply in a short sentence; I will use the earlier messages as context.",
    ],
  },
  blocked: {
    title: "I cannot help with that here",
    why: "This request falls outside what PolicyLens is allowed or designed to do.",
    tips: [
      "I can answer evidence-based questions on labour-market policy, with citations you can open.",
    ],
  },
};

interface AnswerContentProps {
  answer: string;
  response?: AgentAnswerResponse;
  copied: boolean;
  onCopyCitation: (value: string) => void;
}

function AnswerContent({
  answer,
  response,
  copied,
  onCopyCitation,
}: AnswerContentProps) {
  const claims = response?.claims ?? [];
  const citations = claims.flatMap((claim) => claim.citations);
  const [pdfPreview, setPdfPreview] = useState<PdfPreviewRequest | null>(null);
  const previewTriggerRef = useRef<HTMLElement | null>(null);
  const openPdfPreview = useCallback(
    (preview: PdfPreviewRequest, trigger: HTMLElement) => {
      previewTriggerRef.current = trigger;
      setPdfPreview(preview);
    },
    [],
  );
  const closePdfPreview = useCallback(() => {
    setPdfPreview(null);
    window.requestAnimationFrame(() => previewTriggerRef.current?.focus());
  }, []);

  function previewRequest(uri: string): PdfPreviewRequest | null {
    const source = resolvePdfSource(uri);
    if (!source) return null;

    const citation = citations.find(
      (item) =>
        resolvePdfSource(item.source_uri, item.source_id)?.uri === source.uri,
    );
    const pageStart = citation?.page_start ?? null;
    const excerpt = citation?.excerpt ?? "";
    return {
      url: pdfViewerUrl(source, pageStart, excerpt),
      title: citation?.title ?? source.title,
      location: pageStart ? `Page ${pageStart}` : "PDF document",
      excerpt,
    };
  }

  const markdownComponents: Components = {
    a({ children, href, title }) {
      if (!href) return <>{children}</>;
      const preview = previewRequest(href);
      if (!preview) {
        return (
          <a href={href} title={title}>
            {children}
          </a>
        );
      }
      return (
        <a
          aria-haspopup="dialog"
          href={preview.url}
          onClick={(event) => {
            event.preventDefault();
            openPdfPreview(preview, event.currentTarget);
          }}
          title={title}
        >
          {children}
        </a>
      );
    },
  };

  function openCitationPreview(
    citation: (typeof citations)[number],
    trigger: HTMLElement,
  ) {
    const source = resolvePdfSource(
      citation.source_uri,
      citation.source_id,
      true,
    );
    if (!source) return;
    const pageStart = citation.page_start;
    openPdfPreview(
      {
        url: pdfViewerUrl(source, pageStart, citation.excerpt),
        title: citation.title,
        location: pageStart ? `Page ${pageStart}` : "PDF document",
        excerpt: citation.excerpt,
      },
      trigger,
    );
  }

  return (
    <>
      {claims.length === 0 ? (
        <div
          className={`answer-notice${
            response && NOTICE_COPY[response.status]
              ? ` answer-notice-${response.status}`
              : ""
          }`}
        >
          {response && NOTICE_COPY[response.status] && (
            <p className="answer-notice-title">
              {NOTICE_COPY[response.status]?.title}
            </p>
          )}
          <div className="answer-markdown">
            <ReactMarkdown
              components={markdownComponents}
              remarkPlugins={[remarkGfm]}
            >
              {answer}
            </ReactMarkdown>
          </div>
          {response && NOTICE_COPY[response.status] && (
            <div className="answer-notice-help">
              <p>{NOTICE_COPY[response.status]?.why}</p>
              <ul>
                {NOTICE_COPY[response.status]?.tips.map((tip) => (
                  <li key={tip}>{tip}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      ) : (
        <div className="answer-summary">
          <p className="answer-overline">Evidence-backed answer</p>
          <ol className="answer-findings">
            {claims.map((claim, index) => (
              <li className="answer-finding" key={claim.claim_id}>
                <span aria-hidden="true" className="answer-finding-index">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <div className="answer-finding-body">
                  <div className="answer-markdown">
                    <ReactMarkdown
                      components={markdownComponents}
                      remarkPlugins={[remarkGfm]}
                    >
                      {claim.text}
                    </ReactMarkdown>
                  </div>
                  {claim.citations.length > 0 && (
                    <div
                      aria-label={`Sources for finding ${index + 1}`}
                      className="answer-citations"
                    >
                      {claim.citations.map((citation) => (
                        <EvidenceDrawer
                          citation={citation}
                          copied={copied}
                          key={`${claim.claim_id}-${citation.passage_id}`}
                          onCopyCitation={onCopyCitation}
                          onOpenPdfPreview={(trigger) =>
                            openCitationPreview(citation, trigger)
                          }
                        />
                      ))}
                    </div>
                  )}
                </div>
              </li>
            ))}
          </ol>
        </div>
      )}
      {pdfPreview && (
        <PdfPreviewDialog onClose={closePdfPreview} preview={pdfPreview} />
      )}
    </>
  );
}

const WORKSPACE_ID_STORAGE_KEY = "policylens.workspace-id";
const ACTIVE_SESSION_STORAGE_PREFIX = "policylens.active-session.";

function workspaceIdForBrowser(): string {
  const stored = window.localStorage.getItem(WORKSPACE_ID_STORAGE_KEY);
  if (stored) return stored;
  const workspaceId = crypto.randomUUID();
  window.localStorage.setItem(WORKSPACE_ID_STORAGE_KEY, workspaceId);
  return workspaceId;
}

function messagesFromHistory(
  history: SessionHistoryResponse,
): ConversationMessage[] {
  return history.turns.flatMap((turn) => [
    { role: "user" as const, content: turn.user_content },
    ...(turn.assistant_content
      ? [
          {
            role: "assistant" as const,
            content: turn.assistant_content,
            response: turn.answer ?? undefined,
          },
        ]
      : []),
  ]);
}

function latestRunFromHistory(
  history: SessionHistoryResponse,
): ResearchRun | null {
  const latestTurn = [...history.turns]
    .reverse()
    .find((turn) => turn.answer !== null);
  if (!latestTurn?.answer) return null;
  return {
    id: latestTurn.answer.run_id,
    question: latestTurn.user_content,
    provider: latestTurn.answer.provider,
    status: latestTurn.answer.status,
    response: latestTurn.answer,
  };
}

// The server keeps sessions in per-instance storage on serverless hosts, so the
// browser also sends the recent turns and the server can rebuild context.
function recentContext(
  messages: ConversationMessage[],
): Array<{ role: "user" | "assistant"; content: string }> {
  const selected: Array<{ role: "user" | "assistant"; content: string }> = [];
  let total = 0;
  for (const message of [...messages].reverse()) {
    const content = message.content.trim().slice(0, 4000);
    if (!content || selected.length >= 10) continue;
    if (total + content.length > 11000) break;
    total += content.length;
    selected.unshift({ role: message.role, content });
  }
  return selected;
}

function pairMessages(messages: ConversationMessage[]): ConversationPair[] {
  const pairs: ConversationPair[] = [];
  for (const message of messages) {
    const lastPair = pairs[pairs.length - 1];
    if (message.role === "user" || !lastPair || lastPair.assistant) {
      pairs.push({ [message.role]: message });
    } else {
      lastPair.assistant = message;
    }
  }
  return pairs;
}

function memoryRetrievalLabel(
  status: "used" | "empty" | "disabled" | "unavailable" | "embedding_mismatch",
): string {
  const labels: Record<typeof status, string> = {
    used: "Relevant memories used",
    empty: "No relevant memories",
    disabled: "Off",
    unavailable: "Unavailable",
    embedding_mismatch: "Needs attention",
  };
  return labels[status];
}

function memoryWriteLabel(status: "stored" | "skipped" | "failed"): string {
  const labels: Record<typeof status, string> = {
    stored: "Saved",
    skipped: "Not saved",
    failed: "Save failed",
  };
  return labels[status];
}

function statusLabel(status: AgentAnswerResponse["status"]): string {
  const labels: Record<AgentAnswerResponse["status"], string> = {
    answered: "Answer ready",
    clarification_required: "Clarification needed",
    abstained: "Not enough evidence",
    conflict: "Conflicting evidence",
    blocked: "Blocked safely",
    failed_safe: "Run stopped safely",
  };
  return labels[status];
}

function failureExplanation(
  errorCode: string,
  events: AgentProgressEvent[] = [],
): string {
  if (errorCode === "CITATION_INVALID") {
    const reasonCode = events.find(
      (event) =>
        event.event_type === "citations_validated" && event.status === "failed",
    )?.error_code;
    const citationMessages: Record<string, string> = {
      CALCULATION_REFERENCE_INVALID:
        "The model referenced a statistics calculation that was not produced in this run. The statistics service itself did not fail.",
      PASSAGE_NOT_RETURNED:
        "The answer referenced a passage that was not among the evidence retrieved for this run.",
      RUN_NOT_FOUND:
        "The current-run evidence record was unavailable for validation. Retry to perform a fresh retrieval.",
      CLAIM_NOT_FOUND:
        "A citation was not linked to a claim in the generated answer.",
      SOURCE_MISMATCH:
        "The citation's source details did not match the retrieved passage.",
      HASH_MISMATCH:
        "The source content hash in a citation did not match the retrieved evidence.",
      LOCATION_MISMATCH:
        "The cited page, section, row, or retrieval location did not match the selected evidence.",
      QUOTE_NOT_EXACT:
        "The cited quote was not an exact match for the retrieved passage.",
      QUOTE_TOO_LONG: "The cited quote exceeded the maximum excerpt length.",
      DUPLICATE_CITATION: "The generated answer repeated the same citation.",
      UNCOVERED_CLAIM:
        "At least one factual claim did not have an accepted citation.",
    };
    return (
      (reasonCode && citationMessages[reasonCode]) ??
      "The system could not verify a cited passage, exact quote, or calculation reference against this run's evidence."
    );
  }
  const mcpMessages: Record<string, string> = {
    MCP_PASSAGE_MISMATCH:
      "The Policy Data MCP passage did not match the evidence selected from the active index. No model answer was generated.",
    MCP_CATALOG_STALE:
      "The Policy Data MCP passage catalog is out of sync with the active retrieval index. Refresh the passage catalog and retry.",
    MCP_RESOURCE_NOT_FOUND:
      "The Policy Data MCP server could not find a selected passage. Its catalog may be out of sync with the retrieval index.",
    MCP_IDENTITY_MISMATCH:
      "The configured MCP server identity or protocol does not match the approved server.",
    MCP_CAPABILITY_MISMATCH:
      "The MCP server does not expose the approved tools and passage resource.",
    MCP_SCHEMA_INVALID:
      "The MCP server response schema does not match the approved contract.",
    MCP_MALFORMED_RESPONSE:
      "The Policy Data MCP server returned a passage response that could not be validated.",
    MCP_INTERNAL_ERROR:
      "The Policy Data MCP server reported an internal error. No answer was generated.",
  };
  if (mcpMessages[errorCode]) return mcpMessages[errorCode];
  if (errorCode === "MODEL_UNAVAILABLE") {
    return (
      "The backend uses this safe code for provider or model configuration " +
      "problems, provider errors, and timeouts. “Model finished” means a model " +
      "call ended; it does not confirm the whole agent run succeeded. Check " +
      "backend logs for the trace ID below to find the underlying cause."
    );
  }
  return `The run stopped safely (${errorCode}). Check backend logs for the trace ID below for details.`;
}

function safeRequestError(error: unknown): string {
  if (!(error instanceof ApiClientError)) {
    return "The request could not be completed safely. Check system status and try again.";
  }
  const messages: Record<string, string> = {
    NETWORK_UNAVAILABLE:
      "The backend is offline or unreachable. Check system status and retry.",
    EXTERNAL_PROVIDER_CONSENT_REQUIRED:
      "OpenAI needs your confirmation before this request can be sent.",
    EXTERNAL_EMBEDDING_CONSENT_REQUIRED:
      "OpenAI embeddings need your confirmation before processing this turn.",
    MODEL_UNAVAILABLE:
      "The selected model is unavailable. No alternate provider was used.",
    RETRIEVAL_UNAVAILABLE:
      "Evidence retrieval is unavailable. No answer was generated.",
    MCP_TIMEOUT:
      "The approved data tool timed out. No provider fallback was attempted.",
    MCP_UNAVAILABLE:
      "The approved data service is unavailable. No provider fallback was attempted.",
    MCP_CATALOG_STALE:
      "The Policy Data MCP passage catalog is out of sync with the active retrieval index.",
    MCP_RESOURCE_NOT_FOUND:
      "The Policy Data MCP server could not find a selected passage.",
    MCP_PASSAGE_MISMATCH:
      "The MCP passage did not match the active retrieved evidence. No answer was generated.",
    TOOL_PERMISSION_DENIED: "The requested data is not permitted for this run.",
    INVALID_REQUEST:
      "The question or filters are not valid. Review them and try again.",
    WORKSPACE_REQUIRED:
      "Select a workspace before continuing this conversation.",
    SESSION_NOT_FOUND:
      "This conversation is unavailable. Select another session or create a new one.",
    SESSION_PERSISTENCE_FAILED:
      "The response could not be saved to this conversation.",
  };
  if (error.status === 422) {
    return "The question or filters are not valid. Review them and try again.";
  }
  return messages[error.code] ?? `The request failed safely (${error.code}).`;
}

export default function ResearchPage() {
  const {
    modelOptions,
    modelOptionsError,
    selectedProvider,
    setSelectedProvider,
  } = useWorkbench();
  const [question, setQuestion] = useState("");
  const [conversation, setConversation] = useState<ConversationMessage[]>([]);
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [longMemoryEnabled, setLongMemoryEnabled] = useState(false);
  const [sessionLoading, setSessionLoading] = useState(true);
  const [sessionError, setSessionError] = useState<string | null>(null);
  const [olderHistoryCursor, setOlderHistoryCursor] = useState<string | null>(
    null,
  );
  const [historyLoading, setHistoryLoading] = useState(false);
  const [memoryControlPending, setMemoryControlPending] = useState<
    "preference" | "clear" | "delete" | null
  >(null);
  const [memoryControlError, setMemoryControlError] = useState<string | null>(
    null,
  );
  const [memoryControlStatus, setMemoryControlStatus] = useState<string | null>(
    null,
  );
  const [confirmMemoryClear, setConfirmMemoryClear] = useState(false);
  const [confirmSessionDelete, setConfirmSessionDelete] = useState(false);
  const [pendingQuestion, setPendingQuestion] = useState<string | null>(null);
  const [progressEvents, setProgressEvents] = useState<AgentProgressEvent[]>(
    [],
  );
  const [sourceId, setSourceId] = useState("");
  const [consentOpen, setConsentOpen] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [runMessage, setRunMessage] = useState<string | null>(null);
  const [latestRun, setLatestRun] = useState<ResearchRun | null>(null);
  const [copyStatus, setCopyStatus] = useState<string | null>(null);
  const controllerRef = useRef<AbortController | null>(null);

  const selectedOption = modelOptions?.options.find(
    (option) => option.provider === selectedProvider,
  );
  const availableOptions =
    modelOptions?.options.filter((option) => option.configured) ?? [];
  const activeSession = sessions.find(
    (session) => session.session_id === activeSessionId,
  );
  const exchanges = pairMessages(conversation);
  const showStandaloneTrail = !latestRun?.response || isRunning;

  useEffect(() => {
    const controller = new AbortController();
    let active = true;

    async function restoreWorkspace() {
      try {
        const id = workspaceIdForBrowser();
        if (!active) return;
        setWorkspaceId(id);
        const [preferencesResult, pageResult] = await Promise.allSettled([
          getWorkspacePreferences(id, controller.signal),
          listSessions(id, 50, undefined, controller.signal),
        ]);
        if (!active) return;
        if (preferencesResult.status === "fulfilled") {
          setLongMemoryEnabled(preferencesResult.value.long_memory_enabled);
        } else {
          // Memory settings are optional; they must never prevent chat history loading.
          setLongMemoryEnabled(false);
        }
        if (pageResult.status === "rejected") throw pageResult.reason;
        const page = pageResult.value;
        setSessions(page.sessions);
        const savedSessionId = window.localStorage.getItem(
          `${ACTIVE_SESSION_STORAGE_PREFIX}${id}`,
        );
        const selected =
          page.sessions.find(
            (session) => session.session_id === savedSessionId,
          ) ?? page.sessions[0];
        if (selected) {
          const history = await readSession(
            id,
            selected.session_id,
            100,
            undefined,
            controller.signal,
          );
          if (!active) return;
          setActiveSessionId(selected.session_id);
          setConversation(messagesFromHistory(history));
          const latest = latestRunFromHistory(history);
          setLatestRun(latest);
          setProgressEvents(latest?.response?.events ?? []);
          setOlderHistoryCursor(history.next_before_turn_id);
          window.localStorage.setItem(
            `${ACTIVE_SESSION_STORAGE_PREFIX}${id}`,
            selected.session_id,
          );
        } else {
          const created = await createSession(id);
          if (!active) return;
          setSessions([created]);
          setActiveSessionId(created.session_id);
          window.localStorage.setItem(
            `${ACTIVE_SESSION_STORAGE_PREFIX}${id}`,
            created.session_id,
          );
        }
      } catch (error) {
        if (
          active &&
          !(error instanceof DOMException && error.name === "AbortError")
        ) {
          setSessionError(safeRequestError(error));
        }
      } finally {
        if (active) setSessionLoading(false);
      }
    }

    void restoreWorkspace();
    return () => {
      active = false;
      controller.abort();
    };
  }, []);

  async function openSession(sessionId: string) {
    if (!workspaceId || isRunning) return;
    setSessionLoading(true);
    setSessionError(null);
    try {
      const history = await readSession(workspaceId, sessionId);
      setActiveSessionId(sessionId);
      setConversation(messagesFromHistory(history));
      const latest = latestRunFromHistory(history);
      setLatestRun(latest);
      setProgressEvents(latest?.response?.events ?? []);
      setOlderHistoryCursor(history.next_before_turn_id);
      setQuestion("");
      setSourceId("");
      window.localStorage.setItem(
        `${ACTIVE_SESSION_STORAGE_PREFIX}${workspaceId}`,
        sessionId,
      );
    } catch (error) {
      setSessionError(safeRequestError(error));
    } finally {
      setSessionLoading(false);
    }
  }

  async function startNewSession() {
    if (!workspaceId) return;
    setSessionLoading(true);
    setSessionError(null);
    try {
      const session = await createSession(workspaceId);
      setSessions((current) => [session, ...current]);
      setActiveSessionId(session.session_id);
      setConversation([]);
      setLatestRun(null);
      setProgressEvents([]);
      setQuestion("");
      setSourceId("");
      setOlderHistoryCursor(null);
      window.localStorage.setItem(
        `${ACTIVE_SESSION_STORAGE_PREFIX}${workspaceId}`,
        session.session_id,
      );
    } catch (error) {
      setSessionError(safeRequestError(error));
    } finally {
      setSessionLoading(false);
    }
  }

  async function loadOlderHistory() {
    if (!workspaceId || !activeSessionId || !olderHistoryCursor) return;
    setHistoryLoading(true);
    try {
      const older = await readSession(
        workspaceId,
        activeSessionId,
        100,
        olderHistoryCursor,
      );
      setConversation((current) => [...messagesFromHistory(older), ...current]);
      setOlderHistoryCursor(older.next_before_turn_id);
    } catch (error) {
      setSessionError(safeRequestError(error));
    } finally {
      setHistoryLoading(false);
    }
  }

  async function setLongMemoryPreference(enabled: boolean) {
    if (!workspaceId) return;
    setMemoryControlPending("preference");
    setMemoryControlError(null);
    setMemoryControlStatus(null);
    try {
      const preferences = await updateWorkspacePreferences(workspaceId, {
        long_memory_enabled: enabled,
      });
      setLongMemoryEnabled(preferences.long_memory_enabled);
      setMemoryControlStatus(
        preferences.long_memory_enabled
          ? "Long-term memory enabled for this workspace."
          : "Long-term memory paused for this workspace.",
      );
    } catch (error) {
      setMemoryControlError(safeRequestError(error));
    } finally {
      setMemoryControlPending(null);
    }
  }

  async function clearLongMemory() {
    if (!workspaceId) return;
    setMemoryControlPending("clear");
    setMemoryControlError(null);
    setMemoryControlStatus(null);
    try {
      const result = await clearWorkspaceMemories(workspaceId);
      setMemoryControlStatus(
        `Cleared ${result.deleted_count} long-term ${
          result.deleted_count === 1 ? "memory" : "memories"
        }.`,
      );
      setConfirmMemoryClear(false);
    } catch (error) {
      setMemoryControlError(safeRequestError(error));
    } finally {
      setMemoryControlPending(null);
    }
  }

  async function deleteActiveSession() {
    if (!workspaceId || !activeSessionId) return;
    setMemoryControlPending("delete");
    setMemoryControlError(null);
    setMemoryControlStatus(null);
    try {
      await deleteSession(workspaceId, activeSessionId);
      setSessions((current) =>
        current.filter((session) => session.session_id !== activeSessionId),
      );
      setActiveSessionId(null);
      setConversation([]);
      setLatestRun(null);
      setProgressEvents([]);
      setOlderHistoryCursor(null);
      setQuestion("");
      setSourceId("");
      setConfirmSessionDelete(false);
      if (
        window.localStorage.getItem(
          `${ACTIVE_SESSION_STORAGE_PREFIX}${workspaceId}`,
        ) === activeSessionId
      ) {
        window.localStorage.removeItem(
          `${ACTIVE_SESSION_STORAGE_PREFIX}${workspaceId}`,
        );
      }
      setMemoryControlStatus(
        "Conversation and its saved memories were deleted.",
      );
    } catch (error) {
      setMemoryControlError(safeRequestError(error));
    } finally {
      setMemoryControlPending(null);
    }
  }

  function fillExample(example: (typeof examplePrompts)[number]) {
    setQuestion(example.question);
    setSourceId(example.sourceId ?? "");
  }

  async function runQuestion(
    allowExternalProvider: boolean,
    allowExternalEmbeddings: boolean,
  ) {
    if (!selectedProvider || !selectedOption?.configured || !question.trim())
      return;
    if (!workspaceId || !activeSessionId) {
      setRunMessage("Open a chat before asking a question.");
      return;
    }

    const submittedQuestion = question.trim();
    const provider = selectedProvider;
    const controller = new AbortController();
    controllerRef.current = controller;
    setConsentOpen(false);
    setIsRunning(true);
    setPendingQuestion(submittedQuestion);
    setProgressEvents([]);
    setRunMessage("Preparing the research run…");

    try {
      const response = await submitAgentAnswerStream(
        {
          schema_version: "1.0",
          query: submittedQuestion,
          mode: "hybrid",
          top_k: 6,
          filters: {
            source_ids: sourceId ? [sourceId] : [],
          },
          provider,
          allow_external_provider: allowExternalProvider,
          allow_external_embeddings: allowExternalEmbeddings,
          reasoning_effort: "none",
          session_id: activeSessionId,
          conversation: recentContext(conversation),
        },
        controller.signal,
        (event) =>
          setProgressEvents((current) => [...current, event].slice(-200)),
        workspaceId,
      );
      const run: ResearchRun = {
        id: response.run_id,
        question: submittedQuestion,
        provider,
        status: response.status,
        response,
      };
      setLatestRun(run);
      setConversation((current) => [
        ...current,
        { role: "user", content: submittedQuestion },
        {
          role: "assistant",
          content:
            response.answer ??
            response.clarification_question ??
            response.abstention_reason ??
            statusLabel(response.status),
          response,
        },
      ]);
      setSessions((current) =>
        current.map((session) =>
          session.session_id === activeSessionId
            ? {
                ...session,
                turn_count: session.turn_count + 1,
                updated_at: new Date().toISOString(),
              }
            : session,
        ),
      );
      setProgressEvents((current) =>
        response.events.length > 0 ? response.events : current,
      );
      setQuestion("");
      setSourceId("");
      setRunMessage(
        response.session_context?.persisted === false
          ? "The answer is ready, but this turn was not saved to the session."
          : null,
      );
      if (response.session_context?.persisted === false)
        setSessionError("The answer was not saved to this conversation.");
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        const run: ResearchRun = {
          id: crypto.randomUUID(),
          question: submittedQuestion,
          provider,
          status: "cancelled",
          message:
            "Stopped waiting in this browser. Backend work may continue until its configured timeout.",
        };
        setLatestRun(run);
        setRunMessage(run.message ?? null);
      } else {
        const message = safeRequestError(error);
        const run: ResearchRun = {
          id: crypto.randomUUID(),
          question: submittedQuestion,
          provider,
          status: "failed_safe",
          message,
        };
        setLatestRun(run);
        setRunMessage(run.message ?? null);
      }
    } finally {
      controllerRef.current = null;
      setIsRunning(false);
      setPendingQuestion(null);
    }
  }

  async function copyText(value: string, label: string) {
    try {
      await navigator.clipboard.writeText(value);
      setCopyStatus(`${label} copied.`);
    } catch {
      setCopyStatus("Clipboard access is unavailable in this browser.");
    }
  }

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!activeSessionId || !workspaceId) {
      setRunMessage("Open a conversation before asking a question.");
      return;
    }
    if (!selectedOption?.configured) {
      setRunMessage(
        "Choose a configured model in Model settings before running a question.",
      );
      return;
    }
    if (
      selectedOption.consent_required ||
      modelOptions?.embedding_consent_required
    ) {
      setConsentOpen(true);
      return;
    }
    void runQuestion(false, false);
  }

  return (
    <div className="research-page">
      <section className="page-intro research-intro">
        <div>
          <p className="eyebrow">RESEARCH</p>
          <h1>Ask a question. Get evidence.</h1>
          <p className="page-description">
            Keep follow-ups, answers, and sources together in one chat.
          </p>
        </div>
        <div className="workspace-stamp">
          <span className="stamp-pip" aria-hidden="true" />
          <span>LOCAL WORKSPACE</span>
        </div>
      </section>

      <div
        className={`research-layout${showStandaloneTrail ? " has-agent-trail" : ""}`}
      >
        <aside
          aria-label="Conversation sessions and memory"
          className="conversation-sidebar"
        >
          <section className="session-panel" aria-labelledby="sessions-title">
            <div className="session-panel-heading">
              <div>
                <p className="eyebrow">CHATS</p>
                <h2 id="sessions-title">Your chats</h2>
              </div>
              <button
                className="button button-secondary"
                disabled={!workspaceId || sessionLoading || isRunning}
                onClick={() => void startNewSession()}
                type="button"
              >
                <MessageSquarePlus aria-hidden="true" size={15} />
                New chat
              </button>
            </div>
            {sessionError && (
              <p className="inline-alert" role="alert">
                {sessionError}
              </p>
            )}
            {sessionLoading ? (
              <p className="session-loading" role="status">
                <LoaderCircle aria-hidden="true" className="spin" size={15} />
                Loading conversations…
              </p>
            ) : sessions.length > 0 ? (
              <ul className="session-list" aria-label="Saved conversations">
                {sessions.map((session) => (
                  <li key={session.session_id}>
                    <button
                      aria-current={
                        session.session_id === activeSessionId
                          ? "page"
                          : undefined
                      }
                      className={
                        session.session_id === activeSessionId
                          ? "session-option is-active"
                          : "session-option"
                      }
                      disabled={isRunning}
                      onClick={() => void openSession(session.session_id)}
                      type="button"
                    >
                      <span>{session.title}</span>
                      <span>
                        {session.turn_count}{" "}
                        {session.turn_count === 1 ? "exchange" : "exchanges"}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="session-empty">Select New chat to get started.</p>
            )}
            <div className="memory-controls">
              <label className="memory-toggle">
                <input
                  checked={longMemoryEnabled}
                  disabled={sessionLoading || memoryControlPending !== null}
                  onChange={(event) =>
                    void setLongMemoryPreference(event.target.checked)
                  }
                  type="checkbox"
                />
                <span>Enable long-term memory</span>
              </label>
              <span className="memory-state" role="status">
                {longMemoryEnabled
                  ? "On · relevant context may carry across chats."
                  : "Off · nothing is remembered between chats."}
              </span>
              {memoryControlPending && (
                <p className="memory-operation-status" role="status">
                  {memoryControlPending === "preference"
                    ? "Saving memory setting…"
                    : memoryControlPending === "clear"
                      ? "Clearing long-term memory…"
                      : "Deleting chat and its memories…"}
                </p>
              )}
              {memoryControlStatus && (
                <p className="memory-operation-status" role="status">
                  {memoryControlStatus}
                </p>
              )}
              {memoryControlError && (
                <p className="inline-alert" role="alert">
                  {memoryControlError}
                </p>
              )}
              <details className="memory-options">
                <summary>Manage memory</summary>
                <div className="memory-options-content">
                  <p className="memory-explainer">
                    Chats keep their own history. You can clear saved memories
                    or delete this chat and its memories here.
                  </p>
                  <div className="memory-actions">
                    <button
                      className="button button-secondary"
                      disabled={memoryControlPending !== null || sessionLoading}
                      onClick={() => {
                        setMemoryControlError(null);
                        setMemoryControlStatus(null);
                        setConfirmMemoryClear(true);
                      }}
                      type="button"
                    >
                      Clear long-term memory
                    </button>
                    {activeSession && (
                      <button
                        className="button button-secondary danger-button"
                        disabled={
                          memoryControlPending !== null || sessionLoading
                        }
                        onClick={() => {
                          setMemoryControlError(null);
                          setMemoryControlStatus(null);
                          setConfirmSessionDelete(true);
                        }}
                        type="button"
                      >
                        Delete conversation
                      </button>
                    )}
                  </div>
                  {confirmMemoryClear && (
                    <div className="memory-confirmation">
                      <p>
                        Clear all long-term memories for this browser workspace?
                        Saved conversation transcripts will remain.
                      </p>
                      <button
                        className="button button-secondary"
                        disabled={memoryControlPending !== null}
                        onClick={() => setConfirmMemoryClear(false)}
                        type="button"
                      >
                        Cancel clear
                      </button>
                      <button
                        className="button button-primary danger-button"
                        disabled={memoryControlPending !== null}
                        onClick={() => void clearLongMemory()}
                        type="button"
                      >
                        Confirm clear memory
                      </button>
                    </div>
                  )}
                  {confirmSessionDelete && activeSession && (
                    <div className="memory-confirmation">
                      <p>
                        Delete “{activeSession.title}”, its transcript, and
                        derived memories? This cannot be undone.
                      </p>
                      <button
                        className="button button-secondary"
                        disabled={memoryControlPending !== null}
                        onClick={() => setConfirmSessionDelete(false)}
                        type="button"
                      >
                        Cancel deletion
                      </button>
                      <button
                        className="button button-primary danger-button"
                        disabled={memoryControlPending !== null}
                        onClick={() => void deleteActiveSession()}
                        type="button"
                      >
                        Confirm delete conversation
                      </button>
                    </div>
                  )}
                </div>
              </details>
            </div>
          </section>
        </aside>

        <section
          className="conversation-thread"
          aria-labelledby="conversation-title"
        >
          <div className="chat-header">
            <div className="chat-title-group">
              <p className="eyebrow">ACTIVE CHAT</p>
              <h2 id="conversation-title">
                {activeSession?.title ?? "Start a new chat"}
              </h2>
              <p>
                {activeSession
                  ? `${activeSession.turn_count} ${activeSession.turn_count === 1 ? "exchange" : "exchanges"}`
                  : "Create a chat to start asking questions."}
              </p>
            </div>
            {olderHistoryCursor && (
              <button
                className="button button-secondary"
                disabled={historyLoading || isRunning}
                onClick={() => void loadOlderHistory()}
                type="button"
              >
                {historyLoading ? "Loading…" : "Load older messages"}
              </button>
            )}
          </div>

          <p className="chat-context-note" aria-label="How follow-ups work">
            Follow-ups use the last 5 completed exchanges. Older messages stay
            in this chat, and every answer searches current evidence.
          </p>

          {conversation.length > 0 || pendingQuestion ? (
            <ol className="conversation-list" aria-label="Chat exchanges">
              {exchanges.map((pair, index) => (
                <li
                  className="conversation-pair"
                  key={`${index}-${pair.user?.content ?? pair.assistant?.content}`}
                >
                  <span className="exchange-number">Exchange {index + 1}</span>
                  {pair.user && (
                    <article className="conversation-message message-user">
                      <span>You · Question</span>
                      <p>{pair.user.content}</p>
                    </article>
                  )}
                  {pair.assistant && (
                    <article className="conversation-message message-assistant">
                      <span>PolicyLens · Answer</span>
                      <AnswerContent
                        answer={pair.assistant.content}
                        copied={copyStatus === "Citation copied."}
                        onCopyCitation={(value) =>
                          void copyText(value, "Citation")
                        }
                        response={pair.assistant.response}
                      />
                      {pair.assistant.response?.status === "failed_safe" &&
                        pair.assistant.response.error_code && (
                          <div className="answer-failure-note" role="status">
                            <strong>Why it stopped</strong>
                            <p>
                              {failureExplanation(
                                pair.assistant.response.error_code,
                                pair.assistant.response.events,
                              )}
                            </p>
                            <span>
                              Trace ID:{" "}
                              <code>{pair.assistant.response.trace_id}</code>
                            </span>
                          </div>
                        )}
                      {index === exchanges.length - 1 &&
                        latestRun?.response &&
                        pair.assistant.content ===
                          latestRun.response.answer && (
                          <button
                            aria-label="Copy answer"
                            className="icon-button copy-button"
                            onClick={() =>
                              void copyText(
                                latestRun.response?.answer ?? "",
                                "Answer",
                              )
                            }
                            title="Copy answer"
                            type="button"
                          >
                            {copyStatus === "Answer copied." ? (
                              <ClipboardCheck aria-hidden="true" size={15} />
                            ) : (
                              <Clipboard aria-hidden="true" size={15} />
                            )}
                          </button>
                        )}
                      <AgentTrail
                        embedded
                        events={pair.assistant.response?.events ?? []}
                        hasRun={pair.assistant.response !== undefined}
                        isRunning={false}
                        modelMetadata={
                          pair.assistant.response?.model_metadata ?? null
                        }
                      />
                    </article>
                  )}
                </li>
              ))}
              {pendingQuestion && (
                <li className="conversation-pair is-pending">
                  <span className="exchange-number">Next exchange</span>
                  <article className="conversation-message message-user">
                    <span>You · Question</span>
                    <p>{pendingQuestion}</p>
                  </article>
                  <article className="conversation-message message-assistant pending-answer">
                    <span>
                      <LoaderCircle
                        aria-hidden="true"
                        className="spin"
                        size={13}
                      />
                      PolicyLens is working
                    </span>
                    <p>{runMessage ?? "Preparing evidence and tools…"}</p>
                  </article>
                </li>
              )}
            </ol>
          ) : (
            <div className="chat-welcome">
              <div className="chat-welcome-mark" aria-hidden="true">
                P
              </div>
              <p className="eyebrow">EVIDENCE-LED CHAT</p>
              <h3>Start with a policy question</h3>
              <p>
                Ask about a policy, outcome, or statistic. Continue with
                follow-ups here, and check the sources behind each answer.
              </p>
              <div className="example-section">
                <div className="example-heading">
                  <span>Try an example</span>
                  <span className="example-hint">
                    Click to fill the composer
                  </span>
                </div>
                <div className="example-prompts">
                  {examplePrompts.map((example) => (
                    <button
                      className="example-prompt"
                      key={example.id}
                      onClick={() => fillExample(example)}
                      type="button"
                    >
                      <span>{example.label}</span>
                      <ArrowDown aria-hidden="true" size={15} />
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}
        </section>

        <section
          className="question-workspace"
          aria-labelledby="question-title"
        >
          <div className="section-heading">
            <div>
              <p className="eyebrow">YOUR MESSAGE</p>
              <h2 id="question-title">
                {conversation.length > 0
                  ? "Ask a follow-up"
                  : "Ask your first question"}
              </h2>
            </div>
            <label className="provider-control">
              <span>Model</span>
              <select
                aria-label="Model provider"
                disabled={availableOptions.length === 0}
                onChange={(event) =>
                  setSelectedProvider(event.target.value as ModelProvider)
                }
                value={selectedProvider ?? ""}
              >
                {availableOptions.map((option) => (
                  <option key={option.provider} value={option.provider}>
                    {option.provider === "mlx" ? "Local · " : "OpenAI · "}
                    {option.model_id}
                  </option>
                ))}
              </select>
            </label>
            {selectedOption?.route === "openai_chat_completions" && (
              <p className="reasoning-route-note">
                This deployment uses Chat Completions, so SDK reasoning
                summaries are unavailable. For a compatible Foundry endpoint,
                set <code>OPENAI_USE_RESPONSES_API=true</code> and restart the
                API.
              </p>
            )}
          </div>
          {modelOptionsError && (
            <p className="inline-alert" role="status">
              {modelOptionsError}
            </p>
          )}
          {modelOptions && availableOptions.length === 0 && (
            <p className="inline-alert" role="alert">
              No generation model is configured. Check Model settings.
            </p>
          )}
          {selectedOption?.execution_scope === "external" && (
            <p className="provider-note" role="status">
              OpenAI receives your question, selected evidence, and any
              conversation context only after confirmation for each run.
            </p>
          )}
          {modelOptions?.embedding_consent_required &&
            selectedOption?.execution_scope !== "external" && (
              <p className="provider-note" role="status">
                OpenAI embeddings will process this turn's question and, when
                enabled, the completed conversation pair for long-term memory
                after your confirmation.
              </p>
            )}

          <form className="composer" onSubmit={handleSubmit}>
            <label className="sr-only" htmlFor="research-question">
              Research question
            </label>
            <textarea
              id="research-question"
              aria-label="Research question"
              maxLength={2000}
              onChange={(event) => {
                setQuestion(event.target.value);
                setSourceId("");
              }}
              placeholder="Ask a question about policy, evidence, or outcomes…"
              value={question}
              rows={3}
            />
            <div className="composer-toolbar">
              <span className="composer-spacer" />
              {isRunning ? (
                <button
                  className="button button-secondary cancel-button"
                  onClick={() => controllerRef.current?.abort()}
                  type="button"
                >
                  <Square aria-hidden="true" size={14} fill="currentColor" />
                  Stop waiting
                </button>
              ) : (
                <button
                  className="button button-primary ask-button"
                  disabled={
                    !question.trim() ||
                    !selectedOption?.configured ||
                    !activeSessionId ||
                    sessionLoading
                  }
                  type="submit"
                >
                  {conversation.length > 0 ? "Send follow-up" : "Ask question"}
                  <ArrowUp aria-hidden="true" size={16} />
                </button>
              )}
            </div>
            <div className="composer-footnote">
              <span>
                Each answer uses current evidence. Private reasoning is not
                shown.
              </span>
              <span>{question.length}/2000</span>
            </div>
          </form>

          {runMessage && (isRunning || !latestRun?.message) && (
            <p className="run-status" role="status">
              {isRunning ? (
                <LoaderCircle aria-hidden="true" className="spin" size={16} />
              ) : (
                <Clock3 aria-hidden="true" size={16} />
              )}
              {runMessage}
            </p>
          )}
        </section>

        {showStandaloneTrail && (
          <AgentTrail
            events={progressEvents}
            hasRun={latestRun !== null}
            isRunning={isRunning}
          />
        )}

        {latestRun && (
          <section className="latest-run" aria-labelledby="latest-run-title">
            <div className="run-heading">
              <div>
                <p className="eyebrow">ANSWER DETAILS</p>
                <h2 id="latest-run-title">
                  {latestRun.response
                    ? statusLabel(latestRun.response.status)
                    : "Run ended"}
                </h2>
              </div>
              {latestRun.response && (
                <span className="trace-id">
                  Trace {latestRun.response.trace_id}
                </span>
              )}
            </div>
            {latestRun.response?.session_context && (
              <div className="session-result-status" role="status">
                <span>
                  Chat{" "}
                  {latestRun.response.session_context.persisted
                    ? "saved"
                    : "not saved"}
                </span>
                <span>
                  Long-term memory:{" "}
                  {memoryRetrievalLabel(
                    latestRun.response.session_context.memory_retrieval_status,
                  )}
                  {latestRun.response.session_context
                    .memory_retrieval_status === "used" &&
                    ` · ${latestRun.response.session_context.retrieved_memory_count} found`}
                </span>
                <span>
                  Memory update:{" "}
                  {memoryWriteLabel(
                    latestRun.response.session_context.memory_write_status,
                  )}
                </span>
              </div>
            )}
            {latestRun.message && (
              <p className="answer-limitation" role="status">
                {latestRun.message}
              </p>
            )}
            {latestRun.response?.limitations.map((limitation) => (
              <p className="answer-limitation" key={limitation}>
                {limitation}
              </p>
            ))}
            {latestRun.response?.uncertainty.length ? (
              <section className="response-detail-section">
                <h3>Uncertainty</h3>
                <ul>
                  {latestRun.response.uncertainty.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </section>
            ) : null}
            {latestRun.response?.conflicts.map((conflict, index) => (
              <section
                className="response-detail-section conflict-section"
                key={`${conflict.summary}-${index}`}
              >
                <h3>Evidence conflict</h3>
                <p>{conflict.summary}</p>
                <span>Related claims: {conflict.claim_ids.join(", ")}</span>
              </section>
            ))}
            {latestRun.response?.calculations.length ? (
              <h3 className="answer-details-heading">Calculations</h3>
            ) : null}
            {latestRun.response?.calculations.map((calculation) => (
              <details
                className="calculation-detail"
                key={calculation.calculation_id}
              >
                <summary>
                  {calculation.operation} calculation ·{" "}
                  {calculation.rows.length} rows
                </summary>
                <p>
                  {calculation.formula} {calculation.rounding}
                </p>
                <div className="calculation-table-wrap">
                  <table>
                    <caption className="sr-only">
                      Deterministic calculation rows
                    </caption>
                    <thead>
                      <tr>
                        <th scope="col">Geography</th>
                        <th scope="col">Year</th>
                        <th scope="col">Value</th>
                        <th scope="col">Unit</th>
                      </tr>
                    </thead>
                    <tbody>
                      {calculation.rows.map((row, index) => (
                        <tr
                          key={`${row.geography ?? "all"}-${row.year ?? index}`}
                        >
                          <td>{row.geography ?? "All"}</td>
                          <td>{row.year ?? "Aggregate"}</td>
                          <td>{row.value ?? "Not reported"}</td>
                          <td>{row.unit ?? ""}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {calculation.warnings.map((warning) => (
                  <p className="answer-limitation" key={warning}>
                    {warning}
                  </p>
                ))}
              </details>
            ))}
            {copyStatus && (
              <p className="copy-status" role="status">
                {copyStatus}
              </p>
            )}
          </section>
        )}
      </div>

      {consentOpen && (
        <ProviderConsentDialog
          onCancel={() => setConsentOpen(false)}
          onConfirm={() =>
            void runQuestion(
              Boolean(selectedOption?.consent_required),
              Boolean(modelOptions?.embedding_consent_required),
            )
          }
          hasConversation={conversation.length > 0}
          externalGeneration={Boolean(selectedOption?.consent_required)}
          externalEmbeddings={Boolean(modelOptions?.embedding_consent_required)}
          longMemoryEnabled={longMemoryEnabled}
          question={question.trim()}
        />
      )}
    </div>
  );
}
