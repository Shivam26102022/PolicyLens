import { expect, test } from "@playwright/test";

const options = {
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
      reasoning_efforts: ["none"],
    },
  ],
};

test("core navigation and architecture remain keyboard usable at 320px", async ({
  page,
}) => {
  await page.setViewportSize({ width: 320, height: 780 });
  await page.route("**/model/options", (route) =>
    route.fulfill({ json: options }),
  );
  await page.goto("/research");

  await page.keyboard.press("Tab");
  await expect(page.locator(":focus")).toHaveAttribute(
    "aria-label",
    "PolicyLens home",
  );
  await page.getByRole("link", { name: "Architecture" }).focus();
  await page.keyboard.press("Enter");
  await expect(
    page.getByRole("heading", { name: "Architecture" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: /Hot memory \(session context\)/ }),
  ).toBeVisible();

  const dimensions = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth);
});
