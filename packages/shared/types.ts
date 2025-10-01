export type Status = "Replicated" | "Setting Drift" | "Underspecified" | "Not Reproduced";

export interface Settings {
  prompt_template: string; shots: number; temperature: number; top_p: number;
  max_tokens: number; k: number; seed: number; tools: string[];
  timeout_s: number; cot?: boolean; environment_sha?: string; dataset_variant?: string;
}

export interface Claim {
  id: string; model: string; domain: string; task: string; metric: string;
  settings: Settings; reference_score: number; source_url?: string;
  confidence: number; created_at: string;
}

export interface ModelConfig { provider: "openai"|"anthropic"|"openrouter"|"vllm"; name: string; api_key_ref: string; }

export interface RunSummary {
  run_id: string; status: "queued"|"running"|"succeeded"|"failed"; score_value: number;
  ci_lower: number; ci_upper: number; status_label: Status; created_at: string;
}
