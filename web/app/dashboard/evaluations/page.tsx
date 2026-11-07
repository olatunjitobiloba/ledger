import type { Metadata } from "next"
import { EvaluationsView } from "@/components/dashboard/views/evaluations"

export const metadata: Metadata = { title: "Evaluations" }

// DashboardShell only renders pages in the browser, once the project is read from localStorage.
export const instant = false

export default function Page() {
  return <EvaluationsView />
}
