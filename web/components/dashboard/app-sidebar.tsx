"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import {
  ArrowLeftIcon,
  BeakerIcon,
  BellIcon,
  BookOpenIcon,
  ChevronUpDownIcon,
  Cog6ToothIcon,
  KeyIcon,
  MoonIcon,
  QueueListIcon,
  ServerIcon,
  Squares2X2Icon,
  SunIcon,
} from "@heroicons/react/24/outline"
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
  SidebarTrigger,
  useSidebar,
} from "@/components/ui/sidebar"
import { LogoMark } from "@/components/site/logo"
import { applyTheme } from "@/components/site/theme"
import { ProjectSwitcher } from "@/components/dashboard/project-switcher"
import { useAlerts, useHealth } from "@/lib/ledger/hooks"
import type { StoredProject } from "@/lib/ledger/projects"
import { site } from "@/lib/site"

const primaryNav = [
  { label: "Overview", href: "/dashboard", icon: Squares2X2Icon },
  { label: "Traces", href: "/dashboard/traces", icon: QueueListIcon },
  { label: "Evaluations", href: "/dashboard/evaluations", icon: BeakerIcon },
  { label: "Alerts", href: "/dashboard/alerts", icon: BellIcon },
]

const secondaryNav = [
  { label: "API keys", href: "/dashboard/api-keys", icon: KeyIcon },
  { label: "Settings", href: "/dashboard/settings", icon: Cog6ToothIcon },
]

function NavList({
  items,
  showAlertCount = false,
}: {
  items: typeof primaryNav
  showAlertCount?: boolean
}) {
  const pathname = usePathname()
  const { isMobile, setOpenMobile } = useSidebar()
  return (
    <SidebarMenu className="gap-1">
      {items.map((item) => {
        const active =
          item.href === "/dashboard" ? pathname === item.href : pathname.startsWith(item.href)
        return (
          <SidebarMenuItem key={item.href}>
            <SidebarMenuButton
              isActive={active}
              tooltip={item.label}
              className="h-9 rounded-lg px-2.5 text-[0.9375rem] text-sidebar-foreground/75 data-active:font-medium data-active:text-sidebar-foreground [&_svg]:size-[18px]"
              render={
                <Link href={item.href} onClick={() => isMobile && setOpenMobile(false)} />
              }
            >
              <item.icon />
              <span>{item.label}</span>
            </SidebarMenuButton>
            {showAlertCount && item.href === "/dashboard/alerts" && <AlertCount />}
          </SidebarMenuItem>
        )
      })}
    </SidebarMenu>
  )
}

function AlertCount() {
  const { data } = useAlerts()
  const count = data?.items.length ?? 0
  if (!count) return null
  return (
    <SidebarMenuBadge className="top-2 rounded-full bg-destructive/15 text-destructive">
      {count}
    </SidebarMenuBadge>
  )
}

function ApiStatus() {
  const { data, error, isLoading } = useHealth()
  const online = data?.status === "ok"
  const label = isLoading ? "Checking…" : online ? "Online" : "Unreachable"

  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <DropdownMenu>
          <DropdownMenuTrigger
            render={
              <SidebarMenuButton
                size="lg"
                className="rounded-xl px-2 data-popup-open:bg-sidebar-accent"
              />
            }
          >
            <span className="flex size-8 shrink-0 items-center justify-center rounded-full border bg-sidebar-accent/60">
              <ServerIcon className="size-4!" />
            </span>
            <span className="grid flex-1 text-left leading-tight">
              <span className="truncate font-medium">Ledger API</span>
              <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <span
                  className={cn(
                    "size-1.5 rounded-full",
                    isLoading
                      ? "bg-muted-foreground"
                      : online
                        ? "bg-brand"
                        : "bg-destructive"
                  )}
                />
                <span title={error?.message}>{label}</span>
              </span>
            </span>
            <ChevronUpDownIcon className="text-muted-foreground" />
          </DropdownMenuTrigger>
          <DropdownMenuContent side="top" className="w-(--anchor-width) min-w-56">
            <DropdownMenuItem
              onClick={() =>
                applyTheme(
                  document.documentElement.classList.contains("dark") ? "light" : "dark"
                )
              }
            >
              <SunIcon className="hidden dark:block" />
              <MoonIcon className="dark:hidden" />
              Toggle theme
            </DropdownMenuItem>
            <DropdownMenuItem
              render={<a href={site.links.apiContract} target="_blank" rel="noreferrer" />}
            >
              <BookOpenIcon />
              API documentation
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem render={<Link href="/" />}>
              <ArrowLeftIcon />
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
}: {
  projects: StoredProject[]
  active: StoredProject | null
}) {
  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="gap-4 px-3 pt-4 group-data-[collapsible=icon]:px-2">
        <div className="flex h-8 items-center justify-between gap-2 pl-1.5 group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:pl-0">
          <Link
            href="/"
            className="flex items-center gap-2 rounded-lg font-semibold tracking-tight outline-none focus-visible:ring-3 focus-visible:ring-ring/50 group-data-[collapsible=icon]:hidden"
          >
            <LogoMark className="size-6" />
            Ledger
          </Link>
          <SidebarTrigger className="text-muted-foreground hover:text-foreground" />
        </div>
        <ProjectSwitcher projects={projects} active={active} />
      </SidebarHeader>

      <SidebarContent className="px-1 group-data-[collapsible=icon]:px-0">
        <SidebarGroup>
          {/* Alert counts need a project to read from. */}
          <NavList items={primaryNav} showAlertCount={active !== null} />
        </SidebarGroup>
        <SidebarSeparator className="mx-3" />
        <SidebarGroup>
          <NavList items={secondaryNav} />
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter className="p-3 group-data-[collapsible=icon]:p-2">
        <ApiStatus />
      </SidebarFooter>
    </Sidebar>
  )
}
