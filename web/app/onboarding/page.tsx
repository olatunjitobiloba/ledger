import { Suspense } from "react"
import type { Metadata } from "next"
import { Onboarding } from "@/components/onboarding/onboarding"

export const metadata: Metadata = {
  title: "Set up a project — Ledger",
  robots: { index: false },
}

export default function Page() {
  return (
    // The form reads `?mode=` from the URL, which is only known in the browser.
    <Suspense>
      <Onboarding />
    </Suspense>
  )
}
