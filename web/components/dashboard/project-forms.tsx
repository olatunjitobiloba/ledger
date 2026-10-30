"use client"

import { useState, type FormEvent } from "react"
import { HugeiconsIcon } from "@hugeicons/react"
import { Alert02Icon, ArrowRight01Icon } from "@hugeicons/core-free-icons"
import { Button } from "@/components/ui/button"
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Spinner } from "@/components/ui/spinner"
import { Switch } from "@/components/ui/switch"
import { Textarea } from "@/components/ui/textarea"
import { CopyButton, ErrorNotice } from "@/components/dashboard/primitives"
import { LedgerError, ledger } from "@/lib/ledger/api"
import { projectStore, type StoredProject } from "@/lib/ledger/projects"

/** Free-tier projects keep data for at most 7 days (POST /v1/projects). */
export const MAX_RETENTION = 7

export type CreateDraft = {
  name: string
  retention: string
  capture: boolean
  patterns: string
}

export type ConnectDraft = { name: string; projectId: string; apiKey: string }

export const emptyCreateDraft: CreateDraft = {
  name: "",
  retention: String(MAX_RETENTION),
  capture: false,
  patterns: "",
}

export const emptyConnectDraft: ConnectDraft = { name: "", projectId: "", apiKey: "" }

export function redactPatterns(draft: Pick<CreateDraft, "capture" | "patterns">) {
  return draft.capture ? draft.patterns.split("\n").map((p) => p.trim()).filter(Boolean) : []
}

export function SecretReveal({ secret }: { secret: string }) {
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2 rounded-xl border bg-muted/40 py-1.5 pr-1.5 pl-3">
        <code className="min-w-0 flex-1 truncate font-mono text-[0.8125rem]">{secret}</code>
        <CopyButton value={secret} label="Copy API key" />
      </div>
      <p className="flex gap-2 text-[0.8125rem] text-pretty text-muted-foreground">
        <HugeiconsIcon icon={Alert02Icon} className="mt-0.5 size-4 shrink-0 text-amber-500" />
        Copy it now and keep it somewhere safe. Ledger stores only a hash, so
        this key can&apos;t be shown again.
      </p>
    </div>
  )
}

function SubmitButton({ pending, idle, busy }: { pending: boolean; idle: string; busy: string }) {
  return (
    <Button type="submit" size="lg" className="self-start" disabled={pending}>
      {pending && <Spinner />}
      {pending ? busy : idle}
      {!pending && <HugeiconsIcon icon={ArrowRight01Icon} data-icon="inline-end" />}
    </Button>
  )
}

export function CreateProjectForm({
  draft,
  onDraftChange,
  onCreated,
}: {
  draft: CreateDraft
  onDraftChange: (patch: Partial<CreateDraft>) => void
  onCreated: (project: StoredProject) => void
}) {
  const [error, setError] = useState<Error | null>(null)
  const [pending, setPending] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setPending(true)
    setError(null)
    const name = draft.name.trim()
    try {
      const created = await ledger.createProject({
        name,
        capture_prompt: draft.capture,
        redact_patterns: redactPatterns(draft),
        retention_days: Number(draft.retention),
      })
      const project: StoredProject = {
        id: created.project_id,
        name,
        apiKey: created.api_key,
        retentionDays: created.retention_days,
        capturePrompt: draft.capture,
        addedAt: new Date().toISOString(),
        source: "created",
        issuedKeys: [],
      }
      projectStore.add(project)
      onCreated(project)
    } catch (err) {
      if (err instanceof LedgerError && err.status === 409) {
        setError(new Error("A project with that name already exists. Try another name."))
      } else if (err instanceof LedgerError && err.status === 500) {
        // Older API versions report a taken name as a bare server error.
        setError(
          new Error(
            "The Ledger API couldn't create the project . The name may already be taken, so try another."
          )
        )
      } else if (err instanceof LedgerError && err.status === 401) {
        // The browser never handles the token now: this means the dashboard's
        // own copy doesn't match the API's, which only its operator can fix.
        setError(
          new Error(
            "This dashboard isn't authorised to create projects. Ask whoever runs it to check its admin token."
          )
        )
      } else {
        setError(err as Error)
      }
    } finally {
      setPending(false)
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-7">
      <FieldGroup className="gap-6">
        <Field>
          <FieldLabel htmlFor="project-name">Project name</FieldLabel>
          <Input
            id="project-name"
            required
            maxLength={120}
            placeholder="support-assistant"
            className="h-10"
            value={draft.name}
            onChange={(e) => onDraftChange({ name: e.target.value })}
            autoFocus
          />
          <FieldDescription className="text-right text-xs tabular-nums">
            {draft.name.length}/120
          </FieldDescription>
        </Field>
        <Field>
          <FieldLabel htmlFor="project-retention">Keep traces for</FieldLabel>
          <div className="relative">
            <Input
              id="project-retention"
              type="number"
              required
              min={1}
              max={MAX_RETENTION}
              className="h-10 pr-14 tabular-nums"
              value={draft.retention}
              onChange={(e) => onDraftChange({ retention: e.target.value })}
            />
            <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-sm text-muted-foreground">
              days
            </span>
          </div>
          <FieldDescription>The free tier allows up to {MAX_RETENTION} days.</FieldDescription>
        </Field>
        <Field orientation="horizontal" className="items-start justify-between gap-6">
          <div className="flex flex-col gap-1"> 
            <FieldLabel htmlFor="project-capture">Capture prompts</FieldLabel>
            <FieldDescription>
              Store prompt and response text. When off, Ledger keeps only
              tokens, cost and model.
            </FieldDescription>
          </div>
          <Switch
            id="project-capture"
            checked={draft.capture}
            onCheckedChange={(capture) => onDraftChange({ capture })}
          />
        </Field>
        {draft.capture && (
          <Field className="rise-in">
            <FieldLabel htmlFor="project-redact">Redaction patterns</FieldLabel>
            <Textarea
              id="project-redact"
              rows={3}
              placeholder={"\\b\\d{16}\\b\n[\\w.]+@[\\w.]+"}
              className="font-mono text-[0.8125rem]"
              value={draft.patterns}
              onChange={(e) => onDraftChange({ patterns: e.target.value })}
            />
            <FieldDescription>
              One regular expression per line. Matches are replaced before storage.
            </FieldDescription>
          </Field>
        )}
      </FieldGroup>
      {error && <ErrorNotice title="Couldn't create the project" error={error} />}
      <SubmitButton pending={pending} idle="Create project" busy="Creating…" />
    </form>
  )
}

export function ConnectProjectForm({
  draft,
  onDraftChange,
  onConnected,
}: {
  draft: ConnectDraft
  onDraftChange: (patch: Partial<ConnectDraft>) => void
  onConnected: (project: StoredProject) => void
}) {
  const [error, setError] = useState<Error | null>(null)
  const [pending, setPending] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setPending(true)
    setError(null)
    const id = draft.projectId.trim()
    const key = draft.apiKey.trim()
    try {
      // There is no "who am I" endpoint: a one-trace read proves the key
      // belongs to this project (401 bad key, 403 another project).
      await ledger.traces(key, id, 1, 0)
      const project: StoredProject = {
        id,
        name: draft.name.trim() || id.slice(0, 8),
        apiKey: key,
        retentionDays: null,
        capturePrompt: null,
        addedAt: new Date().toISOString(),
        source: "connected",
        issuedKeys: [],
      }
      projectStore.add(project)
      onConnected(project)
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
    <form onSubmit={submit} className="flex flex-col gap-7">
      <FieldGroup className="gap-6">
        <Field>
          <FieldLabel htmlFor="connect-id">Project ID</FieldLabel>
          <Input
            id="connect-id"
            required
            className="h-10 font-mono"
            placeholder="3f6c1d2e-…"
            value={draft.projectId}
            onChange={(e) => onDraftChange({ projectId: e.target.value })}
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
            className="h-10 font-mono"
            value={draft.apiKey}
            onChange={(e) => onDraftChange({ apiKey: e.target.value })}
          />
          <FieldDescription>Any key issued for the project works.</FieldDescription>
        </Field>
        <Field>
          <FieldLabel htmlFor="connect-name">
            Display name <span className="font-normal text-muted-foreground">(optional)</span>
          </FieldLabel>
          <Input
            id="connect-name"
            maxLength={120}
            placeholder="support-assistant"
            className="h-10"
            value={draft.name}
            onChange={(e) => onDraftChange({ name: e.target.value })}
          />
          <FieldDescription>
            The API doesn&apos;t return project names, so pick one for this browser.
          </FieldDescription>
        </Field>
      </FieldGroup>
      {error && <ErrorNotice title="Couldn't connect" error={error} />}
      <SubmitButton pending={pending} idle="Connect project" busy="Checking key…" />
    </form>
  )
}
