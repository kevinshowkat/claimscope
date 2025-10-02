import { defineConfig } from "@playwright/test";

const baseURL = process.env.CGUI_BASE_URL || "http://localhost:3999";

export default defineConfig({
  testDir: "./tests",
  timeout: 30_000,
  reporter: [["json", { outputFile: "playwright-report.json" }]],
  use: {
    baseURL,
    trace: "on",
    video: "off",
    screenshot: "off",
  },
  webServer: {
    command: "PORT=3999 node server.js",
    port: 3999,
    reuseExistingServer: true,
    timeout: 120_000,
  },
});
