import type { Metadata } from "next"
import { OverviewView } from "@/components/dashboard/views/overview"

export const metadata: Metadata = { title: "Overview" }

// DashboardShell only renders pages in the browser, once the project is read from localStorage.
export const instant = false

export default function Page() {
  return <OverviewView />
}
