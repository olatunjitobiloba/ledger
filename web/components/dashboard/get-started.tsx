"use client"

import Link from "next/link"
import { HugeiconsIcon } from "@hugeicons/react"
import { ArrowRight01Icon, Cancel01Icon, Tick02Icon } from "@hugeicons/core-free-icons"
import { cn } from "cn"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { Progress } from "@/components/ui/progress"
import { useActiveProject, useEvalRuns, useTraces } from "@/lib/ledger/hooks"
import { projectStore } from "@/lib/ledger/projects"

/** A small checklist in the sidebar until the project is fully wired up. */
export function GetStarted() {
  const project = useActiveProject()
  const traces = useTraces(1)
  const runs = useEvalRuns()

  const steps = [
    { label: "Create a project", done: true, href: "/dashboard/settings" },
    {
      label: "Send your first trace",
      done: (traces.data?.items.length ?? 0) > 0,
      href: "/dashboard/traces",
    },
    {
      label: "Run an evaluation",
      done: (runs.data?.items.length ?? 0) > 0,
      href: "/dashboard/evaluations",
    },
    {
      label: "Issue a key for your app",
      done: project.issuedKeys.length > 0,
      href: "/dashboard/api-keys",
    },
  ]
  const completed = steps.filter((step) => step.done).length
  const next = steps.find((step) => !step.done)
  // Until both lists load, the count would undercount and jump.
  if (!traces.data || !runs.data || !next) return null

  return (
    <Card size="sm" className="rise-in gap-3 bg-background shadow-xs group-data-[collapsible=icon]:hidden">
      <div className="flex items-start justify-between gap-2 px-3">
        <div>
          <p className="text-sm font-medium">Get started</p>
          <p className="mt-0.5 text-xs text-muted-foreground tabular-nums">
            {completed} of {steps.length} done
          </p>
        </div>
        <Button
          variant="ghost"
          size="icon-xs"
          aria-label="Hide checklist"
          className="-mt-0.5 -mr-1 text-muted-foreground"
          onClick={projectStore.dismissGuide}
        >
          <HugeiconsIcon icon={Cancel01Icon} />
        </Button>
      </div>
      <Progress
        value={(completed / steps.length) * 100}
        aria-label="Setup progress"
        className="px-3 [&_[data-slot=progress-indicator]]:bg-brand [&_[data-slot=progress-indicator]]:duration-500 [&_[data-slot=progress-indicator]]:ease-out-strong"
      />
      <div className="px-1.5">
        <Popover>
          <PopoverTrigger
            render={
              <Button
                variant="ghost"
                size="sm"
                className="w-full justify-between px-1.5 text-[0.8125rem] font-normal"
              />
            }
          >
            <span className="truncate">Next: {next.label}</span>
            <HugeiconsIcon icon={ArrowRight01Icon} className="text-muted-foreground" />
          </PopoverTrigger>
          <PopoverContent side="right" align="end" sideOffset={12} className="w-64 p-1.5">
            <ol>
              {steps.map((step) => (
                <li key={step.label}>
                  <Link
                    href={step.href}
                    className="flex items-center gap-3 rounded-md px-2 py-2 text-sm transition-colors duration-150 hover:bg-muted"
                  >
                    <span
                      className={cn(
                        "flex size-5 shrink-0 items-center justify-center rounded-full border",
                        step.done && "border-transparent bg-brand text-primary-foreground"
                      )}
                    >
                      {step.done && <HugeiconsIcon icon={Tick02Icon} className="size-3" strokeWidth={2.5} />}
                    </span>
                    <span className={cn(step.done && "text-muted-foreground line-through")}>
                      {step.label}
                    </span>
                  </Link>
                </li>
              ))}
            </ol>
          </PopoverContent>
        </Popover>
      </div>
    </Card>
  )
}
