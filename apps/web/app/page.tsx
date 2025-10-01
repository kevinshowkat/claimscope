"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Claim = { id: string; model: string; domain: string; task: string; metric: string; reference_score?: number; confidence: number };

type SubmitResp = { claim_ids: string[]; claims: Claim[] };

type RunResp = { run_id: string };

type RunStatus = {
  run_id: string;
  status: "queued"|"running"|"succeeded"|"failed";
  scores?: { metric: string; value: number; n?: number };
  ops?: Record<string, any>;
  diffs?: Array<Record<string, any>>;
  ci?: { lower: number; upper: number; method: string } | null;
  artifacts?: { name: string; url: string }[];
};

const PRESETS = [
  { label: "Coding — HumanEval", text: "Preset: HumanEval coding claim (pass@1)" },
  { label: "Agents — cAgent-12", text: "Preset: cAgent-12 agent claim (success@1)" },
  { label: "Computer-use — cGUI-10", text: "Preset: cGUI-10 GUI claim (task_success)" },
  { label: "Reasoning — GSM8K", text: "Preset: GSM8K accuracy claim" },
];

export default function Page() {
  const [raw, setRaw] = useState("");
  const [claims, setClaims] = useState<Claim[]>([]);
  const [runStatus, setRunStatus] = useState<Record<string, RunStatus | undefined>>({});
  const [busy, setBusy] = useState(false);

  function canRun(id: string) {
    return !!id && !runStatus[id];
  }

  async function submitClaim() {
    setBusy(true);
    try {
      const r = await fetch(`${API}/submit_claim`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ raw_text: raw }) });
      const data: SubmitResp = await r.json();
      setClaims(data.claims);
    } finally {
      setBusy(false);
    }
  }

  async function runRepro(claim: Claim) {
    setBusy(true);
    try {
      const body = { claim_id: claim.id, model_config: { provider: "anthropic", name: "claude-3-5-sonnet-20240620", api_key_ref: "anthropic_default" }, budget_usd: 0.02 };
      const r = await fetch(`${API}/run_reproduction`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
      const data: RunResp = await r.json();
      // start polling for this run
      const runId = data.run_id;
      let stopped = false;
      async function poll() {
        const pr = await fetch(`${API}/runs/${runId}`);
        const rs: RunStatus = await pr.json();
        setRunStatus(prev => ({ ...prev, [claim.id]: rs }));
        if (!stopped && rs.status !== "succeeded" && rs.status !== "failed") {
          setTimeout(poll, 800);
        }
      }
      poll();
      return () => { stopped = true; };
    } finally {
      setBusy(false);
    }
  }

  // per-run polling handled in runRepro

  return (
    <main>
      <section style={{marginBottom: 24}}>
        <h2>Claim Intake</h2>
        <div style={{display:'flex', gap:12, flexWrap:'wrap', marginBottom:12}}>
          {PRESETS.map(p => (
            <button key={p.label} onClick={() => setRaw(p.text)} style={{background:'#11161C', color:'#E6EDF3', border:'1px solid #223', borderRadius:6, padding:'8px 12px'}}>
              {p.label}
            </button>
          ))}
          <Link href="/demo" style={{marginLeft:'auto', color:'#26D07C'}}>Open Demo Receipts →</Link>
        </div>
        <textarea value={raw} onChange={e=>setRaw(e.target.value)} rows={4} style={{width:'100%', background:'#11161C', color:'#E6EDF3', border:'1px solid #223', borderRadius:6, padding:12}} placeholder="Paste a claim or choose a preset above" />
        <div style={{marginTop:12, display:'flex', gap:12}}>
          <button onClick={submitClaim} disabled={busy || !raw} style={{background:'#26D07C', color:'#0B0F14', border:'none', borderRadius:6, padding:'8px 12px', opacity: busy || !raw ? 0.6 : 1}}>Submit Claim</button>
        </div>
      </section>

      {claims.length > 0 && (
        <section style={{border:'1px solid #223', borderRadius:8, padding:16, marginBottom:24}}>
          <h3 style={{marginTop:0}}>Parsed Claims</h3>
          <ul style={{listStyle:'none', padding:0}}>
            {claims.map(c => (
              <li key={c.id} style={{border:'1px solid #223', borderRadius:8, padding:12, margin:'8px 0'}}>
                <div style={{display:'flex', justifyContent:'space-between', alignItems:'center', gap:12}}>
                  <div>
                    <div style={{fontWeight:600}}>{c.domain} / {c.task} — {c.metric}</div>
                    <div style={{opacity:0.8, fontSize:13}}>ref {c.reference_score ?? '—'} | id: {c.id}</div>
                  </div>
                  <button onClick={() => runRepro(c)} disabled={!canRun(c.id) || busy} style={{background:'#F5C451', color:'#0B0F14', border:'none', borderRadius:6, padding:'6px 10px', opacity: !canRun(c.id) || busy ? 0.6 : 1}}>Run</button>
                </div>
                {runStatus[c.id] && (
                  <div style={{marginTop:8, borderTop:'1px solid #223', paddingTop:8}}>
                    <div>Status: <strong>{runStatus[c.id]!.status}</strong></div>
                    {runStatus[c.id]!.scores && (
                      <div>Score: {runStatus[c.id]!.scores!.metric} = {runStatus[c.id]!.scores!.value}</div>
                    )}
                    {runStatus[c.id]!.ci && (
                      <div>95% CI: [{runStatus[c.id]!.ci!.lower.toFixed(2)}, {runStatus[c.id]!.ci!.upper.toFixed(2)}]</div>
                    )}
                    {runStatus[c.id]!.ops && (
                      <div style={{marginTop:4, fontSize:13, opacity:0.9}}>Ops: p95={runStatus[c.id]!.ops!.p95_latency_s ?? '—'}s, $={runStatus[c.id]!.ops!.cost_usd ?? '—'}</div>
                    )}
                    {runStatus[c.id]!.artifacts && runStatus[c.id]!.artifacts!.length > 0 && (
                      <div style={{marginTop:4, fontSize:13}}>
                        Artifacts: {runStatus[c.id]!.artifacts!.map(a => (
                          <a key={a.url} href={a.url} style={{color:'#26D07C', marginRight:8}}>{a.name}</a>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}
