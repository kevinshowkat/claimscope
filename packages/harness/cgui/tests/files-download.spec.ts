import { test, expect } from "@playwright/test";

test("mission brief is downloadable", async ({ page }) => {
  await page.goto("/files");
  const href = await page.locator('a[href$="mission-brief.txt"]').getAttribute("href");
  expect(href).toBe("/cgui/static/mission-brief.txt");

  const response = await page.request.get(href!);
  expect(response.ok()).toBeTruthy();
  const body = await response.text();
  expect(body).toContain("Aurora mission objectives");
});
