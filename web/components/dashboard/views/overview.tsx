"use client"

import type { ReactNode } from "react"
import Link from "next/link"
import { HugeiconsIcon } from "@hugeicons/react"
import {
  Activity01Icon,
  ArrowRight01Icon,
  CheckmarkCircle02Icon,
  Coins01Icon,
  CpuIcon,
  Notification03Icon,
  Shield01Icon,
  TestTube01Icon,
} from "@hugeicons/core-free-icons"
import { cn } from "cn"
import { buttonVariants } from "@/components/ui/button"
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { CostChart, ScoreChart, scoredRuns } from "@/components/dashboard/charts"
import {
  EmptyState,
  ErrorNotice,
  EvalResult,
  PageHeader,
  gateOf,
  type Icon,
} from "@/components/dashboard/primitives"
import { SendTestTrace } from "@/components/dashboard/send-test-trace"
import { formatCost, formatPercent, formatScore } from "@/lib/format"
import { MAX_TRACE_PAGE, useAlerts, useEvalRuns, useTraces } from "@/lib/ledger/hooks"
import type { EvalRun, Trace } from "@/lib/ledger/types"

const costOf = (trace: Trace) => trace.cost_actual || trace.cost_estimated

function StatCard({
  icon,
  label,
  value,
  detail,
  loading,
}: {
  icon: Icon
  label: string
  value: ReactNode
  detail: ReactNode
  loading: boolean
}) {
  return (
    <Card size="sm" className="gap-3 px-4 py-4">
      <div className="flex items-center justify-between text-muted-foreground">
        <span className="text-[0.8125rem]">{label}</span>
        <HugeiconsIcon icon={icon} className="size-4" />
      </div>
      {loading ? (
        <div className="flex flex-col gap-2">
          <Skeleton className="h-7 w-20" />
          <Skeleton className="h-3.5 w-28" />
        </div>
      ) : (
        <div>
          <p className="text-2xl font-semibold tracking-tight tabular-nums">{value}</p>
          <p className="mt-1 truncate text-xs text-muted-foreground">{detail}</p>
        </div>
      )}
    </Card>
  )
}

function Stats({ traces, runs, loading }: { traces: Trace[]; runs: EvalRun[]; loading: boolean }) {
  const actual = traces.reduce((sum, t) => sum + t.cost_actual, 0)
  const estimated = traces.reduce((sum, t) => sum + t.cost_estimated, 0)
  const flagged = traces.filter((t) => t.risk_score > 0)
  const models = new Set(traces.map((t) => t.model).filter(Boolean)).size
  const scored = runs.filter((r) => r.status === "completed")
  const passed = scored.filter((r) => r.passed).length
  const none = <span className="text-muted-foreground/60">—</span>

  return (
    <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
      <StatCard
        icon={Activity01Icon}
        label="Traces"
        loading={loading}
        value={traces.length === MAX_TRACE_PAGE ? `${MAX_TRACE_PAGE}+` : traces.length}
        detail={traces.length ? `${models} ${models === 1 ? "model" : "models"}` : "None recorded yet"}
      />
      <StatCard
        icon={Coins01Icon}
        label="Spend"
        loading={loading}
        value={traces.length ? formatCost(actual) : none}
        detail={traces.length ? `${formatCost(estimated)} at list prices` : "No cost recorded"}
      />
      <StatCard
        icon={CheckmarkCircle02Icon}
        label="Eval pass rate"
        loading={loading}
        value={scored.length ? formatPercent(passed, scored.length) : none}
        detail={scored.length ? `${passed} of ${scored.length} runs passed` : "No scored runs"}
      />
      <StatCard
        icon={Shield01Icon}
        label="Injection risk"
        loading={loading}
        value={traces.length ? flagged.length : none}
        detail={
          flagged.length
            ? `Peak score ${Math.max(...flagged.map((t) => t.risk_score)).toFixed(2)}`
            : traces.length
              ? "No traces flagged"
              : "Nothing to scan yet"
        }
      />
    </div>
  )
}

function LegendItem({ dashed, label, value }: { dashed?: boolean; label: string; value: string }) {
  return (
    <span className="flex items-center gap-2">
      <span className={cn("w-3.5 border-t-2", dashed ? "border-dashed border-muted-foreground" : "border-brand")} />
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium tabular-nums">{value}</span>
    </span>
  )
}

function ScoreCard({ runs, loading }: { runs: EvalRun[]; loading: boolean }) {
  const data = scoredRuns(runs)
  const latestRun = runs.find((r) => r.status === "completed")
  const latest = data.at(-1)
  const judging = runs.some((r) => r.status === "queued" || r.status === "running")

  return (
    <Card className="lg:col-span-2">
      <CardHeader>
        <CardDescription>Evaluation score</CardDescription>
        <CardTitle className="flex flex-wrap items-center gap-3">
          <span className="text-3xl font-semibold tracking-tight tabular-nums">
            {latest ? formatScore(latest.score) : "—"}
          </span>
          {latestRun && <EvalResult run={latestRun} />}
        </CardTitle>
        <CardAction className="hidden items-center gap-4 pt-1 text-xs sm:flex">
          <LegendItem label="Score" value={latest ? formatScore(latest.score) : "—"} />
          <LegendItem dashed label="Gate" value={latestRun ? formatScore(gateOf(latestRun)) : "—"} />
        </CardAction>
      </CardHeader>
      <CardContent className="flex-1">
        {loading ? (
          <Skeleton className="h-64 w-full rounded-xl" />
        ) : data.length > 0 ? (
          <ScoreChart data={data} />
        ) : (
          <EmptyState
            icon={TestTube01Icon}
            title={judging ? "Judging your first run" : "No scored runs yet"}
            className="h-64 border"
            action={
              !judging && (
                <Link href="/dashboard/evaluations" className={buttonVariants({ variant: "outline", size: "sm" })}>
                  Run an evaluation
                </Link>
              )
            }
          >
            {judging
              ? "Scores appear here as soon as the judge finishes."
              : "Score a golden set against a baseline to see each run plotted against its gate."}
          </EmptyState>
        )}
      </CardContent>
    </Card>
  )
}

function SpendByModel({ traces, loading }: { traces: Trace[]; loading: boolean }) {
  const totals = new Map<string, number>()
  for (const trace of traces) {
    const model = trace.model ?? "Unknown"
    totals.set(model, (totals.get(model) ?? 0) + costOf(trace))
  }
  const rows = [...totals].sort((a, b) => b[1] - a[1]).slice(0, 5)
  const max = rows[0]?.[1] ?? 0

  return (
    <Card>
      <CardHeader>
        <CardTitle>Spend by model</CardTitle>
        <CardDescription>Across recent traces</CardDescription>
      </CardHeader>
      <CardContent className="flex-1">
        {loading ? (
          <div className="flex flex-col gap-4">
            {Array.from({ length: 3 }, (_, i) => (
              <Skeleton key={i} className="h-9 w-full" />
            ))}
          </div>
        ) : rows.length === 0 ? (
          <EmptyState icon={CpuIcon} title="No models yet" className="h-full min-h-56 border">
            Costs per model appear once traces arrive.
          </EmptyState>
        ) : (
          <ul className="flex flex-col gap-4">
            {rows.map(([model, cost]) => (
              <li key={model}>
                <div className="flex items-baseline justify-between gap-3 text-sm">
                  <span className="truncate">{model}</span>
                  <span className="font-mono text-[0.8125rem] text-muted-foreground tabular-nums">
                    {formatCost(cost)}
                  </span>
                </div>
                <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-muted">
                  <div
                    className="h-full origin-left rounded-full bg-brand/80 transition-transform duration-500 ease-out-strong"
                    style={{ transform: `scaleX(${max ? Math.max(cost / max, 0.02) : 0})` }}
                  />
                </div>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}

function ViewAll({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Link
      href={href}
      className="group flex items-center gap-1 text-xs text-muted-foreground transition-colors duration-150 hover:text-foreground"
    >
      {children}
      <HugeiconsIcon
        icon={ArrowRight01Icon}
        className="size-3.5 transition-transform duration-150 ease-out group-hover:translate-x-0.5"
      />
    </Link>
  )
}

export function OverviewView() {
  const traces = useTraces(MAX_TRACE_PAGE)
  const runs = useEvalRuns()
  const alerts = useAlerts()
  const items = traces.data?.items ?? []
  const runItems = runs.data?.items ?? []
  const alertItems = alerts.data?.items ?? []
  const error = traces.error ?? runs.error ?? alerts.error
  const loading = traces.isLoading || runs.isLoading

  return (
    <div className="stagger flex flex-col gap-6">
      <PageHeader
        title="Overview"
        description={
          items.length === MAX_TRACE_PAGE
            ? `Your latest ${MAX_TRACE_PAGE} traces and every evaluation run.`
            : "Cost, risk and quality across your traces and evaluation runs."
        }
        actions={<SendTestTrace />}
      />

      {error && (
        <ErrorNotice
          title="Couldn't load this project"
          error={error}
          onRetry={() => {
            traces.mutate()
            runs.mutate()
            alerts.mutate()
          }}
        />
      )}

      <Stats traces={items} runs={runItems} loading={loading} />

      <div className="grid gap-4 lg:grid-cols-3">
        <ScoreCard runs={runItems} loading={runs.isLoading} />
        <SpendByModel traces={items} loading={traces.isLoading} />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Cost per trace</CardTitle>
            <CardDescription>Oldest to newest</CardDescription>
            <CardAction>
              <ViewAll href="/dashboard/traces">All traces</ViewAll>
            </CardAction>
          </CardHeader>
          <CardContent className="flex-1">
            {traces.isLoading ? (
              <Skeleton className="h-48 w-full rounded-xl" />
            ) : items.length ? (
              <CostChart traces={items} />
            ) : (
              <EmptyState
                icon={Activity01Icon}
                title="No traces yet"
                className="h-48 border"
                action={<SendTestTrace size="sm" />}
              >
                Send one from the SDK, or try a test trace.
              </EmptyState>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Recent alerts</CardTitle>
            <CardDescription>Runs that fell below their gate</CardDescription>
            <CardAction>
              <ViewAll href="/dashboard/alerts">View all</ViewAll>
            </CardAction>
          </CardHeader>
          <CardContent className="flex-1">
            {alerts.isLoading ? (
              <div className="flex flex-col gap-3">
                {Array.from({ length: 3 }, (_, i) => (
                  <Skeleton key={i} className="h-10 w-full" />
                ))}
              </div>
            ) : alertItems.length ? (
              <ul className="-mx-1 flex flex-col">
                {alertItems.slice(0, 4).map((alert) => (
                  <li key={alert.alert_id} className="flex gap-3 rounded-lg px-1 py-2.5">
                    <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-destructive" />
                    <p className="line-clamp-2 text-sm leading-relaxed text-pretty">{alert.message}</p>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState icon={Notification03Icon} title="All clear" className="h-48 border">
                No run has scored below its gate.
              </EmptyState>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
