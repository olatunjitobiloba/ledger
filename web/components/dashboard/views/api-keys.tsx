"use client"

import { useState, type FormEvent } from "react"
import { EyeIcon, EyeSlashIcon, KeyIcon, PlusIcon } from "@heroicons/react/24/outline"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { CopyButton, ErrorNotice, PageHeader, Panel } from "@/components/dashboard/primitives"
import { SecretReveal } from "@/components/dashboard/project-forms"
import { formatDate } from "@/lib/format"
import { ledger } from "@/lib/ledger/api"
import { useActiveProject } from "@/lib/ledger/hooks"
import { keyPrefix, projectStore } from "@/lib/ledger/projects"

function IssueKeyDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const project = useActiveProject()
  const [name, setName] = useState("")
  const [secret, setSecret] = useState<string | null>(null)
  const [error, setError] = useState<Error | null>(null)
  const [pending, setPending] = useState(false)

  function close() {
    onOpenChange(false)
    // Wait out the exit animation before clearing the one-time secret.
    setTimeout(() => {
      setSecret(null)
      setName("")
      setError(null)
    }, 200)
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    setPending(true)
    setError(null)
    try {
      const keyName = name.trim() || "default"
      const created = await ledger.createApiKey(project.apiKey, keyName)
      // Only the name and prefix are kept; the secret is shown once below.
      projectStore.recordKey(project.id, {
        name: keyName,
        prefix: keyPrefix(created.api_key),
        createdAt: new Date().toISOString(),
      })
      setSecret(created.api_key)
    } catch (err) {
      setError(err as Error)
    } finally {
      setPending(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => (next ? onOpenChange(true) : close())}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{secret ? "Key created" : "Issue API key"}</DialogTitle>
          <DialogDescription>
            {secret
              ? "Give this key to the service that sends traces or runs evaluations."
              : `Creates another key for ${project.name}. Keys can't be revoked from the API yet.`}
          </DialogDescription>
        </DialogHeader>
        {secret ? (
          <SecretReveal secret={secret} onDone={close} />
        ) : (
          <form onSubmit={submit} className="flex flex-col gap-5">
            <FieldGroup>
              <Field>
                <FieldLabel htmlFor="key-name">Name</FieldLabel>
                <Input
                  id="key-name"
                  maxLength={120}
                  placeholder="production-backend"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  autoFocus
                />
              </Field>
            </FieldGroup>
            {error && <ErrorNotice error={error} />}
            <Button type="submit" className="self-end" disabled={pending}>
              {pending ? "Creating…" : "Create key"}
            </Button>
          </form>
        )}
      </DialogContent>
    </Dialog>
  )
}

function KeyRow({
  name,
  prefix,
  meta,
  children,
}: {
  name: string
  prefix: string
  meta: string
  children?: React.ReactNode
}) {
  return (
    <li className="flex flex-wrap items-center gap-x-4 gap-y-2 px-5 py-4">
      <div className="flex size-9 shrink-0 items-center justify-center rounded-lg border bg-background">
        <KeyIcon className="size-4 text-muted-foreground" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium">{name}</p>
        <p className="mt-0.5 text-xs text-muted-foreground">{meta}</p>
      </div>
      <code className="font-mono text-[0.8125rem] text-muted-foreground">{prefix}…</code>
      {children}
    </li>
  )
}

export function ApiKeysView() {
  const project = useActiveProject()
  const [issuing, setIssuing] = useState(false)
  const [revealed, setRevealed] = useState(false)

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="API keys"
        description="Keys authenticate the SDK and API calls for this project."
        actions={
          <Button onClick={() => setIssuing(true)}>
            <PlusIcon />
            Issue key
          </Button>
        }
      />

      <Panel>
        <ul className="divide-y">
          <KeyRow
            name="Dashboard key"
            prefix={keyPrefix(project.apiKey)}
            meta={`Used by this dashboard · added ${formatDate(project.addedAt)}`}
          >
            <div className="flex items-center gap-1">
              <Button
                variant="ghost"
                size="icon-xs"
                aria-label={revealed ? "Hide key" : "Reveal key"}
                className="text-muted-foreground hover:text-foreground"
                onClick={() => setRevealed((r) => !r)}
              >
                {revealed ? <EyeSlashIcon /> : <EyeIcon />}
              </Button>
              <CopyButton value={project.apiKey} label="Copy dashboard key" />
            </div>
            {revealed && (
              <code className="w-full rounded-lg border bg-background px-3 py-2 font-mono text-[0.8125rem] break-all">
                {project.apiKey}
              </code>
            )}
          </KeyRow>
          {project.issuedKeys.map((key) => (
            <KeyRow
              key={key.prefix + key.createdAt}
              name={key.name}
              prefix={key.prefix}
              meta={`Issued ${formatDate(key.createdAt)}`}
            />
          ))}
        </ul>
      </Panel>

      <p className="text-xs text-pretty text-muted-foreground">
        The Ledger API has no endpoint to list keys, so this page shows the
        dashboard&apos;s own key and the keys issued from this browser. Ledger
        stores keys as SHA-256 hashes.
      </p>

      <IssueKeyDialog open={issuing} onOpenChange={setIssuing} />
    </div>
  )
}
