"use client";

import { useEffect, useState } from "react";

interface RunSummary {
  run_id: string;
  status: string;
  score_value?: number;
  ci_lower?: number;
  ci_upper?: number;
  status_label?: string;
  created_at?: string;
}

interface Claim {
  id: string; model: string; domain: string; task: string; metric: string;
  reference_score?: number; confidence: number; source_url?: string;
}

export default function DemoPage() {
  const [claims, setClaims] = useState<Claim[]>([]);
  useEffect(() => {
    fetch("/demo/seed_claims.json").then(r => r.json()).then(setClaims).catch(()=>{});
  }, []);

  return (
    <main>
      <h2>Demo Receipts</h2>
      <p>Seeded examples for preview. These are illustrative only.</p>
      <ul style={{listStyle:'none', padding:0}}>
        {claims.map((c) => (
          <li key={c.id} style={{border:'1px solid #223', borderRadius:8, padding:16, margin:'12px 0'}}>
            <div style={{display:'flex', justifyContent:'space-between'}}>
              <strong>{c.model}</strong>
              <span style={{opacity:0.8}}>{c.domain} / {c.task} — {c.metric}</span>
            </div>
            <div style={{fontSize:14, opacity:0.9}}>
              Ref: {c.reference_score ?? "—"} | Confidence: {c.confidence}
            </div>
            <div>
              <a href={`/demo/runs/${c.id}.json`} style={{color:'#26D07C'}}>View receipt JSON</a>
            </div>
          </li>
        ))}
      </ul>
    </main>
  );
}
