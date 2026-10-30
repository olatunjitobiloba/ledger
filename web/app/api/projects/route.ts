import { NextResponse } from "next/server"

/*
 * Creating a project is the one call that needs the API's admin token. The
 * token lives only in this server's environment, so the browser never holds it
 * and nobody has to paste it into the dashboard.
 */
const BACKEND_URL = (process.env.NEXT_PUBLIC_BACKEND_URL ?? "").trim().replace(/\/+$/, "")
const ADMIN_TOKEN = (process.env.LEDGER_ADMIN_TOKEN ?? "").trim()

/*
 * A scaled-to-zero host answers with a 503 HTML "waking up" page until the API
 * is running. Those requests never reached the API, so retrying is safe.
 */
const WAKE_RETRIES = 12
const WAKE_DELAY_MS = 2_500

function isWaking(response: Response) {
  const type = response.headers.get("content-type") ?? ""
  return response.status === 503 && type.includes("text/html")
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

export async function POST(request: Request) {
  if (!BACKEND_URL) {
    console.error("NEXT_PUBLIC_BACKEND_URL is not set. See web/env.sample.")
    return NextResponse.json(
      { detail: "This dashboard isn't connected to a Ledger API yet." },
      { status: 503 }
    )
  }

  const body = await request.text()
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "application/json",
  }
  // An API with no admin token of its own allows creation without the header.
  if (ADMIN_TOKEN) headers["X-Admin-Token"] = ADMIN_TOKEN

  for (let attempt = 0; ; attempt++) {
    let response: Response
    try {
      response = await fetch(`${BACKEND_URL}/v1/projects`, {
        method: "POST",
        headers,
        body,
        cache: "no-store",
      })
    } catch {
      return NextResponse.json(
        { detail: "Can't reach the Ledger API. Check your connection and try again." },
        { status: 502 }
      )
    }

    if (isWaking(response)) {
      await response.body?.cancel()
      if (attempt < WAKE_RETRIES) {
        await sleep(WAKE_DELAY_MS)
        continue
      }
      return NextResponse.json(
        { detail: "The Ledger API is still starting up. Try again in a moment." },
        { status: 503 }
      )
    }

    // Pass the API's own status and body through so the form can still tell a
    // taken name (409) apart from a token the API rejected (401).
    return new Response(await response.text(), {
      status: response.status,
      headers: {
        "Content-Type": response.headers.get("content-type") ?? "application/json",
        "Cache-Control": "no-store",
      },
    })
  }
}
