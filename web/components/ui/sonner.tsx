"use client"

import { useSyncExternalStore } from "react"
import { Toaster as Sonner, type ToasterProps } from "sonner"
import { HugeiconsIcon } from "@hugeicons/react"
import {
  Alert02Icon,
  CancelCircleIcon,
  CheckmarkCircle02Icon,
  InformationCircleIcon,
  Loading03Icon,
} from "@hugeicons/core-free-icons"

// The site toggles a `dark` class on <html> (see lib/theme-script.ts) rather
// than using next-themes, so follow that class directly.
function subscribe(onChange: () => void) {
  const observer = new MutationObserver(onChange)
  observer.observe(document.documentElement, { attributeFilter: ["class"] })
  return () => observer.disconnect()
}

function useDocumentTheme(): "dark" | "light" {
  return useSyncExternalStore(
    subscribe,
    () =>
      document.documentElement.classList.contains("dark") ? "dark" : "light",
    () => "dark"
  )
}

const Toaster = ({ ...props }: ToasterProps) => {
  const theme = useDocumentTheme()

  return (
    <Sonner
      theme={theme}
      className="toaster group"
      icons={{
        success: <HugeiconsIcon icon={CheckmarkCircle02Icon} className="size-4 text-brand" />,
        info: <HugeiconsIcon icon={InformationCircleIcon} className="size-4" />,
        warning: <HugeiconsIcon icon={Alert02Icon} className="size-4 text-amber-500" />,
        error: <HugeiconsIcon icon={CancelCircleIcon} className="size-4 text-destructive" />,
        loading: <HugeiconsIcon icon={Loading03Icon} className="size-4 animate-spin" />,
      }}
      style={
        {
          "--normal-bg": "var(--popover)",
          "--normal-text": "var(--popover-foreground)",
          "--normal-border": "var(--border)",
          "--border-radius": "var(--radius)",
        } as React.CSSProperties
      }
      toastOptions={{
        classNames: {
          toast: "cn-toast",
        },
      }}
      {...props}
    />
  )
}

export { Toaster }
