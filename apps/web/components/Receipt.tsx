"use client";

import { Fragment } from "react";

export type RunStatus = {
  run_id: string;
  status: "queued" | "running" | "succeeded" | "failed";
  scores?: { metric: string; value: number; n?: number };
  ops?: Record<string, any>;
  diffs?: Array<Record<string, any>>;
  ci?: { lower: number; upper: number; method: string } | null;
  artifacts?: { name: string; url: string }[];
  validation_count?: number;
  status_label?: "Replicated" | "Setting Drift" | "Underspecified" | "Not Reproduced";
};

export type ClaimSummary = {
  id: string;
  domain: string;
  task: string;
  metric: string;
  reference_score?: number;
};

type ReceiptProps = {
  claim: ClaimSummary;
  status: RunStatus;
};

function MetricBar({ label, value }: { label: string; value: number }) {
  const percent = Math.max(0, Math.min(value, 1)) * 100;
  return (
    <div style={{ marginBottom: 8 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}>
        <span>{label}</span>
        <span>{percent.toFixed(1)}%</span>
      </div>
      <div
        role="progressbar"
        aria-valuenow={Number(percent.toFixed(1))}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={label}
        style={{
          position: "relative",
          height: 8,
          borderRadius: 999,
          background: "#1f2a36",
          overflow: "hidden",
        }}
      >
        <div style={{ width: `${percent}%`, background: "#3fb950", height: "100%" }} />
      </div>
    </div>
  );
}

function renderArtifacts(artifacts?: { name: string; url: string }[]) {
  if (!artifacts || artifacts.length === 0) return null;
  return (
    <div style={{ marginTop: 12 }}>
      <span style={{ fontWeight: 600 }}>Artifacts:</span>
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginTop: 6 }}>
        {artifacts.map((artifact) => {
          const isDataUrl = artifact.url.startsWith("data:");
          const isExternal = artifact.url.startsWith("http");
          return (
            <a
              key={`${artifact.name}-${artifact.url}`}
              href={artifact.url}
              download={isDataUrl ? artifact.name : undefined}
              target={isExternal ? "_blank" : undefined}
              rel={isExternal ? "noreferrer" : undefined}
              style={{
                background: "#21262d",
                padding: "6px 10px",
                borderRadius: 6,
                color: "#58a6ff",
                fontSize: 13,
              }}
            >
              {artifact.name}
            </a>
          );
        })}
      </div>
    </div>
  );
}

function extractMetricRates(status: RunStatus): Record<string, number> {
  const metrics: Record<string, number> = {};
  const diffMetrics = status.diffs?.find((entry) => entry && typeof entry === "object" && "metrics" in entry);
  if (diffMetrics && typeof diffMetrics.metrics === "object") {
    for (const [key, value] of Object.entries(diffMetrics.metrics as Record<string, any>)) {
      if (typeof value === "number") {
        metrics[key] = value;
      }
    }
  }
  if (status.scores && typeof status.scores.value === "number") {
    metrics[status.scores.metric] = status.scores.value;
  }
  return metrics;
}

function formatPercent(value: number | undefined) {
  if (typeof value !== "number" || Number.isNaN(value)) return "—";
  return `${(Math.max(0, Math.min(value, 1)) * 100).toFixed(1)}%`;
}

function formatMetric(metric: string, value: number | undefined) {
  if (typeof value !== "number" || Number.isNaN(value)) return "—";
  const lower = metric.toLowerCase();
  if (lower.includes("rate") || lower.includes("success") || lower.includes("accuracy") || lower.includes("pass")) {
    return formatPercent(value);
  }
  return value.toFixed(2);
}

function summarizeClaim(claim: ClaimSummary, status: RunStatus, metrics: Record<string, number>) {
  const bullets: string[] = [];
  let headline = "";

  const primaryValue = metrics[claim.metric] ?? (status.scores?.metric === claim.metric ? status.scores.value : undefined);
  const reference = typeof claim.reference_score === "number" ? claim.reference_score : undefined;
  const formattedPrimary = formatMetric(claim.metric, primaryValue);
  const formattedReference = formatMetric(claim.metric, reference);

  const domainContext: Record<string, { success: string; caveat: string }> = {
    coding: {
      success: "Cleared all HumanEval programming prompts in our sample without assertion failures.",
      caveat: "Only 25 deterministic Python functions are covered here; broader coding ability is not guaranteed.",
    },
    "reasoning-math": {
      success: "Answered the GSM8K word problems we sampled correctly.",
      caveat: "This subset is small—it’s evidence of competence, not absolute proof of mathematical supremacy.",
    },
    agents: {
      success: "Executed every cAgent-12 workflow (tool calls, decisions, follow-ups) to completion.",
      caveat: "These flows mirror our internal tasks; real-world agent complexity can vary widely.",
    },
    "computer-use": {
      success: "Completed all scripted browser tasks in the cGUI-10 benchmark without timeouts.",
      caveat: "This harness is a deterministic simulation and does not prove superiority on every computer-use task.",
    },
  };

  if (status.status === "succeeded") {
    headline = `All ${claim.task} checks passed.`;
    if (formattedPrimary !== "—") {
      const referenceNote = formattedReference !== "—" ? ` (target ${formattedReference})` : "";
      bullets.push(`Observed ${claim.metric} at ${formattedPrimary}${referenceNote}.`);
    }
    const context = domainContext[claim.domain];
    if (context) {
      bullets.push(context.success);
      bullets.push(context.caveat);
    }
    if (status.ops?.p95_latency_s) {
      bullets.push(`Runs completed with roughly ${status.ops.p95_latency_s.toFixed(2)}s p95 latency and no service issues.`);
    }
  } else if (status.status === "failed") {
    headline = `Validation failed for ${claim.task}.`;
    if (status.diffs && status.diffs.length > 0) {
      for (const diff of status.diffs) {
        const reason = diff.reason ? diff.reason.replace(/_/g, " ") : "issue";
        bullets.push(`${reason}: ${diff.message ?? JSON.stringify(diff)}`);
      }
    } else if (formattedPrimary !== "—") {
      bullets.push(`Observed ${claim.metric} at ${formattedPrimary}, which did not meet the expected target.`);
    } else {
      bullets.push(`The harness exited before finishing. Check the attached artifacts or logs for details.`);
    }
  } else if (status.status === "running") {
    headline = `Running ${claim.task} harness…`;
    bullets.push(`The evaluation is still gathering evidence; results will update automatically.`);
  } else if (status.status === "queued") {
    headline = `Queued for execution.`;
    bullets.push(`Waiting for an available worker to start the ${claim.task} suite.`);
  } else {
    headline = `Awaiting validation.`;
    bullets.push(`Kick off the ${claim.task} suite to test this claim.`);
  }

  return { headline, bullets };
}

export function Receipt({ claim, status }: ReceiptProps) {
  const metrics = extractMetricRates(status);
  const rateEntries = Object.entries(metrics).filter(([key, value]) =>
    typeof value === "number" && (key.toLowerCase().includes("success") || key.toLowerCase().includes("rate"))
  ) as Array<[string, number]>;

  const otherMetrics = Object.entries(metrics).filter(
    ([key]) => key !== "unknown" && !rateEntries.some(([found]) => found === key)
  );
  const summary = summarizeClaim(claim, status, metrics);

  const opsItems: Array<[string, string]> = [];
  if (status.ops) {
    const { p95_latency_s, tokens_prompt, tokens_output, cost_usd, progress, ...rest } = status.ops;
    if (typeof p95_latency_s === "number") opsItems.push(["p95 latency", `${p95_latency_s}s`]);
    if (typeof tokens_prompt === "number") opsItems.push(["tokens in", String(tokens_prompt)]);
    if (typeof tokens_output === "number") opsItems.push(["tokens out", String(tokens_output)]);
    if (typeof cost_usd === "number") opsItems.push(["cost", `$${cost_usd.toFixed(4)}`]);
    for (const [key, value] of Object.entries(rest)) {
      opsItems.push([key.replace(/_/g, " "), typeof value === "number" ? value.toString() : String(value)]);
    }
  }

  return (
    <div>
      <div
        style={{
          marginBottom: 12,
          padding: "12px 14px",
          background: "rgba(23, 33, 50, 0.55)",
          border: "1px solid rgba(37, 56, 83, 0.6)",
          borderRadius: 10,
          textAlign: "left",
          fontSize: 13,
        }}
      >
        <div style={{ fontWeight: 600, marginBottom: 6 }}>{summary.headline}</div>
        <ul style={{ margin: 0, paddingLeft: 18, display: "flex", flexDirection: "column", gap: 4 }}>
          {summary.bullets.map((line, index) => (
            <li key={index}>{line}</li>
          ))}
        </ul>
      </div>

      {rateEntries.length > 0 && (
        <div style={{ marginTop: 8 }}>
          {rateEntries.map(([label, value]) => (
            <MetricBar key={label} label={label} value={value} />
          ))}
        </div>
      )}

      {otherMetrics.length > 0 && (
        <dl style={{ display: "grid", gridTemplateColumns: "max-content auto", gap: "4px 12px", fontSize: 13, marginTop: 8 }}>
          {otherMetrics.map(([label, value]) => (
            <Fragment key={label}>
              <dt style={{ textTransform: "capitalize" }}>{label.replace(/_/g, " ")}</dt>
              <dd style={{ margin: 0 }}>
                {typeof value === "number"
                  ? Number.isInteger(value)
                    ? value
                    : value.toFixed(3)
                  : String(value)}
              </dd>
            </Fragment>
          ))}
        </dl>
      )}

      {status.ci && (
        <div style={{ marginTop: 8, fontSize: 13 }}>
          95% CI: [{status.ci.lower.toFixed(2)}, {status.ci.upper.toFixed(2)}] ({status.ci.method})
        </div>
      )}

      {opsItems.length > 0 && (
        <div
          style={{
            marginTop: 12,
            display: "flex",
            gap: 12,
            flexWrap: "wrap",
            fontSize: 13,
          }}
        >
          {opsItems.map(([label, value]) => (
            <span key={label} style={{ background: "#21262d", padding: "6px 10px", borderRadius: 999 }}>
              <strong>{label}:</strong> {value}
            </span>
          ))}
        </div>
      )}

      {renderArtifacts(status.artifacts)}
    </div>
  );
}
