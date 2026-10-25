"use client"

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Panel } from "@/components/dashboard/primitives"
import { ConnectProjectForm, CreateProjectForm } from "@/components/dashboard/project-forms"

/** Shown in place of every dashboard page until a project exists in this browser. */
export function Onboarding() {
  return (
    <div className="mx-auto flex max-w-lg flex-col pt-4 sm:pt-10">
      <h1 className="text-2xl font-semibold tracking-tight">Set up your first project</h1>
      <p className="mt-2 text-sm text-pretty text-muted-foreground">
        A project groups the traces, evaluation runs and alerts for one AI
        application. No account needed: the dashboard remembers projects in
        this browser.
      </p>

      <Panel className="mt-8 bg-background p-5 sm:p-6">
        <Tabs defaultValue="create">
          <TabsList className="w-full">
            <TabsTrigger value="create">New project</TabsTrigger>
            <TabsTrigger value="connect">Connect existing</TabsTrigger>
          </TabsList>
          <TabsContent value="create" className="pt-5">
            <CreateProjectForm onDone={() => {}} />
          </TabsContent>
          <TabsContent value="connect" className="pt-5">
            <ConnectProjectForm onDone={() => {}} />
          </TabsContent>
        </Tabs>
      </Panel>
    </div>
  )
}
