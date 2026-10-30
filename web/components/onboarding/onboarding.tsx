"use client"

import { useLayoutEffect, useState } from "react"
import Link from "next/link"
import { useRouter, useSearchParams } from "next/navigation"
import { HugeiconsIcon } from "@hugeicons/react"
import { FolderAddIcon, Link01Icon } from "@hugeicons/core-free-icons"
import { toast } from "sonner"
import { Tabs, TabsContent, TabsIndicator, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Logo } from "@/components/site/logo"
import { ThemeToggle } from "@/components/site/theme"
import {
  ConnectProjectForm,
  CreateProjectForm,
  emptyConnectDraft,
  emptyCreateDraft,
  type ConnectDraft,
  type CreateDraft,
} from "@/components/dashboard/project-forms"
import { OnboardingPreview } from "@/components/onboarding/preview"
import { useProjectState } from "@/lib/ledger/projects"

type Mode = "create" | "connect"

const triggerClass =
  "relative z-10 h-full gap-2 rounded-md text-[0.8125rem] transition-colors duration-200 ease-out data-active:bg-transparent data-active:shadow-none dark:data-active:border-transparent dark:data-active:bg-transparent"

export function Onboarding() {
  const router = useRouter()
  const params = useSearchParams()
  const state = useProjectState()
  const hasProjects = (state?.projects.length ?? 0) > 0

  const linked: Mode = params.get("mode") === "connect" ? "connect" : "create"
  const [mode, setMode] = useState<Mode>(linked)
  // The sidebar links here with ?mode=, possibly while this page is kept alive.
  const [lastLinked, setLastLinked] = useState(linked)
  if (linked !== lastLinked) {
    setLastLinked(linked)
    setMode(linked)
  }

  const [create, setCreate] = useState<CreateDraft>(emptyCreateDraft)
  const [connect, setConnect] = useState<ConnectDraft>(emptyConnectDraft)

  // Next keeps visited pages alive while hidden. Drop the API key typed here
  // as soon as the page is hidden so it never lingers in the DOM.
  useLayoutEffect(() => () => setConnect((draft) => ({ ...draft, apiKey: "" })), [])

  function finish(message: string, description?: string) {
    setCreate(emptyCreateDraft)
    setConnect(emptyConnectDraft)
    toast.success(message, { description })
    router.push("/dashboard")
  }

  return (
    <div className="grid min-h-dvh lg:grid-cols-2">
      <div className="flex flex-col">
        <header className="flex h-16 items-center justify-between px-6 sm:px-8">
          <Logo />
          <div className="flex items-center gap-1">
            <ThemeToggle />
            <Link
              href={hasProjects ? "/dashboard" : "/"}
              className="rounded-md px-2 py-1 text-sm text-muted-foreground transition-colors duration-150 hover:text-foreground"
            >
              {hasProjects ? "Back to dashboard" : "Back to website"}
            </Link>
          </div>
        </header>

        <main className="flex flex-1 items-center justify-center px-6 py-12 sm:px-8">
          <Tabs
            value={mode}
            onValueChange={(value) => setMode(value as Mode)}
            className="stagger w-full max-w-sm gap-10"
          >
            <TabsList className="relative w-full p-1 group-data-horizontal/tabs:h-10">
              <TabsIndicator />
              <TabsTrigger value="create" className={triggerClass}>
                <HugeiconsIcon icon={FolderAddIcon} />
                Create new
              </TabsTrigger>
              <TabsTrigger value="connect" className={triggerClass}>
                <HugeiconsIcon icon={Link01Icon} />
                Connect existing
              </TabsTrigger>
            </TabsList>

            <TabsContent value="create" className="swap-in">
              <h1 className="text-3xl font-semibold tracking-tight text-balance">
                {hasProjects ? "Create a project" : "Create your first project"}
              </h1>
              <p className="mt-2 mb-8 text-sm text-pretty text-muted-foreground">
                A project groups the traces, evaluation runs and alerts for one
                AI application.
              </p>
              <CreateProjectForm
                draft={create}
                onDraftChange={(patch) => setCreate((draft) => ({ ...draft, ...patch }))}
                onCreated={(project) =>
                  finish(`${project.name} is ready`, "Copy its API key any time from API keys.")
                }
              />
            </TabsContent>

            <TabsContent value="connect" className="swap-in">
              <h1 className="text-3xl font-semibold tracking-tight text-balance">
                Connect a project
              </h1>
              <p className="mt-2 mb-8 text-sm text-pretty text-muted-foreground">
                Open a project that already exists on your Ledger API with its
                ID and one of its API keys.
              </p>
              <ConnectProjectForm
                draft={connect}
                onDraftChange={(patch) => setConnect((draft) => ({ ...draft, ...patch }))}
                onConnected={(project) => finish(`Connected ${project.name}`)}
              />
            </TabsContent>
          </Tabs>
        </main>
      </div>

      <aside className="relative hidden items-center justify-center overflow-hidden border-l bg-muted/50 px-12 py-16 lg:flex">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -top-40 -right-40 size-[32rem] rounded-full bg-brand/10 blur-3xl dark:bg-brand/[0.06]"
        />
        <div className="relative w-full max-w-md">
          <OnboardingPreview mode={mode} create={create} connect={connect} />
        </div>
      </aside>
    </div>
  )
}
