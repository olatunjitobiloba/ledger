"use client"

import { useState, type FormEvent, type ReactNode } from "react"
import { HugeiconsIcon } from "@hugeicons/react"
import { Key01Icon, PlusSignIcon } from "@hugeicons/core-free-icons"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Spinner } from "@/components/ui/spinner"
import { CopyButton, ErrorNotice, PageHeader } from "@/components/dashboard/primitives"
import { SecretReveal } from "@/components/dashboard/project-forms"
import { formatDate, maskKey } from "@/lib/format"
import { ledger } from "@/lib/ledger/api"
import { useActiveProject } from "@/lib/ledger/hooks"
import { keyPrefix, projectStore } from "@/lib/ledger/projects"

function IssueKeyDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
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
      <DialogContent className="sm:max-w-md" showCloseButton={!secret}>
        <DialogHeader>
          <DialogTitle>{secret ? "Key created" : "Issue API key"}</DialogTitle>
          <DialogDescription>
            {secret
              ? "Give this key to the service that sends traces or runs evaluations."
              : `Creates another key for ${project.name}.`}
          </DialogDescription>
        </DialogHeader>
        {secret ? (
          <div className="rise-in flex flex-col gap-5">
            <SecretReveal secret={secret} />
            <DialogFooter>
              <DialogClose render={<Button />}>Done</DialogClose>
            </DialogFooter>
          </div>
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
            {error && <ErrorNotice title="Couldn't create the key" error={error} />}
            <DialogFooter>
              <Button type="submit" disabled={pending}>
                {pending && <Spinner />}
                {pending ? "Creating…" : "Create key"}
              </Button>
            </DialogFooter>
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
  badge,
  children,
}: {
  name: string
  prefix: string
  meta: string
  badge?: ReactNode
  children?: ReactNode
}) {
  return (
    <li className="flex flex-wrap items-center gap-x-4 gap-y-2 px-5 py-4">
      <span className="flex size-9 shrink-0 items-center justify-center rounded-lg border bg-muted/50">
        <HugeiconsIcon icon={Key01Icon} className="size-4 text-muted-foreground" />
      </span>
      <div className="min-w-0 flex-1">
        <p className="flex items-center gap-2 text-sm font-medium">
          {name}
          {badge}
        </p>
        <p className="mt-0.5 text-xs text-muted-foreground">{meta}</p>
      </div>
      <code className="font-mono text-[0.8125rem] text-muted-foreground">{maskKey(prefix)}</code>
      <div className="flex w-6 justify-end">{children}</div>
    </li>
  )
}

export function ApiKeysView() {
  const project = useActiveProject()
  const [issuing, setIssuing] = useState(false)

  return (
    <div className="stagger flex flex-col gap-6">
      <PageHeader
        title="API keys"
        description="Keys authenticate the SDK and API calls for this project."
        actions={
          <Button onClick={() => setIssuing(true)}>
            <HugeiconsIcon icon={PlusSignIcon} />
            Issue key
          </Button>
        }
      />

      <Card className="gap-0 py-0">
        <ul className="divide-y">
          <KeyRow
            name="Dashboard key"
            prefix={keyPrefix(project.apiKey)}
            meta={`Added ${formatDate(project.addedAt)}`}
            badge={<Badge variant="secondary">This browser</Badge>}
          >
            <CopyButton value={project.apiKey} label="Copy key" />
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
      </Card>

      <p className="text-xs text-pretty text-muted-foreground">
        Only keys issued from this browser are listed. Ledger stores keys as
        hashes, so a key can only be copied when it&apos;s created.
      </p>

      <IssueKeyDialog open={issuing} onOpenChange={setIssuing} />
    </div>
  )
}
