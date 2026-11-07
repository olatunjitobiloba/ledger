import type { Metadata } from "next"
import { AlertsView } from "@/components/dashboard/views/alerts"

export const metadata: Metadata = { title: "Alerts" }

// DashboardShell only renders pages in the browser, once the project is read from localStorage.
export const instant = false

export default function Page() {
  return <AlertsView />
}
