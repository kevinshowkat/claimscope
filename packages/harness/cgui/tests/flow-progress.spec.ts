import { test, expect } from "@playwright/test";

test("flow button advances steps", async ({ page }) => {
  await page.goto("/flow");

  await page.click("text=Mark step complete");
  const first = page.locator("li", { hasText: "Authenticate" });
  const second = page.locator("li", { hasText: "Review data" });

  await expect(first.locator("span"))
    .toHaveText("Completed");
  await expect(second.locator("span"))
    .toHaveText("In progress");
});
