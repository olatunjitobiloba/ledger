import type { Metadata } from "next"
import { ApiKeysView } from "@/components/dashboard/views/api-keys"

export const metadata: Metadata = { title: "API keys" }

export default function Page() {
  return <ApiKeysView />
}
