"use client"

import { HugeiconsIcon } from "@hugeicons/react"
import { Alert02Icon, Notification03Icon } from "@hugeicons/core-free-icons"
import { Card } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import {
  EmptyState,
  ErrorNotice,
  PageHeader,
  StatusBadge,
  gateOf,
} from "@/components/dashboard/primitives"
import { formatScore } from "@/lib/format"
import { useAlerts, useEvalRuns } from "@/lib/ledger/hooks"

export function AlertsView() {
  const { data, error, isLoading, mutate } = useAlerts()
  const runs = useEvalRuns()
  const alerts = data?.items ?? []
  const runById = new Map(runs.data?.items.map((run) => [run.eval_run_id, run]))

  return (
    <div className="stagger flex flex-col gap-6">
      <PageHeader
        title="Alerts"
        description="Raised when an evaluation run scores below its gate."
      />

      {error && <ErrorNotice title="Couldn't load alerts" error={error} onRetry={() => mutate()} />}

      <Card className="gap-0 py-0">
        {isLoading ? (
          <div className="flex flex-col gap-3 p-5">
            {Array.from({ length: 3 }, (_, i) => (
              <Skeleton key={i} className="h-14 w-full" />
            ))}
          </div>
        ) : alerts.length === 0 ? (
          <EmptyState icon={Notification03Icon} title="All clear">
            Every evaluation run so far has stayed at or above its gate.
          </EmptyState>
        ) : (
          <ul className="divide-y">
            {alerts.map((alert) => {
              const run = runById.get(alert.eval_run_id)
              return (
                <li key={alert.alert_id} className="flex gap-4 px-5 py-4">
                  <span className="flex size-9 shrink-0 items-center justify-center rounded-lg border border-destructive/20 bg-destructive/10 text-destructive">
                    <HugeiconsIcon icon={Alert02Icon} className="size-4" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <StatusBadge tone="bad">
                        <span className="capitalize">{alert.kind}</span>
                      </StatusBadge>
                      {run && (
                        <span className="text-xs text-muted-foreground">
                          {run.config_id} · dataset {run.dataset_version}
                        </span>
                      )}
                    </div>
                    <p className="mt-2 text-sm leading-relaxed text-pretty">{alert.message}</p>
                  </div>
                  {run?.result_score != null && (
                    <div className="hidden shrink-0 text-right sm:block">
                      <p className="font-mono text-sm font-medium text-destructive tabular-nums">
                        {formatScore(run.result_score)}
                      </p>
                      <p className="mt-0.5 text-xs text-muted-foreground tabular-nums">
                        gate {formatScore(gateOf(run))}
                      </p>
                    </div>
                  )}
                </li>
              )
            })}
          </ul>
        )}
      </Card>
    </div>
  )
}
