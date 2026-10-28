import axios, { AxiosError, type InternalAxiosRequestConfig } from "axios"
import type {
  Accepted,
  Alert,
  CreatedApiKey,
  CreatedProject,
  EvalRun,
  Items,
  TracePage,
} from "@/lib/ledger/types"

const BACKEND_URL = (process.env.NEXT_PUBLIC_BACKEND_URL ?? "").trim().replace(/\/+$/, "")

export class LedgerError extends Error {
  constructor(
    message: string,
    readonly status: number
  ) {
    super(message)
    this.name = "LedgerError"
  }
}

export const http = axios.create({
  baseURL: BACKEND_URL,
  timeout: 20_000,
  headers: { Accept: "application/json" },
})

/*
 * A scaled-to-zero host answers with a 503 HTML "waking up" page until the
 * API is running. Those requests never reached the API, so retrying them is
 * safe, including POSTs.
 */
const WAKE_RETRIES = 12
const WAKE_DELAY_MS = 2_500

type RetryableConfig = InternalAxiosRequestConfig & { wakeAttempt?: number }

function isWaking(error: AxiosError) {
  const type = String(error.response?.headers?.["content-type"] ?? "")
  return error.response?.status === 503 && type.includes("text/html")
}

http.interceptors.response.use(undefined, async (error: AxiosError) => {
  const config = error.config as RetryableConfig | undefined
  if (config && isWaking(error) && (config.wakeAttempt ?? 0) < WAKE_RETRIES) {
    config.wakeAttempt = (config.wakeAttempt ?? 0) + 1
    await new Promise((resolve) => setTimeout(resolve, WAKE_DELAY_MS))
    return http.request(config)
  }
  if (!error.response && !isTimeout(error) && (await apiIsUp())) {
    // The API answered /health, so this request did reach it and failed
    // there. A server error sent without CORS headers looks like this.
    return Promise.reject(
      new LedgerError("The Ledger API ran into an error while handling this request.", 500)
    )
  }
  return Promise.reject(toLedgerError(error))
})

function isTimeout(error: AxiosError) {
  return error.code === AxiosError.ECONNABORTED || error.code === AxiosError.ETIMEDOUT
}

/** Plain axios, not `http`, so a failing probe can't re-enter the interceptor. */
async function apiIsUp() {
  try {
    const response = await axios.get(`${BACKEND_URL}/health`, { timeout: 5_000 })
    return response.data?.status === "ok"
  } catch {
    return false
  }
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

function toLedgerError(error: AxiosError): LedgerError {
  if (!error.response) {
    if (isTimeout(error)) {
      return new LedgerError("The Ledger API took too long to respond. Try again.", 0)
    }
    return new LedgerError("Can't reach the Ledger API. Check your connection and try again.", 0)
  }

  const { status, data } = error.response
  const detail = describe((data as { detail?: unknown } | null)?.detail)
  if (detail) return new LedgerError(detail, status)
  if (isWaking(error)) {
    return new LedgerError("The Ledger API is still starting up. Try again in a moment.", status)
  }
  if (status >= 500) {
    return new LedgerError("The Ledger API ran into a problem. Try again shortly.", status)
  }
  return new LedgerError(`Request failed (${status}).`, status)
}

type Auth = { apiKey?: string; adminToken?: string }

function headers({ apiKey, adminToken }: Auth = {}) {
  const result: Record<string, string> = {}
  if (apiKey) result["X-API-Key"] = apiKey
  if (adminToken) result["X-Admin-Token"] = adminToken
  return result
}

function ensureConfigured() {
  if (!BACKEND_URL) {
    // Developers see the variable name in the console; users never do.
    console.error("NEXT_PUBLIC_BACKEND_URL is not set. See web/env.sample.")
    throw new LedgerError("This dashboard isn't connected to a Ledger API yet.", 0)
  }
}

async function get<T>(path: string, auth?: Auth, params?: Record<string, unknown>) {
  ensureConfigured()
  const response = await http.get<T>(path, { headers: headers(auth), params })
  return response.data
}

async function post<T>(path: string, body: unknown, auth?: Auth) {
  ensureConfigured()
  const response = await http.post<T>(path, body, { headers: headers(auth) })
  return response.data
}

const segment = encodeURIComponent

export const ledger = {
  health: () => get<{ status: string }>("/health"),

  createProject: (
    body: {
      name: string
      capture_prompt: boolean
      redact_patterns: string[]
      retention_days: number
    },
    adminToken?: string
  ) => post<CreatedProject>("/v1/projects", body, { adminToken }),

  createApiKey: (apiKey: string, name: string) =>
    post<CreatedApiKey>("/v1/api-keys", { name }, { apiKey }),

  ingest: (apiKey: string, body: unknown) => post<Accepted>("/v1/ingest", body, { apiKey }),

  traces: (apiKey: string, projectId: string, limit: number, offset: number) =>
    get<TracePage>(`/v1/traces/${segment(projectId)}`, { apiKey }, { limit, offset }),

  runEval: (
    apiKey: string,
    body: {
      dataset_version: string
      config_id: string
      baseline_score: number
      variance: number
      cases: { prompt: string; response: string }[]
    }
  ) => post<Accepted>("/v1/eval/run", body, { apiKey }),

  evalRuns: (apiKey: string, projectId: string) =>
    get<Items<EvalRun>>(`/v1/eval/runs/${segment(projectId)}`, { apiKey }),

  alerts: (apiKey: string, projectId: string) =>
    get<Items<Alert>>(`/v1/alerts/${segment(projectId)}`, { apiKey }),
}
