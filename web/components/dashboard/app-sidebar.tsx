"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { HugeiconsIcon } from "@hugeicons/react"
import {
  ArrowLeft01Icon,
  BookOpen01Icon,
  Moon02Icon,
  ServerStack01Icon,
  Sun03Icon,
  UnfoldMoreIcon,
} from "@hugeicons/core-free-icons"
import { cn } from "cn"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuBadge,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarSeparator,
  useSidebar,
} from "@/components/ui/sidebar"
import { LogoMark } from "@/components/site/logo"
import { applyTheme } from "@/components/site/theme"
import { GetStarted } from "@/components/dashboard/get-started"
import { isActive, primaryNav, secondaryNav, type NavItem } from "@/components/dashboard/nav"
import { ProjectSwitcher } from "@/components/dashboard/project-switcher"
import { useAlerts, useHealth } from "@/lib/ledger/hooks"
import type { StoredProject } from "@/lib/ledger/projects"
import { site } from "@/lib/site"

function NavList({ items }: { items: readonly NavItem[] }) {
  const pathname = usePathname()
  const { isMobile, setOpenMobile } = useSidebar()
  return (
    <SidebarMenu className="gap-0.5">
      {items.map((item) => (
        <SidebarMenuItem key={item.href}>
          <SidebarMenuButton
            isActive={isActive(item.href, pathname)}
            tooltip={item.label}
            className="h-9 rounded-lg px-2.5 text-sidebar-foreground/70 transition-[background-color,color] duration-150 hover:text-sidebar-foreground data-active:bg-sidebar-accent data-active:font-medium data-active:text-sidebar-foreground [&_svg]:size-[18px]"
            render={<Link href={item.href} onClick={() => isMobile && setOpenMobile(false)} />}
          >
            <HugeiconsIcon icon={item.icon} />
            <span>{item.label}</span>
          </SidebarMenuButton>
          {item.href === "/dashboard/alerts" && <AlertCount />}
        </SidebarMenuItem>
      ))}
    </SidebarMenu>
  )
}

function AlertCount() {
  const { data } = useAlerts()
  const count = data?.items.length ?? 0
  if (!count) return null
  return (
    <SidebarMenuBadge className="top-2 rounded-full bg-destructive/15 px-1.5 text-destructive tabular-nums">
      {count}
    </SidebarMenuBadge>
  )
}

function ApiStatus() {
  const { data, isLoading } = useHealth()
  const online = data?.status === "ok"
  const label = isLoading ? "Connecting…" : online ? "Operational" : "Unreachable"

  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <DropdownMenu>
          <DropdownMenuTrigger
            render={
              <SidebarMenuButton
                size="lg"
                tooltip={`Ledger API · ${label}`}
                className="rounded-xl px-2 data-popup-open:bg-sidebar-accent"
              />
            }
          >
            <span className="relative flex size-8 shrink-0 items-center justify-center rounded-lg border bg-background">
              <HugeiconsIcon icon={ServerStack01Icon} className="size-4!" />
              <span
                className={cn(
                  "absolute -right-0.5 -bottom-0.5 size-2.5 rounded-full ring-2 ring-sidebar",
                  isLoading ? "animate-pulse bg-muted-foreground" : online ? "bg-brand" : "bg-destructive"
                )}
              />
            </span>
            <span className="grid flex-1 text-left leading-tight">
              <span className="truncate text-sm font-medium">Ledger API</span>
              <span className="truncate text-xs text-muted-foreground">{label}</span>
            </span>
            <HugeiconsIcon icon={UnfoldMoreIcon} className="text-muted-foreground" />
          </DropdownMenuTrigger>
          <DropdownMenuContent side="top" className="w-(--anchor-width) min-w-56">
            <DropdownMenuItem
              onClick={() =>
                applyTheme(document.documentElement.classList.contains("dark") ? "light" : "dark")
              }
            >
              <HugeiconsIcon icon={Sun03Icon} className="hidden dark:block" />
              <HugeiconsIcon icon={Moon02Icon} className="dark:hidden" />
              Toggle theme
            </DropdownMenuItem>
            <DropdownMenuItem
              render={<a href={site.links.apiContract} target="_blank" rel="noreferrer" />}
            >
              <HugeiconsIcon icon={BookOpen01Icon} />
              API documentation
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem render={<Link href="/" />}>
              <HugeiconsIcon icon={ArrowLeft01Icon} />
              Back to website
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarMenuItem>
    </SidebarMenu>
  )
}

export function AppSidebar({
  projects,
  active,
  guideDismissed,
}: {
  projects: StoredProject[]
  active: StoredProject
  guideDismissed: boolean
}) {
  return (
    <Sidebar variant="inset" collapsible="icon">
      <SidebarHeader className="gap-3 pt-3">
        <Link
          href="/"
          className="flex h-8 items-center gap-2 rounded-lg px-1.5 font-semibold tracking-tight outline-none focus-visible:ring-3 focus-visible:ring-ring/50 group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:px-0"
        >
          <LogoMark className="size-6" />
          <span className="group-data-[collapsible=icon]:hidden">Ledger</span>
        </Link>
        <ProjectSwitcher projects={projects} active={active} />
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <NavList items={primaryNav} />
        </SidebarGroup>
        <SidebarSeparator className="mx-3 w-auto" />
        <SidebarGroup>
          <NavList items={secondaryNav} />
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter className="gap-3">
        {!guideDismissed && <GetStarted />}
        <ApiStatus />
      </SidebarFooter>
    </Sidebar>
  )
}
