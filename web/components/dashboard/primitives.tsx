"use client"

import { useEffect, useRef, useState, type ReactNode } from "react"
import { HugeiconsIcon, type IconSvgElement } from "@hugeicons/react"
import { AlertCircleIcon, Copy01Icon, Tick02Icon } from "@hugeicons/core-free-icons"
import { cn } from "cn"
import { Alert, AlertAction, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import type { EvalRun } from "@/lib/ledger/types"

export type Icon = IconSvgElement

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
    <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-4">
      <div className="min-w-0 max-w-2xl">
        <h1 className="text-2xl font-semibold tracking-tight text-balance">{title}</h1>
        {description && (
          <p className="mt-1.5 text-sm text-pretty text-muted-foreground">{description}</p>
        )}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
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
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined)
  useEffect(() => () => clearTimeout(timer.current), [])

  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <Button
            type="button"
            variant="ghost"
            size="icon-xs"
            aria-label={copied ? "Copied" : label}
            className={cn("relative text-muted-foreground hover:text-foreground", className)}
            onClick={async (event) => {
              event.stopPropagation()
              try {
                await navigator.clipboard.writeText(value)
                setCopied(true)
                clearTimeout(timer.current)
                timer.current = setTimeout(() => setCopied(false), 1500)
              } catch {}
            }}
          />
        }
      >
        {/* Both icons stay mounted and cross-fade, blurred to read as one morph. */}
        <HugeiconsIcon
          icon={Copy01Icon}
          className={cn(
            "transition-[opacity,filter,transform] duration-200 ease-out",
            copied && "scale-75 opacity-0 blur-[2px]"
          )}
        />
        <HugeiconsIcon
          icon={Tick02Icon}
          className={cn(
            "absolute text-brand transition-[opacity,filter,transform] duration-200 ease-out",
            !copied && "scale-75 opacity-0 blur-[2px]"
          )}
        />
      </TooltipTrigger>
      <TooltipContent>{copied ? "Copied" : label}</TooltipContent>
    </Tooltip>
  )
}

const tones = {
  good: { dot: "bg-brand", badge: "border-brand/25 bg-brand/10 text-foreground" },
  bad: { dot: "bg-destructive", badge: "border-destructive/25 bg-destructive/10 text-destructive" },
  warn: { dot: "bg-amber-500", badge: "border-amber-500/25 bg-amber-500/10 text-foreground" },
  neutral: { dot: "bg-muted-foreground", badge: "border-border bg-muted text-muted-foreground" },
} as const

export type Tone = keyof typeof tones

export function StatusBadge({
  tone,
  pulse = false,
  children,
}: {
  tone: Tone
  pulse?: boolean
  children: ReactNode
}) {
  return (
    <Badge variant="outline" className={cn("gap-1.5 font-medium", tones[tone].badge)}>
      <span className={cn("size-1.5 rounded-full", tones[tone].dot, pulse && "animate-pulse")} />
      {children}
    </Badge>
  )
}

export function EvalResult({ run }: { run: EvalRun }) {
  if (run.status === "queued") return <StatusBadge tone="neutral" pulse>Queued</StatusBadge>
  if (run.status === "running") return <StatusBadge tone="neutral" pulse>Judging</StatusBadge>
  if (run.status === "failed") return <StatusBadge tone="warn">No score</StatusBadge>
  return run.passed ? (
    <StatusBadge tone="good">Passed</StatusBadge>
  ) : (
    <StatusBadge tone="bad">Regressed</StatusBadge>
  )
}

export function gateOf(run: Pick<EvalRun, "baseline_score" | "variance">) {
  return run.baseline_score - run.variance
}

export function EmptyState({
  icon,
  title,
  children,
  action,
  className,
}: {
  icon: Icon
  title: string
  children: ReactNode
  action?: ReactNode
  className?: string
}) {
  return (
    <Empty className={cn("py-14", className)}>
      <EmptyHeader>
        <EmptyMedia variant="icon" className="size-10 rounded-xl border bg-background">
          <HugeiconsIcon icon={icon} className="size-5 text-muted-foreground" />
        </EmptyMedia>
        <EmptyTitle>{title}</EmptyTitle>
        <EmptyDescription className="text-pretty">{children}</EmptyDescription>
      </EmptyHeader>
      {action && <EmptyContent>{action}</EmptyContent>}
    </Empty>
  )
}

export function ErrorNotice({
  error,
  title = "Something went wrong",
  onRetry,
}: {
  error: Error
  title?: string
  onRetry?: () => void
}) {
  return (
    <Alert variant="destructive" className="rise-in border-destructive/25 bg-destructive/5 px-4 py-3">
      <HugeiconsIcon icon={AlertCircleIcon} />
      <AlertTitle>{title}</AlertTitle>
      <AlertDescription>{error.message}</AlertDescription>
      {onRetry && (
        <AlertAction className="top-1/2 right-3 -translate-y-1/2">
          <Button size="sm" variant="outline" onClick={onRetry}>
            Retry
          </Button>
        </AlertAction>
      )}
    </Alert>
  )
}

/** A label/value pair for detail sheets and settings. */
export function DetailRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-6 py-3 text-sm">
      <dt className="shrink-0 text-muted-foreground">{label}</dt>
      <dd className="min-w-0 text-right">{children}</dd>
    </div>
  )
}
