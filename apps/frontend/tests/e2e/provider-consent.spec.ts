import { expect, test, type Page } from "@playwright/test";

const options = {
  schema_version: "1.0",
  default_provider: "mlx",
  embedding_provider: "local",
  embedding_consent_required: false,
  options: [
    {
      provider: "openai",
      model_id: "openai-test-model",
      execution_scope: "external",
      configured: true,
      selected_by_default: false,
      consent_required: true,
      reasoning_efforts: ["none", "low", "medium", "high"],
    },
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

const answer = {
  schema_version: "1.0",
  run_id: "run-openai",
  trace_id: "trace-openai",
  index_version: "a".repeat(64),
  status: "abstained",
  answer: null,
  claims: [],
  calculations: [],
  uncertainty: [],
  conflicts: [],
  clarification_question: null,
  abstention_reason: "No eligible evidence was retrieved.",
  limitations: [],
  provider: "openai",
  model: "openai-test-model",
  prompt_version: "agent-v1",
  events: [],
  error_code: null,
};

async function mockAcknowledgedSession(page: Page) {
  const sessionId = "00000000-0000-4000-8000-000000000001";
  const session = {
    session_id: sessionId,
    title: "Synthetic consent session",
    created_at: "2026-10-27T00:00:00Z",
    updated_at: "2026-10-27T00:00:00Z",
    turn_count: 0,
  };
  await page.route("**/sessions**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === "/sessions/preferences") {
      return route.fulfill({
        json: {
          schema_version: "1.0",
          data_use_acknowledged: true,
          data_use_acknowledged_at: "2026-10-27T00:00:00Z",
          long_memory_enabled: false,
        },
      });
    }
    if (url.pathname === "/sessions" && route.request().method() === "GET") {
      return route.fulfill({
        json: {
          schema_version: "1.0",
          sessions: [session],
          next_cursor: null,
        },
      });
    }
    if (url.pathname === `/sessions/${sessionId}`) {
      return route.fulfill({
        json: {
          schema_version: "1.0",
          session,
          turns: [],
          next_before_turn_id: null,
        },
      });
    }
    return route.fulfill({ status: 404, json: { error_code: "NOT_FOUND" } });
  });
}

test("OpenAI receives a request only after explicit per-run consent", async ({
  page,
}) => {
  let answerRequests = 0;
  let requestBody: Record<string, unknown> | undefined;
  await mockAcknowledgedSession(page);
  await page.route("**/model/options", (route) =>
    route.fulfill({ json: options }),
  );
  await page.route("**/agent/answer/stream", async (route) => {
    answerRequests += 1;
    requestBody = route.request().postDataJSON() as Record<string, unknown>;
    await route.fulfill({
      contentType: "text/event-stream",
      body: `event: result\ndata: ${JSON.stringify(answer)}\n\n`,
    });
  });

  await page.goto("/research");
  await page
    .getByRole("combobox", { name: "Model provider" })
    .selectOption("openai");
  await page
    .getByRole("textbox", { name: "Research question" })
    .fill("Summarize the evidence.");
  await expect(
    page.getByRole("button", { name: "Ask question" }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "Ask question" }).click();

  await expect(
    page.getByRole("dialog", { name: "Send this question to OpenAI?" }),
  ).toBeVisible();
  expect(answerRequests).toBe(0);
  await page.getByRole("button", { name: "Continue with OpenAI" }).click();
  await expect(
    page.getByText("No eligible evidence was retrieved."),
  ).toBeVisible();
  expect(answerRequests).toBe(1);
  expect(requestBody).toMatchObject({
    provider: "openai",
    allow_external_provider: true,
  });
});

test("local model selection sends directly without an external-consent dialog", async ({
  page,
}) => {
  let answerRequests = 0;
  let requestBody: Record<string, unknown> | undefined;
  await mockAcknowledgedSession(page);
  await page.route("**/model/options", (route) =>
    route.fulfill({ json: options }),
  );
  await page.route("**/agent/answer/stream", async (route) => {
    answerRequests += 1;
    requestBody = route.request().postDataJSON() as Record<string, unknown>;
    await route.fulfill({
      contentType: "text/event-stream",
      body: `event: result\ndata: ${JSON.stringify({
        ...answer,
        provider: "mlx",
        model: "local-test-model",
      })}\n\n`,
    });
  });

  await page.goto("/research");
  await page
    .getByRole("combobox", { name: "Model provider" })
    .selectOption("openai");
  await page
    .getByRole("combobox", { name: "Model provider" })
    .selectOption("mlx");
  await page
    .getByRole("textbox", { name: "Research question" })
    .fill("SYNTHETIC: local provider check");
  await expect(
    page.getByRole("button", { name: "Ask question" }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "Ask question" }).click();

  await expect(
    page.getByText("No eligible evidence was retrieved."),
  ).toBeVisible();
  expect(answerRequests).toBe(1);
  expect(requestBody).toMatchObject({
    provider: "mlx",
    allow_external_provider: false,
  });
  await expect(
    page.getByRole("dialog", { name: "Send this question to OpenAI?" }),
  ).toHaveCount(0);
});
