"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

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

type Verdict = "likely_exaggerated" | "likely_true" | "no_evidence" | "true_replicated";

type Segment = {
  id: string;
  text: string;
  start: number | null;
  end: number | null;
  status: RunStatus["status"] | "idle";
  verdict: Verdict;
};

const STATUS_META: Record<RunStatus["status"] | "idle", StatusVisual> = {
  idle: {
    label: "Awaiting run",
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
    label: "True / replicated",
    background: "#10291A",
    border: "#1F4D30",
    chipBg: "#2EA043",
    chipText: "#E9F6ED",
    text: "#E6EDF3",
  },
  failed: {
    label: "Likely exaggerated",
    background: "#331820",
    border: "#5B202F",
    chipBg: "#F85149",
    chipText: "#FEE2E2",
    text: "#FBE6E6",
  },
};

const VERDICT_META: Record<Verdict, StatusVisual> = {
  likely_exaggerated: {
    label: "Likely exaggerated",
    background: "#331820",
    border: "#5B202F",
    chipBg: "#F85149",
    chipText: "#FEE2E2",
    text: "#FBE6E6",
  },
  likely_true: {
    label: "Likely true",
    background: "#241C0F",
    border: "#3B2D15",
    chipBg: "#F59E0B",
    chipText: "#1F2937",
    text: "#FDE68A",
  },
  no_evidence: {
    label: "No evidence of accuracy",
    background: "#11161E",
    border: "#1F2734",
    chipBg: "#4B5563",
    chipText: "#E5E7EB",
    text: "#D1D5DB",
  },
  true_replicated: {
    label: "True / replicated",
    background: "#10291A",
    border: "#1F4D30",
    chipBg: "#2EA043",
    chipText: "#E9F6ED",
    text: "#E6EDF3",
  },
};

function escapeRegExp(value: string): string {
  return value.replace(/[-/\\^$*+?.()|[\]{}]/g, "\\$&");
}

function hexToRgba(hex: string, alpha: number): string {
  const sanitized = hex.replace(/^#/, "");
  const normalized = sanitized.length === 3
    ? sanitized
        .split("")
        .map((char) => char + char)
        .join("")
    : sanitized;

  if (normalized.length !== 6) {
    return `rgba(255, 255, 255, ${alpha})`;
  }

  const value = Number.parseInt(normalized, 16);
  const r = (value >> 16) & 255;
  const g = (value >> 8) & 255;
  const b = value & 255;
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function findSegmentRange(raw: string, fragment: string, fromIndex: number): { start: number; end: number } | null {
  if (!fragment.trim()) return null;

  const normalizedPattern = escapeRegExp(fragment).replace(/\s+/g, "\\s+");
  const forward = new RegExp(normalizedPattern, "gi");
  forward.lastIndex = fromIndex;

  const forwardMatch = forward.exec(raw);
  if (forwardMatch) {
    return { start: forwardMatch.index, end: forwardMatch.index + forwardMatch[0].length };
  }

  const fallback = new RegExp(normalizedPattern, "gi");
  const fallbackMatch = fallback.exec(raw);
  if (fallbackMatch) {
    return { start: fallbackMatch.index, end: fallbackMatch.index + fallbackMatch[0].length };
  }

  return null;
}

function extractSegments(raw: string, claims: Claim[]): Segment[] {
  const compact = raw.replace(/\s+/g, " ").trim();

  const lineCandidates = raw
    .split(/\n+/)
    .map((line) => line.trim())
    .filter((line) => line.length > 0);

  const sentenceCandidates = (compact.match(/[^.!?\n]+[.!?]?/g) ?? [])
    .map((sentence) => sentence.trim())
    .filter((sentence) => sentence.length > 0);

  const candidates = lineCandidates.length >= claims.length && lineCandidates.length > 1
    ? lineCandidates
    : sentenceCandidates.length >= claims.length
      ? sentenceCandidates
      : lineCandidates.length > 0
        ? lineCandidates
        : compact
          ? [compact]
          : [];

  let cursor = 0;

  return claims.map((claim, index) => {
    const candidate = candidates[index] ?? candidates[candidates.length - 1] ?? `${claim.domain} / ${claim.task}`;
    const match = findSegmentRange(raw, candidate, cursor);

    if (match) {
      cursor = match.end;
      return {
        id: claim.id,
        text: candidate,
        start: match.start,
        end: match.end,
        status: "idle",
        verdict: "no_evidence",
      };
    }

    return {
      id: claim.id,
      text: candidate,
      start: null,
      end: null,
      status: "idle",
      verdict: "no_evidence",
    };
  });
}

function resolveVerdict(claim: Claim | undefined, status: RunStatus | undefined): Verdict {
  const defaultVerdict: Verdict = "no_evidence";
  if (!status || !status.status) return defaultVerdict;

  switch (status.status) {
    case "queued":
      return "no_evidence";
    case "running":
      return "likely_true";
    case "succeeded": {
      const value = status.scores?.value;
      const reference = typeof claim?.reference_score === "number" ? claim.reference_score : undefined;
      if (typeof value === "number" && typeof reference === "number") {
        if (value >= reference) return "true_replicated";
        if (value >= reference * 0.75) return "likely_true";
        return "likely_exaggerated";
      }
      return "true_replicated";
    }
    case "failed": {
      const diffText = JSON.stringify(status.diffs ?? []).toLowerCase();
      if (
        diffText.includes("no evidence") ||
        diffText.includes("not found") ||
        diffText.includes("missing") ||
        diffText.includes("unavailable")
      ) {
        return "no_evidence";
      }
      return "likely_exaggerated";
    }
    default:
      return defaultVerdict;
  }
}

function verdictSummary(verdict: Verdict, statusKey: RunStatus["status"] | "idle") {
  if (statusKey === "running") {
    return { text: "Running tests...", tone: "indigo" as const };
  }
  if (statusKey === "queued") {
    return { text: "Queued for execution", tone: "muted" as const };
  }
  if (statusKey === "idle") {
    return { text: "No evidence yet — run validation.", tone: "muted" as const };
  }

  switch (verdict) {
    case "true_replicated":
      return { text: "Claim replicated successfully", tone: "positive" as const };
    case "likely_true":
      return { text: "Evidence leans toward accuracy", tone: "warning" as const };
    case "likely_exaggerated":
      return { text: "Evidence points to exaggeration", tone: "negative" as const };
    case "no_evidence":
    default:
      return { text: "No supporting evidence found", tone: "muted" as const };
  }
}

export default function Page() {
  const [raw, setRaw] = useState("");
  const [claims, setClaims] = useState<Claim[]>([]);
  const [segments, setSegments] = useState<Segment[]>([]);
  const [runStatus, setRunStatus] = useState<Record<string, RunStatus | undefined>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [openClaimId, setOpenClaimId] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const highlightContentRef = useRef<HTMLDivElement | null>(null);
  const [isFocused, setIsFocused] = useState(false);

  const syncHighlightScroll = useCallback((element: HTMLTextAreaElement | null) => {
    if (!element || !highlightContentRef.current) return;
    const { scrollTop, scrollLeft } = element;
    highlightContentRef.current.style.transform = `translate(${-scrollLeft}px, ${-scrollTop}px)`;
  }, []);

  useEffect(() => {
    const claimLookup = new Map(claims.map((claim) => [claim.id, claim] as const));

    setSegments((previous) => {
      if (previous.length === 0) return previous;

      let hasChanges = false;
      const next = previous.map((segment) => {
        const statusObj = runStatus[segment.id];
        const statusKey = (statusObj?.status ?? "idle") as Segment["status"];
        const verdict = resolveVerdict(claimLookup.get(segment.id), statusObj);

        if (segment.status === statusKey && segment.verdict === verdict) {
          return segment;
        }
        hasChanges = true;
        return { ...segment, status: statusKey, verdict };
      });

      return hasChanges ? next : previous;
    });
  }, [claims, runStatus]);

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

  const highlightNodes = useMemo<ReactNode[]>(() => {
    if (!raw) {
      return [
        <span key="placeholder" className="claim-placeholder">
          Paste a claim statement here...
        </span>,
      ];
    }

    const styleFor = (verdictKey: Verdict) => {
      const meta = VERDICT_META[verdictKey] ?? VERDICT_META.no_evidence;
      const emphasis = verdictKey === "no_evidence" ? 0.16 : 0.28;
      return {
        color: meta.chipText,
        textDecorationColor: meta.chipBg,
        backgroundColor: hexToRgba(meta.chipBg, emphasis),
        boxShadow: `0 0 0 1px ${hexToRgba(meta.chipBg, 0.25)} inset`,
      };
    };

    const positioned = segments
      .filter((segment) => segment.start !== null && segment.end !== null && segment.end > segment.start)
      .sort((a, b) => (a.start! - b.start!));

    if (positioned.length === 0) {
      if (segments.length === 0) {
        return [
          <span key="plain" className="claim-plain">
            {raw}
          </span>,
        ];
      }

      return segments.flatMap((segment, index) => {
        const verdictKey = segment.verdict;
        const content = (
          <span
            key={`segment-${segment.id}-${index}`}
            className={`highlight-segment verdict-${verdictKey}`}
            style={styleFor(verdictKey)}
          >
            {segment.text}
          </span>
        );

        if (index === segments.length - 1) {
          return [content];
        }

        return [
          content,
          <span key={`space-${segment.id}-${index}`} className="claim-plain">
            {" "}
          </span>,
        ];
      });
    }

    const nodes: ReactNode[] = [];
    let cursor = 0;

    positioned.forEach((segment, index) => {
      const start = Math.max(segment.start ?? 0, cursor);
      const end = Math.max(segment.end ?? start, start);
      if (start > cursor) {
        nodes.push(
          <span key={`plain-${cursor}-${start}`} className="claim-plain">
            {raw.slice(cursor, start)}
          </span>,
        );
      }

      if (end > start) {
        const verdictKey = segment.verdict;
        nodes.push(
          <span
            key={`segment-${segment.id}-${index}`}
            className={`highlight-segment verdict-${verdictKey}`}
            style={styleFor(verdictKey)}
          >
            {raw.slice(start, end)}
          </span>,
        );
      }

      cursor = Math.max(cursor, end);
    });

    if (cursor < raw.length) {
      nodes.push(
        <span key="plain-tail" className="claim-plain">
          {raw.slice(cursor)}
        </span>,
      );
    }

    return nodes;
  }, [raw, segments]);

  useEffect(() => {
    syncHighlightScroll(textareaRef.current);
  }, [raw, segments, syncHighlightScroll]);

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
        <div className={`claim-input-wrapper ${isFocused ? "is-focused" : ""}`}>
          <div className="claim-input-highlights" aria-hidden="true">
            <div className="claim-input-highlights-content" ref={highlightContentRef}>
              {highlightNodes}
            </div>
          </div>
          <textarea
            ref={textareaRef}
            value={raw}
            onChange={(event) => setRaw(event.target.value)}
            placeholder="Paste a claim statement here..."
            className="claim-input"
            onFocus={() => setIsFocused(true)}
            onBlur={() => setIsFocused(false)}
            onScroll={(event) => syncHighlightScroll(event.currentTarget)}
          />
        </div>
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
        {claims.length > 0 && (
          <section className="results">
            <h2>Results</h2>
            <div className="claim-list">
              {claims.map((claim) => {
                const status = runStatus[claim.id];
                const statusKey: RunStatus["status"] | "idle" = status?.status ?? "idle";
                const verdict = resolveVerdict(claim, status);
                const verdictMeta = VERDICT_META[verdict];
                const isProgress = statusKey === "queued" || statusKey === "running";
                const surfaceMeta = isProgress ? STATUS_META[statusKey] : verdictMeta;
                const chipMeta = isProgress ? STATUS_META[statusKey] : verdictMeta;
                const chipLabel = isProgress ? STATUS_META[statusKey].label : verdictMeta.label;
                const summaryInfo = verdictSummary(verdict, statusKey);
                const isOpen = openClaimId === claim.id;
                const reference = typeof claim.reference_score === "number" ? claim.reference_score : "—";

                return (
                  <div
                    key={claim.id}
                    className="claim-card"
                    style={{
                      background: surfaceMeta.background,
                      borderColor: surfaceMeta.border,
                      color: surfaceMeta.text,
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
                          style={{ background: chipMeta.chipBg, color: chipMeta.chipText }}
                        >
                          {chipLabel}
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

                    <div className="status-summary">
                      <span className={`summary ${summaryInfo.tone}`}>{summaryInfo.text}</span>
                    </div>

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
          width: min(960px, 100%);
          display: flex;
          flex-direction: column;
          gap: 20px;
          text-align: left;
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

        .claim-input-wrapper {
          position: relative;
          width: 100%;
          min-height: clamp(36rem, 65vh, 52rem);
          background: #0F1622;
          border: 1px solid #223040;
          border-radius: 18px;
          box-shadow: 0 26px 45px rgba(8, 12, 20, 0.45);
          transition: border-color 0.18s ease, box-shadow 0.18s ease;
        }

        .claim-input-wrapper.is-focused {
          border-color: #2EA043;
          box-shadow: 0 0 0 3px rgba(46, 160, 67, 0.25);
        }

        .claim-input {
          position: relative;
          z-index: 2;
          width: 100%;
          min-height: clamp(36rem, 65vh, 52rem);
          resize: vertical;
          border: none;
          background: transparent;
          color: transparent;
          caret-color: #E6EDF3;
          font-size: 6.75rem;
          line-height: 1.1;
          padding: 36px;
          font-family: "Inter", system-ui, -apple-system, "Segoe UI", sans-serif;
          overflow: auto;
          text-align: left;
        }

        .claim-input::placeholder {
          color: transparent;
        }

        .claim-input:focus {
          outline: none;
        }

        .claim-input-highlights {
          position: absolute;
          inset: 0;
          padding: 36px;
          color: #E6EDF3;
          font-size: 6.75rem;
          line-height: 1.1;
          font-family: "Inter", system-ui, -apple-system, "Segoe UI", sans-serif;
          pointer-events: none;
          overflow: hidden;
          z-index: 1;
          text-align: left;
        }

        .claim-input-highlights-content {
          position: relative;
          white-space: pre-wrap;
          word-break: break-word;
          transform: translate(0, 0);
        }

        .claim-placeholder {
          color: #9BA7B4;
        }

        .claim-plain {
          color: rgba(230, 237, 243, 0.82);
        }

        .highlight-segment {
          text-decoration-line: underline;
          text-decoration-thickness: 0.18em;
          text-decoration-skip-ink: none;
          font-weight: 600;
          border-radius: 10px;
          padding: 0.05em 0.18em;
          margin: 0 -0.05em;
          transition: background-color 0.2s ease, color 0.2s ease;
        }

        .highlight-segment.verdict-no_evidence {
          text-decoration-style: dotted;
        }

        .highlight-segment.verdict-likely_true {
          text-decoration-style: dashed;
        }

        .highlight-segment.verdict-likely_exaggerated {
          text-decoration-style: double;
        }

        .highlight-segment.verdict-true_replicated {
          text-decoration-style: solid;
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

        .summary.warning {
          background: rgba(245, 158, 11, 0.22);
          color: #FDE68A;
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

        @media (max-width: 640px) {
          .claim-input-wrapper,
          .claim-input {
            min-height: 18rem;
          }

          .claim-input,
          .claim-input-highlights {
            font-size: 3rem;
            line-height: 1.25;
            padding: 20px;
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
