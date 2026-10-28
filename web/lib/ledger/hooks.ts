"use client"

import { createContext, useContext } from "react"
import useSWR, { useSWRConfig } from "swr"
import { ledger } from "@/lib/ledger/api"
import type { StoredProject } from "@/lib/ledger/projects"
import type { EvalRun, Items } from "@/lib/ledger/types"

export const ProjectContext = createContext<StoredProject | null>(null)

/** The selected project. Only rendered below the shell's project gate. */
export function useActiveProject(): StoredProject {
  const project = useContext(ProjectContext)
  if (!project) throw new Error("useActiveProject must be used inside the dashboard shell")
  return project
}

/** The API's maximum page size, and how many traces the overview summarizes. */
export const MAX_TRACE_PAGE = 100

export function useTraces(limit: number, offset = 0) {
  const { id, apiKey } = useActiveProject()
  return useSWR(
    ["traces", id, apiKey, limit, offset],
    () => ledger.traces(apiKey, id, limit, offset),
    { keepPreviousData: true }
  )
}

const pending = (data?: Items<EvalRun>) =>
  data?.items.some((run) => run.status === "queued" || run.status === "running") ?? false

export function useEvalRuns() {
  const { id, apiKey } = useActiveProject()
  const { mutate } = useSWRConfig()
  return useSWR(["eval-runs", id, apiKey], () => ledger.evalRuns(apiKey, id), {
    // Runs are judged by the worker; poll until every queued run settles.
    refreshInterval: (data) => (pending(data) ? 2000 : 0),
    // A run that settles below its gate raises an alert.
    onSuccess: (data) => {
      if (!pending(data)) mutate(["alerts", id, apiKey])
    },
  })
}

export function useAlerts() {
  const { id, apiKey } = useActiveProject()
  return useSWR(["alerts", id, apiKey], () => ledger.alerts(apiKey, id))
}

export function useHealth() {
  return useSWR("health", ledger.health, {
    refreshInterval: 30_000,
    shouldRetryOnError: false,
  })
}

/** Revalidate every cached query of one kind ("traces", "eval-runs", "alerts"). */
export function useRevalidate() {
  const { mutate } = useSWRConfig()
  return (...kinds: string[]) =>
    mutate((key) => Array.isArray(key) && kinds.includes(key[0]))
}
