import type { Metadata } from "next"
import { EvaluationsView } from "@/components/dashboard/views/evaluations"

export const metadata: Metadata = { title: "Evaluations" }

export default function Page() {
  return <EvaluationsView />
}
