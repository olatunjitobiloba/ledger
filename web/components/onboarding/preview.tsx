"use client"

import type { ReactNode } from "react"
import { HugeiconsIcon } from "@hugeicons/react"
import { Activity01Icon, LockKeyIcon } from "@hugeicons/core-free-icons"
import { cn } from "cn"
import { Badge } from "@/components/ui/badge"
import { Card } from "@/components/ui/card"
import { Separator } from "@/components/ui/separator"
import { ProjectAvatar } from "@/components/dashboard/project-switcher"
import { StatusBadge } from "@/components/dashboard/primitives"
import {
  MAX_RETENTION,
  redactPatterns,
  type ConnectDraft,
  type CreateDraft,
} from "@/components/dashboard/project-forms"

/** Stands in for a field the user hasn't filled yet. */
function Hint({ children }: { children: ReactNode }) {
  return (
    <span className="rounded-[0.3rem] bg-foreground/[0.07] px-1 text-muted-foreground">
      {children}
    </span>
  )
}

function Bar({ className }: { className?: string }) {
  return <span className={cn("block h-2 rounded-full bg-foreground/[0.07]", className)} />
}

function PlaceholderRow() {
  return (
    <div className="flex items-center gap-3 border-t px-4 py-3.5">
      <span className="size-7 shrink-0 rounded-md bg-foreground/[0.06]" />
      <div className="flex flex-1 flex-col gap-2">
        <Bar className="w-2/5" />
        <Bar className="w-3/5" />
      </div>
    </div>
  )
}

function TracesCard({ name, connected }: { name: string; connected: boolean }) {
  return (
    <Card className="gap-0 py-0 shadow-sm">
      <div className="flex items-center justify-between px-4 py-3">
        <span className="flex items-center gap-2 text-[0.8125rem] font-medium">
          <HugeiconsIcon icon={Activity01Icon} className="size-4 text-brand" />
          Traces
        </span>
        <span className="text-xs text-muted-foreground">{connected ? "Synced" : "Live"}</span>
      </div>
      {connected ? (
        <div className="flex items-center gap-3 border-t px-4 py-3.5">
          <ProjectAvatar name={name || "?"} className="size-7" />
          <p className="flex-1 text-[0.8125rem] text-pretty text-muted-foreground">
            Existing traces, evaluations and alerts load once the key is checked.
          </p>
        </div>
      ) : (
        <div className="flex items-center gap-3 border-t px-4 py-3.5">
          <ProjectAvatar name={name || "?"} className="size-7" />
          <div className="min-w-0 flex-1 text-[0.8125rem] leading-snug">
            <p className="truncate font-medium">{name || <Hint>Project name</Hint>}</p>
            <p className="truncate text-muted-foreground">First trace · gpt-4o-mini</p>
          </div>
          <div className="text-right text-xs leading-snug">
            <p className="font-mono tabular-nums">$0.0004</p>
            <p className="text-muted-foreground">just now</p>
          </div>
        </div>
      )}
      <PlaceholderRow />
      <PlaceholderRow />
    </Card>
  )
}

function FrontCard({ children }: { children: ReactNode }) {
  return (
    <Card className="relative -mt-10 ml-8 gap-5 px-5 py-5 shadow-2xl shadow-black/10 sm:ml-10 dark:shadow-black/60">
      {children}
    </Card>
  )
}

function CreatePreview({ draft }: { draft: CreateDraft }) {
  const name = draft.name.trim()
  const days = Number(draft.retention)
  const validDays = Number.isInteger(days) && days >= 1 && days <= MAX_RETENTION
  const patterns = redactPatterns(draft).length

  return (
    <>
      <TracesCard name={name} connected={false} />
      <FrontCard>
        <div className="flex items-center gap-2.5 text-[0.8125rem] font-medium">
          <ProjectAvatar name={name || "?"} />
          {name || <Hint>Project name</Hint>}
        </div>
        <Separator />
        <div>
          <p className="truncate text-3xl font-semibold tracking-tight">
            {name || <Hint>Your project</Hint>}
          </p>
          <div className="mt-3 flex flex-wrap gap-1.5">
            <Badge variant="outline" className="tabular-nums">
              {validDays ? `${days}-day retention` : <Hint>1–{MAX_RETENTION} days</Hint>}
            </Badge>
            <Badge variant="outline">
              {draft.capture
                ? `Prompts stored${patterns ? `, ${patterns} redaction ${patterns === 1 ? "rule" : "rules"}` : ""}`
                : "Prompts not stored"}
            </Badge>
          </div>
        </div>
        <div className="flex flex-col gap-2">
          <Bar className="w-full" />
          <Bar className="w-11/12" />
          <Bar className="w-3/5" />
        </div>
      </FrontCard>
    </>
  )
}

function ConnectPreview({ draft }: { draft: ConnectDraft }) {
  const name = draft.name.trim()
  const id = draft.projectId.trim()
  const shown = name || (id ? id.slice(0, 8) : "")
  const keyLength = Math.min(draft.apiKey.trim().length, 20)

  return (
    <>
      <TracesCard name={shown} connected />
      <FrontCard>
        <div className="flex items-center gap-2.5 text-[0.8125rem] font-medium">
          <ProjectAvatar name={shown || "?"} />
          {shown || <Hint>Display name</Hint>}
        </div>
        <Separator />
        <p className="truncate text-3xl font-semibold tracking-tight">
          {shown || <Hint>Existing project</Hint>}
        </p>
        <dl className="flex flex-col gap-3 text-[0.8125rem]">
          <div className="flex items-center justify-between gap-6">
            <dt className="text-muted-foreground">Project ID</dt>
            <dd className="min-w-0 truncate font-mono">{id || <Hint>3f6c1d2e-…</Hint>}</dd>
          </div>
          <div className="flex items-center justify-between gap-6">
            <dt className="text-muted-foreground">API key</dt>
            <dd className="flex items-center gap-1.5 font-mono">
              {keyLength ? (
                <>
                  <HugeiconsIcon icon={LockKeyIcon} className="size-3.5 text-muted-foreground" />
                  {"•".repeat(keyLength)}
                </>
              ) : (
                <Hint>ldg_…</Hint>
              )}
            </dd>
          </div>
        </dl>
        <div>
          <StatusBadge tone={id && keyLength ? "good" : "neutral"}>
            {id && keyLength ? "Ready to check" : "Waiting for details"}
          </StatusBadge>
        </div>
      </FrontCard>
    </>
  )
}

export function OnboardingPreview({
  mode,
  create,
  connect,
}: {
  mode: "create" | "connect"
  create: CreateDraft
  connect: ConnectDraft
}) {
  return (
    <div className="w-full max-w-md">
      <p className="mb-4 text-[0.8125rem] text-muted-foreground">
        {mode === "create"
          ? "Your project, as the dashboard will show it"
          : "The project you're connecting"}
      </p>
      {/* Keyed so switching modes swaps the preview with a soft blur. */}
      <div key={mode} className="swap-in">
        {mode === "create" ? <CreatePreview draft={create} /> : <ConnectPreview draft={connect} />}
      </div>
    </div>
  )
}
