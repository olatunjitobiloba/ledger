"use client"

import { useState } from "react"
import { PaperAirplaneIcon } from "@heroicons/react/24/outline"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { ledger } from "@/lib/ledger/api"
import { useActiveProject, useRevalidate } from "@/lib/ledger/hooks"

const between = (min: number, max: number) => Math.round(min + Math.random() * (max - min))

/** Queues one span through POST /v1/ingest, the same call the SDK makes. */
export function SendTestTrace({
  variant = "outline",
}: {
  variant?: "default" | "outline"
}) {
  const { apiKey } = useActiveProject()
  const revalidate = useRevalidate()
  const [pending, setPending] = useState(false)

  async function send() {
    setPending(true)
    const ended = new Date()
    const started = new Date(ended.getTime() - between(400, 2400))
    try {
      await ledger.ingest(apiKey, {
        status: "ok",
        metadata: { source: "ledger-dashboard" },
        span: {
          name: "dashboard_test_call",
          span_type: "llm_call",
          started_at: started.toISOString(),
          ended_at: ended.toISOString(),
          model: "gpt-4o-mini",
          prompt_tokens: between(200, 1600),
          completion_tokens: between(40, 480),
          capture_prompt: false,
        },
      })
      toast.success("Test trace queued", {
        description: "The worker stores it within a few seconds.",
      })
      // Ingest is asynchronous: check back once the worker has had a turn.
      setTimeout(() => revalidate("traces"), 1500)
      setTimeout(() => revalidate("traces"), 5000)
    } catch (error) {
      toast.error((error as Error).message)
    } finally {
      setPending(false)
    }
  }

  return (
    <Button variant={variant} onClick={send} disabled={pending}>
      <PaperAirplaneIcon />
      {pending ? "Sending…" : "Send test trace"}
    </Button>
  )
}
