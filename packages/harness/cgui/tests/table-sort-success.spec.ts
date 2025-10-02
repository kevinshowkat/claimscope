import { test, expect } from "@playwright/test";

test("table sorts by success rate ascending and toggles", async ({ page }) => {
  await page.goto("/table");
  await page.click("text=Sort by success rate");

  const rows = page.locator("tbody tr td:nth-child(3)");
  await expect(rows.first()).toHaveText("88.0%");
  await expect(rows.last()).toHaveText("96.0%");

  await page.click("text=Sort by success rate");
  await expect(rows.first()).toHaveText("96.0%");
  await expect(rows.last()).toHaveText("88.0%");
});
