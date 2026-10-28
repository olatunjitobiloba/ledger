import type { Metadata } from "next"
import { TracesView } from "@/components/dashboard/views/traces"

export const metadata: Metadata = { title: "Traces" }

export default function Page() {
  return <TracesView />
}
