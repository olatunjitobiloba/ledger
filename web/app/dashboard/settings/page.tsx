import type { Metadata } from "next"
import { SettingsView } from "@/components/dashboard/views/settings"

export const metadata: Metadata = { title: "Settings" }

// DashboardShell only renders pages in the browser, once the project is read from localStorage.
export const instant = false

export default function Page() {
  return <SettingsView />
}
