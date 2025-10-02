import { test, expect } from "@playwright/test";

test("index lists all scenarios", async ({ page }) => {
  await page.goto("/");
  const links = page.locator("main ul li a");
  await expect(links).toHaveCount(4);
  const texts = await links.allInnerTexts();
  expect(texts).toEqual([
    "Mission Intake Form",
    "Telemetry Table",
    "Document Download",
    "Checklist Flow",
  ]);
});
