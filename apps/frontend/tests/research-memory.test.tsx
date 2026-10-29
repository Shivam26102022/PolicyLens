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

const modelOptions = {
  schema_version: "1.0",
  default_provider: "mlx",
  embedding_provider: "local",
  embedding_consent_required: false,
  options: [
    {
      provider: "mlx",
      model_id: "local-test-model",
      execution_scope: "loopback",
      configured: true,
      selected_by_default: true,
      consent_required: false,
      reasoning_efforts: ["none"],
    },
  ],
};

function jsonResponse(payload: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
  };
}

function installFetch(options?: {
  preferenceError?: boolean;
  memoryClearError?: boolean;
  memoryDeleteError?: boolean;
}) {
  let longMemoryEnabled = false;
  const sessions = [
    {
      session_id: sessionId,
      title: "Synthetic saved conversation",
      created_at: "2026-10-27T00:00:00Z",
      updated_at: "2026-10-27T00:00:00Z",
      turn_count: 0,
    },
  ];
  const fetchMock = vi.fn(
    async (input: RequestInfo | URL, init?: RequestInit) => {
      const requestUrl = new URL(String(input), "http://localhost");
      const method = init?.method ?? "GET";
      if (requestUrl.pathname === "/model/options") {
        return jsonResponse(modelOptions);
      }
      if (requestUrl.pathname === "/sessions/preferences") {
        if (method === "PUT") {
          if (options?.preferenceError) {
            return jsonResponse(
              { error_code: "WORKSPACE_PREFERENCES_UPDATE_FAILED" },
              503,
            );
          }
          const body = JSON.parse(String(init?.body)) as {
            long_memory_enabled: boolean;
          };
          longMemoryEnabled = body.long_memory_enabled;
        }
        return jsonResponse({
          schema_version: "1.0",
          data_use_acknowledged: true,
          data_use_acknowledged_at: "2026-10-27T00:00:00Z",
          long_memory_enabled: longMemoryEnabled,
        });
      }
      if (requestUrl.pathname === "/sessions" && method === "GET") {
        return jsonResponse({
          schema_version: "1.0",
          sessions,
          next_cursor: null,
        });
      }
      if (
        requestUrl.pathname === `/sessions/${sessionId}` &&
        method === "GET"
      ) {
        return jsonResponse({
          schema_version: "1.0",
          session: sessions[0],
          turns: [],
          next_before_turn_id: null,
        });
      }
      if (requestUrl.pathname === "/sessions/memories" && method === "DELETE") {
        return options?.memoryClearError
          ? jsonResponse({ error_code: "MEMORY_DELETE_FAILED" }, 503)
          : jsonResponse({
              schema_version: "1.0",
              status: "cleared",
              deleted_count: 2,
            });
      }
      if (
        requestUrl.pathname === `/sessions/${sessionId}` &&
        method === "DELETE"
      ) {
        return options?.memoryDeleteError
          ? jsonResponse({ error_code: "MEMORY_DELETE_FAILED" }, 503)
          : jsonResponse({
              schema_version: "1.0",
              session_id: sessionId,
              deleted: true,
            });
      }
      return jsonResponse({ error_code: "NOT_FOUND" }, 404);
    },
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  cleanup();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

describe("research memory controls", () => {
  it("persists the memory preference, confirms clearing, and deletes the active session", async () => {
    const fetchMock = installFetch();
    window.localStorage.setItem("policylens.workspace-id", workspaceId);

    render(<App />);
    const memoryToggle = await screen.findByRole("checkbox", {
      name: "Enable long-term memory",
    });
    await waitFor(() => expect(memoryToggle).toBeEnabled());

    fireEvent.click(memoryToggle);
    await waitFor(() => expect(memoryToggle).toBeChecked());
    expect(
      fetchMock.mock.calls.some(([url, init]) => {
        if (
          new URL(String(url), "http://localhost").pathname !==
            "/sessions/preferences" ||
          init?.method !== "PUT"
        ) {
          return false;
        }
        return JSON.parse(String(init.body)).long_memory_enabled === true;
      }),
    ).toBe(true);

    fireEvent.click(screen.getByText("Manage memory"));
    fireEvent.click(
      screen.getByRole("button", { name: "Clear long-term memory" }),
    );
    expect(
      screen.getByText(/Saved conversation transcripts will remain/),
    ).toBeTruthy();
    expect(
      fetchMock.mock.calls.some(
        ([url, init]) =>
          new URL(String(url), "http://localhost").pathname ===
            "/sessions/memories" && init?.method === "DELETE",
      ),
    ).toBe(false);
    fireEvent.click(
      screen.getByRole("button", { name: "Confirm clear memory" }),
    );
    expect(
      await screen.findByText("Cleared 2 long-term memories."),
    ).toBeTruthy();

    fireEvent.click(
      screen.getByRole("button", { name: "Delete conversation" }),
    );
    expect(screen.getByText(/This cannot be undone/)).toBeTruthy();
    fireEvent.click(
      screen.getByRole("button", { name: "Confirm delete conversation" }),
    );
    expect(
      await screen.findByText(
        "Conversation and its saved memories were deleted.",
      ),
    ).toBeTruthy();
    expect(
      fetchMock.mock.calls.some(
        ([url, init]) =>
          new URL(String(url), "http://localhost").pathname ===
            `/sessions/${sessionId}` && init?.method === "DELETE",
      ),
    ).toBe(true);
    expect(
      screen.queryByRole("button", { name: "Delete conversation" }),
    ).toBeNull();
  });

  it("keeps memory controls honest when preference or deletion requests fail", async () => {
    const fetchMock = installFetch({
      preferenceError: true,
      memoryClearError: true,
      memoryDeleteError: true,
    });
    window.localStorage.setItem("policylens.workspace-id", workspaceId);

    render(<App />);
    const memoryToggle = await screen.findByRole("checkbox", {
      name: "Enable long-term memory",
    });
    await waitFor(() => expect(memoryToggle).toBeEnabled());
    fireEvent.click(memoryToggle);
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(memoryToggle).not.toBeChecked();

    fireEvent.click(screen.getByText("Manage memory"));
    fireEvent.click(
      screen.getByRole("button", { name: "Clear long-term memory" }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Confirm clear memory" }),
    );
    expect(await screen.findByText(/MEMORY_DELETE_FAILED/)).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Confirm clear memory" }),
    ).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Cancel clear" }));
    fireEvent.click(
      screen.getByRole("button", { name: "Delete conversation" }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Confirm delete conversation" }),
    );
    expect(await screen.findByText(/MEMORY_DELETE_FAILED/)).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Delete conversation" }),
    ).toBeTruthy();
    expect(
      fetchMock.mock.calls.some(
        ([url, init]) =>
          new URL(String(url), "http://localhost").pathname ===
            `/sessions/${sessionId}` && init?.method === "DELETE",
      ),
    ).toBe(true);
  });
});
