"use client"

import { Bar, BarChart, CartesianGrid, Line, LineChart, XAxis, YAxis } from "recharts"
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart"
import { formatCost, formatScore, shortId } from "@/lib/format"
import type { EvalRun, Trace } from "@/lib/ledger/types"
import { gateOf } from "@/components/dashboard/primitives"

// Flat colors and straight segments only: no gradients, no smoothing.
const scoreConfig = {
  score: { label: "Score", color: "var(--foreground)" },
  gate: { label: "Gate", color: "var(--muted-foreground)" },
} satisfies ChartConfig

/** Completed runs, oldest first. The API lists them newest first, without dates. */
export function scoredRuns(runs: EvalRun[]) {
  return runs
    .filter((run) => run.status === "completed" && run.result_score != null)
    .reverse()
    .map((run, i) => ({
      label: `#${i + 1}`,
      config: run.config_id,
      score: run.result_score as number,
      gate: gateOf(run),
    }))
}

export function ScoreChart({ data }: { data: ReturnType<typeof scoredRuns> }) {
  return (
    <ChartContainer config={scoreConfig} className="aspect-auto h-72 w-full">
      <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
        <CartesianGrid vertical={false} strokeDasharray="3 3" />
        <XAxis dataKey="label" tickLine={false} axisLine={false} tickMargin={10} minTickGap={16} />
        <YAxis
          domain={[0, 100]}
          ticks={[0, 25, 50, 75, 100]}
          tickLine={false}
          axisLine={false}
          width={32}
        />
        <ChartTooltip
          cursor={false}
          content={
            <ChartTooltipContent
              indicator="line"
              labelFormatter={(_, payload) => {
                const point = payload?.[0]?.payload as { label: string; config: string }
                return `Run ${point?.label} · ${point?.config}`
              }}
              formatter={(value, name) => (
                <div className="flex w-full justify-between gap-4">
                  <span className="text-muted-foreground">
                    {scoreConfig[name as keyof typeof scoreConfig]?.label}
                  </span>
                  <span className="font-mono font-medium tabular-nums">
                    {formatScore(value as number)}
                  </span>
                </div>
              )}
            />
          }
        />
        <Line
          dataKey="gate"
          type="linear"
          stroke="var(--color-gate)"
          strokeWidth={1.5}
          strokeDasharray="4 4"
          dot={false}
          isAnimationActive={false}
        />
        <Line
          dataKey="score"
          type="linear"
          stroke="var(--color-score)"
          strokeWidth={2}
          dot={{ r: 3, fill: "var(--color-score)", strokeWidth: 0 }}
          activeDot={{ r: 4, strokeWidth: 0 }}
          isAnimationActive={false}
        />
      </LineChart>
    </ChartContainer>
  )
}

const costConfig = {
  cost: { label: "Cost", color: "var(--foreground)" },
} satisfies ChartConfig

/**
 * Cost of each trace, oldest to newest. Uses the provider-reported cost when
 * present, otherwise the list-price estimate.
 */
export function CostChart({ traces }: { traces: Trace[] }) {
  const data = [...traces].reverse().map((trace) => ({
    id: shortId(trace.trace_id),
    model: trace.model,
    cost: trace.cost_actual || trace.cost_estimated,
  }))

  return (
    <ChartContainer config={costConfig} className="aspect-auto h-48 w-full">
      <BarChart data={data} margin={{ top: 4, right: 0, bottom: 0, left: 0 }}>
        <CartesianGrid vertical={false} strokeDasharray="3 3" />
        <XAxis dataKey="id" hide />
        <ChartTooltip
          cursor={false}
          content={
            <ChartTooltipContent
              hideIndicator
              labelFormatter={(_, payload) => {
                const point = payload?.[0]?.payload as { id: string; model: string | null }
                return `${point?.id}${point?.model ? ` · ${point.model}` : ""}`
              }}
              formatter={(value) => (
                <span className="font-mono font-medium tabular-nums">
                  {formatCost(value as number)}
                </span>
              )}
            />
          }
        />
        <Bar
          dataKey="cost"
          fill="var(--color-cost)"
          fillOpacity={0.85}
          radius={[2, 2, 0, 0]}
          isAnimationActive={false}
        />
      </BarChart>
    </ChartContainer>
  )
}
