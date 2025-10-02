import { test, expect } from "@playwright/test";

test("layout exposes title and description", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1, name: "cGUI Scenarios" })).toBeVisible();
  await expect(page.getByText("These mini-apps back the deterministic Playwright suite.")).toBeVisible();
});
