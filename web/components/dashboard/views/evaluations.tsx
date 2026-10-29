"use client"

import { useState, type FormEvent } from "react"
import { HugeiconsIcon } from "@hugeicons/react"
import { Delete02Icon, PlusSignIcon, TestTube01Icon } from "@hugeicons/core-free-icons"
import { toast } from "sonner"
import { cn } from "cn"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
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
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import { Skeleton } from "@/components/ui/skeleton"
import { Spinner } from "@/components/ui/spinner"
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
  CopyButton,
  DetailRow,
  EmptyState,
  ErrorNotice,
  EvalResult,
  PageHeader,
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
  const [model, setModel] = useState("")
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
        model: model.trim() || undefined,
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
            <Field className="sm:col-span-2">
              <FieldLabel htmlFor="eval-model">
                Model <span className="font-normal text-muted-foreground">(optional)</span>
              </FieldLabel>
              <Input
                id="eval-model"
                maxLength={120}
                placeholder="gpt-4o-mini"
                value={model}
                onChange={(e) => setModel(e.target.value)}
              />
              <FieldDescription>The model that produced these responses.</FieldDescription>
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
                <HugeiconsIcon icon={PlusSignIcon} />
                Add case
              </Button>
            </div>
            {cases.map((c, i) => (
              <div key={i} className="rise-in flex flex-col gap-2 rounded-xl border bg-muted/40 p-3">
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
                      <HugeiconsIcon icon={Delete02Icon} />
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

          {error && <ErrorNotice title="Couldn't queue the evaluation" error={error} />}
          <DialogFooter>
            <Button type="submit" disabled={pending}>
              {pending && <Spinner />}
              {pending ? "Queuing…" : "Run evaluation"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}


/** The run's score on a 0–100 track, with its gate marked. */
function ScoreMeter({ run }: { run: EvalRun }) {
  const gate = Math.min(Math.max(gateOf(run), 0), 100)
  const score = run.result_score
  return (
    <div>
      <div className="relative h-2 rounded-full bg-muted">
        {score != null && (
          <div
            className={cn(
              "h-full origin-left rounded-full transition-transform duration-500 ease-out-strong",
              run.passed ? "bg-brand" : "bg-destructive"
            )}
            style={{ transform: `scaleX(${Math.min(Math.max(score, 0), 100) / 100})` }}
          />
        )}
        <span
          aria-hidden="true"
          className="absolute -top-1 -bottom-1 w-0.5 -translate-x-1/2 rounded-full bg-foreground"
          style={{ left: `${gate}%` }}
        />
      </div>
      <div className="mt-2 flex justify-between text-xs text-muted-foreground tabular-nums">
        <span>0</span>
        <span>Gate {formatScore(gateOf(run))}</span>
        <span>100</span>
      </div>
    </div>
  )
}

function RunSheet({ run, onClose }: { run: EvalRun | null; onClose: () => void }) {
  // Keep showing the last run while the sheet animates out.
  const [shown, setShown] = useState<EvalRun | null>(run)
  if (run && run !== shown) setShown(run)
  const r = run ?? shown

  return (
    <Sheet open={run !== null} onOpenChange={(open) => !open && onClose()}>
      <SheetContent className="w-full gap-0 sm:max-w-lg">
        {r && (
          <>
            <SheetHeader className="border-b p-5">
              <SheetTitle className="flex items-center gap-2.5">
                {r.config_id}
                <EvalResult run={r} />
              </SheetTitle>
              <SheetDescription>
                Dataset {r.dataset_version}
                {r.model && ` · ${r.model}`}
              </SheetDescription>
            </SheetHeader>

            <div className="flex flex-col gap-6 overflow-y-auto p-5">
              <div className="grid grid-cols-3 gap-3">
                {[
                  ["Score", formatScore(r.result_score)],
                  ["Gate", formatScore(gateOf(r))],
                  ["Baseline", formatScore(r.baseline_score)],
                ].map(([label, value]) => (
                  <Card key={label} size="sm" className="gap-1 px-3.5">
                    <span className="text-xs text-muted-foreground">{label}</span>
                    <span className="text-lg font-semibold tabular-nums">{value}</span>
                  </Card>
                ))}
              </div>

              <ScoreMeter run={r} />

              <dl className="-my-3 divide-y">
                <DetailRow label="Allowed drop">
                  <span className="tabular-nums">{formatScore(r.variance)}</span>
                </DetailRow>
                <DetailRow label="Run ID">
                  <span className="flex items-center justify-end gap-1">
                    <code className="font-mono text-[0.8125rem]">{shortId(r.eval_run_id)}…</code>
                    <CopyButton value={r.eval_run_id} label="Copy run ID" />
                  </span>
                </DetailRow>
              </dl>

              <div>
                <h3 className="text-sm font-medium">Lowest-scoring cases</h3>
                {r.worst_cases.length ? (
                  <ul className="mt-3 flex flex-col gap-2.5">
                    {r.worst_cases.map((c) => (
                      <li key={c.index}>
                        <Card size="sm" className="gap-2 px-3.5">
                          <div className="flex items-center justify-between text-xs">
                            <span className="text-muted-foreground">Case {c.index + 1}</span>
                            <span className="font-mono font-medium tabular-nums">
                              {formatScore(c.score * 100)}
                            </span>
                          </div>
                          <p className="text-sm leading-relaxed text-pretty">{c.reasoning}</p>
                          {c.flags.length > 0 && (
                            <div className="flex flex-wrap gap-1.5">
                              {c.flags.map((flag) => (
                                <Badge key={flag} variant="secondary" className="font-mono">
                                  {flag}
                                </Badge>
                              ))}
                            </div>
                          )}
                        </Card>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="mt-2 text-sm text-pretty text-muted-foreground">
                    {r.status === "failed"
                      ? "The judge returned no scores for this run, so it couldn't be gated."
                      : r.status === "completed"
                        ? "Every case scored well. Nothing to review."
                        : "Case scores appear once the run is judged."}
                  </p>
                )}
              </div>
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  )
}

export function EvaluationsView() {
  const { data, error, isLoading, mutate } = useEvalRuns()
  const [creating, setCreating] = useState(false)
  const [selected, setSelected] = useState<EvalRun | null>(null)
  const runs = data?.items ?? []

  const newButton = (size: "default" | "sm" = "default") => (
    <Button size={size} onClick={() => setCreating(true)}>
      <HugeiconsIcon icon={PlusSignIcon} />
      New evaluation
    </Button>
  )

  return (
    <div className="stagger flex flex-col gap-6">
      <PageHeader
        title="Evaluations"
        description="Golden-set runs scored by the judge, newest first. Select a run to see its weakest cases."
        actions={newButton()}
      />

      {error && <ErrorNotice title="Couldn't load evaluations" error={error} onRetry={() => mutate()} />}

      <Card className="gap-0 py-0">
        {isLoading ? (
          <div className="flex flex-col gap-3 p-5">
            {Array.from({ length: 4 }, (_, i) => (
              <Skeleton key={i} className="h-8 w-full" />
            ))}
          </div>
        ) : runs.length === 0 ? (
          <EmptyState icon={TestTube01Icon} title="No evaluation runs yet" action={newButton("sm")}>
            Submit prompts with the responses your app produced. Ledger judges
            each one and checks the mean against your baseline.
          </EmptyState>
        ) : (
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead className="pl-5">Config</TableHead>
                <TableHead className="hidden md:table-cell">Model</TableHead>
                <TableHead className="hidden sm:table-cell">Dataset</TableHead>
                <TableHead className="text-right">Score</TableHead>
                <TableHead className="hidden text-right sm:table-cell">Gate</TableHead>
                <TableHead className="pr-5">Result</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {runs.map((run) => (
                <TableRow
                  key={run.eval_run_id}
                  tabIndex={0}
                  className="cursor-pointer outline-none focus-visible:bg-muted/60"
                  onClick={() => setSelected(run)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault()
                      setSelected(run)
                    }
                  }}
                >
                  <TableCell className="pl-5 font-medium">{run.config_id}</TableCell>
                  <TableCell className="hidden text-muted-foreground md:table-cell">{run.model ?? "—"}</TableCell>
                  <TableCell className="hidden text-muted-foreground sm:table-cell">{run.dataset_version}</TableCell>
                  <TableCell className="text-right font-mono tabular-nums">
                    {formatScore(run.result_score)}
                  </TableCell>
                  <TableCell className="hidden text-right font-mono text-muted-foreground tabular-nums sm:table-cell">
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
      </Card>

      <NewEvaluationDialog open={creating} onOpenChange={setCreating} />
      <RunSheet run={selected} onClose={() => setSelected(null)} />
    </div>
  )
}
