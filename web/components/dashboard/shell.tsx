"use client"

import { useEffect, type ReactNode } from "react"
import { usePathname, useRouter } from "next/navigation"
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb"
import { Separator } from "@/components/ui/separator"
import { SidebarInset, SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar"
import { Spinner } from "@/components/ui/spinner"
import { TooltipProvider } from "@/components/ui/tooltip"
import { AppSidebar } from "@/components/dashboard/app-sidebar"
import { currentPage } from "@/components/dashboard/nav"
import { ProjectContext } from "@/lib/ledger/hooks"
import { activeProject, useProjectState, type StoredProject } from "@/lib/ledger/projects"

function Loading() {
  return (
    <div className="flex min-h-dvh flex-1 items-center justify-center" aria-busy="true">
      <Spinner className="size-5 text-muted-foreground" />
    </div>
  )
}

function Topbar({ project }: { project: StoredProject }) {
  const page = currentPage(usePathname())
  return (
    <header className="sticky top-0 z-20 flex h-14 shrink-0 md:rounded-t-xl items-center gap-3 border-b bg-background/80 px-4 backdrop-blur-md supports-backdrop-filter:bg-background/65 sm:px-6">
      <SidebarTrigger className="-ml-1.5 text-muted-foreground hover:text-foreground" />
      <Separator orientation="vertical" className="my-auto h-4" />
      <Breadcrumb className="min-w-0">
        <BreadcrumbList className="flex-nowrap">
          <BreadcrumbItem className="min-w-0">
            <span className="truncate">{project.name}</span>
          </BreadcrumbItem>
          {page && (
            <>
              <BreadcrumbSeparator />
              <BreadcrumbItem>
                <BreadcrumbPage className="font-medium">{page.label}</BreadcrumbPage>
              </BreadcrumbItem>
            </>
          )}
        </BreadcrumbList>
      </Breadcrumb>
    </header>
  )
}

export function DashboardShell({ children }: { children: ReactNode }) {
  const router = useRouter()
  const state = useProjectState()
  const active = state ? activeProject(state) : null

  // Without a project there is nothing to show: set one up first.
  useEffect(() => {
    if (state && !active) router.replace("/onboarding")
  }, [state, active, router])

  if (!state || !active) return <Loading />

  return (
    <TooltipProvider delay={400}>
      <ProjectContext.Provider value={active}>
        <SidebarProvider>
          <AppSidebar projects={state.projects} active={active} guideDismissed={state.guideDismissed} />
          {/* On desktop the inset is its own scroll area, so the top bar sticks inside it. */}
          <SidebarInset className="min-w-0 md:peer-data-[variant=inset]:h-[calc(100dvh-1rem)] md:peer-data-[variant=inset]:overflow-y-auto md:peer-data-[variant=inset]:ring-1 md:peer-data-[variant=inset]:ring-border">
            <Topbar project={active} />
            {/* Keyed so per-page state (pagination, open sheets) resets on project switch. */}
            <div key={active.id} className="mx-auto w-full max-w-6xl px-4 py-8 sm:px-8 sm:py-10">
              {children}
            </div>
          </SidebarInset>
        </SidebarProvider>
      </ProjectContext.Provider>
    </TooltipProvider>
  )
}
