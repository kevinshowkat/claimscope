"use client";

import { useMemo, useState } from "react";

type Row = {
  id: string;
  phase: string;
  p95Latency: number;
  successRate: number;
};

const DATA: Row[] = [
  { id: "alpha", phase: "Intake", p95Latency: 1.1, successRate: 0.96 },
  { id: "beta", phase: "Planning", p95Latency: 1.4, successRate: 0.92 },
  { id: "gamma", phase: "Execution", p95Latency: 1.8, successRate: 0.88 },
  { id: "delta", phase: "Review", p95Latency: 1.2, successRate: 0.9 },
];

type SortKey = "phase" | "p95Latency" | "successRate";

export default function TelemetryTable() {
  const [key, setKey] = useState<SortKey>("phase");
  const [direction, setDirection] = useState<"asc" | "desc">("asc");

  const rows = useMemo(() => {
    const copy = [...DATA];
    copy.sort((a, b) => {
      const lhs = a[key];
      const rhs = b[key];
      if (lhs === rhs) return 0;
      const order = lhs < rhs ? -1 : 1;
      return direction === "asc" ? order : -order;
    });
    return copy;
  }, [key, direction]);

  function updateSort(next: SortKey) {
    if (next === key) {
      setDirection((prev) => (prev === "asc" ? "desc" : "asc"));
    } else {
      setKey(next);
      setDirection("asc");
    }
  }

  return (
    <div style={{ marginTop: 32 }}>
      <h2>Telemetry Table</h2>
      <p style={{ maxWidth: 640 }}>
        Sort the mission phases by latency or success rate. Data is deterministic to support
        headless testing.
      </p>
      <div role="group" aria-label="Sort options" style={{ display: "flex", gap: 8, marginBottom: 12 }}>
        <button type="button" onClick={() => updateSort("phase")}>Sort by phase</button>
        <button type="button" onClick={() => updateSort("p95Latency")}>Sort by p95 latency</button>
        <button type="button" onClick={() => updateSort("successRate")}>Sort by success rate</button>
      </div>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            <th scope="col" style={{ borderBottom: "1px solid #2d3440", textAlign: "left" }}>Phase</th>
            <th scope="col" style={{ borderBottom: "1px solid #2d3440", textAlign: "left" }}>p95 latency (s)</th>
            <th scope="col" style={{ borderBottom: "1px solid #2d3440", textAlign: "left" }}>Success rate</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              <td style={{ padding: "8px 4px" }}>{row.phase}</td>
              <td style={{ padding: "8px 4px" }}>{row.p95Latency.toFixed(1)}</td>
              <td style={{ padding: "8px 4px" }}>{(row.successRate * 100).toFixed(1)}%</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p style={{ marginTop: 12, fontSize: 13, color: "#8b949e" }}>Sorted by {key} ({direction}).</p>
    </div>
  );
}
