"use client"

import { useState } from "react"
import {
  CheckIcon,
  ChevronUpDownIcon,
  LinkIcon,
  PlusIcon,
} from "@heroicons/react/24/outline"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { SidebarMenu, SidebarMenuButton, SidebarMenuItem } from "@/components/ui/sidebar"
import { ConnectProjectForm, CreateProjectForm } from "@/components/dashboard/project-forms"
import { projectStore, type StoredProject } from "@/lib/ledger/projects"

export function ProjectAvatar({ name }: { name: string }) {
  return (
    <span className="flex size-6 shrink-0 items-center justify-center rounded-md bg-sidebar-accent text-xs font-semibold uppercase">
      {name.trim().charAt(0) || "?"}
    </span>
  )
}

export function ProjectSwitcher({
  projects,
  active,
}: {
  projects: StoredProject[]
  active: StoredProject | null
}) {
  // Kept apart from `open` so the content doesn't swap during the exit animation.
  const [kind, setKind] = useState<"create" | "connect">("create")
  const [open, setOpen] = useState(false)
  const show = (next: "create" | "connect") => {
    setKind(next)
    setOpen(true)
  }

  return (
    <>
      <SidebarMenu>
        <SidebarMenuItem>
          <DropdownMenu>
            <DropdownMenuTrigger
              render={
                <SidebarMenuButton
                  size="lg"
                  className="h-12 rounded-xl border bg-sidebar-accent/40 px-2.5 data-popup-open:bg-sidebar-accent group-data-[collapsible=icon]:border-0 group-data-[collapsible=icon]:bg-transparent"
                />
              }
            >
              <ProjectAvatar name={active?.name ?? "+"} />
              <span className="flex-1 truncate font-medium">
                {active?.name ?? "No project"}
              </span>
              <ChevronUpDownIcon className="text-muted-foreground" />
            </DropdownMenuTrigger>
            <DropdownMenuContent className="w-(--anchor-width) min-w-56">
              {projects.length > 0 && (
                <>
                  <DropdownMenuGroup>
                    <DropdownMenuLabel>Projects in this browser</DropdownMenuLabel>
                    {projects.map((project) => (
                      <DropdownMenuItem
                        key={project.id}
                        onClick={() => projectStore.select(project.id)}
                      >
                        <ProjectAvatar name={project.name} />
                        <span className="truncate">{project.name}</span>
                        {project.id === active?.id && <CheckIcon className="ml-auto" />}
                      </DropdownMenuItem>
                    ))}
                  </DropdownMenuGroup>
                  <DropdownMenuSeparator />
                </>
              )}
              <DropdownMenuItem onClick={() => show("create")}>
                <PlusIcon />
                New project
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => show("connect")}>
                <LinkIcon />
                Connect existing project
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </SidebarMenuItem>
      </SidebarMenu>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>
              {kind === "connect" ? "Connect a project" : "New project"}
            </DialogTitle>
            <DialogDescription>
              {kind === "connect"
                ? "Read an existing Ledger project with one of its API keys."
                : "Creates a project on your Ledger API and issues its first key."}
            </DialogDescription>
          </DialogHeader>
          {kind === "connect" ? (
            <ConnectProjectForm onDone={() => setOpen(false)} />
          ) : (
            <CreateProjectForm onDone={() => setOpen(false)} />
          )}
        </DialogContent>
      </Dialog>
    </>
  )
}
