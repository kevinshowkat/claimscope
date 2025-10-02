import { test, expect } from "@playwright/test";

function parseCsv(value: string): string[][] {
  return value
    .trim()
    .split(/\r?\n/)
    .map((line) => line.split(","));
}

test("ops checklist csv has deterministic rows", async ({ page }) => {
  await page.goto("/files");
  const href = await page.locator('a[href$="ops-checklist.csv"]').getAttribute("href");
  const response = await page.request.get(href!);
  expect(response.ok()).toBeTruthy();
  const csv = parseCsv(await response.text());
  expect(csv[1]).toEqual(["1", "Verify attitude control", "complete"]);
  expect(csv[2]).toEqual(["2", "Prime docking clamps", "pending"]);
});
