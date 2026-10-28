"use client"

import { useRef } from "react"
import { HugeiconsIcon, type IconSvgElement } from "@hugeicons/react"
import { cn } from "cn"
import { EASE_OUT, MOTION_OK, ScrollTrigger, gsap, useGSAP } from "@/lib/gsap"

export type Step = {
  title: string
  description: string
  center: { badge: string; title: string; subtitle: string }
  /** Three chips placed around the rings: polar angle in degrees, radius in px. */
  chips: { label: string; icon: IconSvgElement; angle: number; radius: number }[]
}

const RINGS = [95, 160, 225]
const STAGE = 520

/** Where the first card sticks (just under the header), in px. */
const STACK_TOP = 88
/** How much of each older card stays visible above the next one, in px. */
const STACK_PEEK = 18
/** Scale lost per card stacked on top. */
const STACK_SHRINK = 0.04

const stackTop = (i: number) => STACK_TOP + i * STACK_PEEK

/**
 * On large screens the cards pin under the header and pile up as you scroll:
 * each newer card sticks a little lower, while the ones beneath shrink from
 * their top edge and dim, leaving a strip of each visible. Smaller screens get
 * a plain list, since a pinned card taller than the viewport would hide its
 * own bottom half.
 */
export function StepStack({ steps, className }: { steps: Step[]; className?: string }) {
  const ref = useRef<HTMLDivElement>(null)

  useGSAP(
    () => {
      const mm = gsap.matchMedia()
      mm.add(`(min-width: 1024px) and ${MOTION_OK}`, () => {
        const items = gsap.utils.toArray<HTMLElement>("[data-stack-item]")
        const last = items[items.length - 1]

        items.slice(0, -1).forEach((item, i) => {
          const depth = items.length - 1 - i
          // Shrink from the moment this card pins until the last one lands.
          const scrollTrigger = {
            trigger: item,
            start: `top ${stackTop(i)}px`,
            endTrigger: last,
            end: `top ${stackTop(items.length - 1)}px`,
            scrub: true,
          }
          gsap.to(item, {
            scale: 1 - depth * STACK_SHRINK,
            transformOrigin: "50% 0%",
            ease: "none",
            scrollTrigger,
          })
          gsap.to(item.querySelector("[data-stack-shade]"), {
            opacity: Math.min(0.18 * depth, 0.5),
            ease: "none",
            scrollTrigger,
          })
        })
      })
    },
    { scope: ref }
  )

  return (
    // Spacing must be `gap`, not `space-y`: sticky items count their own
    // margins against the container edge, which would unpin them early.
    <div ref={ref} className={cn("flex flex-col gap-5 sm:gap-6 lg:gap-16", className)}>
      {steps.map((step, i) => (
        <div
          key={step.title}
          data-stack-item
          className="lg:sticky lg:top-(--stack-top)"
          style={{ "--stack-top": `${stackTop(i)}px` } as React.CSSProperties}
        >
          <StepCard step={step} index={i} />
        </div>
      ))}
    </div>
  )
}

export function StepCard({ step, index }: { step: Step; index: number }) {
  const ref = useRef<HTMLElement>(null)
  const number = String(index + 1).padStart(2, "0")

  useGSAP(
    () => {
      const mm = gsap.matchMedia()
      mm.add(MOTION_OK, () => {
        gsap
          .timeline({
            defaults: { ease: EASE_OUT },
            scrollTrigger: { trigger: ref.current, start: "top 80%", once: true },
          })
          .fromTo(ref.current, { autoAlpha: 0, y: 24 }, { autoAlpha: 1, y: 0, duration: 0.8 })
          .fromTo(
            "[data-chip]",
            { autoAlpha: 0, scale: 0.92 },
            { autoAlpha: 1, scale: 1, duration: 0.6, stagger: 0.08 },
            "-=0.45"
          )

        // Ambient motion: slow ring drift, floating chips, and a pulse leaving
        // the center card. It only runs while the card is on screen.
        const ambient = gsap.timeline({ paused: true })
        ambient
          .to(
            "[data-ring]",
            {
              rotation: (i: number) => (i % 2 ? -360 : 360),
              duration: (i: number) => 90 + i * 30,
              ease: "none",
              repeat: -1,
            },
            0
          )
          .to(
            "[data-float]",
            {
              y: (i: number) => (i % 2 ? 5 : -5),
              duration: (i: number) => 2.6 + i * 0.5,
              ease: "sine.inOut",
              yoyo: true,
              repeat: -1,
            },
            0
          )
          .fromTo(
            "[data-pulse]",
            { scale: 0.92, autoAlpha: 0.45 },
            {
              scale: 1.6,
              autoAlpha: 0,
              duration: 2.4,
              ease: "power2.out",
              repeat: -1,
              repeatDelay: 0.6,
            },
            0
          )

        ScrollTrigger.create({
          trigger: ref.current,
          start: "top bottom",
          end: "bottom top",
          onToggle: (self) => (self.isActive ? ambient.play() : ambient.pause()),
        })
      })
    },
    { scope: ref }
  )

  return (
    <article
      ref={ref}
      data-reveal
      className="relative grid overflow-hidden rounded-[1.75rem] border bg-card shadow-[0_-12px_40px_-12px_rgb(0_0_0/0.12)] lg:grid-cols-2 dark:shadow-[0_-12px_40px_-12px_rgb(0_0_0/0.6)]"
    >
      {/* Darkens the card as newer cards stack over it (see StepStack). */}
      <div
        data-stack-shade
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 z-10 bg-background opacity-0"
      />
      <div className="flex flex-col justify-between gap-12 bg-foreground/[0.025] p-7 sm:p-10 lg:min-h-[26rem]">
        <span
          aria-hidden="true"
          className="text-[5.5rem] leading-none font-semibold tracking-[-0.06em] text-muted-foreground/70 tabular-nums sm:text-[7.5rem]"
        >
          {number}
        </span>
        <div>
          <h3 className="text-[1.375rem] leading-snug font-semibold tracking-tight sm:text-2xl">
            {step.title}
          </h3>
          <p className="mt-3 max-w-md text-[0.9375rem] leading-relaxed text-muted-foreground">
            {step.description}
          </p>
        </div>
      </div>

      <div className="relative h-[22rem] overflow-hidden sm:h-[26rem] lg:h-auto" aria-hidden="true">
        <div
          className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2"
          style={{ width: STAGE, height: STAGE }}
        >
          <div className="relative size-full origin-center scale-[0.72] sm:scale-90 lg:scale-100">
            {RINGS.map((r) => (
              <div
                key={r}
                data-ring
                className="absolute top-1/2 left-1/2 rounded-full border border-dashed border-foreground/15"
                style={{ width: r * 2, height: r * 2, marginLeft: -r, marginTop: -r }}
              />
            ))}

            {step.chips.map((chip) => {
              const rad = (chip.angle * Math.PI) / 180
              return (
                <div
                  key={chip.label}
                  className="absolute -translate-x-1/2 -translate-y-1/2"
                  style={{
                    left: STAGE / 2 + Math.cos(rad) * chip.radius,
                    top: STAGE / 2 + Math.sin(rad) * chip.radius,
                  }}
                >
                  <div data-float>
                    <div
                      data-chip
                      data-reveal
                      className="flex items-center gap-2.5 rounded-full border bg-card py-1.5 pr-4 pl-1.5 shadow-lg shadow-black/5 dark:shadow-black/40"
                    >
                      <span className="flex size-8 items-center justify-center rounded-full bg-primary/15">
                        <HugeiconsIcon icon={chip.icon} className="size-4" />
                      </span>
                      <span className="text-sm font-semibold whitespace-nowrap">{chip.label}</span>
                    </div>
                  </div>
                </div>
              )
            })}

            <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2">
              <div
                data-pulse
                className="absolute inset-0 rounded-2xl border border-brand/50 opacity-0"
              />
              <div
                data-chip
                data-reveal
                className="relative flex items-center gap-3 rounded-2xl border bg-card py-3 pr-5 pl-3 shadow-xl shadow-black/5 dark:shadow-black/50"
              >
                <span className="flex size-9 items-center justify-center rounded-lg bg-primary text-[0.6875rem] font-bold text-primary-foreground">
                  {step.center.badge}
                </span>
                <span>
                  <span className="block text-[0.9375rem] font-semibold whitespace-nowrap">
                    {step.center.title}
                  </span>
                  <span className="block text-[0.8125rem] whitespace-nowrap text-muted-foreground">
                    {step.center.subtitle}
                  </span>
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </article>
  )
}
