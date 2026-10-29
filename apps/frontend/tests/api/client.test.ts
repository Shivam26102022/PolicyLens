import { afterEach, describe, expect, it, vi } from "vitest";

import {
  clearWorkspaceMemories,
  deleteSession,
  getEvaluationSummary,
  getModelOptions,
  getReadiness,
  listSessions,
  readSession,
  submitAgentAnswer,
  updateWorkspacePreferences,
} from "../../src/api/client";

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("backend API client", () => {
  it("requests configured model options from the backend only", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "");
    const payload = {
      schema_version: "1.0",
      default_provider: "mlx",
      options: [],
    };
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => payload,
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(getModelOptions()).resolves.toEqual(payload);
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/model/options",
      expect.objectContaining({
        headers: { Accept: "application/json" },
      }),
    );
  });

  it("requests read-only evaluation summaries and propagates abort signals", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "");
    const controller = new AbortController();
    const payload = {
      schema_version: "1.0",
      status: "empty",
      case_set: {
        case_count: 0,
        approved_case_count: 0,
        category_count: 0,
        split_counts: { dev: 0, test: 0 },
        release_eligible: false,
      },
      runs: [],
      reviewed_case_count: 0,
      error_record_count: 0,
    };
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => payload,
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(getEvaluationSummary(controller.signal)).resolves.toEqual(
      payload,
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/evaluation/summary",
      expect.objectContaining({ signal: controller.signal }),
    );
  });

  it("returns structured degraded readiness details from HTTP 503", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "");
    const readiness = {
      schema_version: "1.0",
      service: "policylens-api",
      version: "0.1.0",
      status: "degraded",
      components: {
        api: "ready",
        generation: "ready",
        retrieval: "unavailable",
        mcp: "ready",
      },
    };
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
      json: async () => readiness,
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(getReadiness()).resolves.toEqual(readiness);
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/health/ready",
      expect.objectContaining({
        headers: { Accept: "application/json" },
      }),
    );
  });

  it("maps backend failures to safe typed errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 403,
        json: async () => ({
          schema_version: "1.0",
          error_code: "EXTERNAL_PROVIDER_CONSENT_REQUIRED",
          message: "Consent is required.",
        }),
      }),
    );

    await expect(getModelOptions()).rejects.toMatchObject({
      status: 403,
      code: "EXTERNAL_PROVIDER_CONSENT_REQUIRED",
      message: "Consent is required.",
    });
  });

  it.each([
    ["VALIDATION_ERROR", 422],
    ["EXTERNAL_PROVIDER_CONSENT_REQUIRED", 403],
    ["MODEL_UNAVAILABLE", 503],
  ])("preserves the typed %s error", async (code, status) => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status,
        json: async () => ({
          schema_version: "1.0",
          error_code: code,
          message: "Safe backend message.",
        }),
      }),
    );

    await expect(getModelOptions()).rejects.toMatchObject({
      status,
      code,
      message: "Safe backend message.",
    });
  });

  it("maps malformed JSON responses to a safe typed error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => {
          throw new SyntaxError("Internal parser detail");
        },
      }),
    );

    await expect(getModelOptions()).rejects.toMatchObject({
      status: 200,
      code: "INVALID_RESPONSE",
      message: "Backend returned an invalid response.",
    });
  });

  it("scopes session list and history requests with the workspace header", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "");
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        schema_version: "1.0",
        sessions: [],
        next_cursor: null,
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await listSessions("workspace-1", 25, "session-cursor");
    await readSession("workspace-1", "session-2", 100, "turn-cursor");

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "http://localhost:8000/sessions?limit=25&before=session-cursor",
      expect.objectContaining({
        headers: {
          Accept: "application/json",
          "X-Workspace-ID": "workspace-1",
        },
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "http://localhost:8000/sessions/session-2?limit=100&before_turn_id=turn-cursor",
      expect.objectContaining({
        headers: {
          Accept: "application/json",
          "X-Workspace-ID": "workspace-1",
        },
      }),
    );
  });

  it("sends the active session id and workspace only for session-backed requests", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "");
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        schema_version: "1.0",
        data_use_acknowledged: true,
      }),
    });
    vi.stubGlobal("fetch", fetchMock);
    const request = {
      schema_version: "1.0" as const,
      query: "synthetic follow-up",
      mode: "hybrid" as const,
      provider: "mlx" as const,
      allow_external_provider: false,
      allow_external_embeddings: false,
      reasoning_effort: "none" as const,
      conversation: [],
      session_id: "session-2",
    };

    await submitAgentAnswer(request, undefined, "workspace-1");

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/agent/answer",
      expect.objectContaining({
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          "X-Workspace-ID": "workspace-1",
        },
        body: JSON.stringify(request),
      }),
    );
    expect(() => submitAgentAnswer(request)).toThrow(
      expect.objectContaining({ code: "WORKSPACE_REQUIRED" }),
    );
  });

  it("updates typed workspace preferences through the backend", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "");
    const payload = {
      schema_version: "1.0" as const,
      data_use_acknowledged: true,
      data_use_acknowledged_at: "2026-10-27T00:00:00Z",
      long_memory_enabled: false,
    };
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => payload,
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      updateWorkspacePreferences("workspace-1", {
        data_use_acknowledged: true,
        long_memory_enabled: false,
      }),
    ).resolves.toEqual(payload);
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/sessions/preferences",
      expect.objectContaining({
        method: "PUT",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          "X-Workspace-ID": "workspace-1",
        },
      }),
    );
  });

  it("uses workspace-scoped endpoints for clearing memories and deleting sessions", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "");
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          schema_version: "1.0",
          status: "cleared",
          deleted_count: 2,
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          schema_version: "1.0",
          session_id: "session-2",
          deleted: true,
        }),
      });
    vi.stubGlobal("fetch", fetchMock);

    await expect(clearWorkspaceMemories("workspace-1")).resolves.toMatchObject({
      status: "cleared",
      deleted_count: 2,
    });
    await expect(
      deleteSession("workspace-1", "session-2"),
    ).resolves.toMatchObject({ session_id: "session-2", deleted: true });

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "http://localhost:8000/sessions/memories",
      expect.objectContaining({
        method: "DELETE",
        headers: {
          Accept: "application/json",
          "X-Workspace-ID": "workspace-1",
        },
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "http://localhost:8000/sessions/session-2",
      expect.objectContaining({
        method: "DELETE",
        headers: {
          Accept: "application/json",
          "X-Workspace-ID": "workspace-1",
        },
      }),
    );
  });
});
