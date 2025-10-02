import { test, expect } from "@playwright/test";

test("flow reaches completion message", async ({ page }) => {
  await page.goto("/flow");
  await page.click("text=Mark step complete");
  await page.click("text=Mark step complete");
  await page.click("text=Mark step complete");

  await expect(page.getByText("Checklist complete")).toBeVisible();
  await expect(page.getByText("Handover logged at 18:00 UTC")).toBeVisible();
});
