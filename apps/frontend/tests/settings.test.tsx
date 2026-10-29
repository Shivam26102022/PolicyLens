import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "../src/App";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("model settings", () => {
  it("shows only backend-configured models and explains per-run consent", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          schema_version: "1.0",
          default_provider: "mlx",
          options: [
            {
              provider: "openai",
              model_id: "configured-openai-model",
              execution_scope: "external",
              configured: true,
              selected_by_default: false,
              consent_required: true,
            },
            {
              provider: "mlx",
              model_id: null,
              execution_scope: "loopback",
              configured: false,
              selected_by_default: true,
              consent_required: false,
            },
          ],
        }),
      }),
    );

    render(<App />);
    fireEvent.click(screen.getByRole("link", { name: "Model settings" }));

    expect(
      await screen.findByRole("heading", { name: "Model settings" }),
    ).toBeTruthy();
    const openAiChoice = screen.getByRole("radio", {
      name: /OpenAI.*configured-openai-model/i,
    });
    expect(openAiChoice).toBeTruthy();
    expect(screen.getByText("No local model is configured.")).toBeTruthy();
    expect(
      screen.getByText(/Each OpenAI run asks for external-processing consent/),
    ).toBeTruthy();

    fireEvent.click(openAiChoice);
    expect(openAiChoice).toBeChecked();
    expect(
      screen.getByText(
        /Consent is requested separately for every research run/,
      ),
    ).toBeTruthy();
  });
});
