import type { Metadata } from "next"
import { OverviewView } from "@/components/dashboard/views/overview"

export const metadata: Metadata = { title: "Overview" }

export default function Page() {
  return <OverviewView />
}
