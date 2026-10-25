"use client"

import { useState, type FormEvent } from "react"
import { BeakerIcon, PlusIcon, TrashIcon } from "@heroicons/react/24/outline"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Textarea } from "@/components/ui/textarea"
import {
  EmptyState,
  ErrorNotice,
  EvalResult,
  PageHeader,
  Panel,
  gateOf,
} from "@/components/dashboard/primitives"
import { formatScore, shortId } from "@/lib/format"
import { ledger } from "@/lib/ledger/api"
import { useActiveProject, useEvalRuns, useRevalidate } from "@/lib/ledger/hooks"
import type { EvalRun } from "@/lib/ledger/types"

type Case = { prompt: string; response: string }

const MAX_CASES = 500

function NewEvaluationDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const { apiKey } = useActiveProject()
  const revalidate = useRevalidate()
  const [configId, setConfigId] = useState("")
  const [dataset, setDataset] = useState("v1")
  const [baseline, setBaseline] = useState("80")
  const [variance, setVariance] = useState("5")
  const [cases, setCases] = useState<Case[]>([{ prompt: "", response: "" }])
  const [error, setError] = useState<Error | null>(null)
  const [pending, setPending] = useState(false)

  const gate = Number(baseline) - Number(variance)
  const updateCase = (index: number, patch: Partial<Case>) =>
    setCases((all) => all.map((c, i) => (i === index ? { ...c, ...patch } : c)))

  async function submit(event: FormEvent) {
    event.preventDefault()
    setPending(true)
    setError(null)
    try {
      await ledger.runEval(apiKey, {
        config_id: configId.trim(),
        dataset_version: dataset.trim(),
        baseline_score: Number(baseline),
        variance: Number(variance),
        cases: cases.map((c) => ({ prompt: c.prompt.trim(), response: c.response.trim() })),
      })
      toast.success("Evaluation queued", {
        description: `${cases.length} ${cases.length === 1 ? "case" : "cases"} will be judged in the background.`,
      })
      revalidate("eval-runs")
      onOpenChange(false)
      setCases([{ prompt: "", response: "" }])
    } catch (err) {
      setError(err as Error)
    } finally {
      setPending(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[calc(100dvh-2rem)] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>New evaluation</DialogTitle>
          <DialogDescription>
            Ledger&apos;s judge scores each response to its prompt. The run passes
            when the mean score stays at or above the gate.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="flex flex-col gap-5">
          <FieldGroup className="grid gap-4 sm:grid-cols-2">
            <Field>
              <FieldLabel htmlFor="eval-config">Config ID</FieldLabel>
              <Input
                id="eval-config"
                required
                maxLength={120}
                placeholder="prompt-v7"
                value={configId}
                onChange={(e) => setConfigId(e.target.value)}
                autoFocus
              />
            </Field>
            <Field>
              <FieldLabel htmlFor="eval-dataset">Dataset version</FieldLabel>
              <Input
                id="eval-dataset"
                required
                maxLength={120}
                value={dataset}
                onChange={(e) => setDataset(e.target.value)}
              />
            </Field>
            <Field>
              <FieldLabel htmlFor="eval-baseline">Baseline score</FieldLabel>
              <Input
                id="eval-baseline"
                type="number"
                required
                min={0}
                max={100}
                step="any"
                value={baseline}
                onChange={(e) => setBaseline(e.target.value)}
              />
            </Field>
            <Field>
              <FieldLabel htmlFor="eval-variance">Allowed drop</FieldLabel>
              <Input
                id="eval-variance"
                type="number"
                required
                min={0}
                max={100}
                step="any"
                value={variance}
                onChange={(e) => setVariance(e.target.value)}
              />
            </Field>
            <FieldDescription className="sm:col-span-2">
              Scores run 0–100. Gate:{" "}
              <span className="font-medium text-foreground tabular-nums">
                {Number.isFinite(gate) ? formatScore(gate) : "—"}
              </span>
            </FieldDescription>
          </FieldGroup>

          <div className="flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium">
                Cases <span className="font-normal text-muted-foreground">({cases.length})</span>
              </p>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                disabled={cases.length >= MAX_CASES}
                onClick={() => setCases((all) => [...all, { prompt: "", response: "" }])}
              >
                <PlusIcon />
                Add case
              </Button>
            </div>
            {cases.map((c, i) => (
              <div key={i} className="flex flex-col gap-2 rounded-xl border bg-muted/50 p-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-muted-foreground">Case {i + 1}</span>
                  {cases.length > 1 && (
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon-xs"
                      aria-label={`Remove case ${i + 1}`}
                      onClick={() => setCases((all) => all.filter((_, j) => j !== i))}
                    >
                      <TrashIcon />
                    </Button>
                  )}
                </div>
                <Textarea
                  required
                  rows={2}
                  aria-label={`Case ${i + 1} prompt`}
                  placeholder="Prompt"
                  value={c.prompt}
                  onChange={(e) => updateCase(i, { prompt: e.target.value })}
                />
                <Textarea
                  required
                  rows={2}
                  aria-label={`Case ${i + 1} response`}
                  placeholder="Response your app produced"
                  value={c.response}
                  onChange={(e) => updateCase(i, { response: e.target.value })}
                />
              </div>
            ))}
          </div>

          {error && <ErrorNotice error={error} />}
          <DialogFooter>
            <Button type="submit" disabled={pending}>
              {pending ? "Queuing…" : "Run evaluation"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function RunDetails({ run, onClose }: { run: EvalRun | null; onClose: () => void }) {
  return (
    <Dialog open={run !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[calc(100dvh-2rem)] overflow-y-auto sm:max-w-lg">
        {run && (
          <>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-3">
                {run.config_id}
                <EvalResult run={run} />
              </DialogTitle>
              <DialogDescription>
                Dataset {run.dataset_version} · run{" "}
                <code className="font-mono">{shortId(run.eval_run_id)}</code>
              </DialogDescription>
            </DialogHeader>
            <dl className="grid grid-cols-3 gap-px overflow-hidden rounded-xl border bg-border">
              {[
                ["Score", formatScore(run.result_score)],
                ["Gate", formatScore(gateOf(run))],
                ["Baseline", `${formatScore(run.baseline_score)} − ${formatScore(run.variance)}`],
              ].map(([label, value]) => (
                <div key={label} className="bg-muted px-3 py-2.5">
                  <dt className="text-xs text-muted-foreground">{label}</dt>
                  <dd className="mt-0.5 font-medium tabular-nums">{value}</dd>
                </div>
              ))}
            </dl>
            <div>
              <h3 className="text-sm font-medium">Lowest-scoring cases</h3>
              {run.worst_cases.length ? (
                <ul className="mt-3 flex flex-col gap-2">
                  {run.worst_cases.map((c) => (
                    <li key={c.index} className="rounded-xl border p-3">
                      <div className="flex items-center justify-between text-xs">
                        <span className="text-muted-foreground">Case {c.index + 1}</span>
                        <span className="font-mono font-medium tabular-nums">
                          {formatScore(c.score * 100)}
                        </span>
                      </div>
                      <p className="mt-1.5 text-sm leading-relaxed text-pretty">{c.reasoning}</p>
                      {c.flags.length > 0 && (
                        <p className="mt-2 flex flex-wrap gap-1.5">
                          {c.flags.map((flag) => (
                            <span key={flag} className="rounded-md bg-muted px-1.5 py-0.5 font-mono text-xs">
                              {flag}
                            </span>
                          ))}
                        </p>
                      )}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-2 text-sm text-muted-foreground">
                  {run.status === "failed"
                    ? "The judge returned no scores for this run. Check that the API has a judge provider key configured."
                    : "Case scores appear once the run is judged."}
                </p>
              )}
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}

export function EvaluationsView() {
  const { data, error, isLoading } = useEvalRuns()
  const [creating, setCreating] = useState(false)
  const [selected, setSelected] = useState<EvalRun | null>(null)
  const runs = data?.items ?? []

  const newButton = (
    <Button onClick={() => setCreating(true)}>
      <PlusIcon />
      New evaluation
    </Button>
  )

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Evaluations"
        description="Golden-set runs scored by the judge, newest first. Select a run to see its weakest cases."
        actions={newButton}
      />

      {error && <ErrorNotice error={error} />}

      <Panel>
        {isLoading ? (
          <div className="space-y-3 p-5">
            {Array.from({ length: 4 }, (_, i) => (
              <Skeleton key={i} className="h-8 w-full" />
            ))}
          </div>
        ) : runs.length === 0 ? (
          <EmptyState icon={BeakerIcon} title="No evaluation runs yet">
            Submit prompts with the responses your app produced. Ledger judges
            each one and checks the mean against your baseline.
          </EmptyState>
        ) : (
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead className="pl-5">Config</TableHead>
                <TableHead>Dataset</TableHead>
                <TableHead className="text-right">Score</TableHead>
                <TableHead className="text-right">Gate</TableHead>
                <TableHead className="pr-5">Result</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {runs.map((run) => (
                <TableRow
                  key={run.eval_run_id}
                  className="cursor-pointer"
                  tabIndex={0}
                  onClick={() => setSelected(run)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault()
                      setSelected(run)
                    }
                  }}
                >
                  <TableCell className="pl-5 font-medium">{run.config_id}</TableCell>
                  <TableCell className="text-muted-foreground">{run.dataset_version}</TableCell>
                  <TableCell className="text-right font-mono tabular-nums">
                    {formatScore(run.result_score)}
                  </TableCell>
                  <TableCell className="text-right font-mono text-muted-foreground tabular-nums">
                    {formatScore(gateOf(run))}
                  </TableCell>
                  <TableCell className="pr-5">
                    <EvalResult run={run} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Panel>

      <NewEvaluationDialog open={creating} onOpenChange={setCreating} />
      <RunDetails run={selected} onClose={() => setSelected(null)} />
    </div>
  )
}
