import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "../src/App";
import { getApiBaseUrl } from "../src/api/health";

const optionsPayload = {
  schema_version: "1.0" as const,
  default_provider: "mlx" as const,
  embedding_provider: "local" as const,
  embedding_consent_required: false,
  options: [
    {
      provider: "openai" as const,
      route: "openai_responses" as const,
      model_id: "test-openai-model",
      execution_scope: "external" as const,
      configured: true,
      selected_by_default: false,
      consent_required: true,
      reasoning_efforts: ["none", "low", "medium", "high"] as const,
    },
    {
      provider: "mlx" as const,
      route: "mlx_chat_completions" as const,
      model_id: "test-local-model",
      execution_scope: "loopback" as const,
      configured: true,
      selected_by_default: true,
      consent_required: false,
      reasoning_efforts: ["none", "low", "medium"] as const,
    },
  ],
};

const answerPayload = {
  schema_version: "1.0",
  run_id: "run-test-1",
  trace_id: "trace-test-1",
  index_version: "a".repeat(64),
  status: "answered",
  answer: "Youth unemployment was 16 percent.",
  claims: [],
  calculations: [],
  uncertainty: [],
  conflicts: [],
  clarification_question: null,
  abstention_reason: null,
  limitations: [],
  provider: "mlx",
  model: "test-local-model",
  session_context: {
    session_id: "00000000-0000-4000-8000-000000000001",
    turn_id: "00000000-0000-4000-8000-000000000002",
    persisted: true,
    long_memory_enabled: false,
    memory_retrieval_status: "disabled",
    retrieved_memory_count: 0,
    memory_write_status: "skipped",
  },
  prompt_version: "agent-v1",
  events: [],
  error_code: null,
};

function response(payload: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
  };
}

function streamResponse(frames: string[]) {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const frame of frames) controller.enqueue(encoder.encode(frame));
      controller.close();
    },
  });
  return { ok: true, status: 200, body };
}

function withSessionApi(
  fallback: unknown,
  options: { acknowledged?: boolean } = {},
) {
  const fallbackFetch = fallback as (
    input: RequestInfo | URL,
    init?: RequestInit,
  ) => Promise<unknown>;
  let acknowledged = options.acknowledged ?? true;
  const sessions: Array<{
    session_id: string;
    title: string;
    created_at: string;
    updated_at: string;
    turn_count: number;
  }> = [];
  const turnsBySession = new Map<string, unknown[]>();
  let nextSessionNumber = 1;

  return vi.fn(
    async (input: RequestInfo | URL, init?: RequestInit): Promise<unknown> => {
      const requestUrl = new URL(String(input), "http://localhost");
      const method = init?.method ?? "GET";
      if (requestUrl.pathname === "/sessions/preferences") {
        if (method === "PUT") {
          const body = JSON.parse(String(init?.body)) as {
            data_use_acknowledged?: boolean;
            long_memory_enabled?: boolean;
          };
          acknowledged = body.data_use_acknowledged ?? acknowledged;
          return response({
            schema_version: "1.0",
            data_use_acknowledged: acknowledged,
            data_use_acknowledged_at: acknowledged
              ? "2026-10-27T00:00:00Z"
              : null,
            long_memory_enabled: body.long_memory_enabled ?? false,
          });
        }
        return response({
          schema_version: "1.0",
          data_use_acknowledged: acknowledged,
          data_use_acknowledged_at: acknowledged
            ? "2026-10-27T00:00:00Z"
            : null,
          long_memory_enabled: false,
        });
      }
      if (requestUrl.pathname === "/sessions" && method === "GET") {
        return response({
          schema_version: "1.0",
          sessions,
          next_cursor: null,
        });
      }
      if (requestUrl.pathname === "/sessions" && method === "POST") {
        const session = {
          session_id: `00000000-0000-4000-8000-${String(nextSessionNumber).padStart(12, "0")}`,
          title: "New conversation",
          created_at: "2026-10-27T00:00:00Z",
          updated_at: "2026-10-27T00:00:00Z",
          turn_count: 0,
        };
        nextSessionNumber += 1;
        sessions.unshift(session);
        turnsBySession.set(session.session_id, []);
        return response(session);
      }
      const sessionMatch = requestUrl.pathname.match(
        /^\/sessions\/([0-9a-f-]+)$/i,
      );
      if (sessionMatch && method === "GET") {
        const session = sessions.find(
          (item) => item.session_id === sessionMatch[1],
        );
        if (!session) return response({ error_code: "SESSION_NOT_FOUND" }, 404);
        return response({
          schema_version: "1.0",
          session,
          turns: turnsBySession.get(session.session_id) ?? [],
          next_before_turn_id: null,
        });
      }
      const result = await fallbackFetch(input, init);
      if (requestUrl.pathname === "/agent/answer/stream" && init?.body) {
        const requestBody = JSON.parse(String(init.body)) as {
          query: string;
          session_id?: string;
        };
        const agentResult = result as {
          ok?: boolean;
          json?: () => Promise<Record<string, unknown>>;
        };
        if (agentResult.ok && agentResult.json && requestBody.session_id) {
          const payload = await agentResult.json();
          const session = sessions.find(
            (item) => item.session_id === requestBody.session_id,
          );
          if (session) {
            const turnId = `turn-${session.turn_count + 1}`;
            const storedAnswer = {
              ...payload,
              session_context: {
                session_id: session.session_id,
                turn_id: turnId,
                persisted: true,
                long_memory_enabled: false,
                memory_retrieval_status: "disabled",
                retrieved_memory_count: 0,
                memory_write_status: "skipped",
              },
            };
            const turns = turnsBySession.get(session.session_id) ?? [];
            turns.push({
              turn_id: turnId,
              position: turns.length + 1,
              user_content: requestBody.query,
              assistant_content:
                typeof payload.answer === "string" ? payload.answer : null,
              answer: storedAnswer,
              status: "completed",
              created_at: "2026-10-27T00:00:00Z",
              completed_at: "2026-10-27T00:00:01Z",
            });
            turnsBySession.set(session.session_id, turns);
            session.turn_count = turns.length;
          }
        }
      }
      return result;
    },
  );
}

afterEach(() => {
  cleanup();
  window.localStorage.clear();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("research workspace", () => {
  it("offers one source-backed statistic for each country", async () => {
    const fetchMock = vi.fn().mockResolvedValue(response(optionsPayload));
    vi.stubGlobal("fetch", withSessionApi(fetchMock));

    render(<App />);

    const prompt = await screen.findByRole("button", {
      name: "India · Women's share of skills trainees",
    });
    expect(
      screen.getByRole("button", {
        name: "Malaysia · Informal employment rate, 2012–2022",
      }),
    ).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Indonesia · Average jobs created" }),
    ).toBeTruthy();
    expect(
      screen.getByRole("button", {
        name: "Singapore · Employment in services, 2007",
      }),
    ).toBeTruthy();
    fireEvent.click(prompt);

    expect(
      screen.getByRole("textbox", { name: "Research question" }),
    ).toHaveValue(
      "In how many of India's five skills schemes did women represent close to half of trainees?",
    );
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("autofills an example without submitting a request", async () => {
    const fetchMock = vi.fn().mockResolvedValue(response(optionsPayload));
    vi.stubGlobal("fetch", withSessionApi(fetchMock));

    render(<App />);

    const prompt = await screen.findByRole("button", {
      name: "Malaysia · Informal employment rate, 2012–2022",
    });
    fireEvent.click(prompt);

    expect(
      screen.getByRole("textbox", { name: "Research question" }),
    ).toHaveValue(
      "Using the study's proxy definition, what was Malaysia's informal-employment rate in 2012 and 2022?",
    );
    expect(screen.queryByRole("group", { name: "Search options" })).toBeNull();
    expect(
      screen.queryByRole("combobox", { name: "Search method" }),
    ).toBeNull();
    expect(screen.queryByRole("combobox", { name: "Answer depth" })).toBeNull();
    expect(screen.queryByRole("combobox", { name: "PDF source" })).toBeNull();
    expect(screen.queryByRole("combobox", { name: "Country" })).toBeNull();
    expect(screen.queryByRole("spinbutton", { name: "Year" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Clear filters" })).toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("submits a selected example with its exact source filter", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(optionsPayload))
      .mockResolvedValueOnce(
        streamResponse([
          `event: result\ndata: ${JSON.stringify(answerPayload)}\n\n`,
        ]),
      );
    vi.stubGlobal("fetch", withSessionApi(fetchMock));

    render(<App />);
    fireEvent.click(
      await screen.findByRole("button", {
        name: "India · Women's share of skills trainees",
      }),
    );
    fireEvent.click(
      await screen.findByRole("button", { name: "Ask question" }),
    );

    await screen.findByText("Youth unemployment was 16 percent.");
    const request = fetchMock.mock.calls.find(
      ([input]) =>
        new URL(String(input), "http://localhost").pathname ===
        "/agent/answer/stream",
    );
    const requestBody = JSON.parse(String(request?.[1]?.body)) as {
      mode: string;
      reasoning_effort: string;
      filters: Record<string, unknown> & { source_ids: string[] };
    };
    expect(requestBody.mode).toBe("hybrid");
    expect(requestBody.reasoning_effort).toBe("none");
    expect(requestBody.filters.source_ids).toEqual([
      "wb-india-skills-programs-2015",
    ]);
    expect(requestBody.filters).toEqual({
      source_ids: ["wb-india-skills-programs-2015"],
    });
  });

  it("clears an example's source scope when its question is edited", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(optionsPayload))
      .mockResolvedValueOnce(
        streamResponse([
          `event: result\ndata: ${JSON.stringify(answerPayload)}\n\n`,
        ]),
      );
    vi.stubGlobal("fetch", withSessionApi(fetchMock));

    render(<App />);
    fireEvent.click(
      await screen.findByRole("button", {
        name: "India · Women's share of skills trainees",
      }),
    );
    fireEvent.change(
      screen.getByRole("textbox", { name: "Research question" }),
      { target: { value: "A different question across the full corpus" } },
    );
    fireEvent.click(
      await screen.findByRole("button", { name: "Ask question" }),
    );

    await screen.findByText("Youth unemployment was 16 percent.");
    const request = fetchMock.mock.calls.find(
      ([input]) =>
        new URL(String(input), "http://localhost").pathname ===
        "/agent/answer/stream",
    );
    const requestBody = JSON.parse(String(request?.[1]?.body)) as {
      filters: Record<string, unknown>;
    };
    expect(requestBody.filters).toEqual({ source_ids: [] });
  });

  it("renders model answers as safe GitHub-flavored Markdown", async () => {
    const markdownAnswer = {
      ...answerPayload,
      answer:
        "## Summary\n\nThe estimate **rose**.\n\n- 2020: 12%\n- 2025: 16%\n\n| Year | Estimate |\n| --- | ---: |\n| 2020 | 12% |\n\n<script>alert(1)</script>",
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(optionsPayload))
      .mockResolvedValueOnce(
        streamResponse([
          `event: result\ndata: ${JSON.stringify(markdownAnswer)}\n\n`,
        ]),
      );
    vi.stubGlobal("fetch", withSessionApi(fetchMock));

    const { container } = render(<App />);
    await screen.findByRole("combobox", { name: "Model provider" });
    fireEvent.change(
      screen.getByRole("textbox", { name: "Research question" }),
      { target: { value: "Show formatted results" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Ask question" }));

    expect(
      await screen.findByRole("heading", { name: "Summary", level: 2 }),
    ).toBeTruthy();
    expect(screen.getByText("rose")).toBeTruthy();
    expect(container.querySelector(".answer-markdown ul")).toBeTruthy();
    expect(container.querySelector(".answer-markdown table")).toBeTruthy();
    expect(container.querySelector(".answer-markdown script")).toBeNull();
  });

  it("explains safe model failures and shows the trace id for diagnosis", async () => {
    const failedAnswer = {
      ...answerPayload,
      status: "failed_safe",
      answer: null,
      error_code: "MODEL_UNAVAILABLE",
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(optionsPayload))
      .mockResolvedValueOnce(
        streamResponse([
          `event: result\ndata: ${JSON.stringify(failedAnswer)}\n\n`,
        ]),
      );
    vi.stubGlobal("fetch", withSessionApi(fetchMock));

    render(<App />);
    await screen.findByRole("combobox", { name: "Model provider" });
    fireEvent.change(
      screen.getByRole("textbox", { name: "Research question" }),
      { target: { value: "Ask a question that hits a model failure" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Ask question" }));

    expect(await screen.findByText("Why it stopped")).toBeTruthy();
    expect(
      screen.getByText(/configuration problems, provider errors, and timeouts/),
    ).toBeTruthy();
    expect(screen.getByText("trace-test-1")).toBeTruthy();
  });

  it("explains the safe reason a citation was rejected", async () => {
    const failedAnswer = {
      ...answerPayload,
      status: "failed_safe",
      answer: null,
      error_code: "CITATION_INVALID",
      events: [
        {
          sequence: 1,
          state: "citation_validation",
          event_type: "citations_validated",
          status: "failed",
          tool_name: null,
          duration_ms: null,
          error_code: "QUOTE_NOT_EXACT",
          retry_count: 0,
        },
        {
          sequence: 2,
          state: "failed_safe",
          event_type: "terminal",
          status: "failed",
          tool_name: null,
          duration_ms: null,
          error_code: "CITATION_INVALID",
          retry_count: 0,
        },
      ],
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(optionsPayload))
      .mockResolvedValueOnce(
        streamResponse([
          `event: result\ndata: ${JSON.stringify(failedAnswer)}\n\n`,
        ]),
      );
    vi.stubGlobal("fetch", withSessionApi(fetchMock));

    render(<App />);
    await screen.findByRole("combobox", { name: "Model provider" });
    fireEvent.change(
      screen.getByRole("textbox", { name: "Research question" }),
      { target: { value: "Summarize the retrieved evidence" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Ask question" }));

    expect(
      await screen.findByText(/cited quote was not an exact match/),
    ).toBeTruthy();
  });

  it("explains safe statistics argument failures without showing raw arguments", async () => {
    const failedAnswer = {
      ...answerPayload,
      status: "failed_safe",
      answer: null,
      error_code: "TOOL_INVALID_ARGUMENTS",
      events: [
        {
          sequence: 1,
          state: "tool_execution",
          event_type: "tool_completed",
          status: "failed",
          tool_name: "query_statistics",
          duration_ms: 25,
          error_code: "TOOL_INVALID_ARGUMENTS",
          retry_count: 0,
        },
      ],
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(optionsPayload))
      .mockResolvedValueOnce(
        streamResponse([
          `event: result\ndata: ${JSON.stringify(failedAnswer)}\n\n`,
        ]),
      );
    vi.stubGlobal("fetch", withSessionApi(fetchMock));

    render(<App />);
    await screen.findByRole("combobox", { name: "Model provider" });
    fireEvent.change(
      screen.getByRole("textbox", { name: "Research question" }),
      { target: { value: "Compare youth unemployment" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Ask question" }));

    expect(
      await screen.findByText(/1 to 4 unique uppercase ISO3 geographies/),
    ).toBeTruthy();
    expect(screen.getByText("TOOL_INVALID_ARGUMENTS")).toBeTruthy();
    expect(
      screen.queryByText(/raw model arguments|internal provider URL/i),
    ).toBeNull();
  });

  it("explains when MCP passage verification prevents an answer", async () => {
    const failedAnswer = {
      ...answerPayload,
      status: "failed_safe",
      answer: null,
      error_code: "MCP_PASSAGE_MISMATCH",
      events: [
        {
          sequence: 4,
          state: "retrieving",
          event_type: "mcp_resource_completed",
          status: "failed",
          tool_name: null,
          duration_ms: 8,
          error_code: "MCP_PASSAGE_MISMATCH",
          retry_count: 0,
        },
      ],
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(optionsPayload))
      .mockResolvedValueOnce(
        streamResponse([
          `event: result\ndata: ${JSON.stringify(failedAnswer)}\n\n`,
        ]),
      );
    vi.stubGlobal("fetch", withSessionApi(fetchMock));

    render(<App />);
    await screen.findByRole("combobox", { name: "Model provider" });
    fireEvent.change(
      screen.getByRole("textbox", { name: "Research question" }),
      { target: { value: "Verify selected passage" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Ask question" }));

    expect(
      await screen.findByText(
        /did not match the evidence selected from the active index/,
      ),
    ).toBeTruthy();
    expect(screen.getByText("MCP_PASSAGE_MISMATCH")).toBeTruthy();
  });

  it("shows cross-encoder reranking details in the answer activity trail", async () => {
    const rerankingEvent = {
      sequence: 4,
      state: "retrieving",
      event_type: "reranking_completed",
      status: "succeeded",
      tool_name: null,
      duration_ms: 85,
      error_code: null,
      retry_count: 0,
      item_count: 20,
      reranker_model: "jinaai/jina-reranker-v1-tiny-en",
    };
    const answerWithReranking = {
      ...answerPayload,
      events: [rerankingEvent],
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(optionsPayload))
      .mockResolvedValueOnce(
        streamResponse([
          `event: result\ndata: ${JSON.stringify(answerWithReranking)}\n\n`,
        ]),
      );
    vi.stubGlobal("fetch", withSessionApi(fetchMock));

    render(<App />);
    await screen.findByRole("combobox", { name: "Model provider" });
    fireEvent.change(
      screen.getByRole("textbox", { name: "Research question" }),
      { target: { value: "Compare policy evidence" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Ask question" }));
    await screen.findByText("Youth unemployment was 16 percent.");

    expect(screen.getByText("Cross-encoder reranked candidates")).toBeTruthy();
    expect(screen.getByText("20 candidates scored")).toBeTruthy();
    expect(
      screen.getByText("Model: jinaai/jina-reranker-v1-tiny-en"),
    ).toBeTruthy();
    expect(screen.getByText("85 ms")).toBeTruthy();
  });

  it("explains when reranking failed and the baseline hybrid order was retained", async () => {
    const failedReranking = {
      sequence: 4,
      state: "retrieving",
      event_type: "reranking_completed",
      status: "failed",
      tool_name: null,
      duration_ms: 85,
      error_code: "RERANKER_UNAVAILABLE",
      retry_count: 0,
      item_count: 20,
      reranker_model: "jinaai/jina-reranker-v1-tiny-en",
    };
    const answerWithFailedReranking = {
      ...answerPayload,
      events: [failedReranking],
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(optionsPayload))
      .mockResolvedValueOnce(
        streamResponse([
          `event: result\ndata: ${JSON.stringify(answerWithFailedReranking)}\n\n`,
        ]),
      );
    vi.stubGlobal("fetch", withSessionApi(fetchMock));

    render(<App />);
    await screen.findByRole("combobox", { name: "Model provider" });
    fireEvent.change(
      screen.getByRole("textbox", { name: "Research question" }),
      { target: { value: "Compare policy evidence" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Ask question" }));
    await screen.findByText("Youth unemployment was 16 percent.");

    expect(
      screen.getByText(
        "Cross-encoder reranking unavailable; hybrid order retained",
      ),
    ).toBeTruthy();
    expect(screen.getByText("RERANKER_UNAVAILABLE")).toBeTruthy();
  });

  it("shows a clear out-of-scope response instead of a model failure", async () => {
    const blockedAnswer = {
      ...answerPayload,
      status: "blocked",
      answer: null,
      abstention_reason:
        "PolicyLens answers evidence-based policy questions and cannot draw or generate images. Ask a policy or evidence question instead.",
      error_code: "OUT_OF_SCOPE",
      events: [
        {
          sequence: 1,
          state: "blocked",
          event_type: "terminal",
          status: "succeeded",
          tool_name: null,
          duration_ms: null,
          error_code: "OUT_OF_SCOPE",
          retry_count: 0,
        },
      ],
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(optionsPayload))
      .mockResolvedValueOnce(
        streamResponse([
          `event: result\ndata: ${JSON.stringify(blockedAnswer)}\n\n`,
        ]),
      );
    vi.stubGlobal("fetch", withSessionApi(fetchMock));

    render(<App />);
    await screen.findByRole("combobox", { name: "Model provider" });
    fireEvent.change(
      screen.getByRole("textbox", { name: "Research question" }),
      { target: { value: "Could you draw a cat?" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Ask question" }));

    expect(
      await screen.findByText(/cannot draw or generate images/),
    ).toBeTruthy();
    expect(screen.queryByText("Why it stopped")).toBeNull();
    expect(screen.queryByText("MODEL_UNAVAILABLE")).toBeNull();
  });

  it("creates a first chat and accepts a question without an acknowledgement screen", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      void init;
      return Promise.resolve(
        String(input).endsWith("/model/options")
          ? response(optionsPayload)
          : response(answerPayload),
      );
    });
    const sessionFetch = withSessionApi(fetchMock, { acknowledged: false });
    vi.stubGlobal("fetch", sessionFetch);

    render(<App />);
    expect(
      await screen.findByRole("button", { name: "New chat" }),
    ).toBeTruthy();
    expect(screen.queryByText("Before your first chat")).toBeNull();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "New chat" })).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: "New chat" }));
    await waitFor(() =>
      expect(
        sessionFetch.mock.calls.some(([url, init]) => {
          const path = new URL(String(url), "http://localhost").pathname;
          return path === "/sessions" && init?.method === "POST";
        }),
      ).toBe(true),
    );
    fireEvent.change(
      screen.getByRole("textbox", { name: "Research question" }),
      { target: { value: "Synthetic first question" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Ask question" }));
    expect(
      await screen.findByText("Youth unemployment was 16 percent."),
    ).toBeTruthy();
    expect(
      fetchMock.mock.calls.some(([url]) =>
        String(url).endsWith("/agent/answer/stream"),
      ),
    ).toBe(true);
    expect(
      sessionFetch.mock.calls.some(([url, init]) => {
        const path = new URL(String(url), "http://localhost").pathname;
        return path === "/sessions" && init?.method === "POST";
      }),
    ).toBe(true);
  });

  it("switches between persisted sessions without carrying one session's transcript into another", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) =>
      Promise.resolve(
        String(input).endsWith("/model/options")
          ? response(optionsPayload)
          : response(answerPayload),
      ),
    );
    vi.stubGlobal("fetch", withSessionApi(fetchMock));

    render(<App />);
    await screen.findByRole("combobox", { name: "Model provider" });
    await waitFor(() =>
      expect(
        screen.getAllByRole("button", { name: "New chat" })[0],
      ).toBeEnabled(),
    );
    const composer = screen.getByRole("textbox", { name: "Research question" });
    fireEvent.change(composer, { target: { value: "First session question" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask question" }));
    await screen.findByText("Youth unemployment was 16 percent.");
    await waitFor(() =>
      expect(
        screen.getAllByRole("button", { name: "New chat" })[0],
      ).toBeEnabled(),
    );

    fireEvent.click(screen.getAllByRole("button", { name: "New chat" })[0]);
    await waitFor(() =>
      expect(
        within(
          screen.getByRole("list", { name: "Saved conversations" }),
        ).getAllByRole("button"),
      ).toHaveLength(2),
    );
    await waitFor(() =>
      expect(
        screen.getAllByRole("button", { name: "New chat" })[0],
      ).toBeEnabled(),
    );
    fireEvent.change(composer, {
      target: { value: "Second session question" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Ask question" }));
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.filter(([url]) =>
          String(url).endsWith("/agent/answer/stream"),
        ),
      ).toHaveLength(2),
    );
    await waitFor(() =>
      expect(
        screen.getAllByRole("button", { name: "New chat" })[0],
      ).toBeEnabled(),
    );

    const savedSessions = within(
      screen.getByRole("list", { name: "Saved conversations" }),
    ).getAllByRole("button");
    fireEvent.click(savedSessions[1]);
    expect(await screen.findByText("First session question")).toBeTruthy();
    expect(screen.queryByText("Second session question")).toBeNull();
  });

  it("reopens a session after reload with stable workspace identity and backend-bounded follow-up context", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      void init;
      return Promise.resolve(
        String(input).endsWith("/model/options")
          ? response(optionsPayload)
          : response(answerPayload),
      );
    });
    const sessionFetch = withSessionApi(fetchMock);
    vi.stubGlobal("fetch", sessionFetch);

    render(<App />);
    await screen.findByRole("combobox", { name: "Model provider" });
    await waitFor(() =>
      expect(
        screen.getAllByRole("button", { name: "New chat" })[0],
      ).toBeEnabled(),
    );
    fireEvent.change(
      screen.getByRole("textbox", { name: "Research question" }),
      { target: { value: "Question saved before reload" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Ask question" }));
    await screen.findByText("Youth unemployment was 16 percent.");
    const firstRequest = fetchMock.mock.calls.find(([url]) =>
      String(url).endsWith("/agent/answer/stream"),
    );
    const firstBody = JSON.parse(String(firstRequest?.[1]?.body)) as {
      session_id: string;
      conversation: unknown[];
    };

    cleanup();
    render(<App />);
    expect(
      await screen.findByText("Youth unemployment was 16 percent."),
    ).toBeTruthy();
    await waitFor(() =>
      expect(
        screen.getAllByRole("button", { name: "New chat" })[0],
      ).toBeEnabled(),
    );
    fireEvent.change(
      screen.getByRole("textbox", { name: "Research question" }),
      { target: { value: "Follow-up after reload" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Send follow-up" }));
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.filter(([url]) =>
          String(url).endsWith("/agent/answer/stream"),
        ),
      ).toHaveLength(2),
    );

    const followUpRequest = fetchMock.mock.calls
      .filter(([url]) => String(url).endsWith("/agent/answer/stream"))
      .at(-1);
    const followUpBody = JSON.parse(String(followUpRequest?.[1]?.body)) as {
      session_id: string;
      conversation: unknown[];
    };
    expect(followUpBody.session_id).toBe(firstBody.session_id);
    expect(followUpBody.conversation).toHaveLength(2);
    const workspaceIds = sessionFetch.mock.calls
      .filter(([url]) => {
        const path = new URL(String(url), "http://localhost").pathname;
        return path.startsWith("/sessions") || path === "/agent/answer/stream";
      })
      .map(([, init]) => {
        const headers = init?.headers as Record<string, string> | undefined;
        return headers?.["X-Workspace-ID"];
      })
      .filter((id): id is string => Boolean(id));
    expect(new Set(workspaceIds).size).toBe(1);
  });

  it("submits local-model questions only through the backend", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(optionsPayload))
      .mockResolvedValueOnce(response(answerPayload));
    vi.stubGlobal("fetch", withSessionApi(fetchMock));

    render(<App />);

    await screen.findByRole("combobox", { name: "Model provider" });
    fireEvent.change(
      screen.getByRole("textbox", { name: "Research question" }),
      {
        target: { value: "What was the youth unemployment estimate?" },
      },
    );
    fireEvent.click(screen.getByRole("button", { name: "Ask question" }));

    expect(
      await screen.findByText("Youth unemployment was 16 percent."),
    ).toBeTruthy();
    const answerCall = fetchMock.mock.calls.find(([url]) =>
      String(url).endsWith("/agent/answer/stream"),
    );
    expect(answerCall).toBeDefined();
    expect(JSON.parse(String(answerCall?.[1]?.body))).toMatchObject({
      provider: "mlx",
      allow_external_provider: false,
      mode: "hybrid",
      filters: { source_ids: [] },
      reasoning_effort: "none",
      conversation: [],
    });
  });

  it("sends the active session id on follow-up and leaves hot-context selection to the backend", async () => {
    const followUpAnswer = { ...answerPayload, run_id: "run-test-2" };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(optionsPayload))
      .mockResolvedValueOnce(response(answerPayload))
      .mockResolvedValueOnce(response(followUpAnswer));
    vi.stubGlobal("fetch", withSessionApi(fetchMock));

    render(<App />);
    await screen.findByRole("combobox", { name: "Model provider" });
    fireEvent.change(
      screen.getByRole("textbox", { name: "Research question" }),
      {
        target: { value: "First policy question" },
      },
    );
    fireEvent.click(screen.getByRole("button", { name: "Ask question" }));
    await screen.findByText("Youth unemployment was 16 percent.");
    expect(screen.getByText(/last 5 completed exchanges/)).toBeTruthy();
    expect(screen.getByText(/Older messages stay in this chat/)).toBeTruthy();
    fireEvent.change(
      screen.getByRole("textbox", { name: "Research question" }),
      {
        target: { value: "Can you compare that with the prior year?" },
      },
    );
    fireEvent.click(screen.getByRole("button", { name: "Send follow-up" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    expect(screen.getByText("Exchange 1")).toBeTruthy();
    expect(screen.getByText("Exchange 2")).toBeTruthy();

    const followUpBody = JSON.parse(String(fetchMock.mock.calls[2][1]?.body));
    expect(followUpBody).toMatchObject({
      mode: "hybrid",
      filters: { source_ids: [] },
      reasoning_effort: "none",
      conversation: expect.any(Array),
    });
    expect(followUpBody.session_id).toMatch(/^[0-9a-f]{8}-[0-9a-f-]{27}$/i);
    expect(String(fetchMock.mock.calls[2][0])).toContain(
      "/agent/answer/stream",
    );
  });

  it("requires fresh OpenAI consent for a follow-up turn", async () => {
    const followUpAnswer = { ...answerPayload, run_id: "run-test-2" };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(optionsPayload))
      .mockResolvedValueOnce(response(answerPayload))
      .mockResolvedValueOnce(response(followUpAnswer));
    vi.stubGlobal("fetch", withSessionApi(fetchMock));

    render(<App />);
    await screen.findByRole("combobox", { name: "Model provider" });
    fireEvent.change(screen.getByRole("combobox", { name: "Model provider" }), {
      target: { value: "openai" },
    });
    fireEvent.change(
      screen.getByRole("textbox", { name: "Research question" }),
      {
        target: { value: "First OpenAI question" },
      },
    );
    fireEvent.click(screen.getByRole("button", { name: "Ask question" }));
    fireEvent.click(
      await screen.findByRole("button", { name: "Continue with OpenAI" }),
    );
    await screen.findByText("Youth unemployment was 16 percent.");

    fireEvent.change(
      screen.getByRole("textbox", { name: "Research question" }),
      {
        target: { value: "OpenAI follow-up question" },
      },
    );
    fireEvent.click(screen.getByRole("button", { name: "Send follow-up" }));

    expect(
      await screen.findByRole("dialog", {
        name: "Send this question to OpenAI?",
      }),
    ).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledTimes(2);

    fireEvent.click(
      screen.getByRole("button", { name: "Continue with OpenAI" }),
    );
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    expect(JSON.parse(String(fetchMock.mock.calls[2][1]?.body))).toMatchObject({
      provider: "openai",
      allow_external_provider: true,
      conversation: expect.any(Array),
    });
  });

  it("starts a separate session before submitting an independent question", async () => {
    const secondAnswer = { ...answerPayload, run_id: "run-test-2" };
    const thirdAnswer = { ...answerPayload, run_id: "run-test-3" };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(optionsPayload))
      .mockResolvedValueOnce(response(answerPayload))
      .mockResolvedValueOnce(response(secondAnswer))
      .mockResolvedValueOnce(response(thirdAnswer));
    vi.stubGlobal("fetch", withSessionApi(fetchMock));

    render(<App />);
    await screen.findByRole("combobox", { name: "Model provider" });
    const composer = screen.getByRole("textbox", { name: "Research question" });
    fireEvent.change(composer, { target: { value: "First question" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask question" }));
    await screen.findByText("Youth unemployment was 16 percent.");

    fireEvent.change(composer, { target: { value: "Second question" } });
    fireEvent.click(screen.getByRole("button", { name: "Send follow-up" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    const previousSessionId = JSON.parse(
      String(fetchMock.mock.calls[2][1]?.body),
    ).session_id as string;
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "New chat" })).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: "New chat" }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "New chat" })).toBeEnabled(),
    );
    fireEvent.change(composer, {
      target: { value: "New independent question" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Ask question" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(4));

    const newSessionRequest = JSON.parse(
      String(fetchMock.mock.calls[3][1]?.body),
    ) as { query: string; conversation: unknown[]; session_id: string };
    expect(newSessionRequest).toMatchObject({
      query: "New independent question",
      conversation: [],
    });
    expect(newSessionRequest.session_id).not.toBe(previousSessionId);
  });

  it("renders typed retrieval progress without exposing raw event details", async () => {
    const progress = {
      sequence: 3,
      state: "retrieving",
      event_type: "state_transition",
      status: "succeeded",
      tool_name: null,
      duration_ms: null,
      error_code: null,
      retry_count: 0,
    };
    const toolStarted = {
      ...progress,
      sequence: 7,
      state: "tool_execution",
      event_type: "tool_started",
      status: "started",
      tool_name: "query_statistics",
    };
    const passageStarted = {
      ...progress,
      sequence: 5,
      event_type: "mcp_resource_started",
      status: "started",
    };
    const passageCompleted = {
      ...passageStarted,
      sequence: 6,
      event_type: "mcp_resource_completed",
      status: "succeeded",
      item_count: 1,
    };
    const toolCompleted = {
      ...progress,
      sequence: 8,
      state: "tool_execution",
      event_type: "tool_completed",
      status: "succeeded",
      tool_name: "query_statistics",
    };
    const answerWithEvents = {
      ...answerPayload,
      events: [
        progress,
        passageStarted,
        passageCompleted,
        toolStarted,
        toolCompleted,
      ],
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(optionsPayload))
      .mockResolvedValueOnce(
        streamResponse([
          `event: progress\ndata: ${JSON.stringify(progress)}\n\n`,
          `event: progress\ndata: ${JSON.stringify(toolStarted)}\n\n`,
          `event: result\ndata: ${JSON.stringify(answerWithEvents)}\n\n`,
        ]),
      );
    vi.stubGlobal("fetch", withSessionApi(fetchMock));

    render(<App />);
    await screen.findByRole("combobox", { name: "Model provider" });
    fireEvent.change(
      screen.getByRole("textbox", { name: "Research question" }),
      {
        target: { value: "Show retrieval progress" },
      },
    );
    fireEvent.click(screen.getByRole("button", { name: "Ask question" }));

    const trailSummary = await screen.findByText(
      "How this answer was prepared",
    );
    expect(trailSummary.closest("details.answer-agent-trail")).toHaveProperty(
      "open",
      true,
    );
    expect(screen.getByText("Searching policy evidence")).toBeTruthy();
    expect(
      screen.getByText("Loading retrieved passages from Policy Data MCP"),
    ).toBeTruthy();
    expect(
      screen.getByText("Passages verified by Policy Data MCP"),
    ).toBeTruthy();
    expect(screen.getByText("1 passage verified")).toBeTruthy();
    expect(screen.getByText("Statistics query started")).toBeTruthy();
    expect(screen.getByText("Statistics query completed")).toBeTruthy();
    expect(screen.getAllByText("Finished")).toHaveLength(2);
    expect(screen.queryByText("In progress")).toBeNull();
    expect(screen.queryByText("PolicyLens Policy Data Server")).toBeNull();
    expect(screen.queryByText("query_statistics")).toBeNull();
  });

  it("settles unfinished trail steps when a response has ended", async () => {
    const modelStarted = {
      sequence: 1,
      state: "answering",
      event_type: "model_started",
      status: "started",
      tool_name: null,
      duration_ms: null,
      error_code: null,
      retry_count: 0,
    };
    const answerWithUnfinishedStep = {
      ...answerPayload,
      events: [modelStarted],
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(optionsPayload))
      .mockResolvedValueOnce(
        streamResponse([
          `event: result\ndata: ${JSON.stringify(answerWithUnfinishedStep)}\n\n`,
        ]),
      );
    vi.stubGlobal("fetch", withSessionApi(fetchMock));

    render(<App />);
    await screen.findByRole("combobox", { name: "Model provider" });
    fireEvent.change(
      screen.getByRole("textbox", { name: "Research question" }),
      { target: { value: "Check completed trail statuses" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Ask question" }));
    await screen.findByText("Youth unemployment was 16 percent.");

    expect(
      screen
        .getByText("How this answer was prepared")
        .closest("details.answer-agent-trail"),
    ).toHaveProperty("open", true);
    expect(screen.getByText("Model started")).toBeTruthy();
    expect(screen.getByText("Run ended")).toBeTruthy();
    expect(screen.queryByText("In progress")).toBeNull();
  });

  it("opens each answer's processing summary by default and lets it be collapsed", async () => {
    const retrievalEvent = {
      sequence: 1,
      state: "retrieving",
      event_type: "retrieval_completed",
      status: "succeeded",
      tool_name: null,
      duration_ms: 12,
      error_code: null,
      retry_count: 0,
    };
    const modelEvent = {
      sequence: 1,
      state: "answering",
      event_type: "model_completed",
      status: "succeeded",
      tool_name: null,
      duration_ms: 20,
      error_code: null,
      retry_count: 0,
    };
    const firstAnswer = {
      ...answerPayload,
      run_id: "run-first",
      answer: "First turn answer.",
      events: [retrievalEvent],
    };
    const secondAnswer = {
      ...answerPayload,
      run_id: "run-second",
      answer: "Second turn answer.",
      events: [modelEvent],
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(optionsPayload))
      .mockResolvedValueOnce(
        streamResponse([
          `event: result\ndata: ${JSON.stringify(firstAnswer)}\n\n`,
        ]),
      )
      .mockResolvedValueOnce(
        streamResponse([
          `event: result\ndata: ${JSON.stringify(secondAnswer)}\n\n`,
        ]),
      );
    vi.stubGlobal("fetch", withSessionApi(fetchMock));

    const { container } = render(<App />);
    await screen.findByRole("combobox", { name: "Model provider" });
    const composer = screen.getByRole("textbox", { name: "Research question" });
    fireEvent.change(composer, {
      target: { value: "First synthetic question" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Ask question" }));
    await screen.findByText("First turn answer.");

    fireEvent.change(composer, {
      target: { value: "Second synthetic question" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send follow-up" }));
    await screen.findByText("Second turn answer.");

    const disclosures = container.querySelectorAll<HTMLDetailsElement>(
      "details.answer-agent-trail",
    );
    expect(disclosures).toHaveLength(2);
    expect(disclosures[0]?.open).toBe(true);
    expect(disclosures[1]?.open).toBe(true);
    expect(
      disclosures[0]?.querySelector(".answer-agent-trail-toggle svg"),
    ).not.toBeNull();
    expect(disclosures[0]?.textContent).toContain("Evidence search completed");
    expect(disclosures[0]?.textContent).not.toContain("Model finished");
    expect(disclosures[1]?.textContent).toContain("Model finished");
    expect(disclosures[1]?.textContent).not.toContain(
      "Evidence search completed",
    );

    const firstSummary = disclosures[0]?.querySelector("summary");
    expect(firstSummary).not.toBeNull();
    if (firstSummary) fireEvent.click(firstSummary);
    expect(disclosures[0]?.open).toBe(false);
    if (firstSummary) fireEvent.click(firstSummary);
    expect(disclosures[0]?.open).toBe(true);
  });

  it("shows Responses API usage and the SDK reasoning summary per answer", async () => {
    const responseAnswer = {
      ...answerPayload,
      provider: "openai",
      model: "test-openai-model",
      model_metadata: {
        provider: "openai",
        model_id: "test-openai-model",
        prompt_version: "agent-v1",
        latency_ms: 42,
        usage: {
          requests: 2,
          prompt_tokens: 125,
          completion_tokens: 48,
          total_tokens: 173,
          cached_input_tokens: 10,
          reasoning_tokens: 21,
        },
        capabilities: { route: "openai_responses" },
        reasoning_effort: "low",
        reasoning_summary: "Compared the available evidence.",
      },
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(optionsPayload))
      .mockResolvedValueOnce(
        streamResponse([
          `event: result\ndata: ${JSON.stringify(responseAnswer)}\n\n`,
        ]),
      );
    vi.stubGlobal("fetch", withSessionApi(fetchMock));

    const { container } = render(<App />);
    await screen.findByRole("combobox", { name: "Model provider" });
    fireEvent.change(screen.getByRole("combobox", { name: "Model provider" }), {
      target: { value: "openai" },
    });
    fireEvent.change(
      screen.getByRole("textbox", { name: "Research question" }),
      { target: { value: "Compare synthetic evidence." } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Ask question" }));
    fireEvent.click(
      await screen.findByRole("button", { name: "Continue with OpenAI" }),
    );
    await screen.findByText("Youth unemployment was 16 percent.");

    const summary = container.querySelector(
      "details.answer-agent-trail summary",
    );
    expect(summary).not.toBeNull();
    expect(summary?.closest("details")).toHaveProperty("open", true);

    const modelDetails = screen.getByRole("region", {
      name: "Model usage and reasoning",
    });
    expect(within(modelDetails).getByText("OpenAI Responses API")).toBeTruthy();
    expect(within(modelDetails).getByText("125")).toBeTruthy();
    expect(within(modelDetails).getByText("48")).toBeTruthy();
    expect(within(modelDetails).getByText("21")).toBeTruthy();
    expect(
      within(modelDetails).getByText("Compared the available evidence."),
    ).toBeTruthy();
    expect(within(modelDetails).queryByText(/PRIVATE_REASONING/)).toBeNull();
  });

  it("explains Chat Completions summary limits and displays event token usage", async () => {
    const chatOptions = {
      ...optionsPayload,
      options: optionsPayload.options.map((option) =>
        option.provider === "openai"
          ? {
              ...option,
              route: "openai_chat_completions",
              reasoning_efforts: ["none"],
            }
          : option,
      ),
    };
    const chatAnswer = {
      ...answerPayload,
      provider: "openai",
      model: "test-openai-model",
      events: [
        {
          sequence: 1,
          state: "answering",
          event_type: "model_completed",
          status: "succeeded",
          tool_name: null,
          duration_ms: 50,
          error_code: null,
          retry_count: 0,
          model_route: "openai_chat_completions",
          reasoning_effort: "none",
          model_usage: {
            requests: 1,
            prompt_tokens: 22,
            completion_tokens: 10,
            total_tokens: 32,
            cached_input_tokens: null,
            reasoning_tokens: null,
          },
        },
      ],
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(chatOptions))
      .mockResolvedValueOnce(
        streamResponse([
          `event: result\ndata: ${JSON.stringify(chatAnswer)}\n\n`,
        ]),
      );
    vi.stubGlobal("fetch", withSessionApi(fetchMock));

    const { container } = render(<App />);
    await screen.findByRole("combobox", { name: "Model provider" });
    fireEvent.change(screen.getByRole("combobox", { name: "Model provider" }), {
      target: { value: "openai" },
    });
    expect(
      screen.getByText(/This deployment uses Chat Completions/),
    ).toBeTruthy();
    fireEvent.change(
      screen.getByRole("textbox", { name: "Research question" }),
      { target: { value: "Ask a synthetic question." } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Ask question" }));
    fireEvent.click(
      await screen.findByRole("button", { name: "Continue with OpenAI" }),
    );
    await screen.findByText("Youth unemployment was 16 percent.");

    const summary = container.querySelector(
      "details.answer-agent-trail summary",
    );
    expect(summary).not.toBeNull();
    expect(summary?.closest("details")).toHaveProperty("open", true);

    const modelDetails = screen.getByRole("region", {
      name: "Model usage and reasoning",
    });
    expect(
      within(modelDetails).getByText("OpenAI Chat Completions"),
    ).toBeTruthy();
    expect(within(modelDetails).getByText("22")).toBeTruthy();
    expect(within(modelDetails).getByText("10")).toBeTruthy();
    expect(
      within(modelDetails).getByText(
        /does not provide the Responses API reasoning summary/,
      ),
    ).toBeTruthy();
  });

  it("renders answer states, calculations, conflicts, and safe failed-tool details", async () => {
    const calculationAnswer = {
      ...answerPayload,
      status: "conflict",
      answer: null,
      claims: [
        {
          claim_id: "claim-a",
          text: "First synthetic claim.",
          citations: [],
          calculation_ids: ["calculation-1"],
        },
        {
          claim_id: "claim-b",
          text: "Second synthetic claim.",
          citations: [],
          calculation_ids: ["calculation-1"],
        },
      ],
      calculations: [
        {
          calculation_id: "calculation-1",
          tool_name: "query_statistics",
          operation: "year-over-year change",
          formula: "current - prior",
          rounding: "rounded to one decimal",
          rows: [{ geography: "India", year: 2025, value: 1.2, unit: "%" }],
          evidence: [],
          warnings: ["Synthetic calculation warning."],
        },
      ],
      uncertainty: ["Synthetic uncertainty."],
      conflicts: [
        {
          summary: "The synthetic sources disagree.",
          claim_ids: ["claim-a", "claim-b"],
        },
      ],
      limitations: ["Synthetic limitation."],
      events: [
        {
          sequence: 1,
          state: "tool_execution",
          event_type: "tool_completed",
          status: "failed",
          tool_name: "query_statistics",
          duration_ms: 25,
          error_code: "MCP_TIMEOUT",
          retry_count: 1,
        },
      ],
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(optionsPayload))
      .mockResolvedValueOnce(response(calculationAnswer));
    vi.stubGlobal("fetch", withSessionApi(fetchMock));

    render(<App />);
    await screen.findByRole("combobox", { name: "Model provider" });
    fireEvent.change(
      screen.getByRole("textbox", { name: "Research question" }),
      { target: { value: "SYNTHETIC: conflict and calculation check" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Ask question" }));

    expect(
      await screen.findByRole("heading", { name: "Conflicting evidence" }),
    ).toBeTruthy();
    expect(screen.getByText("The synthetic sources disagree.")).toBeTruthy();
    expect(screen.getByText("Synthetic uncertainty.")).toBeTruthy();
    expect(screen.getByText("Synthetic limitation.")).toBeTruthy();
    fireEvent.click(
      screen.getByText("year-over-year change calculation · 1 rows"),
    );
    expect(
      screen.getByText("current - prior rounded to one decimal"),
    ).toBeTruthy();

    expect(screen.getAllByText("Statistics query failed")).toHaveLength(2);
    expect(screen.getByText("MCP_TIMEOUT")).toBeTruthy();
    expect(screen.getByText("1 retry")).toBeTruthy();
    expect(screen.queryByText("query_statistics")).toBeNull();
  });

  it("opens structured evidence details and renders untrusted strings as text", async () => {
    const unsafeTitle = "<img src=x onerror=alert(1)>";
    const unsafeExcerpt = "<script>alert('synthetic')</script>";
    const citation = {
      source_id: "unsafe <source>",
      title: unsafeTitle,
      source_uri: null,
      passage_id: `sha256:${"c".repeat(64)}`,
      excerpt: unsafeExcerpt,
      page_start: null,
      page_end: null,
      section_path: [],
      row_key: {
        country_iso3: "IND",
        year: 2025,
        indicator_id: "SYNTHETIC",
        observation_id: "observation-7",
      },
      source_content_sha256: "d".repeat(64),
    };
    const evidenceAnswer = {
      ...answerPayload,
      claims: [
        {
          claim_id: "claim-1",
          text: unsafeExcerpt,
          citations: [citation],
          calculation_ids: [],
        },
      ],
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(optionsPayload))
      .mockResolvedValueOnce(response(evidenceAnswer));
    vi.stubGlobal("fetch", withSessionApi(fetchMock));

    render(<App />);
    await screen.findByRole("combobox", { name: "Model provider" });
    fireEvent.change(
      screen.getByRole("textbox", { name: "Research question" }),
      { target: { value: "SYNTHETIC: structured evidence check" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Ask question" }));
    await screen.findByText(unsafeTitle);

    expect(screen.getAllByText(unsafeExcerpt)).toHaveLength(2);
    fireEvent.click(screen.getByText("Provenance details"));
    expect(screen.getByText("observation-7")).toBeTruthy();
    expect(screen.queryByRole("img")).toBeNull();
    expect(screen.queryByRole("script")).toBeNull();
  });

  it.each([
    {
      error_code: "INVALID_REQUEST",
      status: 422,
      expected: /question or filters are not valid/i,
    },
    {
      error_code: "TOOL_PERMISSION_DENIED",
      status: 403,
      expected: /not permitted for this run/i,
    },
    {
      error_code: "MCP_TIMEOUT",
      status: 503,
      expected: /data tool timed out/i,
    },
  ])(
    "shows a safe recoverable message for $error_code",
    async ({ error_code, status, expected }) => {
      const fetchMock = vi
        .fn()
        .mockResolvedValueOnce(response(optionsPayload))
        .mockResolvedValueOnce(
          response(
            {
              schema_version: "1.0",
              error_code,
              message: "Synthetic internal details are not user-facing.",
            },
            status,
          ),
        );
      vi.stubGlobal("fetch", withSessionApi(fetchMock));

      render(<App />);
      await screen.findByRole("combobox", { name: "Model provider" });
      fireEvent.change(
        screen.getByRole("textbox", { name: "Research question" }),
        { target: { value: "SYNTHETIC: error handling check" } },
      );
      fireEvent.click(screen.getByRole("button", { name: "Ask question" }));

      expect(await screen.findByText(expected)).toBeTruthy();
      expect(
        screen.queryByText("Synthetic internal details are not user-facing."),
      ).toBeNull();
    },
  );

  it("opens a PDF at its cited page with a search highlight and copies provenance", async () => {
    const citation = {
      source_id: "synthetic-source",
      title: "Synthetic source",
      source_uri: "https://example.test/source.pdf?version=1",
      passage_id: `sha256:${"a".repeat(64)}`,
      excerpt: "Synthetic bounded evidence excerpt.",
      page_start: 4,
      page_end: 4,
      section_path: ["Employment"],
      row_key: null,
      source_content_sha256: "b".repeat(64),
    };
    const evidenceAnswer = {
      ...answerPayload,
      claims: [
        {
          claim_id: "claim-1",
          text: "A synthetic claim tied to evidence.",
          citations: [citation],
          calculation_ids: [],
        },
      ],
    };
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(optionsPayload))
      .mockResolvedValueOnce(response(evidenceAnswer));
    vi.stubGlobal("fetch", withSessionApi(fetchMock));

    render(<App />);
    await screen.findByRole("combobox", { name: "Model provider" });
    fireEvent.change(
      screen.getByRole("textbox", { name: "Research question" }),
      { target: { value: "SYNTHETIC: citation check" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Ask question" }));

    const previewButton = await screen.findByRole("button", {
      name: "Open PDF preview at page 4, with cited text highlighted",
    });
    fireEvent.click(previewButton);

    const dialog = await screen.findByRole("dialog", {
      name: "PDF preview: Synthetic source",
    });
    const iframe = within(dialog).getByTitle("PDF preview: Synthetic source");
    expect(iframe.getAttribute("src")).toBe(
      "https://example.test/source.pdf?version=1#page=4&search=Synthetic%20bounded%20evidence%20excerpt.&phrase=true",
    );
    expect(
      within(dialog)
        .getByRole("link", { name: "Open in new tab" })
        .getAttribute("href"),
    ).toBe(
      "https://example.test/source.pdf?version=1#page=4&search=Synthetic%20bounded%20evidence%20excerpt.&phrase=true",
    );
    expect(
      within(dialog).getByText("Synthetic bounded evidence excerpt."),
    ).toBeTruthy();
    const quote = screen.getByText("Synthetic bounded evidence excerpt.", {
      selector: ".citation-quote .citation-highlight",
    });
    expect(quote).toHaveTextContent("Synthetic bounded evidence excerpt.");
    expect(quote.tagName).toBe("MARK");
    fireEvent.keyDown(window, { key: "Escape" });
    await waitFor(() => {
      expect(
        screen.queryByRole("dialog", { name: "PDF preview: Synthetic source" }),
      ).toBeNull();
    });
    fireEvent.click(screen.getByText("Provenance details"));
    expect(screen.getByText("synthetic-source")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Copy citation" }));
    expect(await screen.findByText("Citation copied.")).toBeTruthy();
    expect(writeText).toHaveBeenCalledWith(
      'Synthetic source (synthetic-source), Page 4 · Employment. "Synthetic bounded evidence excerpt." [sha256:' +
        "a".repeat(64) +
        "]",
    );
  });

  it("routes canonical PDF links and citations into the in-app preview", async () => {
    const canonicalUri =
      "https://documents.worldbank.org/en/publication/documents-reports/documentdetail/101071468299971244";
    const citation = {
      source_id: "wb-singapore-workforce-development-2012",
      title: "SABER Workforce Development Country Report: Singapore 2012",
      source_uri: canonicalUri,
      passage_id: `sha256:${"c".repeat(64)}`,
      excerpt: "Singapore coordinates workforce development across partners.",
      page_start: 9,
      page_end: 9,
      section_path: ["Institutional Arrangements"],
      row_key: null,
      source_content_sha256: "d".repeat(64),
    };
    const evidenceAnswer = {
      ...answerPayload,
      claims: [
        {
          claim_id: "claim-saber",
          text: `[Open the report](${canonicalUri})`,
          citations: [citation],
          calculation_ids: [],
        },
      ],
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(optionsPayload))
      .mockResolvedValueOnce(response(evidenceAnswer));
    vi.stubGlobal("fetch", withSessionApi(fetchMock));

    render(<App />);
    await screen.findByRole("combobox", { name: "Model provider" });
    fireEvent.change(
      screen.getByRole("textbox", { name: "Research question" }),
      { target: { value: "SYNTHETIC: open a canonical PDF link" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Ask question" }));
    fireEvent.click(
      await screen.findByRole("link", { name: "Open the report" }),
    );

    const dialog = await screen.findByRole("dialog", {
      name: "PDF preview: SABER Workforce Development Country Report: Singapore 2012",
    });
    const expectedUrl = `${getApiBaseUrl().replace(/\/+$/u, "")}/sources/wb-singapore-workforce-development-2012/pdf#page=9&search=Singapore%20coordinates%20workforce%20development%20across%20partners.&phrase=true`;
    expect(
      within(dialog)
        .getByTitle(
          "PDF preview: SABER Workforce Development Country Report: Singapore 2012",
        )
        .getAttribute("src"),
    ).toBe(expectedUrl);
    expect(
      within(dialog).getByText(citation.excerpt, { selector: "mark" }),
    ).toBeTruthy();

    fireEvent.keyDown(window, { key: "Escape" });
    fireEvent.click(
      await screen.findByRole("button", {
        name: "Open PDF preview at page 9, with cited text highlighted",
      }),
    );
    expect(
      await screen.findByRole("dialog", {
        name: "PDF preview: SABER Workforce Development Country Report: Singapore 2012",
      }),
    ).toBeTruthy();
  });

  it("opens a plain canonical report URL from an answer in the PDF preview", async () => {
    const canonicalUri =
      "https://documents.worldbank.org/en/publication/documents-reports/documentdetail/101071468299971244";
    const linkedAnswer = {
      ...answerPayload,
      answer: `The report discusses Singapore's workforce development system.\n\n${canonicalUri}`,
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(optionsPayload))
      .mockResolvedValueOnce(response(linkedAnswer));
    vi.stubGlobal("fetch", withSessionApi(fetchMock));

    render(<App />);
    await screen.findByRole("combobox", { name: "Model provider" });
    fireEvent.change(
      screen.getByRole("textbox", { name: "Research question" }),
      { target: { value: "SYNTHETIC: open a plain report URL" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Ask question" }));
    fireEvent.click(await screen.findByRole("link", { name: canonicalUri }));

    const dialog = await screen.findByRole("dialog", {
      name: "PDF preview: SABER Workforce Development Country Report: Singapore",
    });
    expect(
      within(dialog)
        .getByTitle(
          "PDF preview: SABER Workforce Development Country Report: Singapore",
        )
        .getAttribute("src"),
    ).toBe(
      `${getApiBaseUrl().replace(/\/+$/u, "")}/sources/wb-singapore-workforce-development-2012/pdf`,
    );
  });

  it("does not embed unregistered PDF URLs from answer Markdown", async () => {
    const externalPdfUri = "https://unregistered.example/research.pdf";
    const linkedAnswer = {
      ...answerPayload,
      answer: `[Unregistered PDF](${externalPdfUri})`,
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(optionsPayload))
      .mockResolvedValueOnce(response(linkedAnswer));
    vi.stubGlobal("fetch", withSessionApi(fetchMock));

    render(<App />);
    await screen.findByRole("combobox", { name: "Model provider" });
    fireEvent.change(
      screen.getByRole("textbox", { name: "Research question" }),
      { target: { value: "SYNTHETIC: keep an unregistered URL external" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Ask question" }));

    const link = await screen.findByRole("link", { name: "Unregistered PDF" });
    expect(link).toHaveAttribute("href", externalPdfUri);
    expect(link).not.toHaveAttribute("aria-haspopup", "dialog");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("requires per-run confirmation before submitting to OpenAI", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(optionsPayload))
      .mockResolvedValueOnce(response(answerPayload));
    vi.stubGlobal("fetch", withSessionApi(fetchMock));

    render(<App />);

    const provider = await screen.findByRole("combobox", {
      name: "Model provider",
    });
    fireEvent.change(provider, { target: { value: "openai" } });
    fireEvent.change(
      screen.getByRole("textbox", { name: "Research question" }),
      {
        target: { value: "Summarize the source evidence." },
      },
    );
    fireEvent.click(screen.getByRole("button", { name: "Ask question" }));

    expect(
      await screen.findByRole("dialog", {
        name: "Send this question to OpenAI?",
      }),
    ).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledTimes(1);

    fireEvent.click(
      screen.getByRole("button", { name: "Continue with OpenAI" }),
    );
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const answerCall = fetchMock.mock.calls[1];
    expect(JSON.parse(String(answerCall[1]?.body))).toMatchObject({
      provider: "openai",
      allow_external_provider: true,
    });
  });

  it("discloses that stopping the browser wait does not guarantee server cancellation", async () => {
    const fetchMock = vi
      .fn()
      .mockImplementation((_url: string, init?: RequestInit) => {
        if (String(_url).endsWith("/model/options")) {
          return Promise.resolve(response(optionsPayload));
        }
        return new Promise((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => {
            reject(new DOMException("Aborted", "AbortError"));
          });
        });
      });
    vi.stubGlobal("fetch", withSessionApi(fetchMock));

    render(<App />);
    await screen.findByRole("combobox", { name: "Model provider" });
    fireEvent.change(
      screen.getByRole("textbox", { name: "Research question" }),
      {
        target: { value: "SYNTHETIC: cancellation check" },
      },
    );
    fireEvent.click(screen.getByRole("button", { name: "Ask question" }));
    fireEvent.click(
      await screen.findByRole("button", { name: "Stop waiting" }),
    );

    expect(
      await screen.findByText(
        /Backend work may continue until its configured timeout/,
      ),
    ).toBeTruthy();
  });

  it("shows a distinct safe message when the selected model is unavailable", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(optionsPayload))
      .mockResolvedValueOnce(
        response(
          {
            schema_version: "1.0",
            error_code: "MODEL_UNAVAILABLE",
            message:
              "Internal provider URL and exception detail are not displayed.",
          },
          503,
        ),
      );
    vi.stubGlobal("fetch", withSessionApi(fetchMock));

    render(<App />);
    await screen.findByRole("combobox", { name: "Model provider" });
    fireEvent.change(
      screen.getByRole("textbox", { name: "Research question" }),
      {
        target: { value: "SYNTHETIC: availability check" },
      },
    );
    fireEvent.click(screen.getByRole("button", { name: "Ask question" }));

    expect(
      await screen.findByText(
        /selected model is unavailable\. No alternate provider was used/,
      ),
    ).toBeTruthy();
    expect(screen.queryByText(/Internal provider URL/)).toBeNull();
  });

  it("shows a generic safe message when the backend is unreachable", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(optionsPayload))
      .mockRejectedValueOnce(new TypeError("Internal network detail"));
    vi.stubGlobal("fetch", withSessionApi(fetchMock));

    render(<App />);
    await screen.findByRole("combobox", { name: "Model provider" });
    fireEvent.change(
      screen.getByRole("textbox", { name: "Research question" }),
      { target: { value: "SYNTHETIC: offline check" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Ask question" }));

    expect(
      await screen.findByText(
        /backend is offline or unreachable\. Check system status and retry/,
      ),
    ).toBeTruthy();
    expect(screen.queryByText("Internal network detail")).toBeNull();
  });
});
