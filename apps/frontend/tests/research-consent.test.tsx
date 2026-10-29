import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "../src/App";

const workspaceId = "00000000-0000-4000-8000-000000000001";
const sessionId = "00000000-0000-4000-8000-000000000002";

const session = {
  session_id: sessionId,
  title: "Synthetic session",
  created_at: "2026-10-27T00:00:00Z",
  updated_at: "2026-10-27T00:00:00Z",
  turn_count: 0,
};

const answer = {
  schema_version: "1.0",
  run_id: "run-consent",
  trace_id: "trace-consent",
  index_version: "a".repeat(64),
  status: "answered",
  answer: "Synthetic consent test answer.",
  claims: [],
  calculations: [],
  uncertainty: [],
  conflicts: [],
  clarification_question: null,
  abstention_reason: null,
  limitations: [],
  provider: "mlx",
  model: "synthetic-model",
  prompt_version: "agent-v1",
  events: [],
  error_code: null,
};

function jsonResponse(payload: unknown) {
  return {
    ok: true,
    status: 200,
    json: async () => payload,
  };
}

function eventStream(payload: unknown) {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(
        encoder.encode(`event: result\ndata: ${JSON.stringify(payload)}\n\n`),
      );
      controller.close();
    },
  });
  return { ok: true, status: 200, body };
}

function installConsentScenario(embeddingProvider: "local" | "openai") {
  const provider: "mlx" | "openai" =
    embeddingProvider === "openai" ? "openai" : "mlx";
  const modelOptions = {
    schema_version: "1.0",
    default_provider: provider,
    embedding_provider: embeddingProvider,
    embedding_consent_required: embeddingProvider === "openai",
    options: [
      {
        provider: "openai",
        model_id: "synthetic-openai-model",
        execution_scope: "external",
        configured: true,
        selected_by_default: embeddingProvider === "openai",
        consent_required: true,
        reasoning_efforts: ["none"],
      },
      {
        provider: "mlx",
        model_id: "synthetic-local-model",
        execution_scope: "loopback",
        configured: true,
        selected_by_default: embeddingProvider === "local",
        consent_required: false,
        reasoning_efforts: ["none"],
      },
    ],
  };
  const requests: Array<Record<string, unknown>> = [];
  let turnNumber = 0;
  const fetchMock = vi.fn(
    async (input: RequestInfo | URL, init?: RequestInit) => {
      const requestUrl = new URL(String(input), "http://localhost");
      const method = init?.method ?? "GET";
      if (requestUrl.pathname === "/model/options") {
        return jsonResponse(modelOptions);
      }
      if (requestUrl.pathname === "/sessions/preferences") {
        return jsonResponse({
          schema_version: "1.0",
          data_use_acknowledged: true,
          data_use_acknowledged_at: "2026-10-27T00:00:00Z",
          long_memory_enabled: false,
        });
      }
      if (requestUrl.pathname === "/sessions" && method === "GET") {
        return jsonResponse({
          schema_version: "1.0",
          sessions: [session],
          next_cursor: null,
        });
      }
      if (
        requestUrl.pathname === `/sessions/${sessionId}` &&
        method === "GET"
      ) {
        return jsonResponse({
          schema_version: "1.0",
          session,
          turns: [],
          next_before_turn_id: null,
        });
      }
      if (requestUrl.pathname === "/agent/answer/stream") {
        requests.push(
          JSON.parse(String(init?.body)) as Record<string, unknown>,
        );
        turnNumber += 1;
        return eventStream({
          ...answer,
          run_id: `run-consent-${turnNumber}`,
          provider,
          model: `synthetic-${provider}-model`,
        });
      }
      return {
        ok: false,
        status: 404,
        json: async () => ({ error_code: "NOT_FOUND" }),
      };
    },
  );
  window.localStorage.setItem("policylens.workspace-id", workspaceId);
  vi.stubGlobal("fetch", fetchMock);
  return { requests };
}

afterEach(() => {
  cleanup();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

describe("external processing consent", () => {
  it("requires fresh generation and embedding consent before every external turn", async () => {
    const { requests } = installConsentScenario("openai");
    render(<App />);
    await screen.findByRole("combobox", { name: "Model provider" });
    const composer = screen.getByRole("textbox", {
      name: "Research question",
    });

    fireEvent.change(composer, {
      target: { value: "First synthetic question" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Ask question" }));
    expect(
      await screen.findByRole("dialog", {
        name: "Allow external processing for this turn?",
      }),
    ).toBeTruthy();
    expect(
      screen.getByText(/OpenAI embeddings will process this question/),
    ).toBeTruthy();
    expect(requests).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(requests).toHaveLength(0);

    fireEvent.click(screen.getByRole("button", { name: "Ask question" }));
    fireEvent.click(
      await screen.findByRole("button", { name: "Allow this turn" }),
    );
    await screen.findByText("Synthetic consent test answer.");
    await waitFor(() => expect(requests).toHaveLength(1));
    expect(requests[0]).toMatchObject({
      provider: "openai",
      allow_external_provider: true,
      allow_external_embeddings: true,
    });

    fireEvent.change(composer, {
      target: { value: "Second synthetic follow-up" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send follow-up" }));
    expect(
      await screen.findByRole("dialog", {
        name: "Allow external processing for this turn?",
      }),
    ).toBeTruthy();
    expect(requests).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "Allow this turn" }));
    await waitFor(() => expect(requests).toHaveLength(2));
    expect(requests[1]).toMatchObject({
      provider: "openai",
      allow_external_provider: true,
      allow_external_embeddings: true,
    });
  });

  it("asks separately before local generation uses external embeddings", async () => {
    const { requests } = installConsentScenario("openai");
    render(<App />);
    await screen.findByRole("combobox", { name: "Model provider" });
    fireEvent.change(screen.getByRole("combobox", { name: "Model provider" }), {
      target: { value: "mlx" },
    });
    fireEvent.change(
      screen.getByRole("textbox", { name: "Research question" }),
      { target: { value: "Synthetic local question" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Ask question" }));

    expect(
      await screen.findByRole("dialog", {
        name: "Allow external processing for this turn?",
      }),
    ).toBeTruthy();
    expect(requests).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: "Allow this turn" }));
    await waitFor(() => expect(requests).toHaveLength(1));
    expect(requests[0]).toMatchObject({
      provider: "mlx",
      allow_external_provider: false,
      allow_external_embeddings: true,
    });
  });
});
