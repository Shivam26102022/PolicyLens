import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "../src/App";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("system status", () => {
  it("shows ready components distinctly", async () => {
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url.endsWith("/model/options")) {
        return Promise.resolve({
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
        });
      }
      if (url.endsWith("/health/ready")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            schema_version: "1.0",
            service: "policylens-api",
            version: "0.1.0",
            status: "ready",
            components: {
              api: "ready",
              retrieval: "ready",
              mcp: "unavailable",
              diagnostics: "/private/internal/path",
            },
          }),
        });
      }
      throw new Error("Unexpected request");
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    fireEvent.click(screen.getByRole("link", { name: "System status" }));

    expect(await screen.findByText("PolicyLens API · 0.1.0")).toBeTruthy();
    expect(screen.getAllByText("Ready").length).toBeGreaterThan(0);
    expect(screen.getByText("Unavailable")).toBeTruthy();
    expect(screen.queryByText("/private/internal/path")).toBeNull();
  });

  it("distinguishes component status without showing backend internals", async () => {
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url.endsWith("/model/options")) {
        return Promise.resolve({
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
        });
      }
      if (url.endsWith("/health/ready")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            schema_version: "1.0",
            service: "policylens-api",
            version: "0.1.0",
            status: "degraded",
            components: {
              api: "ready",
              retrieval: "not_configured",
              mcp: "unavailable",
              generation: "ready",
              diagnostics: "/private/internal/path",
            },
          }),
        });
      }
      throw new Error("Unexpected request");
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    fireEvent.click(screen.getByRole("link", { name: "System status" }));

    expect(
      await screen.findByRole("heading", { name: "System status" }),
    ).toBeTruthy();
    expect(await screen.findByText("Degraded")).toBeTruthy();
    expect(screen.getByText("Not configured")).toBeTruthy();
    expect(screen.getByText("Unavailable")).toBeTruthy();
    expect(screen.queryByText("/private/internal/path")).toBeNull();
  });

  it("shows component details returned with a degraded HTTP 503", async () => {
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url.endsWith("/model/options")) {
        return Promise.resolve({
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
        });
      }
      if (url.endsWith("/health/ready")) {
        return Promise.resolve({
          ok: false,
          status: 503,
          json: async () => ({
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
          }),
        });
      }
      throw new Error("Unexpected request");
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    fireEvent.click(screen.getByRole("link", { name: "System status" }));

    const degradedStatus = await screen.findByText("Degraded");
    expect(degradedStatus).toBeTruthy();
    expect(degradedStatus.className).toContain("run-badge-degraded");
    expect(screen.getAllByText("Ready").length).toBeGreaterThan(0);
    expect(screen.getByText("Unavailable")).toBeTruthy();
    expect(
      screen.getByText(
        "Some components need attention. Components marked Ready remain available.",
      ),
    ).toBeTruthy();
    expect(screen.queryByText("Backend readiness is unavailable.")).toBeNull();
  });
});
