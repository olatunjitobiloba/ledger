import type { Metadata } from "next"
import { ApiKeysView } from "@/components/dashboard/views/api-keys"

export const metadata: Metadata = { title: "API keys" }

// DashboardShell only renders pages in the browser, once the project is read from localStorage.
export const instant = false

export default function Page() {
  return <ApiKeysView />
}
