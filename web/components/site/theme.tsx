"use client"

import { HugeiconsIcon } from "@hugeicons/react"
import { Moon02Icon, Sun03Icon } from "@hugeicons/core-free-icons"
import { Button } from "@/components/ui/button"
import { THEME_COLORS, THEME_STORAGE_KEY } from "@/lib/theme-script"

export function applyTheme(theme: "dark" | "light") {
  const root = document.documentElement

  // Suppress every transition for one frame so colors swap at once instead of
  // each element easing at its own pace.
  const style = document.createElement("style")
  style.textContent = "*,*::before,*::after{transition:none!important}"
  document.head.appendChild(style)

  root.classList.toggle("dark", theme === "dark")
  document
    .querySelector('meta[name="theme-color"]')
    ?.setAttribute("content", THEME_COLORS[theme])
  try {
    localStorage.setItem(THEME_STORAGE_KEY, theme)
  } catch {}

  // Force a style flush so the new colors commit while transitions are off.
  void window.getComputedStyle(document.body).opacity
  requestAnimationFrame(() => style.remove())
}

export function ThemeToggle() {
  return (
    <Button
      variant="ghost"
      size="icon"
      aria-label="Toggle color theme"
      onClick={() =>
        applyTheme(
          document.documentElement.classList.contains("dark") ? "light" : "dark"
        )
      }
    >
      {/* Both icons render; CSS picks one, so server and client markup match. */}
      <HugeiconsIcon icon={Sun03Icon} className="hidden size-[18px] dark:block" />
      <HugeiconsIcon icon={Moon02Icon} className="size-[18px] dark:hidden" />
    </Button>
  )
}
