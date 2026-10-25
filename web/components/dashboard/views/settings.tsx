"use client"

import { useState, type ReactNode } from "react"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { CopyButton, PageHeader, Panel, StatusDot } from "@/components/dashboard/primitives"
import { formatDate } from "@/lib/format"
import { API_BASE } from "@/lib/ledger/api"
import { useActiveProject, useHealth } from "@/lib/ledger/hooks"
import { projectStore } from "@/lib/ledger/projects"

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid gap-1 px-5 py-4 sm:grid-cols-[12rem_1fr] sm:items-center sm:gap-6">
      <dt className="text-sm text-muted-foreground">{label}</dt>
      <dd className="min-w-0 text-sm">{children}</dd>
    </div>
  )
}

const unknown = <span className="text-muted-foreground">Not reported by the API</span>

export function SettingsView() {
  const project = useActiveProject()
  const health = useHealth()
  const [confirming, setConfirming] = useState(false)
  const online = health.data?.status === "ok"

  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        title="Settings"
        description="Ledger fixes a project's configuration at creation; the API has no endpoint to change it."
      />

      <section>
        <h2 className="mb-3 text-sm font-medium">Project</h2>
        <Panel>
          <dl className="divide-y">
            <Row label="Name">{project.name}</Row>
            <Row label="Project ID">
              <span className="flex items-center gap-1">
                <code className="truncate font-mono text-[0.8125rem]">{project.id}</code>
                <CopyButton value={project.id} label="Copy project ID" />
              </span>
            </Row>
            <Row label="Retention">
              {project.retentionDays == null ? unknown : `${project.retentionDays} days`}
            </Row>
            <Row label="Prompt capture">
              {project.capturePrompt == null
                ? unknown
                : project.capturePrompt
                  ? "On, with redaction before storage"
                  : "Off: tokens, cost and model only"}
            </Row>
            <Row label="Added to this browser">
              {formatDate(project.addedAt)} ·{" "}
              {project.source === "created" ? "created here" : "connected"}
            </Row>
          </dl>
        </Panel>
      </section>

      <section>
        <h2 className="mb-3 text-sm font-medium">Connection</h2>
        <Panel>
          <dl className="divide-y">
            <Row label="API status">
              {health.isLoading ? (
                <StatusDot tone="neutral">Checking…</StatusDot>
              ) : online ? (
                <StatusDot tone="good">Online</StatusDot>
              ) : (
                <StatusDot tone="bad">{health.error?.message ?? "Unreachable"}</StatusDot>
              )}
            </Row>
            <Row label="Endpoint">
              <code className="font-mono text-[0.8125rem]">{API_BASE}</code>
              <span className="text-muted-foreground">
                {" "}→ proxied to <code className="font-mono">LEDGER_API_URL</code>
              </span>
            </Row>
          </dl>
        </Panel>
      </section>

      <section>
        <h2 className="mb-3 text-sm font-medium">Remove project</h2>
        <Panel className="flex flex-wrap items-center justify-between gap-4 px-5 py-4">
          <p className="max-w-xl text-sm text-pretty text-muted-foreground">
            Forgets this project and its dashboard key in this browser. The
            project and its data stay on the Ledger API.
          </p>
          <Button variant="destructive" onClick={() => setConfirming(true)}>
            Remove from browser
          </Button>
        </Panel>
      </section>

      <Dialog open={confirming} onOpenChange={setConfirming}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Remove {project.name}?</DialogTitle>
            <DialogDescription>
              To reconnect later you&apos;ll need the project ID and an API key.
              Copy them first if you don&apos;t have them elsewhere.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <DialogClose render={<Button variant="outline" />}>Cancel</DialogClose>
            <Button variant="destructive" onClick={() => projectStore.remove(project.id)}>
              Remove
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
