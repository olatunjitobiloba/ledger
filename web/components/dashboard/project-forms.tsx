"use client"

import { useState, type FormEvent } from "react"
import { ExclamationTriangleIcon } from "@heroicons/react/24/outline"
import { Button } from "@/components/ui/button"
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Switch } from "@/components/ui/switch"
import { Textarea } from "@/components/ui/textarea"
import { CopyButton, ErrorNotice } from "@/components/dashboard/primitives"
import { LedgerError, ledger } from "@/lib/ledger/api"
import { projectStore } from "@/lib/ledger/projects"

/** Free-tier projects keep data for at most 7 days (POST /v1/projects). */
const MAX_RETENTION = 7

export function SecretReveal({
  secret,
  onDone,
  doneLabel = "Done",
}: {
  secret: string
  onDone: () => void
  doneLabel?: string
}) {
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2 rounded-xl border bg-background py-1.5 pr-1.5 pl-3">
        <code className="min-w-0 flex-1 truncate font-mono text-[0.8125rem]">{secret}</code>
        <CopyButton value={secret} label="Copy API key" />
      </div>
      <p className="flex gap-2 text-sm text-muted-foreground">
        <ExclamationTriangleIcon className="mt-0.5 size-4 shrink-0" />
        Copy it now. Ledger stores only a hash, so this key can&apos;t be shown
        again by the API.
      </p>
      <Button className="self-end" onClick={onDone}>
        {doneLabel}
      </Button>
    </div>
  )
}

export function CreateProjectForm({ onDone }: { onDone: () => void }) {
  const [name, setName] = useState("")
  const [retention, setRetention] = useState(String(MAX_RETENTION))
  const [capture, setCapture] = useState(false)
  const [patterns, setPatterns] = useState("")
  const [adminToken, setAdminToken] = useState("")
  const [error, setError] = useState<Error | null>(null)
  const [pending, setPending] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setPending(true)
    setError(null)
    try {
      const created = await ledger.createProject(
        {
          name: name.trim(),
          capture_prompt: capture,
          redact_patterns: capture
            ? patterns.split("\n").map((p) => p.trim()).filter(Boolean)
            : [],
          retention_days: Number(retention),
        },
        adminToken.trim() || undefined
      )
      const project = {
        id: created.project_id,
        name: name.trim(),
        apiKey: created.api_key,
        retentionDays: created.retention_days,
        capturePrompt: capture,
        addedAt: new Date().toISOString(),
        source: "created" as const,
        issuedKeys: [],
      }
      // The shell shows the new key once, even as this form unmounts.
      projectStore.add(project, { reveal: true })
      onDone()
    } catch (err) {
      // Project names are unique; the API surfaces the conflict as a bare 500.
      if (err instanceof LedgerError && err.status === 500) {
        setError(new Error("Couldn't create the project. Names must be unique, so try another."))
      } else if (err instanceof LedgerError && err.status === 401) {
        setError(new Error("This Ledger API requires an admin token to create projects."))
      } else {
        setError(err as Error)
      }
    } finally {
      setPending(false)
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-5">
      <FieldGroup>
        <Field>
          <FieldLabel htmlFor="project-name">Project name</FieldLabel>
          <Input
            id="project-name"
            required
            maxLength={120}
            placeholder="support-assistant"
            value={name}
            onChange={(e) => setName(e.target.value)}
            autoFocus
          />
        </Field>
        <Field>
          <FieldLabel htmlFor="project-retention">Retention (days)</FieldLabel>
          <Input
            id="project-retention"
            type="number"
            required
            min={1}
            max={MAX_RETENTION}
            value={retention}
            onChange={(e) => setRetention(e.target.value)}
          />
          <FieldDescription>
            Traces older than this are purged. The free tier allows up to {MAX_RETENTION}.
          </FieldDescription>
        </Field>
        <Field orientation="horizontal" className="justify-between">
          <div>
            <FieldLabel htmlFor="project-capture">Capture prompts</FieldLabel>
            <FieldDescription>
              Store prompt and response text. Off records only tokens, cost and model.
            </FieldDescription>
          </div>
          <Switch id="project-capture" checked={capture} onCheckedChange={setCapture} />
        </Field>
        {capture && (
          <Field>
            <FieldLabel htmlFor="project-redact">Redaction patterns</FieldLabel>
            <Textarea
              id="project-redact"
              rows={3}
              placeholder={"\\b\\d{16}\\b\n[\\w.]+@[\\w.]+"}
              className="font-mono text-[0.8125rem]"
              value={patterns}
              onChange={(e) => setPatterns(e.target.value)}
            />
            <FieldDescription>
              One regular expression per line. Matches are replaced before storage.
            </FieldDescription>
          </Field>
        )}
        <Field>
          <FieldLabel htmlFor="project-admin">Admin token</FieldLabel>
          <Input
            id="project-admin"
            type="password"
            autoComplete="off"
            placeholder="Optional"
            value={adminToken}
            onChange={(e) => setAdminToken(e.target.value)}
          />
          <FieldDescription>
            Only needed when the API sets <code className="font-mono">LEDGER_ADMIN_TOKEN</code>.
            It is sent once and not stored.
          </FieldDescription>
        </Field>
      </FieldGroup>
      {error && <ErrorNotice error={error} />}
      <Button type="submit" className="self-end" disabled={pending}>
        {pending ? "Creating…" : "Create project"}
      </Button>
    </form>
  )
}

export function ConnectProjectForm({ onDone }: { onDone: () => void }) {
  const [name, setName] = useState("")
  const [projectId, setProjectId] = useState("")
  const [apiKey, setApiKey] = useState("")
  const [error, setError] = useState<Error | null>(null)
  const [pending, setPending] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setPending(true)
    setError(null)
    const id = projectId.trim()
    const key = apiKey.trim()
    try {
      // There is no "who am I" endpoint: a one-trace read proves the key
      // belongs to this project (401 bad key, 403 another project).
      await ledger.traces(key, id, 1, 0)
      projectStore.add({
        id,
        name: name.trim() || id.slice(0, 8),
        apiKey: key,
        retentionDays: null,
        capturePrompt: null,
        addedAt: new Date().toISOString(),
        source: "connected",
        issuedKeys: [],
      })
      onDone()
    } catch (err) {
      if (err instanceof LedgerError && err.status === 401) {
        setError(new Error("That API key isn't valid."))
      } else if (err instanceof LedgerError && err.status === 403) {
        setError(new Error("That API key belongs to a different project."))
      } else {
        setError(err as Error)
      }
    } finally {
      setPending(false)
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-5">
      <FieldGroup>
        <Field>
          <FieldLabel htmlFor="connect-id">Project ID</FieldLabel>
          <Input
            id="connect-id"
            required
            className="font-mono"
            placeholder="3f6c1d2e-…"
            value={projectId}
            onChange={(e) => setProjectId(e.target.value)}
            autoFocus
          />
        </Field>
        <Field>
          <FieldLabel htmlFor="connect-key">API key</FieldLabel>
          <Input
            id="connect-key"
            required
            type="password"
            autoComplete="off"
            className="font-mono"
            placeholder="ldg_…"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
          />
        </Field>
        <Field>
          <FieldLabel htmlFor="connect-name">Display name</FieldLabel>
          <Input
            id="connect-name"
            maxLength={120}
            placeholder="Optional"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <FieldDescription>
            The API doesn&apos;t return project names, so pick one for this browser.
          </FieldDescription>
        </Field>
      </FieldGroup>
      {error && <ErrorNotice error={error} />}
      <Button type="submit" className="self-end" disabled={pending}>
        {pending ? "Checking…" : "Connect project"}
      </Button>
    </form>
  )
}
