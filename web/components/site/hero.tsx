"use client"

import { useRef } from "react"
import Link from "next/link"
import { HugeiconsIcon } from "@hugeicons/react"
import {
  ArrowRight01Icon,
  GithubIcon,
  Tick02Icon,
} from "@hugeicons/core-free-icons"
import { cn } from "cn"
import { buttonVariants } from "@/components/ui/button"
import { EASE_OUT, MOTION_OK, gsap, useGSAP } from "@/lib/gsap"
import { site } from "@/lib/site"

const checks = [
  { name: "regression", detail: "mean 0.912 → 0.904 · allowed drop 0.05" },
  { name: "quality floor", detail: "48 / 48 trials at or above 0.70" },
  { name: "security", detail: "96 fields scanned · 0 rules matched" },
  { name: "coverage", detail: "every trial scored · judge cost attributed" },
]

export function Hero() {
  const ref = useRef<HTMLElement>(null)

  useGSAP(
    () => {
      const mm = gsap.matchMedia()
      mm.add(MOTION_OK, () => {
        gsap
          .timeline({ defaults: { ease: EASE_OUT } })
          .fromTo(
            "[data-hero]",
            { autoAlpha: 0, y: 16 },
            { autoAlpha: 1, y: 0, duration: 0.8, stagger: 0.08 }
          )
          .fromTo(
            "[data-mockup]",
            { autoAlpha: 0, y: 32 },
            { autoAlpha: 1, y: 0, duration: 1 },
            "-=0.5"
          )
          // The terminal "runs": each check prints, then the decision lands.
          .fromTo(
            "[data-line]",
            { autoAlpha: 0, x: -6 },
            { autoAlpha: 1, x: 0, duration: 0.4, stagger: 0.14 },
            "-=0.5"
          )
          .fromTo(
            "[data-decision]",
            { autoAlpha: 0, scale: 0.96 },
            { autoAlpha: 1, scale: 1, duration: 0.5 },
            "+=0.1"
          )
      })
    },
    { scope: ref }
  )

  return (
    <section ref={ref} className="relative overflow-hidden">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 -top-40 mx-auto h-[520px] max-w-4xl rounded-full blur-2xl"
      />

      <div className="relative mx-auto max-w-6xl px-5 pt-14 pb-20 sm:px-6 sm:pt-24 sm:pb-28">
        <div className="mx-auto flex max-w-3xl flex-col items-center text-center">
        

          <h1
            data-reveal
            data-hero
            className="mt-6 text-[2.5rem] leading-[1.05] font-semibold tracking-[-0.035em] text-balance sm:text-6xl lg:text-7xl"
          >
            Ship model changes{" "}
            <span className="text-muted-foreground">with proof, not hope.</span>
          </h1>

          <p
            data-reveal
            data-hero
            className="mt-5 max-w-xl text-base leading-relaxed text-pretty text-muted-foreground sm:text-lg"
          >
            Ledger records cost and risk on every AI call without slowing it
            down, scores each release against your golden set, and blocks the
            ones that regress.
          </p>

          <div
            data-reveal
            data-hero
            className="mt-8 flex w-full flex-col gap-3 sm:w-auto sm:flex-row"
          >
            <Link
              href="/dashboard"
              className={cn(buttonVariants({ size: "lg" }), "group")}
            >
              Get started
              <HugeiconsIcon
                icon={ArrowRight01Icon}
                className="transition-transform duration-150 ease-out group-hover:translate-x-0.5"
              />
            </Link>
            <a
              href={site.links.repo}
              target="_blank"
              rel="noreferrer"
              className={buttonVariants({ size: "lg", variant: "outline" })}
            >
              <HugeiconsIcon icon={GithubIcon} />
              View on GitHub
            </a>
          </div>

        </div>

        <div data-reveal data-mockup className="relative mx-auto mt-14 max-w-4xl sm:mt-20">
          <div
            aria-hidden="true"
            className="absolute -inset-x-6 -inset-y-8 rounded-[2.5rem] bg-[radial-gradient(closest-side,rgb(0_211_147/0.12),transparent)] blur-2xl"
          />
          <figure className="relative overflow-hidden rounded-2xl border bg-card shadow-2xl shadow-black/10 dark:shadow-black/50">
            <div className="flex items-center gap-2 border-b px-4 py-3">
              <span className="size-2.5 rounded-full bg-[#FF6369]" />
              <span className="size-2.5 rounded-full bg-[#E48338]" />
              <span className="size-2.5 rounded-full bg-[#37A175]" />
              <figcaption className="ml-2 truncate font-mono text-xs text-muted-foreground">
                release_policy check
              </figcaption>
            </div>

            <div className="overflow-x-auto p-5 font-mono text-[0.8125rem] leading-7 sm:p-7 sm:text-sm">
              <p data-reveal data-line className="whitespace-nowrap">
                <span className="text-muted-foreground select-none">$ </span>
                python -m ledger.pipeline.release_policy check{" "}
                <span className="text-muted-foreground">
                  --baseline 9f2c41e0 --candidate 4e1a07b3
                </span>
              </p>
              <p data-reveal data-line className="mt-3 text-muted-foreground">
                policy <span className="ml-3">ledger-release-policy-v1</span>
              </p>

              <ul className="mt-3 space-y-1">
                {checks.map((check) => (
                  <li
                    key={check.name}
                    data-reveal
                    data-line
                    className="grid grid-cols-[7.5rem_auto] items-center gap-x-4 sm:grid-cols-[8.5rem_4.5rem_1fr]"
                  >
                    <span className="text-muted-foreground">{check.name}</span>
                    <span className="inline-flex items-center gap-1.5 font-medium">
                      <span className="size-1.5 rounded-full bg-brand" />
                      PASS
                    </span>
                    <span className="hidden truncate text-muted-foreground sm:block">
                      {check.detail}
                    </span>
                  </li>
                ))}
              </ul>

              <div
                data-reveal
                data-decision
                className="mt-5 flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-dashed pt-5"
              >
                <span className="w-[7.5rem] text-muted-foreground sm:w-[8.5rem]">
                  decision
                </span>
                <span className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-2.5 py-0.5 font-sans text-xs font-semibold tracking-wide text-primary-foreground">
                  <HugeiconsIcon icon={Tick02Icon} className="size-3.5" strokeWidth={2.5} />
                  READY
                </span>
                <span className="font-sans text-xs text-muted-foreground">
                  Configured checks passed on the tested cases.
                </span>
              </div>
            </div>
          </figure>
        </div>
      </div>
    </section>
  )
}
