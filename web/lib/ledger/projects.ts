"use client"

import { useSyncExternalStore } from "react"

/**
 * The Ledger API has no endpoint to list projects or keys, and the dashboard
 * has no accounts. Projects created or connected here are remembered in this
 * browser only, together with the key the dashboard uses to read them.
 */

export type IssuedKey = { name: string; prefix: string; createdAt: string }

export type StoredProject = {
  id: string
  name: string
  apiKey: string
  /** Unknown for connected projects: the API never returns it after creation. */
  retentionDays: number | null
  capturePrompt: boolean | null
  addedAt: string
  source: "created" | "connected"
  issuedKeys: IssuedKey[]
}

type State = {
  projects: StoredProject[]
  activeId: string | null
  guideDismissed: boolean
}

const STORAGE_KEY = "ledger.dashboard.v1"
const EMPTY: State = { projects: [], activeId: null, guideDismissed: false }

const listeners = new Set<() => void>()
let cachedRaw: string | null | undefined
let cachedState: State = EMPTY

function read(): State {
  let raw: string | null = null
  try {
    raw = localStorage.getItem(STORAGE_KEY)
  } catch {}
  // useSyncExternalStore needs a stable snapshot between changes.
  if (raw === cachedRaw) return cachedState
  cachedRaw = raw
  try {
    cachedState = raw ? { ...EMPTY, ...JSON.parse(raw) } : EMPTY
  } catch {
    cachedState = EMPTY
  }
  return cachedState
}

function write(update: (state: State) => State) {
  const next = update(read())
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
  } catch {}
  listeners.forEach((listener) => listener())
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  const onStorage = (event: StorageEvent) => {
    if (event.key === STORAGE_KEY) listener()
  }
  window.addEventListener("storage", onStorage)
  return () => {
    listeners.delete(listener)
    window.removeEventListener("storage", onStorage)
  }
}

/** `null` until the browser store has been read (server render and hydration). */
export function useProjectState(): State | null {
  return useSyncExternalStore(subscribe, read, () => null)
}

export function activeProject(state: State): StoredProject | null {
  return (
    state.projects.find((project) => project.id === state.activeId) ??
    state.projects[0] ??
    null
  )
}

export const projectStore = {
  add(project: StoredProject) {
    write((state) => ({
      ...state,
      projects: [...state.projects.filter((p) => p.id !== project.id), project],
      activeId: project.id,
    }))
  },
  select(id: string) {
    write((state) => ({ ...state, activeId: id }))
  },
  remove(id: string) {
    write((state) => {
      const projects = state.projects.filter((p) => p.id !== id)
      return {
        ...state,
        projects,
        activeId: state.activeId === id ? (projects[0]?.id ?? null) : state.activeId,
      }
    })
  },
  recordKey(id: string, key: IssuedKey) {
    write((state) => ({
      ...state,
      projects: state.projects.map((p) =>
        p.id === id ? { ...p, issuedKeys: [key, ...p.issuedKeys] } : p
      ),
    }))
  },
  dismissGuide() {
    write((state) => ({ ...state, guideDismissed: true }))
  },
}

/** The API stores the first 12 characters of each key as its prefix. */
export function keyPrefix(secret: string) {
  return secret.slice(0, 12)
}
