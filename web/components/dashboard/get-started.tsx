"use client"

import Link from "next/link"
import { CheckIcon, ChevronUpIcon } from "@heroicons/react/24/outline"
import { cn } from "cn"
import { Button } from "@/components/ui/button"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { useActiveProject, useEvalRuns, useTraces } from "@/lib/ledger/hooks"
import { projectStore } from "@/lib/ledger/projects"

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
      label: "Issue an API key for your app",
      done: project.issuedKeys.length > 0,
      href: "/dashboard/api-keys",
    },
  ]
  const completed = steps.filter((step) => step.done).length
  const allDone = completed === steps.length

  return (
    <div className="fixed right-5 bottom-5 z-30">
      <Popover>
        <PopoverTrigger
          render={
            <Button
              variant="outline"
              size="lg"
              className="rounded-full bg-popover pr-4 shadow-lg shadow-black/20 dark:bg-popover"
            />
          }
        >
          <span className="font-semibold">{allDone ? "All set" : "Get started"}</span>
          <span className="text-muted-foreground">
            · {completed}/{steps.length}
          </span>
          <ChevronUpIcon className="text-muted-foreground" />
        </PopoverTrigger>
        <PopoverContent side="top" align="end" sideOffset={8} className="w-72 p-2">
          <div className="px-2 pt-1.5 pb-2">
            <p className="text-sm font-medium">Get started with Ledger</p>
            <div className="mt-2.5 h-1 overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full bg-brand transition-[width] duration-300 ease-out"
                style={{ width: `${(completed / steps.length) * 100}%` }}
              />
            </div>
          </div>
          <ol>
            {steps.map((step) => (
              <li key={step.label}>
                <Link
                  href={step.href}
                  className="flex items-center gap-3 rounded-lg px-2 py-2 text-sm transition-colors duration-150 hover:bg-muted"
                >
                  <span
                    className={cn(
                      "flex size-5 shrink-0 items-center justify-center rounded-full border",
                      step.done && "border-transparent bg-brand text-primary-foreground"
                    )}
                  >
                    {step.done && <CheckIcon className="size-3" strokeWidth={2.5} />}
                  </span>
                  <span className={cn(step.done && "text-muted-foreground line-through")}>
                    {step.label}
                  </span>
                </Link>
              </li>
            ))}
          </ol>
          <div className="mt-1 border-t px-2 pt-2">
            <button
              type="button"
              className="text-xs text-muted-foreground transition-colors duration-150 hover:text-foreground"
              onClick={projectStore.dismissGuide}
            >
              Hide this guide
            </button>
          </div>
        </PopoverContent>
      </Popover>
    </div>
  )
}
