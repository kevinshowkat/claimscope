import type { ReactNode } from "react";

export const metadata = {
  title: "cGUI Harness",
  description: "Deterministic GUI scenarios for evaluation",
};

export default function CGUILayout({ children }: { children: ReactNode }) {
  return (
    <div style={{ padding: "24px", maxWidth: 960, margin: "0 auto" }}>
      <h1>cGUI Scenarios</h1>
      <p style={{ color: "#8b949e" }}>
        These mini-apps back the deterministic Playwright suite.
      </p>
      {children}
    </div>
  );
}
