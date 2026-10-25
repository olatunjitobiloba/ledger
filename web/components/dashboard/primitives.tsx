"use client"

import { useState, type ReactNode } from "react"
import { CheckIcon, Square2StackIcon } from "@heroicons/react/24/outline"
import { cn } from "cn"
import { Button } from "@/components/ui/button"
import type { EvalRun } from "@/lib/ledger/types"

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string
  description?: ReactNode
  actions?: ReactNode
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {description && (
          <p className="mt-2 text-sm text-muted-foreground">{description}</p>
        )}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  )
}

/** The bordered surface every dashboard section sits on. */
export function Panel({ className, ...props }: React.ComponentProps<"section">) {
  return (
    <section
      className={cn("overflow-hidden rounded-2xl border bg-muted", className)}
      {...props}
    />
  )
}

export function CopyButton({
  value,
  label = "Copy",
  className,
}: {
  value: string
  label?: string
  className?: string
}) {
  const [copied, setCopied] = useState(false)
  return (
    <Button
      type="button"
      variant="ghost"
      size="icon-xs"
      aria-label={copied ? "Copied" : label}
      className={cn("text-muted-foreground hover:text-foreground", className)}
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(value)
          setCopied(true)
          setTimeout(() => setCopied(false), 1500)
        } catch {}
      }}
    >
      {copied ? <CheckIcon /> : <Square2StackIcon />}
    </Button>
  )
}

const dotTone = {
  good: "bg-brand",
  bad: "bg-destructive",
  warn: "bg-[#e48338]",
  neutral: "bg-muted-foreground",
} as const

export function StatusDot({
  tone,
  children,
}: {
  tone: keyof typeof dotTone
  children: ReactNode
}) {
  return (
    <span className="inline-flex items-center gap-1.5 text-sm whitespace-nowrap">
      <span className={cn("size-1.5 shrink-0 rounded-full", dotTone[tone])} />
      {children}
    </span>
  )
}

export function EvalResult({ run }: { run: EvalRun }) {
  if (run.status === "queued") return <StatusDot tone="neutral">Queued</StatusDot>
  if (run.status === "running") return <StatusDot tone="neutral">Judging</StatusDot>
  if (run.status === "failed") return <StatusDot tone="warn">No score</StatusDot>
  return run.passed ? (
    <StatusDot tone="good">Passed</StatusDot>
  ) : (
    <StatusDot tone="bad">Regressed</StatusDot>
  )
}

export function gateOf(run: Pick<EvalRun, "baseline_score" | "variance">) {
  return run.baseline_score - run.variance
}

export function EmptyState({
  icon: Icon,
  title,
  children,
  action,
}: {
  icon: React.ComponentType<{ className?: string }>
  title: string
  children: ReactNode
  action?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center px-6 py-16 text-center">
      <div className="flex size-10 items-center justify-center rounded-xl border bg-background">
        <Icon className="size-5 text-muted-foreground" />
      </div>
      <h3 className="mt-4 text-sm font-medium">{title}</h3>
      <p className="mt-1.5 max-w-sm text-sm text-pretty text-muted-foreground">
        {children}
      </p>
      {action && <div className="mt-5">{action}</div>}
    </div>
  )
}

export function ErrorNotice({ error }: { error: Error }) {
  return (
    <div
      role="alert"
      className="rounded-xl border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive"
    >
      {error.message}
    </div>
  )
}
