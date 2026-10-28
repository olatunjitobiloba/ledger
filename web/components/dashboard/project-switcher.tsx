"use client"

import Link from "next/link"
import { HugeiconsIcon } from "@hugeicons/react"
import { Link01Icon, PlusSignIcon, Tick02Icon, UnfoldMoreIcon } from "@hugeicons/core-free-icons"
import { cn } from "cn"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { SidebarMenu, SidebarMenuButton, SidebarMenuItem } from "@/components/ui/sidebar"
import { projectStore, type StoredProject } from "@/lib/ledger/projects"

export function ProjectAvatar({ name, className }: { name: string; className?: string }) {
  return (
    <Avatar className={cn("size-6 rounded-md after:rounded-md", className)}>
      <AvatarFallback className="rounded-md bg-brand/15 text-xs font-semibold text-foreground uppercase">
        {name.trim().charAt(0) || "?"}
      </AvatarFallback>
    </Avatar>
  )
}

export function ProjectSwitcher({
  projects,
  active,
}: {
  projects: StoredProject[]
  active: StoredProject
}) {
  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <DropdownMenu>
          <DropdownMenuTrigger
            render={
              <SidebarMenuButton
                size="lg"
                tooltip={active.name}
                className="rounded-xl border bg-background px-2 shadow-xs data-popup-open:bg-sidebar-accent group-data-[collapsible=icon]:border-0 group-data-[collapsible=icon]:bg-transparent group-data-[collapsible=icon]:shadow-none"
              />
            }
          >
            <ProjectAvatar name={active.name} className="size-7" />
            <span className="grid flex-1 text-left leading-tight">
              <span className="truncate text-sm font-medium">{active.name}</span>
              <span className="truncate text-xs text-muted-foreground">
                {projects.length} {projects.length === 1 ? "project" : "projects"}
              </span>
            </span>
            <HugeiconsIcon icon={UnfoldMoreIcon} className="text-muted-foreground" />
          </DropdownMenuTrigger>
          <DropdownMenuContent className="w-(--anchor-width) min-w-60">
            <DropdownMenuGroup>
              {projects.map((project) => (
                <DropdownMenuItem key={project.id} onClick={() => projectStore.select(project.id)}>
                  <ProjectAvatar name={project.name} />
                  <span className="truncate">{project.name}</span>
                  {project.id === active.id && (
                    <HugeiconsIcon icon={Tick02Icon} className="ml-auto text-brand" />
                  )}
                </DropdownMenuItem>
              ))}
            </DropdownMenuGroup>
            <DropdownMenuSeparator />
            <DropdownMenuItem render={<Link href="/onboarding" />}>
              <HugeiconsIcon icon={PlusSignIcon} />
              New project
            </DropdownMenuItem>
            <DropdownMenuItem render={<Link href="/onboarding?mode=connect" />}>
              <HugeiconsIcon icon={Link01Icon} />
              Connect existing project
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarMenuItem>
    </SidebarMenu>
  )
}
