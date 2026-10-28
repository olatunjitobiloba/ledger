"use client"

import { useState } from "react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { CopyButton, DetailRow, PageHeader, StatusBadge } from "@/components/dashboard/primitives"
import { formatDate } from "@/lib/format"
import { useActiveProject, useHealth } from "@/lib/ledger/hooks"
import { projectStore } from "@/lib/ledger/projects"

const unknown = <span className="text-muted-foreground">Not reported by the API</span>

export function SettingsView() {
  const project = useActiveProject()
  const health = useHealth()
  const [confirming, setConfirming] = useState(false)
  const online = health.data?.status === "ok"

  return (
    <div className="stagger flex flex-col gap-6">
      <PageHeader
        title="Settings"
        description="A project's configuration is fixed when it's created."
      />

      <Card>
        <CardHeader>
          <CardTitle>Project</CardTitle>
          <CardDescription>How Ledger stores this project&apos;s data.</CardDescription>
        </CardHeader>
        <CardContent>
          <dl className="-my-3 divide-y">
            <DetailRow label="Name">{project.name}</DetailRow>
            <DetailRow label="Project ID">
              <span className="flex items-center justify-end gap-1">
                <code className="truncate font-mono text-[0.8125rem]">{project.id}</code>
                <CopyButton value={project.id} label="Copy project ID" />
              </span>
            </DetailRow>
            <DetailRow label="Retention">
              {project.retentionDays == null ? unknown : `${project.retentionDays} days`}
            </DetailRow>
            <DetailRow label="Prompt capture">
              {project.capturePrompt == null
                ? unknown
                : project.capturePrompt
                  ? "On, redacted before storage"
                  : "Off: tokens, cost and model only"}
            </DetailRow>
            <DetailRow label="Added">
              {formatDate(project.addedAt)} ·{" "}
              {project.source === "created" ? "created here" : "connected"}
            </DetailRow>
          </dl>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Connection</CardTitle>
          <CardDescription>Checked every 30 seconds.</CardDescription>
        </CardHeader>
        <CardContent>
          <dl className="-my-3">
            <DetailRow label="Ledger API">
              {health.isLoading ? (
                <StatusBadge tone="neutral" pulse>Connecting</StatusBadge>
              ) : online ? (
                <StatusBadge tone="good">Operational</StatusBadge>
              ) : (
                <StatusBadge tone="bad">Unreachable</StatusBadge>
              )}
            </DetailRow>
          </dl>
        </CardContent>
      </Card>

      <Card className="ring-destructive/25">
        <CardHeader>
          <CardTitle>Remove project</CardTitle>
          <CardDescription className="max-w-xl text-pretty">
            Forgets this project and its dashboard key in this browser. The
            project and its data stay on the Ledger API.
          </CardDescription>
        </CardHeader>
        <CardFooter className="justify-end border-destructive/15 bg-destructive/[0.03]">
          <Button variant="destructive" onClick={() => setConfirming(true)}>
            Remove from this browser
          </Button>
        </CardFooter>
      </Card>

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
            <Button
              variant="destructive"
              onClick={() => {
                setConfirming(false)
                projectStore.remove(project.id)
                toast.success(`Removed ${project.name}`)
              }}
            >
              Remove
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
