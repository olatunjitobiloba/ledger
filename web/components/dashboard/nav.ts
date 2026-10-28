import {
  Activity01Icon,
  DashboardSquare01Icon,
  Key01Icon,
  Notification03Icon,
  Settings02Icon,
  TestTube01Icon,
} from "@hugeicons/core-free-icons"

export const primaryNav = [
  { label: "Overview", href: "/dashboard", icon: DashboardSquare01Icon },
  { label: "Traces", href: "/dashboard/traces", icon: Activity01Icon },
  { label: "Evaluations", href: "/dashboard/evaluations", icon: TestTube01Icon },
  { label: "Alerts", href: "/dashboard/alerts", icon: Notification03Icon },
] as const

export const secondaryNav = [
  { label: "API keys", href: "/dashboard/api-keys", icon: Key01Icon },
  { label: "Settings", href: "/dashboard/settings", icon: Settings02Icon },
] as const

export type NavItem = (typeof primaryNav)[number] | (typeof secondaryNav)[number]

export function isActive(href: string, pathname: string) {
  return href === "/dashboard" ? pathname === href : pathname.startsWith(href)
}

export function currentPage(pathname: string): NavItem | undefined {
  return [...primaryNav, ...secondaryNav].find((item) => isActive(item.href, pathname))
}
