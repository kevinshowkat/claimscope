"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type MouseEvent, type ReactNode } from "react";

import { RunStatus } from "../components/Receipt";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Claim = {
  id: string;
  model: string;
  domain: string;
  task: string;
  metric: string;
  reference_score?: number;
  confidence: number;
  validation_count: number;
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
  isClaim: boolean;
  claimId: string | null;
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
    label: "Replicated",
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
    label: "Replicated",
    background: "#10291A",
    border: "#1F4D30",
    chipBg: "#2EA043",
    chipText: "#E9F6ED",
    text: "#E6EDF3",
  },
};

type ShareTheme = {
  background: string;
  text: string;
  accentPrimary: string;
  accentSecondary: string;
  caption: string;
};

const SHARE_THEME: Record<Verdict | "queued" | "running" | "idle", ShareTheme> = {
  idle: {
    background: "#111827",
    text: "#E5E7EB",
    accentPrimary: "#4B5563",
    accentSecondary: "#6B7280",
    caption: "#9CA3AF",
  },
  queued: {
    background: "#13203B",
    text: "#E0E7FF",
    accentPrimary: "#8FA7FF",
    accentSecondary: "#617BFF",
    caption: "#B4C4FF",
  },
  running: {
    background: "#102347",
    text: "#E0E7FF",
    accentPrimary: "#7DD3FC",
    accentSecondary: "#38BDF8",
    caption: "#93C5FD",
  },
  true_replicated: {
    background: "#0B3DFF",
    text: "#F5F8FF",
    accentPrimary: "#2EA043",
    accentSecondary: "#1F4D30",
    caption: "#D0DCFF",
  },
  likely_true: {
    background: "#1E293B",
    text: "#E2E8F0",
    accentPrimary: "#FACC15",
    accentSecondary: "#F59E0B",
    caption: "#FFE08A",
  },
  likely_exaggerated: {
    background: "#3C1424",
    text: "#FFE4E6",
    accentPrimary: "#FB7185",
    accentSecondary: "#F43F5E",
    caption: "#FCA5A5",
  },
  no_evidence: {
    background: "#1B2532",
    text: "#E5E7EB",
    accentPrimary: "#9CA3AF",
    accentSecondary: "#6B7280",
    caption: "#CBD5F5",
  },
};

const WORKING_MESSAGES = [
  "Weaving harness signals",
  "Syncing trace manifests",
  "Calibrating budget envelopes",
  "Comparing baseline receipts",
  "Capturing ops telemetry",
];

const MIN_INPUT_HEIGHT = 64;

const DOMAIN_SUMMARY: Record<string, { success: string; caveat: string }> = {
  coding: {
    success: "Cleared all HumanEval programming prompts in our sample without assertion failures.",
    caveat: "Only 25 deterministic Python functions are covered here; broader coding ability is not guaranteed.",
  },
  "reasoning-math": {
    success: "Answered the GSM8K word problems we sampled correctly.",
    caveat: "This subset is small—it’s evidence of competence, not absolute proof of mathematical supremacy.",
  },
  agents: {
    success: "Executed every cAgent-12 workflow to completion.",
    caveat: "These flows mirror our internal tasks; real-world agent complexity can vary widely.",
  },
  "computer-use": {
    success: "Completed all scripted browser tasks in the cGUI-10 benchmark without timeouts.",
    caveat: "This harness is a deterministic simulation and does not prove superiority on every computer-use task.",
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

function darkenHex(hex: string, amount: number): string {
  const sanitized = hex.replace(/^#/, "");
  const normalized = sanitized.length === 3
    ? sanitized
        .split("")
        .map((char) => char + char)
        .join("")
    : sanitized;

  if (normalized.length !== 6) {
    return hex;
  }

  const r = Math.max(0, Math.min(255, Math.round(Number.parseInt(normalized.slice(0, 2), 16) * (1 - amount))));
  const g = Math.max(0, Math.min(255, Math.round(Number.parseInt(normalized.slice(2, 4), 16) * (1 - amount))));
  const b = Math.max(0, Math.min(255, Math.round(Number.parseInt(normalized.slice(4, 6), 16) * (1 - amount))));

  return `#${r.toString(16).padStart(2, "0")}${g.toString(16).padStart(2, "0")}${b.toString(16).padStart(2, "0")}`;
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

type ClaimSignals = {
  hasQuantitative: boolean;
  hasNumber: boolean;
  hasSuperlative: boolean;
  hasLeadership: boolean;
  hasImprovementAdjective: boolean;
  hasProgressNoun: boolean;
  hasImpactVerb: boolean;
  hasDomainTerm: boolean;
  hasBenchmarkDescription: boolean;
  hasNowLeadership: boolean;
};

const QUANT_PATTERN = /\b\d+(?:\.\d+)?\s?(?:%|percent|percentage|pts?|points|pp|x|times|wins?|score(?:s)?|pp)\b/i;
const NUMBER_PATTERN = /\b\d+(?:\.\d+)?\b/;
const SUPERLATIVE_PATTERN = /\b(best|strongest|leading|leader|top|dominant|premier|ultimate|unmatched|unrivaled|superior|elite|flagship|number\s?one|#1|most\s+(?:advanced|capable|powerful|accurate|efficient|effective|comprehensive|trusted|scalable|secure|innovative|versatile|intelligent|reliable))\b/i;
const LEADERSHIP_PATTERN = /\b(leads?|tops?|dominates?|wins?|outperforms?|surpasses?|beats?|outpaces?|outclasses?|commands?|captures?|ranks?\s*(?:first|#?1|top|highest))\b/i;
const IMPROVEMENT_ADJECTIVE_PATTERN = /\b(significant|major|substantial|dramatic|remarkable|notable|meaningful|transformative|breakthrough|outsized|huge|massive|substantive|strong|large|noteworthy)\b/i;
const PROGRESS_NOUN_PATTERN = /\b(leap|advance|improvement|progress|gain|boost|growth|increase|surge|uptick|lift|advancement|stride|gains)\b/i;
const IMPACT_VERB_PATTERN = /\b(represents|is|are|remains|continues|shows?|demonstrates?|delivers?|drives?|achieves?|posts?|records?|scores?|tests?|evaluates?|measures?|assesses?|validates?|confirms?|proves?|enables?|powers?|supports?)\b/i;
const DOMAIN_PATTERN = /\b(model|models|system|systems|platform|solution|suite|benchmark|benchmarks|score|scores|performance|accuracy|agent|agents|agentic|reasoning|math|maths|compute|computer|coding|code|capability|capabilities|dataset|evaluation|task|tasks|benchmarking)\b/i;
const BENCHMARK_DESCRIPTION_PATTERN = /\bbenchmark\b/i;
const TEST_VERB_PATTERN = /\b(tests?|evaluates?|measures?|assesses?)\b/i;

function claimSignals(text: string): ClaimSignals {
  const normalized = text.replace(/\s+/g, " ").trim();
  const lower = normalized.toLowerCase();

  const hasQuantitative = QUANT_PATTERN.test(normalized);
  const hasNumber = hasQuantitative || NUMBER_PATTERN.test(normalized);
  const hasSuperlative = SUPERLATIVE_PATTERN.test(normalized);
  const hasLeadership = LEADERSHIP_PATTERN.test(normalized);
  const hasImprovementAdjective = IMPROVEMENT_ADJECTIVE_PATTERN.test(normalized);
  const hasProgressNoun = PROGRESS_NOUN_PATTERN.test(normalized);
  const hasImpactVerb = IMPACT_VERB_PATTERN.test(normalized);
  const hasDomainTerm = DOMAIN_PATTERN.test(normalized);
  const hasBenchmarkDescription = BENCHMARK_DESCRIPTION_PATTERN.test(normalized) && TEST_VERB_PATTERN.test(normalized);
  const hasNowLeadership = lower.includes(" now ") && hasLeadership;

  return {
    hasQuantitative,
    hasNumber,
    hasSuperlative,
    hasLeadership,
    hasImprovementAdjective,
    hasProgressNoun,
    hasImpactVerb,
    hasDomainTerm,
    hasBenchmarkDescription,
    hasNowLeadership,
  };
}

function isClaimSentence(text: string): boolean {
  const normalized = text.replace(/\s+/g, " ").trim();
  if (normalized.length < 12) return false;

  const signals = claimSignals(normalized);
  if (signals.hasBenchmarkDescription) return true;
  if (signals.hasQuantitative && (signals.hasLeadership || signals.hasImpactVerb || signals.hasDomainTerm)) return true;
  if (signals.hasLeadership && (signals.hasQuantitative || signals.hasSuperlative || signals.hasDomainTerm || signals.hasNumber)) return true;
  if (signals.hasSuperlative && (signals.hasImpactVerb || signals.hasDomainTerm || signals.hasLeadership)) return true;
  if (signals.hasImprovementAdjective && signals.hasImpactVerb && (signals.hasProgressNoun || signals.hasDomainTerm)) return true;
  if (signals.hasProgressNoun && signals.hasImpactVerb && signals.hasDomainTerm) return true;
  if (signals.hasNumber && signals.hasImpactVerb && signals.hasDomainTerm) return true;
  if (signals.hasNowLeadership) return true;

  return false;
}

type ClaimCandidate = {
  text: string;
  start: number;
  end: number;
  index: number;
};

function splitIntoSentences(raw: string): Array<{ text: string; start: number; end: number }> {
  const sentences: Array<{ text: string; start: number; end: number }> = [];
  let pointer = 0;
  const length = raw.length;

  const push = (from: number, to: number) => {
    if (to <= from) return;
    const fragment = raw.slice(from, to);
    const trimmed = fragment.trim();
    if (!trimmed) return;
    const offset = fragment.indexOf(trimmed);
    const absoluteStart = from + (offset >= 0 ? offset : 0);
    const absoluteEnd = absoluteStart + trimmed.length;
    sentences.push({ text: trimmed, start: absoluteStart, end: absoluteEnd });
  };

  for (let index = 0; index < length; index += 1) {
    const char = raw[index];

    if (char === "\n") {
      push(pointer, index);
      pointer = index + 1;
      continue;
    }

    if (char === "." || char === "!" || char === "?") {
      const prev = index > 0 ? raw[index - 1] : "";
      const next = index + 1 < length ? raw[index + 1] : "";

      if (char === "." && /\d/.test(prev) && /\d/.test(next)) {
        continue;
      }

      let boundary = index + 1;
      while (boundary < length && /["'’\)\]\s]/.test(raw[boundary])) {
        boundary += 1;
      }

      push(pointer, boundary);
      pointer = boundary;
    }
  }

  if (pointer < length) {
    push(pointer, length);
  }

  return sentences;
}

function detectClaimCandidates(raw: string): ClaimCandidate[] {
  if (!raw.trim()) return [];

  const results: ClaimCandidate[] = [];
  const seen = new Set<string>();
  const sentences = splitIntoSentences(raw);

  sentences.forEach((sentence, index) => {
    if (!isClaimSentence(sentence.text)) return;
    const key = `${sentence.start}:${sentence.end}`;
    if (seen.has(key)) return;
    seen.add(key);
    results.push({ ...sentence, index });
  });

  return results.sort((a, b) => a.start - b.start);
}

function tokenize(value: string): string[] {
  return value
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .filter((token) => token.length >= 3);
}

function scoreCandidateForClaim(claim: Claim, candidate: ClaimCandidate, claimPosition: number): number {
  let score = 0;
  const text = candidate.text.toLowerCase();
  const domain = (claim.domain || "").toLowerCase();
  const task = (claim.task || "").toLowerCase();
  const metric = (claim.metric || "").toLowerCase();

  if (domain && text.includes(domain)) score += 12;
  if (task && text.includes(task)) score += 14;
  if (metric && text.includes(metric)) score += 6;

  tokenize(domain).forEach((token) => {
    if (text.includes(token)) score += 4;
  });
  tokenize(task).forEach((token) => {
    if (text.includes(token)) score += 5;
  });
  tokenize(metric).forEach((token) => {
    if (text.includes(token)) score += 2;
  });

  if (task.includes("agent") && text.includes("agent")) score += 8;
  if (task.includes("computer") && text.includes("computer")) score += 8;
  if (task.includes("coding") && (text.includes("coding") || text.includes("code"))) score += 6;

  const signals = claimSignals(candidate.text);
  if (signals.hasSuperlative) score += 3;
  if (signals.hasLeadership) score += 4;
  if (signals.hasQuantitative) score += 3;
  if (signals.hasBenchmarkDescription) score += 5;

  score -= Math.abs(candidate.index - claimPosition) * 0.6;

  return score;
}

function matchCandidatesToClaims(claims: Claim[], candidates: ClaimCandidate[]): {
  assignments: Array<ClaimCandidate | null>;
  remaining: ClaimCandidate[];
} {
  const available = [...candidates];
  const assignments: Array<ClaimCandidate | null> = [];

  claims.forEach((claim, claimIndex) => {
    let bestScore = -Infinity;
    let bestIndex = -1;

    available.forEach((candidate, candidateIndex) => {
      const score = scoreCandidateForClaim(claim, candidate, claimIndex);
      if (score > bestScore) {
        bestScore = score;
        bestIndex = candidateIndex;
      }
    });

    if (bestIndex >= 0) {
      const [picked] = available.splice(bestIndex, 1);
      assignments.push(picked ?? null);
    } else {
      assignments.push(null);
    }
  });

  return { assignments, remaining: available };
}

type DetectionResult = {
  segments: Segment[];
  candidates: ClaimCandidate[];
};

function buildDetectionSegments(raw: string): DetectionResult {
  const detected = detectClaimCandidates(raw);

  if (detected.length === 0) {
    const trimmed = raw.trim();
    if (!trimmed) return { segments: [], candidates: [] };
    const start = raw.indexOf(trimmed);
    const candidate: ClaimCandidate = {
      text: trimmed,
      start: start >= 0 ? start : 0,
      end: (start >= 0 ? start : 0) + trimmed.length,
      index: 0,
    };

    return {
      segments: [
        {
          id: "detected-0",
          text: trimmed,
          start: candidate.start,
          end: candidate.end,
          status: "idle",
          verdict: "no_evidence",
          isClaim: true,
          claimId: null,
        },
      ],
      candidates: [candidate],
    };
  }

  return {
    segments: detected.map((candidate) => ({
      id: `detected-${candidate.index}`,
      text: candidate.text,
      start: candidate.start,
      end: candidate.end,
      status: "idle",
      verdict: "no_evidence",
      isClaim: true,
      claimId: null,
    })),
    candidates: detected,
  };
}

function buildFallbackSegments(raw: string, claims: Claim[], cursorRef: { value: number }): Segment[] {
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
        : [compact];

  return claims.map((claim, index) => {
    const candidate = candidates[index] ?? candidates[candidates.length - 1] ?? compact;
    const match = findSegmentRange(raw, candidate, cursorRef.value);

    if (match) {
      cursorRef.value = match.end;
      return {
        id: `fallback-${claim.id}`,
        text: raw.slice(match.start, match.end).trim() || candidate,
        start: match.start,
        end: match.end,
        status: "idle",
        verdict: "no_evidence",
        isClaim: true,
        claimId: claim.id,
      };
    }

    return {
      id: `fallback-${claim.id}`,
      text: candidate,
      start: null,
      end: null,
      status: "idle",
      verdict: "no_evidence",
      isClaim: true,
      claimId: claim.id,
    };
  });
}

function seedSegmentsFromRaw(raw: string): Segment[] {
  return buildDetectionSegments(raw).segments;
}

function buildSummary(claim: Claim, status: RunStatus | undefined) {
  const current = status ?? { run_id: "", status: "idle" };
  const bullets: string[] = [];
  let headline = "Awaiting validation.";

  const pushDiffBullets = () => {
    if (!current.diffs || current.diffs.length === 0) return;
    for (const diff of current.diffs) {
      if (!diff) continue;
      const reason = typeof diff.reason === "string" ? diff.reason.replace(/_/g, " ") : "note";
      const message = typeof diff.message === "string" ? diff.message : JSON.stringify(diff);
      bullets.push(`${reason}: ${message}`);
    }
  };

  if (current.status === "succeeded") {
    const statusLabel = current.status_label ?? "Replicated";
    if (statusLabel === "Replicated") {
      headline = `All ${claim.task} checks passed.`;
      const domainCopy = DOMAIN_SUMMARY[claim.domain];
      if (domainCopy) {
        bullets.push(domainCopy.success);
        bullets.push(domainCopy.caveat);
      }
      if (current.ops?.p95_latency_s) {
        bullets.push(
          `Runs completed with roughly ${current.ops.p95_latency_s.toFixed(2)}s p95 latency and no service issues.`,
        );
      }
      pushDiffBullets();
    } else if (statusLabel === "Underspecified") {
      headline = "Evidence is incomplete for this claim.";
      bullets.push("We need comparative or grounding data before calling this true.");
      pushDiffBullets();
      if (current.ops?.p95_latency_s) {
        bullets.push(
          `Harness run finished (p95 ${current.ops.p95_latency_s.toFixed(2)}s), but verdict is withheld.`,
        );
      }
    } else {
      headline = `${statusLabel} outcome for ${claim.task}.`;
      pushDiffBullets();
      if (current.ops?.p95_latency_s) {
        bullets.push(`Run completed with p95 latency ${current.ops.p95_latency_s.toFixed(2)}s.`);
      }
    }
  } else if (current.status === "failed") {
    headline = `Validation failed for ${claim.task}.`;
    pushDiffBullets();
  } else if (current.status === "running") {
    headline = `Running ${claim.task} harness…`;
    bullets.push("The evaluation is still gathering evidence; results will update automatically.");
  } else if (current.status === "queued") {
    headline = "Queued for execution.";
    bullets.push(`Waiting for an available worker to start the ${claim.task} suite.`);
  }

  return { headline, bullets };
}

function extractSegments(raw: string, claims: Claim[]): Segment[] {
  const detection = buildDetectionSegments(raw);
  const matching = matchCandidatesToClaims(claims, detection.candidates);

  const detectionMap = new Map<number, Segment>();
  detection.segments.forEach((segment) => {
    const match = /^detected-(\d+)$/.exec(segment.id);
    if (!match) return;
    const index = Number.parseInt(match[1], 10);
    if (!Number.isNaN(index)) {
      detectionMap.set(index, segment);
      segment.claimId = null;
    }
  });

  const unmatched: Claim[] = [];
  matching.assignments.forEach((candidate, claimIndex) => {
    const claim = claims[claimIndex];
    if (!claim) return;

    if (candidate) {
      const segment = detectionMap.get(candidate.index);
      if (segment) {
        segment.claimId = claim.id;
      }
    } else {
      unmatched.push(claim);
    }
  });

  const cursorRef = { value: 0 };
  const fallbackSegments = unmatched.length > 0 ? buildFallbackSegments(raw, unmatched, cursorRef) : [];

  const merged = [...detection.segments];

  fallbackSegments.forEach((fallback) => {
    const normalizedFallback = fallback.text.trim().toLowerCase();
    const detectionMatch = merged.find((segment) => {
      if (segment.claimId) return false;
      return segment.text.trim().toLowerCase() === normalizedFallback;
    });

    if (detectionMatch) {
      detectionMatch.claimId = fallback.claimId;
      if (fallback.start !== null && fallback.end !== null) {
        detectionMatch.start = fallback.start;
        detectionMatch.end = fallback.end;
      }
    } else {
      merged.push(fallback);
    }
  });

  return merged.sort((a, b) => {
    const aStart = typeof a.start === "number" ? a.start : Number.MAX_SAFE_INTEGER;
    const bStart = typeof b.start === "number" ? b.start : Number.MAX_SAFE_INTEGER;
    if (aStart !== bStart) return aStart - bStart;
    return a.id.localeCompare(b.id);
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
      const statusLabel = status.status_label?.toLowerCase();
      if (statusLabel === "underspecified") {
        return "no_evidence";
      }
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
    return { text: "Awaiting validation", tone: "muted" as const };
  }

  switch (verdict) {
    case "true_replicated":
      return { text: "Replicated result", tone: "positive" as const };
    case "likely_true":
      return { text: "Likely true", tone: "warning" as const };
    case "likely_exaggerated":
      return { text: "Signs of exaggeration", tone: "negative" as const };
    case "no_evidence":
    default:
      return { text: "No evidence found", tone: "muted" as const };
  }
}

export default function Page() {
  const [raw, setRaw] = useState("");
  const [claims, setClaims] = useState<Claim[]>([]);
  const [segments, setSegments] = useState<Segment[]>([]);
  const [runStatus, setRunStatus] = useState<Record<string, RunStatus | undefined>>({});
  const [workingLabelIndex, setWorkingLabelIndex] = useState<Record<string, number>>({});
  const [localValidationCounts, setLocalValidationCounts] = useState<Record<string, number>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [openClaimId, setOpenClaimId] = useState<string | null>(null);
  const [inputHeight, setInputHeight] = useState(MIN_INPUT_HEIGHT);
  const [hoverInfo, setHoverInfo] = useState<{ text: string; x: number; y: number } | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const highlightContentRef = useRef<HTMLDivElement | null>(null);
  const [isFocused, setIsFocused] = useState(false);
  const completedRunsRef = useRef<Set<string>>(new Set());
  const runningClaimsRef = useRef<string[]>([]);

  const updateInputHeight = useCallback(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    const next = Math.max(textarea.scrollHeight, MIN_INPUT_HEIGHT);
    textarea.style.height = `${next}px`;
    setInputHeight(next);
  }, []);

  const syncHighlightScroll = useCallback((element: HTMLTextAreaElement | null) => {
    if (!element || !highlightContentRef.current) return;
    const { scrollTop, scrollLeft } = element;
    highlightContentRef.current.style.transform = `translate(${-scrollLeft}px, ${-scrollTop}px)`;
    setHoverInfo(null);
  }, []);

  useEffect(() => {
    updateInputHeight();
  }, [raw, updateInputHeight]);

  useEffect(() => {
    if (claims.length === 0) {
      setSegments(seedSegmentsFromRaw(raw));
    }
  }, [claims.length, raw]);

  const handleHighlightHover = useCallback((event: MouseEvent<HTMLDivElement>) => {
    const highlightContainer = highlightContentRef.current?.parentElement as HTMLElement | null;
    const highlightContent = highlightContentRef.current;
    let elementsAtPointer: Element[] = [];

    if (typeof document !== "undefined") {
      const prevContainerPointer = highlightContainer?.style.pointerEvents ?? "";
      const prevContentPointer = highlightContent?.style.pointerEvents ?? "";
      try {
        if (highlightContainer) highlightContainer.style.pointerEvents = "auto";
        if (highlightContent) highlightContent.style.pointerEvents = "auto";
        elementsAtPointer = document.elementsFromPoint(event.clientX, event.clientY);
      } finally {
        if (highlightContainer) highlightContainer.style.pointerEvents = prevContainerPointer;
        if (highlightContent) highlightContent.style.pointerEvents = prevContentPointer;
      }
    }

    const match = elementsAtPointer.find(
      (element): element is HTMLElement => element instanceof HTMLElement && Boolean(element.dataset.summary),
    );

    if (match) {
      const rect = event.currentTarget.getBoundingClientRect();
      const x = Math.min(Math.max(event.clientX - rect.left, 16), rect.width - 16);
      const y = Math.min(Math.max(event.clientY - rect.top, 16), rect.height - 16);
      const text = match.dataset.summary ?? "";
      setHoverInfo({ text, x, y });
      return;
    }

    setHoverInfo(null);
  }, []);

  const clearHighlightHover = useCallback(() => {
    setHoverInfo(null);
  }, []);

  useEffect(() => {
    const claimLookup = new Map(claims.map((claim) => [claim.id, claim] as const));

    setSegments((previous) => {
      if (previous.length === 0) return previous;

      let hasChanges = false;
      const next = previous.map((segment) => {
        const statusObj = segment.claimId ? runStatus[segment.claimId] : undefined;
        const statusKey = (statusObj?.status ?? "idle") as Segment["status"];
        const verdict = resolveVerdict(segment.claimId ? claimLookup.get(segment.claimId) : undefined, statusObj);

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
      const emphasis = verdictKey === "no_evidence" ? 0.15 : 0.3;
      const textColor = verdictKey === "no_evidence" ? "#E6EDF3" : meta.text;
      const underlineColor = verdictKey === "no_evidence" ? "rgba(148, 163, 184, 0.85)" : meta.chipBg;
      const surface = verdictKey === "no_evidence"
        ? "rgba(148, 163, 184, 0.22)"
        : hexToRgba(meta.chipBg, emphasis);
      const outline = verdictKey === "no_evidence"
        ? "rgba(148, 163, 184, 0.35)"
        : hexToRgba(meta.chipBg, 0.4);
      return {
        color: textColor,
        textDecorationColor: underlineColor,
        backgroundColor: surface,
        boxShadow: `0 0 0 1px ${outline} inset`,
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
        const summary = verdictSummary(verdictKey, segment.status).text;
        const content = segment.isClaim ? (
          <span
            key={`segment-${segment.id}-${index}`}
            className={`highlight-segment verdict-${verdictKey}`}
            style={styleFor(verdictKey)}
            data-summary={summary}
          >
            {segment.text}
          </span>
        ) : (
          <span key={`segment-${segment.id}-${index}`} className="claim-plain">
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
        const summary = verdictSummary(verdictKey, segment.status).text;
        const slice = raw.slice(start, end);
        if (segment.isClaim) {
          nodes.push(
            <span
              key={`segment-${segment.id}-${index}`}
              className={`highlight-segment verdict-${verdictKey}`}
              style={styleFor(verdictKey)}
              data-summary={summary}
            >
              {slice}
            </span>,
          );
        } else {
          nodes.push(
            <span key={`segment-${segment.id}-${index}`} className="claim-plain">
              {slice}
            </span>,
          );
        }
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
  const runningClaimIds = useMemo(
    () => claims.filter((claim) => runStatus[claim.id]?.status === "running").map((claim) => claim.id),
    [claims, runStatus],
  );

  const hasRunning = runningClaimIds.length > 0;

  useEffect(() => {
    runningClaimsRef.current = runningClaimIds;
    const runningSet = new Set(runningClaimIds);

    setWorkingLabelIndex((previous) => {
      const next: Record<string, number> = { ...previous };
      let changed = false;

      runningClaimIds.forEach((id) => {
        if (next[id] === undefined) {
          next[id] = 0;
          changed = true;
        }
      });

      Object.keys(next).forEach((id) => {
        if (!runningSet.has(id)) {
          delete next[id];
          changed = true;
        }
      });

      return changed ? next : previous;
    });
  }, [runningClaimIds]);

  useEffect(() => {
    if (!hasRunning) {
      return () => {};
    }

    const timer = window.setInterval(() => {
      const ids = runningClaimsRef.current;
      if (ids.length === 0) {
        return;
      }

      setWorkingLabelIndex((previous) => {
        const next: Record<string, number> = { ...previous };
        let changed = false;
        ids.forEach((id) => {
          const current = next[id] ?? 0;
          next[id] = (current + 1) % WORKING_MESSAGES.length;
          changed = true;
        });
        return changed ? next : previous;
      });
    }, 2600);

    return () => window.clearInterval(timer);
  }, [hasRunning]);

  function canRun(claimId: string) {
    const current = runStatus[claimId]?.status;
    if (!current) return true;
    return current !== "queued" && current !== "running";
  }

  async function submitClaim() {
    if (!raw.trim()) return;
    setIsSubmitting(true);
    setClaims([]);
    setSegments(seedSegmentsFromRaw(raw));
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
      const normalizedClaims = data.claims.map((claim) => ({
        ...claim,
        validation_count: claim.validation_count ?? 0,
      }));
      setLocalValidationCounts((previous) => {
        const next = { ...previous };
        normalizedClaims.forEach((claim) => {
          next[claim.id] = claim.validation_count ?? 0;
        });
        return next;
      });
      setClaims(normalizedClaims);
      setSegments(extractSegments(raw, normalizedClaims));
      if (normalizedClaims.length > 0) {
        setOpenClaimId(normalizedClaims[0].id);
      }
      for (const claim of normalizedClaims) {
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

    let runId = "";

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
      runId = data.run_id;

      setRunStatus((previous) => ({
        ...previous,
        [claim.id]: {
          run_id: runId,
          status: "queued",
        },
      }));
      if (runId) {
        completedRunsRef.current.delete(runId);
      }

      async function poll() {
        try {
          const pollResponse = await fetch(`${API}/runs/${runId}`);
          if (!pollResponse.ok) {
            throw new Error(await pollResponse.text());
          }
          const status: RunStatus = await pollResponse.json();
          const updatedCount = (() => {
            const serverValue = typeof status.validation_count === "number" ? status.validation_count : undefined;
            const baseline =
              serverValue ?? localValidationCounts[claim.id] ?? claim.validation_count ?? 0;

            if (status.status === "succeeded" && !completedRunsRef.current.has(runId)) {
              completedRunsRef.current.add(runId);
              if (serverValue === undefined) {
                return baseline + 1;
              }
            }

            return serverValue ?? baseline;
          })();

          if (status.status === "succeeded" && typeof status.validation_count !== "number") {
            status.validation_count = updatedCount;
          }

          setLocalValidationCounts((previous) => ({
            ...previous,
            [claim.id]: updatedCount,
          }));

          setClaims((previous) =>
            previous.map((existing) => (
              existing.id === claim.id && existing.validation_count !== updatedCount
                ? { ...existing, validation_count: updatedCount }
                : existing
            )),
          );

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
          if (runId) {
            completedRunsRef.current.delete(runId);
          }
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
      if (runId) {
        completedRunsRef.current.delete(runId);
      }
    }
  }

  return (
    <main className="page">
      <div className="shell">
        <div
          className={`claim-input-wrapper ${isFocused ? "is-focused" : ""}`}
          style={{ minHeight: inputHeight }}
          onMouseMove={handleHighlightHover}
          onMouseLeave={clearHighlightHover}
        >
          <div className="claim-input-highlights" aria-hidden="true" style={{ minHeight: inputHeight }}>
            <div className="claim-input-highlights-content" ref={highlightContentRef}>
              {highlightNodes}
            </div>
          </div>
          <textarea
            ref={textareaRef}
            value={raw}
            onChange={(event) => {
              setRaw(event.target.value);
              updateInputHeight();
            }}
            placeholder="Paste a claim statement here..."
            className="claim-input"
            rows={1}
            onFocus={() => {
              setIsFocused(true);
              updateInputHeight();
            }}
            onBlur={() => setIsFocused(false)}
            onScroll={(event) => syncHighlightScroll(event.currentTarget)}
          />
          <div className="validate-action">
            <button onClick={submitClaim} disabled={isSubmitting || !raw.trim()} className="primary">
              {isSubmitting ? "Validating..." : "Validate"}
            </button>
          </div>
          {hoverInfo && hoverInfo.text && (
            <div className="claim-tooltip" style={{ top: hoverInfo.y, left: hoverInfo.x }}>
              {hoverInfo.text}
            </div>
          )}
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
              {claims.map((claim, index) => {
                const status = runStatus[claim.id];
                const statusKey: RunStatus["status"] | "idle" = status?.status ?? "idle";
                const verdict = resolveVerdict(claim, status);
            const chipLabel = statusKey === "queued" || statusKey === "running"
              ? STATUS_META[statusKey].label
              : VERDICT_META[verdict].label;
            const shareThemeKey: keyof typeof SHARE_THEME =
              statusKey === "queued"
                    ? "queued"
                    : statusKey === "running"
                      ? "running"
                      : statusKey === "idle"
                        ? "idle"
                        : verdict;
                const shareTheme = SHARE_THEME[shareThemeKey] ?? SHARE_THEME.no_evidence;
                const claimSnippet = segments.find((segment) => segment.claimId === claim.id)?.text
              ?? segments.find((segment) => segment.isClaim)?.text
              ?? `${claim.domain} · ${claim.task}`;
            const cleanedSnippet = claimSnippet.trim().replace(/^(["“])/, "").replace(/(["”])$/, "");
            const quotedSnippet = `“${cleanedSnippet}”`;
            const cardState = statusKey === "queued" ? "is-queued" : statusKey === "running" ? "is-running" : "is-rest";
            const summary = buildSummary(claim, status);
            const diffEntries = (status?.diffs ?? [])
              .map((diff) => {
                if (!diff) return null;
                if (typeof diff !== "object") {
                  const text = String(diff).trim();
                  return text ? { reason: undefined, message: text } : null;
                }

                const rawReason = typeof diff.reason === "string" ? diff.reason : undefined;
                const reasonKey = rawReason?.toLowerCase();
                if (reasonKey === "metrics" || reasonKey === "ops" || reasonKey === "artifacts") {
                  return null;
                }

                const messageCandidates = [diff.message, diff.details].map((value) =>
                  typeof value === "string" ? value.trim() : ""
                );
                const message = messageCandidates.find((value) => value);
                if (message) {
                  return { reason: rawReason, message };
                }

                const extraEntries = Object.entries(diff).filter(([key, value]) => {
                  if (key === "reason" || key === "message" || key === "details") return false;
                  if (key === "metrics") return false;
                  return value !== undefined && value !== null;
                });

                if (extraEntries.length === 0) return null;

                const formatted = extraEntries
                  .map(([key, value]) => {
                    const label = key.replace(/_/g, " ");
                    if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
                      return `${label}: ${value}`;
                    }
                    return null;
                  })
                  .filter(Boolean)
                  .join(" · ");

                return formatted ? { reason: rawReason, message: formatted } : null;
              })
              .filter((entry): entry is { reason?: string; message: string } => Boolean(entry?.message));
            const shareFooterItems = [claim.domain, claim.task].filter(Boolean);
            const validationCount = Math.max(
              0,
              status?.validation_count ?? localValidationCounts[claim.id] ?? claim.validation_count ?? 0,
            );
            const formattedValidationCount = validationCount.toLocaleString();
            const validationBadgeText = validationCount === 1 ? "Validated 1×" : `Validated ${formattedValidationCount}×`;
            const badgeStyle = {
              background: hexToRgba(shareTheme.accentSecondary, 0.45),
              color: shareTheme.text,
              boxShadow: `0 0 0 1px ${hexToRgba(shareTheme.accentSecondary, 0.55)} inset`,
            } as const;
            const isRunning = statusKey === "running";
            const progressIndicator = null;
            const workingLabel = WORKING_MESSAGES[workingLabelIndex[claim.id] ?? 0];

                return (
                  <div
                    key={claim.id}
                    className={`claim-card ${cardState}`}
                    style={{ background: shareTheme.background, color: shareTheme.text }}
                  >
                    <div className="share-top">
                      <span className="share-tag" style={{ color: shareTheme.caption }}>
                        Claim {index + 1}
                      </span>
                      <span className="share-claim-title">{quotedSnippet}</span>
                    </div>

                    {progressIndicator}

                    <div className="share-claim-text">
                      <span
                        className="share-chip"
                        style={{
                          background: shareTheme.accentPrimary,
                          color: "#FFFFFF",
                          boxShadow: `0 0 0 1px ${hexToRgba(shareTheme.accentPrimary, 0.4)} inset`,
                        }}
                      >
                        {chipLabel}
                      </span>
                    </div>

                    {isRunning ? (
                      <div className="share-working">
                        <div className="share-working-glow" aria-hidden="true" />
                        <div className="share-working-content">
                          <span className="share-working-spinner" aria-hidden="true" />
                          <span className="share-working-text">{workingLabel}</span>
                        </div>
                      </div>
                    ) : (
                      <div className="share-headline" style={{ borderColor: hexToRgba(shareTheme.accentPrimary, 0.55) }}>
                        <span style={{ color: "#FFFFFF" }}>{summary.headline}</span>
                      </div>
                    )}

                    {summary.bullets.length > 0 && (
                      <ul className="share-summary-list">
                        {summary.bullets.map((item, index) => (
                          <li key={index}>{item}</li>
                        ))}
                      </ul>
                    )}

                    {status && diffEntries.length > 0 && (
                      <ul className="diff-list">
                        {diffEntries.map((diff, index) => (
                          <li key={index}>
                            <span className="diff-key">{diff.reason ?? "details"}</span>
                            <span className="diff-value">{diff.message}</span>
                          </li>
                        ))}
                      </ul>
                    )}

                    <div className="share-footer">
                      <div className="share-footer-left">
                        {shareFooterItems.map((item, index) => (
                          <span key={`${item}-${index}`} className="share-footer-item">
                            {item}
                          </span>
                        ))}
                      </div>
                      <span className="share-footer-badge" style={badgeStyle}>
                        {validationBadgeText}
                      </span>
                    </div>

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
          background: #0B0F14;
          color: #E6EDF3;
        }

        .shell {
          width: min(1100px, 100%);
          display: flex;
          flex-direction: column;
          gap: 32px;
          text-align: left;
        }

        .claim-input-wrapper {
          position: relative;
          width: 100%;
          background: #0B0F14;
          border: 1px solid rgba(230, 237, 243, 0.18);
          border-radius: 16px;
          transition: border-color 0.18s ease, box-shadow 0.18s ease;
        }

        .claim-input-wrapper.is-focused {
          border-color: rgba(86, 156, 255, 0.65);
          box-shadow: 0 0 0 3px rgba(86, 156, 255, 0.18);
        }

        .claim-input {
          position: relative;
          z-index: 1;
          width: 100%;
          min-height: ${MIN_INPUT_HEIGHT}px;
          resize: none;
          border: none;
          background: transparent;
          color: transparent;
          caret-color: #E6EDF3;
          font-size: 2.25rem;
          line-height: 1.3;
          padding: 24px 176px 24px 24px;
          font-family: "Inter", system-ui, -apple-system, "Segoe UI", sans-serif;
          overflow: hidden;
          text-align: left;
        }

        .claim-input::placeholder {
          color: rgba(64, 80, 100, 0.45);
        }

        .claim-input:focus {
          outline: none;
        }

        .claim-input-highlights {
          position: absolute;
          inset: 0;
          padding: 24px 176px 24px 24px;
          color: #E6EDF3;
          font-size: 2.25rem;
          line-height: 1.3;
          font-family: "Inter", system-ui, -apple-system, "Segoe UI", sans-serif;
          pointer-events: none;
          overflow: hidden;
          z-index: 0;
          text-align: left;
        }

        .claim-input-highlights-content {
          position: relative;
          white-space: pre-wrap;
          word-break: break-word;
          transform: translate(0, 0);
        }

        .claim-placeholder {
          color: rgba(120, 137, 160, 0.4);
        }

        .claim-plain {
          color: rgba(230, 237, 243, 0.78);
        }

        .highlight-segment {
          text-decoration-line: underline;
          text-decoration-thickness: 0.12em;
          text-decoration-skip-ink: auto;
          font-weight: 600;
          border-radius: 10px;
          padding: 0.08em 0.18em;
          margin: 0 -0.05em;
          transition: color 0.2s ease, text-decoration-color 0.2s ease, background-color 0.2s ease;
        }

        .highlight-segment.verdict-no_evidence {
          text-decoration-style: dotted;
          background-color: rgba(148, 163, 184, 0.18);
          color: #C7D2FE;
          text-decoration-color: rgba(148, 163, 184, 0.75);
          box-shadow: inset 0 0 0 1px rgba(148, 163, 184, 0.28);
        }

        .highlight-segment.verdict-likely_true {
          text-decoration-style: dashed;
          background-color: rgba(245, 158, 11, 0.24);
          color: #FED7AA;
          text-decoration-color: rgba(245, 158, 11, 0.9);
          box-shadow: inset 0 0 0 1px rgba(245, 158, 11, 0.35);
        }

        .highlight-segment.verdict-likely_exaggerated {
          text-decoration-style: double;
          background-color: rgba(248, 81, 73, 0.22);
          color: #FCA5A5;
          text-decoration-color: rgba(248, 81, 73, 0.85);
          box-shadow: inset 0 0 0 1px rgba(248, 81, 73, 0.32);
        }

        .highlight-segment.verdict-true_replicated {
          text-decoration-style: solid;
          background-color: rgba(46, 160, 67, 0.26);
          color: #B7F7C4;
          text-decoration-color: rgba(46, 160, 67, 0.9);
          box-shadow: inset 0 0 0 1px rgba(46, 160, 67, 0.35);
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
          padding: 14px 42px;
          background: linear-gradient(135deg, #F8FAFC, #E2E8F0);
          color: #0B0F14;
          font-size: 1.05rem;
          box-shadow: 0 16px 32px rgba(148, 163, 184, 0.25);
          border: 1px solid rgba(226, 232, 240, 0.85);
        }

        .secondary {
          padding: 7px 16px;
          background: rgba(25, 32, 44, 0.85);
          color: #E6EDF3;
          border: 1px solid rgba(230, 237, 243, 0.18);
        }

        .validate-action {
          position: absolute;
          bottom: 20px;
          right: 20px;
          z-index: 2;
        }

        .claim-tooltip {
          position: absolute;
          pointer-events: none;
          background: rgba(11, 15, 20, 0.94);
          border: 1px solid rgba(230, 237, 243, 0.25);
          border-radius: 8px;
          padding: 8px 12px;
          color: #E6EDF3;
          font-size: 0.85rem;
          line-height: 1.3;
          max-width: 260px;
          transform: translate(-50%, calc(-100% - 14px));
          box-shadow: 0 16px 32px rgba(0, 0, 0, 0.35);
          white-space: normal;
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
          display: flex;
          flex-direction: column;
          gap: 18px;
        }

        .results h2 {
          margin: 0;
          font-size: 1.35rem;
        }

        .claim-list {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
          gap: 20px;
        }

        .claim-card {
          position: relative;
          border-radius: 24px;
          padding: 26px 30px;
          display: flex;
          flex-direction: column;
          gap: 18px;
          transition: transform 0.2s ease, box-shadow 0.2s ease, filter 0.2s ease, opacity 0.2s ease;
          box-shadow: 0 24px 48px rgba(0, 0, 0, 0.35);
        }

        .claim-card.is-queued {
          opacity: 0.62;
          filter: grayscale(0.4) brightness(0.85);
        }

        .claim-card.is-running,
        .claim-card.is-running,
        .claim-card.is-rest {
          opacity: 1;
          filter: none;
        }

        .claim-card.is-rest:hover,
        .claim-card.is-running:hover {
          transform: translateY(-6px);
          box-shadow: 0 32px 64px rgba(0, 0, 0, 0.4);
        }

        .share-top {
          display: flex;
          flex-direction: column;
          align-items: flex-start;
          gap: 6px;
        }

        .share-tag {
          font-size: 0.78rem;
          text-transform: uppercase;
          letter-spacing: 0.08em;
          font-weight: 600;
        }

        .share-claim-title {
          font-size: 1.05rem;
          font-weight: 500;
          color: rgba(248, 250, 252, 0.9);
          font-family: "Inter", system-ui, -apple-system, "Segoe UI", sans-serif;
        }

        .share-claim-text {
          display: flex;
          flex-direction: column;
          gap: 8px;
        }

        .share-progress {
          display: inline-flex;
          align-items: center;
          gap: 10px;
          font-size: 0.85rem;
          letter-spacing: 0.01em;
        }

        .share-progress-dot {
          width: 9px;
          height: 9px;
          border-radius: 50%;
          animation: pulse 1.4s ease-in-out infinite;
          box-shadow: 0 0 12px rgba(148, 163, 184, 0.35);
        }

        .share-chip {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          padding: 14px 22px;
          border-radius: 18px;
          font-size: clamp(2rem, 4vw, 2.6rem);
          font-weight: 700;
          font-family: "Inter", system-ui, -apple-system, "Segoe UI", sans-serif;
          color: #FFFFFF;
          align-self: stretch;
          letter-spacing: 0.01em;
          text-align: center;
          position: relative;
          overflow: hidden;
          z-index: 0;
        }

        .share-chip::after {
          content: "";
          position: absolute;
          inset: -70%;
          background: conic-gradient(
            from 90deg,
            rgba(99, 102, 241, 0.35),
            rgba(20, 184, 166, 0.18),
            rgba(129, 140, 248, 0.45),
            rgba(20, 184, 166, 0.18),
            rgba(99, 102, 241, 0.35)
          );
          filter: blur(38px);
          opacity: 0;
          pointer-events: none;
          animation: share-orbit 6s linear infinite;
          transition: opacity 0.28s ease;
          mix-blend-mode: screen;
        }

        .claim-card.is-running .share-chip::after {
          opacity: 0.75;
        }

        .share-headline {
          padding: 10px 14px;
          border-radius: 12px;
          background: rgba(11, 20, 35, 0.75);
          border: 1px solid;
          font-size: 1.05rem;
          font-weight: 700;
          display: inline-flex;
          align-items: center;
          gap: 8px;
        }

        .share-working {
          position: relative;
          overflow: hidden;
          border-radius: 14px;
          padding: 14px 18px;
          border: 1px solid rgba(255, 255, 255, 0.25);
          backdrop-filter: blur(12px);
          background: rgba(11, 20, 35, 0.65);
        }

        .share-working-glow {
          position: absolute;
          inset: -60%;
          background: conic-gradient(from 90deg, rgba(99, 102, 241, 0.35), rgba(20, 184, 166, 0.18), rgba(129, 140, 248, 0.45), rgba(20, 184, 166, 0.18), rgba(99, 102, 241, 0.35));
          animation: share-orbit 6s linear infinite;
          opacity: 0.65;
          filter: blur(32px);
        }

        .share-working-content {
          position: relative;
          display: flex;
          align-items: center;
          gap: 14px;
          color: #f8fafc;
          text-transform: uppercase;
          letter-spacing: 0.12em;
          font-size: 0.78rem;
          font-weight: 600;
        }

        .share-working-spinner {
          width: 20px;
          height: 20px;
          border-radius: 50%;
          border: 2px solid rgba(248, 250, 252, 0.35);
          border-top-color: #FFFFFF;
          animation: share-spin 1.4s linear infinite;
        }

        .share-working-text {
          text-shadow: 0 0 18px rgba(148, 163, 184, 0.6);
        }

        .share-rerun {
          background: rgba(11, 15, 20, 0.25);
          border-color: rgba(255, 255, 255, 0.22);
          color: inherit;
          align-self: flex-start;
        }

        .diff-list {
          margin: 12px 0 8px;
          padding: 0;
          list-style: none;
          display: flex;
          flex-direction: column;
          gap: 6px;
          font-size: 0.9rem;
        }

        .share-footer {
          margin-top: 18px;
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
          font-size: 0.85rem;
          color: rgba(248, 250, 252, 0.75);
        }

        .share-footer-left {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
        }

        .share-footer-item {
          background: rgba(15, 23, 42, 0.55);
          border-radius: 999px;
          padding: 6px 12px;
        }

        .share-footer-badge {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          border-radius: 999px;
          padding: 6px 12px;
          font-weight: 600;
          font-size: 0.85rem;
          min-width: 128px;
          text-align: right;
        }

        .share-summary-list {
          margin: 8px 0 14px;
          padding: 12px 16px;
          list-style: none;
          display: flex;
          flex-direction: column;
          gap: 8px;
          font-size: 0.95rem;
          color: rgba(248, 250, 252, 0.92);
          background: rgba(15, 23, 42, 0.55);
          border-radius: 12px;
          border: 1px solid rgba(248, 250, 252, 0.12);
        }

        .share-summary-list li {
          padding-left: 18px;
          position: relative;
        }

        .share-summary-list li::before {
          content: "▌";
          position: absolute;
          left: 0;
          top: 0;
          color: rgba(248, 250, 252, 0.7);
        }

        .diff-list li {
          display: flex;
          gap: 8px;
          align-items: baseline;
        }

        .diff-key {
          text-transform: capitalize;
          font-weight: 600;
          color: rgba(230, 237, 243, 0.9);
        }

        .diff-value {
          color: rgba(230, 237, 243, 0.8);
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

        @keyframes share-orbit {
          0% {
            transform: rotate(0deg);
          }
          100% {
            transform: rotate(360deg);
          }
        }

        @keyframes share-spin {
          0% {
            transform: rotate(0deg);
          }
          100% {
            transform: rotate(360deg);
          }
        }

        @media (max-width: 640px) {
          .claim-input {
            font-size: 1.65rem;
            padding: 18px 132px 18px 18px;
          }

          .claim-input-highlights {
            font-size: 1.65rem;
            padding: 18px 132px 18px 18px;
          }

          .validate-action {
            bottom: 14px;
            right: 14px;
          }

          .claim-list {
            grid-template-columns: 1fr;
            gap: 18px;
          }

          .claim-card {
            padding: 28px 24px;
            gap: 22px;
          }

          .share-claim-text {
            gap: 6px;
          }
        }
      `}</style>
    </main>
  );
}
