"use client"

import type { ReactNode } from "react"
import Link from "next/link"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { SidebarInset, SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar"
import { Skeleton } from "@/components/ui/skeleton"
import { Toaster } from "@/components/ui/sonner"
import { TooltipProvider } from "@/components/ui/tooltip"
import { LogoMark } from "@/components/site/logo"
import { AppSidebar } from "@/components/dashboard/app-sidebar"
import { GetStarted } from "@/components/dashboard/get-started"
import { Onboarding } from "@/components/dashboard/onboarding"
import { SecretReveal } from "@/components/dashboard/project-forms"
import { ProjectContext } from "@/lib/ledger/hooks"
import { activeProject, projectStore, useProjectState } from "@/lib/ledger/projects"

function LoadingShell() {
  return (
    <div aria-busy="true" aria-label="Loading">
      <Skeleton className="h-8 w-40" />
      <Skeleton className="mt-3 h-4 w-28" />
      <Skeleton className="mt-8 h-28 w-full rounded-2xl" />
      <Skeleton className="mt-6 h-80 w-full rounded-2xl" />
    </div>
  )
}

export function DashboardShell({ children }: { children: ReactNode }) {
  const state = useProjectState()
  const active = state ? activeProject(state) : null
  const revealed = state?.projects.find((p) => p.id === state.revealId)

  let content: ReactNode
  if (!state) content = <LoadingShell />
  else if (!active) content = <Onboarding />
  // Keyed so per-page state (pagination, open dialogs) resets on project switch.
  else content = <div key={active.id}>{children}</div>

  return (
    <TooltipProvider>
      <ProjectContext.Provider value={active}>
        <SidebarProvider>
          <AppSidebar projects={state?.projects ?? []} active={active} />
          <SidebarInset className="min-w-0 bg-card">
            <header className="flex h-14 items-center gap-2 border-b px-4 md:hidden">
              <SidebarTrigger />
              <Link href="/" className="flex items-center gap-2 font-semibold tracking-tight">
                <LogoMark className="size-6" />
                Ledger
              </Link>
            </header>
            <div className="mx-auto w-full max-w-6xl px-5 py-8 sm:px-8 sm:py-12">
              {content}
            </div>
          </SidebarInset>
          {active && !state?.guideDismissed && <GetStarted />}
        </SidebarProvider>

        <Dialog open={!!revealed} onOpenChange={(open) => !open && projectStore.clearReveal()}>
          <DialogContent className="sm:max-w-md" showCloseButton={false}>
            <DialogHeader>
              <DialogTitle>Project created</DialogTitle>
              <DialogDescription>
                Use this key with the SDK. The dashboard keeps a copy in this
                browser to read {revealed?.name ?? "your project"}.
              </DialogDescription>
            </DialogHeader>
            {revealed && (
              <SecretReveal secret={revealed.apiKey} onDone={projectStore.clearReveal} />
            )}
          </DialogContent>
        </Dialog>
        <Toaster position="bottom-left" />
      </ProjectContext.Provider>
    </TooltipProvider>
  )
}
