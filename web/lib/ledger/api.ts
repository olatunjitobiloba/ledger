import type {
  Accepted,
  Alert,
  CreatedApiKey,
  CreatedProject,
  EvalRun,
  Items,
  TracePage,
} from "@/lib/ledger/types"

/** Same-origin proxy to the Ledger API, see the rewrite in next.config.ts. */
export const API_BASE = "/api/ledger"

export class LedgerError extends Error {
  constructor(
    message: string,
    readonly status: number
  ) {
    super(message)
    this.name = "LedgerError"
  }
}

type RequestOptions = {
  apiKey?: string
  adminToken?: string
  method?: "GET" | "POST"
  body?: unknown
}

// FastAPI returns `detail` as a string, or a list of validation errors.
function describe(detail: unknown): string | null {
  if (typeof detail === "string") return detail
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        const field = Array.isArray(item?.loc) ? item.loc.at(-1) : null
        return field ? `${field}: ${item.msg}` : String(item?.msg ?? "")
      })
      .filter(Boolean)
      .join("; ")
  }
  return null
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = {}
  if (options.apiKey) headers["X-API-Key"] = options.apiKey
  if (options.adminToken) headers["X-Admin-Token"] = options.adminToken
  if (options.body !== undefined) headers["Content-Type"] = "application/json"

  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method: options.method ?? "GET",
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      cache: "no-store",
    })
  } catch {
    throw new LedgerError("Can't reach the Ledger API.", 0)
  }

  const data = await response.json().catch(() => null)
  if (!response.ok) {
    // A 5xx without a JSON detail is either an unhandled API error or the
    // proxy failing to reach the API at all.
    const message =
      describe(data?.detail) ??
      (response.status >= 500
        ? `The Ledger API failed (${response.status}). Check that it is running.`
        : `Request failed (${response.status}).`)
    throw new LedgerError(message, response.status)
  }
  return data as T
}

export const ledger = {
  health: () => request<{ status: string }>("/health"),

  createProject: (
    body: {
      name: string
      capture_prompt: boolean
      redact_patterns: string[]
      retention_days: number
    },
    adminToken?: string
  ) => request<CreatedProject>("/v1/projects", { method: "POST", body, adminToken }),

  createApiKey: (apiKey: string, name: string) =>
    request<CreatedApiKey>("/v1/api-keys", { method: "POST", apiKey, body: { name } }),

  ingest: (apiKey: string, body: unknown) =>
    request<Accepted>("/v1/ingest", { method: "POST", apiKey, body }),

  traces: (apiKey: string, projectId: string, limit: number, offset: number) =>
    request<TracePage>(
      `/v1/traces/${encodeURIComponent(projectId)}?limit=${limit}&offset=${offset}`,
      { apiKey }
    ),

  runEval: (
    apiKey: string,
    body: {
      dataset_version: string
      config_id: string
      baseline_score: number
      variance: number
      cases: { prompt: string; response: string }[]
    }
  ) => request<Accepted>("/v1/eval/run", { method: "POST", apiKey, body }),

  evalRuns: (apiKey: string, projectId: string) =>
    request<Items<EvalRun>>(`/v1/eval/runs/${encodeURIComponent(projectId)}`, { apiKey }),

  alerts: (apiKey: string, projectId: string) =>
    request<Items<Alert>>(`/v1/alerts/${encodeURIComponent(projectId)}`, { apiKey }),
}
