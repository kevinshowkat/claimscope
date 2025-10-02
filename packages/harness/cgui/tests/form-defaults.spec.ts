import { test, expect } from "@playwright/test";

test("mission form uses deterministic defaults", async ({ page }) => {
  await page.goto("/form");

  await expect(page.locator("#callsign")).toHaveValue("Aurora");
  await expect(page.locator("#crew")).toHaveValue("4");
  await expect(page.locator("#window")).toHaveValue("2035-04-18T13:30");
});
