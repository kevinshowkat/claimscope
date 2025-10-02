import { test, expect } from "@playwright/test";

test("mission form submission surfaces receipt", async ({ page }) => {
  await page.goto("/form");

  await page.fill("#callsign", "Aurora-2");
  await page.fill("#crew", "6");
  await page.fill("#window", "2035-05-01T09:00");
  await page.fill("#notes", "Backup window");

  await page.click("button[type=submit]");

  await expect(page.getByRole("heading", { name: "Submission Receipt" })).toBeVisible();
  await expect(page.getByText("Aurora-2")).toBeVisible();
  await expect(page.getByText("6")).toBeVisible();
  await expect(page.getByText("2035-05-01T09:00")).toBeVisible();
  await expect(page.getByText("Backup window")).toBeVisible();
});
