import type { Metadata } from "next"
import { DashboardShell } from "@/components/dashboard/shell"

export const metadata: Metadata = {
  title: { default: "Dashboard — Ledger", template: "%s — Ledger" },
  robots: { index: false },
}

export default function DashboardLayout({ children }: LayoutProps<"/dashboard">) {
  return <DashboardShell>{children}</DashboardShell>
}
