import type { Metadata } from "next"
import { TracesView } from "@/components/dashboard/views/traces"

export const metadata: Metadata = { title: "Traces" }

// DashboardShell only renders pages in the browser, once the project is read from localStorage.
export const instant = false

export default function Page() {
  return <TracesView />
}
