"use client";

import { useMemo, useState } from "react";

import { Receipt, RunStatus } from "../components/Receipt";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Claim = {
  id: string;
  model: string;
  domain: string;
  task: string;
  metric: string;
  reference_score?: number;
  confidence: number;
};

type SubmitResponse = {
  claim_ids: string[];
  claims: Claim[];
};

type RunResponse = {
  run_id: string;
};

type StatusVisual = {
  label: string;
  background: string;
  border: string;
  chipBg: string;
  chipText: string;
  text: string;
};

type Segment = {
  id: string;
  text: string;
};

const STATUS_META: Record<RunStatus["status"] | "idle", StatusVisual> = {
  idle: {
    label: "Not started",
    background: "#11161C",
    border: "#1D2633",
    chipBg: "#1D2633",
    chipText: "#9BA7B4",
    text: "#E6EDF3",
  },
  queued: {
    label: "Queued",
    background: "#152034",
    border: "#24324A",
    chipBg: "#223863",
    chipText: "#8AB4F8",
    text: "#E6EDF3",
  },
  running: {
    label: "Running",
    background: "#13263B",
    border: "#244862",
    chipBg: "#2563EB",
    chipText: "#DBEAFE",
    text: "#E6EDF3",
  },
  succeeded: {
    label: "Valid",
    background: "#10291A",
    border: "#1F4D30",
    chipBg: "#2EA043",
    chipText: "#E9F6ED",
    text: "#E6EDF3",
  },
  failed: {
    label: "Invalid",
    background: "#331820",
    border: "#5B202F",
    chipBg: "#F85149",
    chipText: "#FEE2E2",
    text: "#FBE6E6",
  },
};

function extractSegments(raw: string, claims: Claim[]): Segment[] {
  const trimmed = raw.replace(/\s+/g, " ").trim();

  const lineCandidates = raw
    .split(/\n+/)
    .map((line) => line.trim())
    .filter((line) => line.length > 0);

  const sentenceCandidates = (trimmed.match(/[^.!?\n]+[.!?]?/g) ?? [])
    .map((sentence) => sentence.trim())
    .filter((sentence) => sentence.length > 0);

  const candidates = lineCandidates.length >= claims.length && lineCandidates.length > 1
    ? lineCandidates
    : sentenceCandidates.length >= claims.length
      ? sentenceCandidates
      : lineCandidates.length > 0
        ? lineCandidates
        : [trimmed];

  return claims.map((claim, index) => ({
    id: claim.id,
    text: candidates[index] ?? candidates[candidates.length - 1] ?? `${claim.domain} / ${claim.task}`,
  }));
}

function MetricsHover({ status }: { status: RunStatus }) {
  const metaKey: RunStatus["status"] | "idle" = status.status ?? "idle";
  const meta = STATUS_META[metaKey];
  const metrics: Array<[string, string]> = [];

  if (status.scores) {
    metrics.push([status.scores.metric, status.scores.value.toFixed(2)]);
  }

  if (status.ops) {
    const { p95_latency_s, tokens_prompt, tokens_output, cost_usd } = status.ops;
    if (p95_latency_s) metrics.push(["p95 latency", `${p95_latency_s}s`]);
    if (tokens_prompt) metrics.push(["tokens in", String(tokens_prompt)]);
    if (tokens_output) metrics.push(["tokens out", String(tokens_output)]);
    if (typeof cost_usd === "number") metrics.push(["cost", `$${cost_usd.toFixed(4)}`]);
  }

  const note = status.diffs && status.diffs.length > 0 ? status.diffs[0] : undefined;

  return (
    <div
      className="hover-card"
      style={{
        borderColor: meta.border,
        background: meta.background,
        color: meta.text,
      }}
    >
      <div className="hover-header">{meta.label}</div>
      <div className="hover-body">
        {metrics.length > 0 ? (
          <ul>
            {metrics.map(([label, value]) => (
              <li key={label}>
                <span>{label}</span>
                <strong>{value}</strong>
              </li>
            ))}
          </ul>
        ) : (
          <p>No metrics yet.</p>
        )}
        {note && (
          <div className="hover-diff">
            <span>Notes:</span>
            <p>{note.message ?? JSON.stringify(note)}</p>
          </div>
        )}
      </div>
    </div>
  );
}

export default function Page() {
  const [raw, setRaw] = useState("");
  const [claims, setClaims] = useState<Claim[]>([]);
  const [segments, setSegments] = useState<Segment[]>([]);
  const [runStatus, setRunStatus] = useState<Record<string, RunStatus | undefined>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [openClaimId, setOpenClaimId] = useState<string | null>(null);
  const [hoverCard, setHoverCard] = useState<{ id: string; x: number; y: number } | null>(null);

  const statusMessage = useMemo(() => {
    if (isSubmitting) return "Parsing claim";
    if (
      claims.some((claim) => {
        const status = runStatus[claim.id]?.status;
        return status === "queued" || status === "running";
      })
    ) {
      return "Running validations";
    }
    return null;
  }, [claims, isSubmitting, runStatus]);

  function canRun(claimId: string) {
    const current = runStatus[claimId]?.status;
    if (!current) return true;
    return current !== "queued" && current !== "running";
  }

  async function submitClaim() {
    if (!raw.trim()) return;
    setIsSubmitting(true);
    setClaims([]);
    setSegments([]);
    setRunStatus({});
    setOpenClaimId(null);
    try {
      const response = await fetch(`${API}/submit_claim`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ raw_text: raw }),
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const data: SubmitResponse = await response.json();
      setClaims(data.claims);
      setSegments(extractSegments(raw, data.claims));
      if (data.claims.length > 0) {
        setOpenClaimId(data.claims[0].id);
      }
      for (const claim of data.claims) {
        void runRepro(claim, { auto: true });
      }
    } catch (error) {
      console.error("Failed to submit claim", error);
      alert("Unable to submit the claim. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function runRepro(claim: Claim, options: { auto?: boolean } = {}) {
    if (!canRun(claim.id) && !options.auto) return;

    setRunStatus((previous) => ({
      ...previous,
      [claim.id]: {
        run_id: previous[claim.id]?.run_id ?? "",
        status: "queued",
      },
    }));

    try {
      const requestBody = {
        claim_id: claim.id,
        model_config: {
          provider: "anthropic",
          name: "claude-3-5-sonnet-20240620",
          api_key_ref: "anthropic_default",
        },
        budget_usd: 0.02,
      };

      const response = await fetch(`${API}/run_reproduction`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(requestBody),
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const data: RunResponse = await response.json();
      const runId = data.run_id;

      setRunStatus((previous) => ({
        ...previous,
        [claim.id]: {
          run_id: runId,
          status: "queued",
        },
      }));

      async function poll() {
        try {
          const pollResponse = await fetch(`${API}/runs/${runId}`);
          if (!pollResponse.ok) {
            throw new Error(await pollResponse.text());
          }
          const status: RunStatus = await pollResponse.json();
          setRunStatus((previous) => ({ ...previous, [claim.id]: status }));
          if (status.status !== "succeeded" && status.status !== "failed") {
            setTimeout(poll, 900);
          }
        } catch (error) {
          console.error("Polling error", error);
          setRunStatus((previous) => ({
            ...previous,
            [claim.id]: {
              run_id: runId,
              status: "failed",
              diffs: [{ reason: "polling_error", message: String(error) }],
            },
          }));
        }
      }

      poll();
    } catch (error) {
      console.error("Failed to run reproduction", error);
      setRunStatus((previous) => ({
        ...previous,
        [claim.id]: {
          run_id: previous[claim.id]?.run_id ?? "",
          status: "failed",
          diffs: [{ reason: "run_error", message: String(error) }],
        },
      }));
    }
  }

  return (
    <main className="page">
      <div className="shell">
        <h1>Claim Validator</h1>
        <p className="subtitle">
          Paste a claim below and click validate. We will parse it, run the appropriate test suite, and color-code the
          results.
        </p>
        <textarea
          value={raw}
          onChange={(event) => setRaw(event.target.value)}
          placeholder="Paste a claim statement here..."
          className="claim-input"
        />
        <div className="actions">
          <button onClick={submitClaim} disabled={isSubmitting || !raw.trim()} className="primary">
            {isSubmitting ? "Validating..." : "Validate Claim"}
          </button>
        </div>

        {statusMessage && (
          <div className="status-banner">
            <span className="status-dot" />
            <span>{statusMessage}...</span>
          </div>
        )}

        {segments.length > 0 && (
          <section className="claim-text">
            <h2>Claim Text</h2>
            <div className="claim-lines">
              {segments.map((segment) => {
                const status = runStatus[segment.id];
                const key: RunStatus["status"] | "idle" = status?.status ?? "idle";
                const meta = STATUS_META[key];
                const isActive = hoverCard?.id === segment.id;
                return (
                  <span
                    key={segment.id}
                    className={`claim-line ${key} ${isActive ? "active" : ""}`}
                    style={{ color: meta.text, borderColor: meta.border }}
                    onMouseEnter={(event) => {
                      const rect = event.currentTarget.getBoundingClientRect();
                      setHoverCard({ id: segment.id, x: rect.left + rect.width / 2, y: rect.top });
                    }}
                    onMouseLeave={() => setHoverCard((info) => (info?.id === segment.id ? null : info))}
                    onClick={() => setOpenClaimId((current) => (current === segment.id ? null : segment.id))}
                  >
                    {segment.text}
                  </span>
                );
              })}
            </div>
          </section>
        )}

        {claims.length > 0 && (
          <section className="results">
            <h2>Results</h2>
            <div className="claim-list">
              {claims.map((claim) => {
                const status = runStatus[claim.id];
                const statusKey: RunStatus["status"] | "idle" = status?.status ?? "idle";
                const meta = STATUS_META[statusKey];
                const isOpen = openClaimId === claim.id;
                const reference = typeof claim.reference_score === "number" ? claim.reference_score : "—";

                return (
                  <div
                    key={claim.id}
                    className="claim-card"
                    style={{
                      background: meta.background,
                      borderColor: meta.border,
                      color: meta.text,
                    }}
                    onClick={() => setOpenClaimId((current) => (current === claim.id ? null : claim.id))}
                  >
                    <div className="card-header">
                      <div className="card-titles">
                        <div className="card-title">
                          {claim.domain} / {claim.task}
                        </div>
                        <div className="card-meta">
                          metric: {claim.metric} &bull; ref {reference}
                        </div>
                      </div>
                      <div className="card-actions">
                        <span
                          className={`status-chip ${statusKey === "running" ? "chip-pulse" : ""}`}
                          style={{ background: meta.chipBg, color: meta.chipText }}
                        >
                          {meta.label}
                        </span>
                        <button
                          className="secondary"
                          onClick={(event) => {
                            event.stopPropagation();
                            void runRepro(claim);
                          }}
                          disabled={!canRun(claim.id)}
                        >
                          Re-run
                        </button>
                      </div>
                    </div>

                    {status && (
                      <div className="status-summary">
                        {status.status === "succeeded" && <span className="summary positive">Claim validated successfully</span>}
                        {status.status === "failed" && <span className="summary negative">Validation failed</span>}
                        {status.status === "running" && <span className="summary indigo">Running tests...</span>}
                        {status.status === "queued" && <span className="summary muted">Queued for execution</span>}
                      </div>
                    )}

                    {status && status.diffs && status.diffs.length > 0 && (
                      <ul className="diff-list">
                        {status.diffs.map((diff, index) => (
                          <li key={index}>
                            <span className="diff-key">{diff.reason ?? "details"}</span>
                            <span className="diff-value">{diff.message ?? JSON.stringify(diff)}</span>
                          </li>
                        ))}
                      </ul>
                    )}

                    {isOpen && status && (
                      <div className="details">
                        <Receipt
                          claim={{
                            id: claim.id,
                            domain: claim.domain,
                            task: claim.task,
                            metric: claim.metric,
                            reference_score: claim.reference_score,
                          }}
                          status={status}
                        />
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </section>
        )}
      </div>

      {hoverCard && runStatus[hoverCard.id] && (
        <div
          className="hover-wrapper"
          style={{ left: hoverCard.x, top: hoverCard.y }}
          onMouseLeave={() => setHoverCard(null)}
        >
          <MetricsHover status={runStatus[hoverCard.id]!} />
        </div>
      )}

      <style jsx>{`
        .page {
          min-height: 100vh;
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 48px 16px;
          background: radial-gradient(circle at top, #172132, #0B0F14 60%);
          color: #E6EDF3;
        }

        .shell {
          width: min(760px, 100%);
          display: flex;
          flex-direction: column;
          gap: 20px;
          text-align: center;
        }

        h1 {
          font-size: clamp(2.2rem, 4vw, 3.1rem);
          margin: 0;
        }

        .subtitle {
          margin: 0;
          color: #9BA7B4;
          font-size: 1rem;
        }

        .claim-input {
          width: 100%;
          min-height: 22rem;
          resize: vertical;
          background: #0F1622;
          border: 1px solid #223040;
          border-radius: 18px;
          padding: 24px;
          font-size: 1.35rem;
          line-height: 1.7;
          color: #E6EDF3;
          box-shadow: 0 26px 45px rgba(8, 12, 20, 0.45);
        }

        .claim-input:focus {
          outline: none;
          border-color: #2EA043;
          box-shadow: 0 0 0 3px rgba(46, 160, 67, 0.25);
        }

        .actions {
          display: flex;
          justify-content: center;
        }

        button {
          cursor: pointer;
          border-radius: 999px;
          border: none;
          font-weight: 600;
          transition: transform 0.18s ease, opacity 0.18s ease;
        }

        button:disabled {
          cursor: not-allowed;
          opacity: 0.55;
        }

        button:not(:disabled):active {
          transform: scale(0.97);
        }

        .primary {
          padding: 15px 44px;
          background: linear-gradient(135deg, #2EA043, #3FB950);
          color: #0B0F14;
          font-size: 1.08rem;
          box-shadow: 0 16px 32px rgba(46, 160, 67, 0.35);
        }

        .secondary {
          padding: 7px 16px;
          background: #19202C;
          color: #9BA7B4;
          border: 1px solid #2A3545;
        }

        .status-banner {
          display: inline-flex;
          align-items: center;
          gap: 10px;
          padding: 10px 18px;
          border-radius: 999px;
          align-self: center;
          background: rgba(86, 137, 255, 0.12);
          color: #C9D7FF;
          font-size: 0.95rem;
        }

        .status-dot {
          width: 10px;
          height: 10px;
          border-radius: 50%;
          background: #5C8DFF;
          animation: pulse 1.4s ease-in-out infinite;
        }

        .claim-text {
          display: flex;
          flex-direction: column;
          gap: 12px;
          text-align: left;
        }

        .claim-text h2 {
          margin: 0;
          font-size: 1.4rem;
        }

        .claim-lines {
          display: flex;
          flex-direction: column;
          gap: 14px;
          font-size: 1.25rem;
        }

        .claim-line {
          border-bottom: 3px solid transparent;
          padding-bottom: 6px;
          position: relative;
          transition: transform 0.15s ease, border-color 0.2s ease;
        }

        .claim-line:hover {
          transform: translateY(-2px);
        }

        .claim-line.idle {
          border-color: rgba(155, 167, 180, 0.45);
        }

        .claim-line.queued {
          border-color: #223863;
        }

        .claim-line.running {
          border-color: #2563EB;
        }

        .claim-line.running::after {
          content: "";
          position: absolute;
          left: 0;
          right: 0;
          bottom: -3px;
          height: 3px;
          background: linear-gradient(90deg, rgba(37, 99, 235, 0), rgba(37, 99, 235, 0.5), rgba(37, 99, 235, 0));
          animation: shimmer 1.4s linear infinite;
        }

        .claim-line.succeeded {
          border-color: #2EA043;
        }

        .claim-line.failed {
          border-color: #F85149;
        }

        .results {
          text-align: left;
          display: flex;
          flex-direction: column;
          gap: 16px;
          margin-top: 16px;
        }

        .results h2 {
          margin: 0;
          font-size: 1.4rem;
        }

        .claim-list {
          display: flex;
          flex-direction: column;
          gap: 12px;
        }

        .claim-card {
          border: 1px solid;
          border-radius: 16px;
          padding: 18px 22px;
          cursor: pointer;
          transition: border-color 0.2s ease, transform 0.15s ease;
          box-shadow: 0 12px 24px rgba(8, 12, 20, 0.35);
        }

        .claim-card:hover {
          transform: translateY(-2px);
        }

        .card-header {
          display: flex;
          justify-content: space-between;
          gap: 12px;
          align-items: flex-start;
        }

        .card-titles {
          text-align: left;
        }

        .card-title {
          font-weight: 600;
          font-size: 1.05rem;
        }

        .card-meta {
          font-size: 0.85rem;
          color: rgba(230, 237, 243, 0.65);
          margin-top: 2px;
        }

        .card-actions {
          display: flex;
          gap: 10px;
          align-items: center;
        }

        .status-chip {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          padding: 6px 14px;
          border-radius: 999px;
          font-size: 0.8rem;
          font-weight: 600;
          min-width: 88px;
        }

        .chip-pulse {
          position: relative;
        }

        .chip-pulse::after {
          content: "";
          position: absolute;
          inset: 0;
          border-radius: inherit;
          border: 1px solid currentColor;
          opacity: 0.5;
          animation: pulse-ring 1.6s ease-in-out infinite;
        }

        .status-summary {
          margin-top: 12px;
          font-size: 0.9rem;
        }

        .summary {
          padding: 6px 10px;
          border-radius: 999px;
          font-weight: 500;
        }

        .summary.positive {
          background: rgba(46, 160, 67, 0.18);
          color: #89F7A5;
        }

        .summary.negative {
          background: rgba(248, 81, 73, 0.2);
          color: #FFC7C3;
        }

        .summary.indigo {
          background: rgba(91, 121, 255, 0.18);
          color: #C7D3FF;
        }

        .summary.muted {
          background: rgba(155, 167, 180, 0.15);
          color: #C0CAD4;
        }

        .diff-list {
          margin: 12px 0 0;
          padding: 0;
          list-style: none;
          display: flex;
          flex-direction: column;
          gap: 6px;
          font-size: 0.85rem;
        }

        .diff-list li {
          display: flex;
          gap: 8px;
          align-items: baseline;
        }

        .diff-key {
          text-transform: capitalize;
          font-weight: 600;
          color: rgba(230, 237, 243, 0.8);
        }

        .diff-value {
          color: rgba(230, 237, 243, 0.68);
        }

        .details {
          margin-top: 18px;
          border-top: 1px solid rgba(255, 255, 255, 0.1);
          padding-top: 18px;
        }

        .hover-wrapper {
          position: fixed;
          transform: translate(-50%, calc(-100% - 16px));
          pointer-events: none;
          z-index: 30;
        }

        .hover-card {
          min-width: 240px;
          max-width: 320px;
          border: 1px solid;
          border-radius: 14px;
          padding: 14px 16px;
          box-shadow: 0 24px 48px rgba(8, 12, 20, 0.45);
        }

        .hover-header {
          font-weight: 600;
          margin-bottom: 10px;
          text-transform: uppercase;
          font-size: 0.8rem;
          letter-spacing: 0.08em;
        }

        .hover-body ul {
          list-style: none;
          margin: 0;
          padding: 0;
          display: flex;
          flex-direction: column;
          gap: 6px;
          font-size: 0.85rem;
        }

        .hover-body li {
          display: flex;
          justify-content: space-between;
        }

        .hover-body li span {
          opacity: 0.75;
        }

        .hover-diff {
          margin-top: 10px;
          font-size: 0.8rem;
          text-align: left;
        }

        .hover-diff p {
          margin: 4px 0 0;
          opacity: 0.8;
        }

        @keyframes pulse {
          0%,
          100% {
            opacity: 0.4;
            transform: scale(0.9);
          }
          50% {
            opacity: 1;
            transform: scale(1.1);
          }
        }

        @keyframes pulse-ring {
          0% {
            transform: scale(1);
            opacity: 0.45;
          }
          70% {
            transform: scale(1.35);
            opacity: 0;
          }
          100% {
            transform: scale(1.35);
            opacity: 0;
          }
        }

        @keyframes shimmer {
          0% {
            transform: translateX(-100%);
          }
          50% {
            transform: translateX(0%);
          }
          100% {
            transform: translateX(100%);
          }
        }

        @media (max-width: 640px) {
          .claim-input {
            min-height: 14rem;
          }

          .card-header {
            flex-direction: column;
            align-items: flex-start;
          }

          .card-actions {
            align-self: stretch;
            justify-content: space-between;
          }
        }
      `}</style>
    </main>
  );
}
