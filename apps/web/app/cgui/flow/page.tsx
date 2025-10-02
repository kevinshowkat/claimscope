"use client";

import { useState } from "react";

const STEPS = [
  { id: 1, title: "Authenticate", description: "Confirm mission token." },
  { id: 2, title: "Review data", description: "Accept archived sensor bundle." },
  { id: 3, title: "Sign off", description: "Record final acknowledgement." },
];

export default function ChecklistFlow() {
  const [index, setIndex] = useState(0);

  const complete = index >= STEPS.length;

  function advance() {
    setIndex((prev) => Math.min(prev + 1, STEPS.length));
  }

  return (
    <section style={{ marginTop: 32 }}>
      <h2>Checklist Flow</h2>
      <p>Simulate the deterministic handover flow.</p>

      <ol style={{ display: "grid", gap: 10, paddingLeft: 20 }}>
        {STEPS.map((step, i) => (
          <li key={step.id} aria-current={i === index ? "step" : undefined}>
            <strong>{step.title}</strong>
            <p style={{ margin: "2px 0 0" }}>{step.description}</p>
            <span style={{ fontSize: 12, color: "#8b949e" }}>
              {i < index ? "Completed" : i === index ? "In progress" : "Pending"}
            </span>
          </li>
        ))}
      </ol>

      <button
        type="button"
        onClick={advance}
        disabled={complete}
        style={{ marginTop: 16 }}
        aria-live="polite"
      >
        {complete ? "Checklist complete" : "Mark step complete"}
      </button>

      {complete && (
        <p style={{ marginTop: 16, padding: 12, border: "1px solid #2d3440", borderRadius: 8 }}>
          All steps confirmed. Handover logged at 18:00 UTC.
        </p>
      )}
    </section>
  );
}
