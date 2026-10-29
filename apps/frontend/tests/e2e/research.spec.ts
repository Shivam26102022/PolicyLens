import { expect, test, type Page } from "@playwright/test";

const options = {
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

const answer = {
  schema_version: "1.0",
  run_id: "run-1",
  trace_id: "trace-1",
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
  model: "local-test-model",
  prompt_version: "agent-v1",
  events: [],
  error_code: null,
};

async function mockWorkspace(page: Page, initialAcknowledgement = true) {
  let acknowledged = initialAcknowledgement;
  let longMemoryEnabled = false;
  let nextSessionNumber = 1;
  const sessions: Array<Record<string, unknown>> = [];
  const turns = new Map<string, Array<Record<string, unknown>>>();
  const sessionId = () =>
    `00000000-0000-4000-8000-${String(nextSessionNumber++).padStart(12, "0")}`;

  await page.route("**/model/options", (route) =>
    route.fulfill({ json: options }),
  );
  await page.route("**/sessions**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method();
    if (url.pathname === "/sessions/preferences") {
      if (method === "PUT") {
        const body = request.postDataJSON() as {
          data_use_acknowledged?: boolean;
          long_memory_enabled?: boolean;
        };
        acknowledged = body.data_use_acknowledged ?? acknowledged;
        longMemoryEnabled = body.long_memory_enabled ?? longMemoryEnabled;
      }
      return route.fulfill({
        json: {
          schema_version: "1.0",
          data_use_acknowledged: acknowledged,
          data_use_acknowledged_at: acknowledged
            ? "2026-10-27T00:00:00Z"
            : null,
          long_memory_enabled: longMemoryEnabled,
        },
      });
    }
    if (url.pathname === "/sessions" && method === "GET") {
      return route.fulfill({
        json: { schema_version: "1.0", sessions, next_cursor: null },
      });
    }
    if (url.pathname === "/sessions" && method === "POST") {
      const item = {
        session_id: sessionId(),
        title: "New conversation",
        created_at: "2026-10-27T00:00:00Z",
        updated_at: "2026-10-27T00:00:00Z",
        turn_count: 0,
      };
      sessions.unshift(item);
      turns.set(item.session_id as string, []);
      return route.fulfill({ status: 201, json: item });
    }
    if (url.pathname === "/sessions/memories" && method === "DELETE") {
      return route.fulfill({
        json: {
          schema_version: "1.0",
          status: "cleared",
          deleted_count: 2,
        },
      });
    }
    const match = url.pathname.match(/^\/sessions\/([0-9a-f-]+)$/i);
    if (match && method === "GET") {
      const selected = sessions.find((item) => item.session_id === match[1]);
      if (!selected) {
        return route.fulfill({
          status: 404,
          json: { error_code: "SESSION_NOT_FOUND" },
        });
      }
      return route.fulfill({
        json: {
          schema_version: "1.0",
          session: selected,
          turns: turns.get(match[1]) ?? [],
          next_before_turn_id: null,
        },
      });
    }
    if (match && method === "DELETE") {
      const index = sessions.findIndex((item) => item.session_id === match[1]);
      if (index < 0) {
        return route.fulfill({
          status: 404,
          json: { error_code: "SESSION_NOT_FOUND" },
        });
      }
      sessions.splice(index, 1);
      turns.delete(match[1]);
      return route.fulfill({
        json: {
          schema_version: "1.0",
          session_id: match[1],
          deleted: true,
        },
      });
    }
    return route.fulfill({
      status: 404,
      json: { error_code: "NOT_FOUND" },
    });
  });
  return { sessions, turns };
}

test("source-backed example fills the composer and answer is submitted only on request", async ({
  page,
}) => {
  let answerRequests = 0;
  await mockWorkspace(page);
  await page.route("**/agent/answer/stream", (route) => {
    answerRequests += 1;
    return route.fulfill({
      contentType: "text/event-stream",
      body: `event: result\ndata: ${JSON.stringify(answer)}\n\n`,
    });
  });

  await page.goto("/research");
  const question = page.getByRole("textbox", { name: "Research question" });
  await page
    .getByRole("button", {
      name: "India · Women's share of skills trainees",
    })
    .click();
  await expect(question).toHaveValue(
    "In how many of India's five skills schemes did women represent close to half of trainees?",
  );
  expect(answerRequests).toBe(0);

  await page.getByRole("button", { name: "Ask question" }).click();
  await expect(
    page.getByText("Youth unemployment was 16 percent."),
  ).toBeVisible();
  expect(answerRequests).toBe(1);
});

test("keeps the research flow readable without horizontal scrolling on mobile", async ({
  page,
}) => {
  await page.setViewportSize({ width: 320, height: 780 });
  await mockWorkspace(page);
  await page.goto("/research");

  await expect(
    page.getByRole("heading", { name: "Ask a question. Get evidence." }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Agent trail" }),
  ).toBeVisible();

  const dimensions = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth);
});

test("supports follow-up questions in the active persisted session", async ({
  page,
}) => {
  const requests: Record<string, unknown>[] = [];
  await mockWorkspace(page);
  await page.route("**/agent/answer/stream", async (route) => {
    requests.push(route.request().postDataJSON() as Record<string, unknown>);
    const turn = requests.length;
    await route.fulfill({
      contentType: "text/event-stream",
      body: `event: result\ndata: ${JSON.stringify({
        ...answer,
        run_id: `run-${turn}`,
        answer: `Synthetic answer ${turn}.`,
      })}\n\n`,
    });
  });

  await page.goto("/research");
  const question = page.getByRole("textbox", { name: "Research question" });
  await question.fill("First synthetic question");
  await page.getByRole("button", { name: "Ask question" }).click();
  await expect(page.getByText("Synthetic answer 1.")).toBeVisible();
  await expect(page.getByText(/last 5 completed exchanges/)).toBeVisible();
  await expect(
    page.getByText(/Older messages stay in this chat/),
  ).toBeVisible();

  await question.fill("A follow-up synthetic question");
  await page.getByRole("button", { name: "Send follow-up" }).click();
  await expect(page.getByText("Synthetic answer 2.")).toBeVisible();
  await expect(page.locator(".conversation-pair")).toHaveCount(2);
  expect(requests[1].conversation).toEqual([]);
  expect(requests[1].session_id).toBe(requests[0].session_id);
});

test("stopping an in-flight browser request is reported without claiming server cancellation", async ({
  page,
}) => {
  let markRequestStarted!: () => void;
  const requestStarted = new Promise<void>((resolve) => {
    markRequestStarted = resolve;
  });
  let releaseRequest!: () => void;
  const responseGate = new Promise<void>((resolve) => {
    releaseRequest = resolve;
  });
  let markRouteFinished!: () => void;
  const routeFinished = new Promise<void>((resolve) => {
    markRouteFinished = resolve;
  });
  await mockWorkspace(page);
  await page.route("**/agent/answer/stream", async (route) => {
    markRequestStarted();
    await responseGate;
    try {
      if (route.request().failure() === null) await route.abort();
    } finally {
      markRouteFinished();
    }
  });

  await page.goto("/research");
  await page
    .getByRole("textbox", { name: "Research question" })
    .fill("SYNTHETIC: cancellation check");
  await page.getByRole("button", { name: "Ask question" }).click();
  await requestStarted;
  await page.getByRole("button", { name: "Stop waiting" }).click();
  await expect(
    page.getByText(/Backend work may continue until its configured timeout/),
  ).toBeVisible();
  releaseRequest();
  await routeFinished;
});

test("shows bounded evidence and safe retrieval/tool progress", async ({
  page,
}) => {
  const citation = {
    source_id: "synthetic-source",
    title: "Synthetic source",
    source_uri: "https://example.test/reports/report.pdf",
    passage_id: `sha256:${"b".repeat(64)}`,
    excerpt: "Synthetic evidence excerpt.",
    page_start: 4,
    page_end: 4,
    section_path: ["Employment"],
    row_key: null,
    source_content_sha256: "c".repeat(64),
  };
  const events = [
    {
      sequence: 1,
      state: "retrieving",
      event_type: "state_transition",
      status: "succeeded",
      tool_name: null,
      duration_ms: 12,
      error_code: null,
      retry_count: 0,
    },
    {
      sequence: 2,
      state: "retrieving",
      event_type: "mcp_resource_started",
      status: "started",
      tool_name: null,
      duration_ms: null,
      error_code: null,
      retry_count: 0,
    },
    {
      sequence: 3,
      state: "retrieving",
      event_type: "mcp_resource_completed",
      status: "succeeded",
      item_count: 1,
      tool_name: null,
      duration_ms: 8,
      error_code: null,
      retry_count: 0,
    },
    {
      sequence: 4,
      state: "retrieving",
      event_type: "retrieval_completed",
      status: "succeeded",
      tool_name: null,
      duration_ms: 12,
      error_code: null,
      retry_count: 0,
    },
    {
      sequence: 5,
      state: "tool_execution",
      event_type: "tool_completed",
      status: "failed",
      tool_name: "query_statistics",
      duration_ms: 25,
      error_code: "MCP_TIMEOUT",
      retry_count: 1,
    },
  ];
  await mockWorkspace(page);
  await page.route("**/agent/answer/stream", (route) =>
    route.fulfill({
      contentType: "text/event-stream",
      body: `event: result\ndata: ${JSON.stringify({
        ...answer,
        claims: [
          {
            claim_id: "claim-1",
            text: citation.excerpt,
            citations: [citation],
            calculation_ids: [],
          },
        ],
        events,
      })}\n\n`,
    }),
  );
  await page.route("https://example.test/reports/report.pdf", (route) =>
    route.abort(),
  );

  await page.goto("/research");
  await page
    .getByRole("textbox", { name: "Research question" })
    .fill("SYNTHETIC: evidence and processing check");
  await page.getByRole("button", { name: "Ask question" }).click();
  await expect(page.getByText("Evidence-backed answer")).toBeVisible();
  await page
    .getByRole("button", {
      name: "Open PDF preview at page 4, with cited text highlighted",
    })
    .click();
  const pdfDialog = page.getByRole("dialog", {
    name: "PDF preview: Synthetic source",
  });
  await expect(pdfDialog).toBeVisible();
  await expect(
    pdfDialog.getByTitle("PDF preview: Synthetic source"),
  ).toHaveAttribute(
    "src",
    "https://example.test/reports/report.pdf#page=4&search=Synthetic%20evidence%20excerpt.&phrase=true",
  );
  await expect(
    pdfDialog.getByRole("link", { name: "Open in new tab" }),
  ).toHaveAttribute(
    "href",
    "https://example.test/reports/report.pdf#page=4&search=Synthetic%20evidence%20excerpt.&phrase=true",
  );
  await expect(
    pdfDialog.locator(".pdf-preview-excerpt mark", {
      hasText: "Synthetic evidence excerpt.",
    }),
  ).toBeVisible();
  await pdfDialog.getByRole("button", { name: "Close PDF preview" }).click();

  const answerTrail = page.locator("details.answer-agent-trail").last();
  await expect(answerTrail).toHaveAttribute("open", "");
  await answerTrail.locator("summary").click();
  await expect(answerTrail).not.toHaveAttribute("open", "");
  await answerTrail.locator("summary").click();
  await expect(answerTrail).toHaveAttribute("open", "");
  await expect(
    answerTrail
      .locator(".agent-trail-list")
      .getByText("Passages verified by Policy Data MCP"),
  ).toBeVisible();
  await expect(
    answerTrail.locator(".agent-trail-list").getByText("1 passage verified"),
  ).toBeVisible();
  await expect(
    answerTrail
      .locator(".agent-trail-list")
      .getByText("Statistics query failed"),
  ).toBeVisible();
  await expect(answerTrail.getByText("MCP_TIMEOUT")).toBeVisible();
  await expect(page.getByText("query_statistics")).toHaveCount(0);
});

test("acknowledges storage, resumes a session, and controls long-term memory", async ({
  page,
}) => {
  const { sessions, turns } = await mockWorkspace(page, false);
  const requests: Record<string, unknown>[] = [];
  let answerCount = 0;
  await page.route("**/agent/answer/stream", async (route) => {
    const body = route.request().postDataJSON() as {
      query: string;
      session_id: string;
    };
    requests.push(body as unknown as Record<string, unknown>);
    answerCount += 1;
    const savedSession = sessions.find(
      (item) => item.session_id === body.session_id,
    );
    if (savedSession) {
      const turnId = `turn-${answerCount}`;
      const result = {
        ...answer,
        run_id: `run-${answerCount}`,
        answer: `Synthetic persisted answer ${answerCount}.`,
        events: [
          {
            sequence: 1,
            state: "retrieving",
            event_type: "retrieval_completed",
            status: "succeeded",
            tool_name: null,
            duration_ms: 12,
            error_code: null,
            retry_count: 0,
          },
        ],
        provider: "mlx",
        session_context: {
          session_id: body.session_id,
          turn_id: turnId,
          persisted: true,
          long_memory_enabled: true,
          memory_retrieval_status: "empty",
          retrieved_memory_count: 0,
          memory_write_status: "stored",
        },
      };
      turns.set(body.session_id, [
        ...(turns.get(body.session_id) ?? []),
        {
          turn_id: turnId,
          position: answerCount,
          user_content: body.query,
          assistant_content: result.answer,
          answer: result,
          status: "completed",
          created_at: "2026-10-27T00:00:00Z",
          completed_at: "2026-10-27T00:00:01Z",
        },
      ]);
      savedSession.turn_count = answerCount;
      savedSession.updated_at = "2026-10-27T00:00:01Z";
      await route.fulfill({
        contentType: "text/event-stream",
        body: `event: result\ndata: ${JSON.stringify(result)}\n\n`,
      });
      return;
    }
    await route.fulfill({
      status: 404,
      json: { error_code: "SESSION_NOT_FOUND" },
    });
  });

  await page.goto("/research");
  await expect(
    page.getByRole("heading", { name: "Before your first chat" }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "New conversation 0 exchanges" }),
  ).toBeEnabled();

  const composer = page.getByRole("textbox", { name: "Research question" });
  await composer.fill("Synthetic first persistent question");
  await page.getByRole("button", { name: "Ask question" }).click();
  await expect(page.getByText("Synthetic persisted answer 1.")).toBeVisible();
  const firstSessionId = requests[0].session_id;
  await expect(
    page.getByRole("checkbox", { name: "Enable long-term memory" }),
  ).toBeVisible();
  await page.getByRole("checkbox", { name: "Enable long-term memory" }).click();
  await expect(
    page.getByRole("checkbox", { name: "Enable long-term memory" }),
  ).toBeChecked();

  await page.reload();
  await expect(page.getByText("Synthetic persisted answer 1.")).toBeVisible();
  const savedAnswerTrail = page.locator("details.answer-agent-trail").first();
  await expect(savedAnswerTrail).toHaveAttribute("open", "");
  await expect(
    savedAnswerTrail
      .locator(".agent-trail-list")
      .getByText("Evidence search completed"),
  ).toBeVisible();
  await expect(
    page.getByRole("checkbox", { name: "Enable long-term memory" }),
  ).toBeChecked();
  await composer.fill("Synthetic follow-up after reload");
  await page.getByRole("button", { name: "Send follow-up" }).click();
  await expect(page.getByText("Synthetic persisted answer 2.")).toBeVisible();
  expect(requests[1].session_id).toBe(firstSessionId);
  expect(requests[1].conversation).toEqual([]);

  await page.getByRole("checkbox", { name: "Enable long-term memory" }).click();
  await expect(
    page.getByRole("checkbox", { name: "Enable long-term memory" }),
  ).not.toBeChecked();
  await page.getByText("Manage memory").click();
  await page.getByRole("button", { name: "Clear long-term memory" }).click();
  await page.getByRole("button", { name: "Confirm clear memory" }).click();
  await expect(page.getByText("Cleared 2 long-term memories.")).toBeVisible();
  await page.getByRole("button", { name: "Delete conversation" }).click();
  await page
    .getByRole("button", { name: "Confirm delete conversation" })
    .click();
  await expect(
    page.getByText("Conversation and its saved memories were deleted."),
  ).toBeVisible();
  expect(sessions).toHaveLength(0);
});
