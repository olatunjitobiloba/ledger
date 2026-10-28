// Response shapes of the Ledger API (ledger_api/main.py).

export type CreatedProject = {
  project_id: string
  api_key: string
  retention_days: number
}

export type CreatedApiKey = {
  api_key: string
  project_id: string
}

export type Accepted = { accepted: true; job_id?: string; eval_run_id?: string }

export type Trace = {
  trace_id: string
  status: string
  model: string | null
  cost_actual: number
  cost_estimated: number
  risk_score: number
}

export type TracePage = { items: Trace[]; offset: number; limit: number }

export type WorstCase = {
  index: number
  score: number
  reasoning: string
  flags: string[]
}

export type EvalRunStatus = "queued" | "running" | "completed" | "failed"

export type EvalRun = {
  eval_run_id: string
  dataset_version: string
  config_id: string
  baseline_score: number
  variance: number
  result_score: number | null
  passed: boolean | null
  status: EvalRunStatus
  worst_cases: WorstCase[]
}

export type Alert = {
  alert_id: string
  eval_run_id: string
  kind: string
  message: string
}

export type Items<T> = { items: T[] }
