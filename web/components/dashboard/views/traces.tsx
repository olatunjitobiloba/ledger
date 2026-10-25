"use client"

import { useState } from "react"
import { ChevronLeftIcon, ChevronRightIcon, QueueListIcon } from "@heroicons/react/24/outline"
import { cn } from "cn"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  CopyButton,
  EmptyState,
  ErrorNotice,
  PageHeader,
  Panel,
  StatusDot,
} from "@/components/dashboard/primitives"
import { SendTestTrace } from "@/components/dashboard/send-test-trace"
import { formatCost, shortId } from "@/lib/format"
import { useTraces } from "@/lib/ledger/hooks"

const PAGE_SIZE = 25

function TraceStatus({ status }: { status: string }) {
  const tone = status === "ok" ? "good" : status === "error" ? "bad" : "neutral"
  return <StatusDot tone={tone}>{status}</StatusDot>
}

function Risk({ score }: { score: number }) {
  return (
    <span
      className={cn(
        "font-mono tabular-nums",
        score === 0 ? "text-muted-foreground" : score >= 0.7 ? "text-destructive" : "text-[#e48338]"
      )}
    >
      {score.toFixed(2)}
    </span>
  )
}

export function TracesView() {
  const [page, setPage] = useState(0)
  const { data, error, isLoading, isValidating } = useTraces(PAGE_SIZE, page * PAGE_SIZE)
  const items = data?.items ?? []
  // The API returns no total, so a short page is the only sign of the end.
  const hasNext = items.length === PAGE_SIZE

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Traces"
        description="Every trace ingested for this project, newest first, with its cost and highest injection-risk score."
        actions={<SendTestTrace />}
      />

      {error && <ErrorNotice error={error} />}

      <Panel>
        {isLoading ? (
          <div className="space-y-3 p-5">
            {Array.from({ length: 6 }, (_, i) => (
              <Skeleton key={i} className="h-8 w-full" />
            ))}
          </div>
        ) : items.length === 0 && page === 0 ? (
          <EmptyState icon={QueueListIcon} title="No traces yet">
            Instrument your app with the Ledger SDK, or send a test trace to see
            how ingestion works. Traces appear a few seconds after they&apos;re queued.
          </EmptyState>
        ) : (
          <Table className={cn("transition-opacity duration-150", isValidating && "opacity-70")}>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead className="pl-5">Trace</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Model</TableHead>
                <TableHead className="text-right">Actual cost</TableHead>
                <TableHead className="text-right">Estimated</TableHead>
                <TableHead className="pr-5 text-right">Risk</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((trace) => (
                <TableRow key={trace.trace_id}>
                  <TableCell className="pl-5">
                    <span className="flex items-center gap-1">
                      <code className="font-mono text-[0.8125rem]" title={trace.trace_id}>
                        {shortId(trace.trace_id)}
                      </code>
                      <CopyButton value={trace.trace_id} label="Copy trace ID" />
                    </span>
                  </TableCell>
                  <TableCell>
                    <TraceStatus status={trace.status} />
                  </TableCell>
                  <TableCell className="text-muted-foreground">{trace.model ?? "—"}</TableCell>
                  <TableCell className="text-right font-mono tabular-nums">
                    {formatCost(trace.cost_actual)}
                  </TableCell>
                  <TableCell className="text-right font-mono text-muted-foreground tabular-nums">
                    {formatCost(trace.cost_estimated)}
                  </TableCell>
                  <TableCell className="pr-5 text-right">
                    <Risk score={trace.risk_score} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}

        {(page > 0 || hasNext) && (
          <div className="flex items-center justify-between border-t px-5 py-3">
            <span className="text-xs text-muted-foreground">Page {page + 1}</span>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={page === 0}
                onClick={() => setPage((p) => p - 1)}
              >
                <ChevronLeftIcon />
                Newer
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={!hasNext}
                onClick={() => setPage((p) => p + 1)}
              >
                Older
                <ChevronRightIcon />
              </Button>
            </div>
          </div>
        )}
      </Panel>
    </div>
  )
}
