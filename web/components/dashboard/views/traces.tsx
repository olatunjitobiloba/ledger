"use client"

import { useState } from "react"
import { HugeiconsIcon } from "@hugeicons/react"
import { Activity01Icon, ArrowLeft01Icon, ArrowRight01Icon } from "@hugeicons/core-free-icons"
import { cn } from "cn"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Separator } from "@/components/ui/separator"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
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
  DetailRow,
  EmptyState,
  ErrorNotice,
  PageHeader,
  StatusBadge,
  type Tone,
} from "@/components/dashboard/primitives"
import { SendTestTrace } from "@/components/dashboard/send-test-trace"
import { formatCost, shortId } from "@/lib/format"
import { useTraces } from "@/lib/ledger/hooks"
import type { Trace } from "@/lib/ledger/types"

const PAGE_SIZE = 25

function statusTone(status: string): Tone {
  return status === "ok" ? "good" : status === "error" ? "bad" : "neutral"
}

function riskLevel(score: number): { tone: Tone; label: string } {
  if (score >= 0.7) return { tone: "bad", label: "High" }
  if (score > 0) return { tone: "warn", label: "Elevated" }
  return { tone: "neutral", label: "None" }
}

function Risk({ score }: { score: number }) {
  return (
    <span
      className={cn(
        "font-mono tabular-nums",
        score === 0 ? "text-muted-foreground" : score >= 0.7 ? "text-destructive" : "text-amber-500"
      )}
    >
      {score.toFixed(2)}
    </span>
  )
}

function TraceSheet({ trace, onClose }: { trace: Trace | null; onClose: () => void }) {
  // Keep showing the last trace while the sheet animates out.
  const [shown, setShown] = useState<Trace | null>(trace)
  if (trace && trace !== shown) setShown(trace)
  const t = trace ?? shown
  const risk = t ? riskLevel(t.risk_score) : null
  const saved = t ? t.cost_estimated - t.cost_actual : 0

  return (
    <Sheet open={trace !== null} onOpenChange={(open) => !open && onClose()}>
      <SheetContent className="w-full gap-0 sm:max-w-md">
        {t && risk && (
          <>
            <SheetHeader className="border-b p-5">
              <SheetTitle className="flex items-center gap-2.5">
                Trace <code className="font-mono text-[0.9375rem]">{shortId(t.trace_id)}</code>
                <StatusBadge tone={statusTone(t.status)}>{t.status}</StatusBadge>
              </SheetTitle>
              <SheetDescription>{t.model ?? "Model not reported"}</SheetDescription>
            </SheetHeader>

            <div className="flex flex-col gap-6 overflow-y-auto p-5">
              <div className="grid grid-cols-2 gap-3">
                <Card size="sm" className="gap-1 px-3.5">
                  <span className="text-xs text-muted-foreground">Actual cost</span>
                  <span className="text-lg font-semibold tabular-nums">{formatCost(t.cost_actual)}</span>
                </Card>
                <Card size="sm" className="gap-1 px-3.5">
                  <span className="text-xs text-muted-foreground">At list prices</span>
                  <span className="text-lg font-semibold tabular-nums">{formatCost(t.cost_estimated)}</span>
                </Card>
              </div>

              <div>
                <div className="flex items-center justify-between text-sm">
                  <span className="font-medium">Injection risk</span>
                  <StatusBadge tone={risk.tone}>{risk.label}</StatusBadge>
                </div>
                <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-muted">
                  <div
                    className={cn(
                      "h-full origin-left rounded-full transition-transform duration-500 ease-out-strong",
                      risk.tone === "bad" ? "bg-destructive" : risk.tone === "warn" ? "bg-amber-500" : "bg-muted-foreground/40"
                    )}
                    style={{ transform: `scaleX(${Math.min(Math.max(t.risk_score, 0), 1)})` }}
                  />
                </div>
                <p className="mt-2 text-xs text-pretty text-muted-foreground">
                  Highest heuristic score across this trace&apos;s spans, from 0 to 1.
                  Flags are for review and never block requests.
                </p>
              </div>

              <Separator />

              <dl className="-my-3 divide-y">
                <DetailRow label="Trace ID">
                  <span className="flex items-center justify-end gap-1">
                    <code className="truncate font-mono text-[0.8125rem]">{shortId(t.trace_id)}…</code>
                    <CopyButton value={t.trace_id} label="Copy trace ID" />
                  </span>
                </DetailRow>
                <DetailRow label="Model">{t.model ?? "—"}</DetailRow>
                <DetailRow label="Risk score">
                  <Risk score={t.risk_score} />
                </DetailRow>
                <DetailRow label="Difference from list price">
                  <span className="font-mono tabular-nums">
                    {t.cost_actual === 0 ? "—" : `${saved >= 0 ? "−" : "+"}${formatCost(Math.abs(saved))}`}
                  </span>
                </DetailRow>
              </dl>
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  )
}

export function TracesView() {
  const [page, setPage] = useState(0)
  const [selected, setSelected] = useState<Trace | null>(null)
  const { data, error, isLoading, isValidating, mutate } = useTraces(PAGE_SIZE, page * PAGE_SIZE)
  const items = data?.items ?? []
  // The API returns no total, so a short page is the only sign of the end.
  const hasNext = items.length === PAGE_SIZE

  return (
    <div className="stagger flex flex-col gap-6">
      <PageHeader
        title="Traces"
        description="Every trace recorded for this project, newest first, with its cost and highest injection-risk score."
        actions={<SendTestTrace />}
      />

      {error && <ErrorNotice title="Couldn't load traces" error={error} onRetry={() => mutate()} />}

      <Card className="gap-0 py-0">
        {isLoading ? (
          <div className="flex flex-col gap-3 p-5">
            {Array.from({ length: 6 }, (_, i) => (
              <Skeleton key={i} className="h-8 w-full" />
            ))}
          </div>
        ) : items.length === 0 && page === 0 ? (
          <EmptyState icon={Activity01Icon} title="No traces yet" action={<SendTestTrace size="sm" />}>
            Instrument your app with the Ledger SDK, or send a test trace to see
            how it works. Traces appear a few seconds after they&apos;re sent.
          </EmptyState>
        ) : (
          <Table className={cn("transition-opacity duration-150", isValidating && "opacity-70")}>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead className="pl-5">Trace</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Model</TableHead>
                <TableHead className="text-right">Actual cost</TableHead>
                <TableHead className="hidden text-right sm:table-cell">At list prices</TableHead>
                <TableHead className="pr-5 text-right">Risk</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((trace) => (
                <TableRow
                  key={trace.trace_id}
                  tabIndex={0}
                  className="cursor-pointer outline-none focus-visible:bg-muted/60"
                  onClick={() => setSelected(trace)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault()
                      setSelected(trace)
                    }
                  }}
                >
                  <TableCell className="pl-5">
                    <code className="font-mono text-[0.8125rem]">{shortId(trace.trace_id)}</code>
                  </TableCell>
                  <TableCell>
                    <StatusBadge tone={statusTone(trace.status)}>{trace.status}</StatusBadge>
                  </TableCell>
                  <TableCell className="text-muted-foreground">{trace.model ?? "—"}</TableCell>
                  <TableCell className="text-right font-mono tabular-nums">
                    {formatCost(trace.cost_actual)}
                  </TableCell>
                  <TableCell className="hidden text-right font-mono text-muted-foreground tabular-nums sm:table-cell">
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
            <span className="text-xs text-muted-foreground tabular-nums">Page {page + 1}</span>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>
                <HugeiconsIcon icon={ArrowLeft01Icon} data-icon="inline-start" />
                Newer
              </Button>
              <Button variant="outline" size="sm" disabled={!hasNext} onClick={() => setPage((p) => p + 1)}>
                Older
                <HugeiconsIcon icon={ArrowRight01Icon} data-icon="inline-end" />
              </Button>
            </div>
          </div>
        )}
      </Card>

      <TraceSheet trace={selected} onClose={() => setSelected(null)} />
    </div>
  )
}
