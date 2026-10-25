"use client"

import Link from "next/link"
import { ArrowRightIcon, BeakerIcon, BellIcon } from "@heroicons/react/24/outline"
import { cn } from "cn"
import { buttonVariants } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { CostChart, ScoreChart, scoredRuns } from "@/components/dashboard/charts"
import {
  ErrorNotice,
  EvalResult,
  PageHeader,
  Panel,
  gateOf,
} from "@/components/dashboard/primitives"
import { SendTestTrace } from "@/components/dashboard/send-test-trace"
import { formatCost, formatPercent, formatScore } from "@/lib/format"
import { MAX_TRACE_PAGE, useAlerts, useEvalRuns, useTraces } from "@/lib/ledger/hooks"
import type { Alert, EvalRun, Trace } from "@/lib/ledger/types"

type Stat = { label: string; value: string | null; detail: string | null }

function stats(traces: Trace[] | undefined, runs: EvalRun[] | undefined, alerts: Alert[] | undefined): Stat[] {
  const t = traces ?? []
  const actual = t.reduce((sum, x) => sum + x.cost_actual, 0)
  const estimated = t.reduce((sum, x) => sum + x.cost_estimated, 0)
  const flagged = t.filter((x) => x.risk_score > 0)
  const models = new Set(t.map((x) => x.model).filter(Boolean)).size
  const scored = (runs ?? []).filter((r) => r.status === "completed")
  const passed = scored.filter((r) => r.passed).length
  const has = t.length > 0

  return [
    {
      label: "Traces",
      value: traces ? String(t.length) : null,
      detail: has ? `${models} ${models === 1 ? "model" : "models"}` : null,
    },
    {
      label: "Actual cost",
      value: has ? formatCost(actual) : null,
      detail: has ? `${formatCost(actual / t.length)} / trace` : null,
    },
    {
      label: "Estimated cost",
      value: has ? formatCost(estimated) : null,
      detail: has ? "at list prices" : null,
    },
    {
      label: "Injection risk",
      value: has ? String(flagged.length) : null,
      detail: has
        ? flagged.length
          ? `max score ${Math.max(...flagged.map((x) => x.risk_score)).toFixed(2)}`
          : "no traces flagged"
        : null,
    },
    {
      label: "Eval pass rate",
      value: scored.length ? formatPercent(passed, scored.length) : null,
      detail: scored.length ? `${passed} of ${scored.length} runs` : null,
    },
    {
      label: "Alerts",
      value: alerts ? String(alerts.length) : null,
      detail: alerts?.length ? "regressions below gate" : null,
    },
  ]
}

function StatStrip({ items, loading }: { items: Stat[]; loading: boolean }) {
  return (
    <div className="grid grid-cols-2 gap-px bg-border sm:grid-cols-3 xl:grid-cols-6">
      {items.map((stat) => (
        <div key={stat.label} className="bg-muted px-5 py-4">
          <p className="text-[0.8125rem] text-muted-foreground">{stat.label}</p>
          {loading ? (
            <Skeleton className="mt-2 h-6 w-16" />
          ) : (
            <p className="mt-1.5 text-lg font-semibold tabular-nums">
              {stat.value ?? <span className="text-muted-foreground/60">—</span>}
            </p>
          )}
          <p className="mt-1 truncate text-xs text-muted-foreground">
            {stat.detail ?? <span className="text-muted-foreground/60">—</span>}
          </p>
        </div>
      ))}
    </div>
  )
}

function LegendItem({ dashed, label, value }: { dashed?: boolean; label: string; value: string }) {
  return (
    <span className="flex items-center gap-2">
      <span
        className={cn(
          "w-3.5 border-t-2",
          dashed ? "border-dashed border-muted-foreground" : "border-foreground"
        )}
      />
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium tabular-nums">{value}</span>
    </span>
  )
}

function ScoreSection({ runs }: { runs: EvalRun[] | undefined }) {
  const data = scoredRuns(runs ?? [])
  const latestRun = runs?.find((r) => r.status === "completed")
  const latest = data.at(-1)

  return (
    <div className="px-5 pt-5 pb-4 sm:px-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm text-muted-foreground">Evaluation score</p>
          <div className="mt-1 flex items-baseline gap-3">
            <span className="text-4xl font-semibold tracking-tight tabular-nums">
              {latest ? formatScore(latest.score) : "—"}
            </span>
            {latestRun ? (
              <span className="flex items-center gap-3 text-sm text-muted-foreground">
                <span>latest of {data.length} {data.length === 1 ? "run" : "runs"}</span>
                <EvalResult run={latestRun} />
              </span>
            ) : (
              <span className="text-sm text-muted-foreground">no scored runs</span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-5 text-xs">
          <LegendItem label="Score" value={latest ? formatScore(latest.score) : "—"} />
          <LegendItem dashed label="Gate" value={latestRun ? formatScore(gateOf(latestRun)) : "—"} />
        </div>
      </div>

      <div className="relative mt-6">
        {data.length > 0 ? (
          <ScoreChart data={data} />
        ) : (
          <div className="flex h-72 flex-col items-center justify-center gap-4 rounded-xl border border-dashed text-center">
            <BeakerIcon className="size-5 text-muted-foreground" />
            <p className="max-w-xs text-sm text-pretty text-muted-foreground">
              {runs?.some((r) => r.status === "queued" || r.status === "running")
                ? "Your first evaluation is being judged. Scores appear here when it completes."
                : "Score a golden set against a baseline to see each run plotted against its gate."}
            </p>
            <Link href="/dashboard/evaluations" className={buttonVariants({ variant: "outline", size: "sm" })}>
              Run an evaluation
            </Link>
          </div>
        )}
      </div>
    </div>
  )
}

function SectionHeader({ title, href, linkLabel }: { title: string; href: string; linkLabel: string }) {
  return (
    <div className="flex items-center justify-between px-5 pt-4 sm:px-6">
      <h2 className="text-sm font-medium">{title}</h2>
      <Link
        href={href}
        className="group flex items-center gap-1 text-xs text-muted-foreground transition-colors duration-150 hover:text-foreground"
      >
        {linkLabel}
        <ArrowRightIcon className="size-3 transition-transform duration-150 ease-out group-hover:translate-x-0.5" />
      </Link>
    </div>
  )
}

export function OverviewView() {
  const traces = useTraces(MAX_TRACE_PAGE)
  const runs = useEvalRuns()
  const alerts = useAlerts()
  const items = traces.data?.items
  const error = traces.error ?? runs.error ?? alerts.error

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Overview"
        description={
          items?.length === MAX_TRACE_PAGE
            ? `Across your latest ${MAX_TRACE_PAGE} traces and every evaluation run`
            : "Across your traces and evaluation runs"
        }
        actions={<SendTestTrace />}
      />

      {error && <ErrorNotice error={error} />}

      <Panel>
        <StatStrip
          items={stats(items, runs.data?.items, alerts.data?.items)}
          loading={traces.isLoading || runs.isLoading || alerts.isLoading}
        />
        <div className="border-t">
          <ScoreSection runs={runs.data?.items} />
        </div>
      </Panel>

      <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <Panel>
          <SectionHeader title="Cost per trace" href="/dashboard/traces" linkLabel="All traces" />
          <div className="px-5 pt-4 pb-5 sm:px-6">
            {items?.length ? (
              <CostChart traces={items} />
            ) : (
              <div className="flex h-48 flex-col items-center justify-center gap-4 rounded-xl border border-dashed px-6 text-center">
                <p className="max-w-xs text-sm text-pretty text-muted-foreground">
                  No traces yet. Send one from the SDK, or try a test trace.
                </p>
                <SendTestTrace />
              </div>
            )}
          </div>
        </Panel>

        <Panel>
          <SectionHeader title="Alerts" href="/dashboard/alerts" linkLabel="View all" />
          <div className="px-2 pt-2 pb-3 sm:px-3">
            {alerts.data?.items.length ? (
              <ul>
                {alerts.data.items.slice(0, 4).map((alert) => (
                  <li key={alert.alert_id} className="flex gap-3 rounded-lg px-3 py-2.5">
                    <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-destructive" />
                    <p className="text-sm leading-relaxed text-pretty">{alert.message}</p>
                  </li>
                ))}
              </ul>
            ) : (
              <div className="flex h-48 flex-col items-center justify-center gap-3 px-6 text-center">
                <BellIcon className="size-5 text-muted-foreground" />
                <p className="max-w-xs text-sm text-pretty text-muted-foreground">
                  No regressions. An alert is raised when a run scores below its gate.
                </p>
              </div>
            )}
          </div>
        </Panel>
      </div>
    </div>
  )
}
