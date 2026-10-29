import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "../src/App";
import { architectureLayers } from "../src/data/architecture";

afterEach(() => {
  cleanup();
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        schema_version: "1.0",
        default_provider: "mlx",
        options: [
          {
            provider: "mlx",
            model_id: "local-test-model",
            execution_scope: "loopback",
            configured: true,
            selected_by_default: true,
            consent_required: false,
          },
        ],
      }),
    }),
  );
});

describe("architecture guide", () => {
  it("documents all layers including MCP and hot/warm memory", () => {
    expect(architectureLayers).toHaveLength(13);
    expect(new Set(architectureLayers.map((layer) => layer.id)).size).toBe(13);
    expect(
      architectureLayers.map((layer) => layer.implementationStatus),
    ).toContain("implemented");
    expect(
      architectureLayers.map((layer) => layer.implementationStatus),
    ).toContain("configured");
    const ids = architectureLayers.map((layer) => layer.id);
    expect(ids).toEqual(
      expect.arrayContaining(["hot-memory", "warm-memory", "mcp-server"]),
    );
    const runLayer = architectureLayers.find(
      (layer) => layer.id === "run-memory",
    );
    expect(runLayer?.description).toMatch(/request-scoped/i);
    const retrievalLayer = architectureLayers.find(
      (layer) => layer.id === "retrieval-index",
    );
    expect(retrievalLayer?.description).toMatch(/cross-encoder/i);
    expect(retrievalLayer?.description).toMatch(/permission-filtered/i);
  });

  it("opens architecture layer details through keyboard-accessible controls", async () => {
    render(<App />);
    fireEvent.click(screen.getByRole("link", { name: "Architecture" }));

    expect(
      await screen.findByRole("heading", { name: "Architecture" }),
    ).toBeTruthy();
    fireEvent.click(
      screen.getByRole("button", { name: /Warm memory \(long-term recall\)/ }),
    );
    expect(screen.getByText(/opt-in long-term recall/)).toBeTruthy();
    fireEvent.click(screen.getByLabelText("MCP server diagram node"));
    expect(screen.getByText(/read-only Model Context Protocol/)).toBeTruthy();
    fireEvent.click(
      screen.getByRole("button", { name: /Cross-encoder rerank/ }),
    );
    expect(screen.getByText(/re-scores them/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Answer with tool" }));
    expect(screen.getByText(/TOOL CALLS/)).toBeTruthy();
  });
});
