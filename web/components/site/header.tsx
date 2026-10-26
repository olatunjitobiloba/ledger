"use client"

import { useEffect, useState } from "react"
import { HugeiconsIcon } from "@hugeicons/react"
import { GithubIcon, Menu01Icon } from "@hugeicons/core-free-icons"
import { cn } from "cn"
import { Button, buttonVariants } from "@/components/ui/button"
import {
  Sheet,
  SheetContent,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet"
import { Logo } from "@/components/site/logo"
import { ThemeToggle } from "@/components/site/theme"
import { navItems, site } from "@/lib/site"

export function Header() {
  const [scrolled, setScrolled] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8)
    onScroll()
    window.addEventListener("scroll", onScroll, { passive: true })
    return () => window.removeEventListener("scroll", onScroll)
  }, [])

  return (
    <header
      className={cn(
        "sticky top-0 z-40 border-b transition-[background-color,border-color] duration-200 ease-out",
        scrolled
          ? "border-border bg-background/80 backdrop-blur-xl"
          : "border-transparent bg-transparent"
      )}
    >
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-6 px-5 sm:px-6">
        <Logo />

        <nav aria-label="Main" className="hidden md:block">
          <ul className="flex items-center gap-1">
            {navItems.map((item) => (
              <li key={item.href}>
                <a
                  href={item.href}
                  className="rounded-lg px-3 py-2 text-sm text-muted-foreground transition-colors duration-150 hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
                >
                  {item.label}
                </a>
              </li>
            ))}
            <li>
              <a
                href={site.links.repo}
                target="_blank"
                rel="noreferrer"
                className="rounded-lg px-3 py-2 text-sm text-muted-foreground transition-colors duration-150 hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
              >
                Docs
              </a>
            </li>
          </ul>
        </nav>

        <div className="flex items-center gap-1.5">
          <a
            href={site.links.repo}
            target="_blank"
            rel="noreferrer"
            aria-label="Ledger on GitHub"
            className={cn(
              buttonVariants({ variant: "ghost", size: "icon" }),
              "hidden sm:inline-flex"
            )}
          >
            <HugeiconsIcon icon={GithubIcon} className="size-[18px]" />
          </a>
          <ThemeToggle />
          <a
            href={site.links.quickStart}
            target="_blank"
            rel="noreferrer"
            className={cn(buttonVariants(), "ml-1 hidden sm:inline-flex")}
          >
            Get started
          </a>

          <Sheet open={menuOpen} onOpenChange={setMenuOpen}>
            <SheetTrigger
              render={
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label="Open menu"
                  className="md:hidden"
                />
              }
            >
              <HugeiconsIcon icon={Menu01Icon} className="size-5" />
            </SheetTrigger>
            <SheetContent side="right" className="w-[86%] gap-0 p-0">
              <div className="flex h-16 items-center border-b px-5">
                <SheetTitle className="text-base font-semibold">Menu</SheetTitle>
              </div>
              <nav aria-label="Mobile" className="flex flex-col p-3">
                {[...navItems, { label: "Docs", href: site.links.repo }].map(
                  (item) => (
                    <a
                      key={item.label}
                      href={item.href}
                      onClick={() => setMenuOpen(false)}
                      className="rounded-xl px-3 py-3 text-[0.9375rem] font-medium transition-colors duration-150 hover:bg-muted"
                    >
                      {item.label}
                    </a>
                  )
                )}
              </nav>
              <div className="mt-auto border-t p-5">
                <a
                  href={site.links.quickStart}
                  target="_blank"
                  rel="noreferrer"
                  className={cn(buttonVariants({ size: "lg" }), "w-full")}
                >
                  Get started
                </a>
              </div>
            </SheetContent>
          </Sheet>
        </div>
      </div>
    </header>
  )
}
