"use client"

import { BellIcon } from "@heroicons/react/24/outline"
import { Skeleton } from "@/components/ui/skeleton"
import {
  CopyButton,
  EmptyState,
  ErrorNotice,
  PageHeader,
  Panel,
} from "@/components/dashboard/primitives"
import { shortId } from "@/lib/format"
import { useAlerts } from "@/lib/ledger/hooks"

export function AlertsView() {
  const { data, error, isLoading } = useAlerts()
  const alerts = data?.items ?? []

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Alerts"
        description="Raised when an evaluation run scores below its gate."
      />

      {error && <ErrorNotice error={error} />}

      <Panel>
        {isLoading ? (
          <div className="space-y-3 p-5">
            {Array.from({ length: 3 }, (_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        ) : alerts.length === 0 ? (
          <EmptyState icon={BellIcon} title="No alerts">
            Every evaluation run so far has stayed at or above its gate.
          </EmptyState>
        ) : (
          <ul className="divide-y">
            {alerts.map((alert) => (
              <li key={alert.alert_id} className="flex gap-4 px-5 py-4">
                <span className="mt-2 size-1.5 shrink-0 rounded-full bg-destructive" />
                <div className="min-w-0 flex-1">
                  <p className="text-sm leading-relaxed text-pretty">{alert.message}</p>
                  <p className="mt-1.5 flex items-center gap-1 text-xs text-muted-foreground">
                    <span className="capitalize">{alert.kind}</span>
                    <span aria-hidden="true">·</span>
                    run <code className="font-mono">{shortId(alert.eval_run_id)}</code>
                    <CopyButton value={alert.eval_run_id} label="Copy run ID" />
                  </p>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  )
}
