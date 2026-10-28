import type { Metadata } from "next"
import { SettingsView } from "@/components/dashboard/views/settings"

export const metadata: Metadata = { title: "Settings" }

export default function Page() {
  return <SettingsView />
}
