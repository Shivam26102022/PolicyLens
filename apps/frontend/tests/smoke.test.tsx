import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  getApiBaseUrl,
  getLiveness,
  type ServiceHealth,
} from "../src/api/health";
import App from "../src/App";

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("PolicyLens frontend foundation", () => {
  it("renders the research workspace and primary navigation", () => {
    render(<App />);

    expect(
      screen.getByRole("heading", { name: "Ask a question. Get evidence." }),
    ).toBeTruthy();
    expect(screen.getByText("LOCAL WORKSPACE")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Agent trail" })).toBeTruthy();
    expect(screen.getByText("PolicyLens Policy Data Server")).toBeTruthy();
    expect(
      screen.getByRole("textbox", { name: "Research question" }),
    ).toBeTruthy();
    expect(
      screen.getByRole("navigation", { name: "Primary navigation" }),
    ).toBeTruthy();
  });

  it("uses the localhost API default and supports a configured API origin", () => {
    vi.stubEnv("VITE_API_BASE_URL", "");
    expect(getApiBaseUrl()).toBe("http://localhost:8000");

    vi.stubEnv("VITE_API_BASE_URL", " https://api.example.test/ ");
    expect(getApiBaseUrl()).toBe("https://api.example.test/");
  });

  it("requests typed backend liveness and returns the response", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "");
    const health: ServiceHealth = {
      schema_version: "1.0",
      service: "policylens-api",
      version: "0.1.0",
      status: "alive",
      components: { api: "ready" },
    };
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => health,
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(getLiveness()).resolves.toEqual(health);
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/health/live",
      {
        signal: undefined,
        headers: { Accept: "application/json" },
      },
    );
  });

  it("surfaces backend health failures without parsing a response body", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false }));

    await expect(getLiveness()).rejects.toThrow(
      "Backend health request failed",
    );
  });
});
