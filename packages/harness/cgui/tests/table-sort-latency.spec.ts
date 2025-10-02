import { test, expect } from "@playwright/test";

test("table sorts by latency ascending", async ({ page }) => {
  await page.goto("/table");
  await page.click("text=Sort by p95 latency");
  const rows = page.locator("tbody tr td:first-child");
  await expect(rows.nth(0)).toHaveText("Intake");
  await expect(rows.nth(1)).toHaveText("Review");
  await expect(rows.nth(3)).toHaveText("Execution");
});
