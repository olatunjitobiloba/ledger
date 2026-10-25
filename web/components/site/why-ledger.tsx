import {
  BalanceScaleIcon,
  CheckmarkCircle02Icon,
  Coins01Icon,
  ContainerIcon,
  Database01Icon,
  FingerPrintIcon,
  GitCommitIcon,
  Shield01Icon,
  Clock01Icon,
} from "@hugeicons/core-free-icons"
import { Reveal } from "@/components/site/reveal"
import { SectionHeading } from "@/components/site/section-heading"
import { StepCard, type Step } from "@/components/site/step-card"

const steps: Step[] = [
  {
    title: "Every call gets recorded",
    description:
      "The SDK hands telemetry off and returns. Tokens, latency, cost and injection risk land in a Postgres queue your users never wait on.",
    center: { badge: "API", title: "generate_response", subtitle: "202 Accepted · queued" },
    chips: [
      { label: "Latency", icon: Clock01Icon, angle: -135, radius: 210 },
      { label: "Cost", icon: Coins01Icon, angle: -28, radius: 190 },
      { label: "Risk score", icon: Shield01Icon, angle: 122, radius: 170 },
    ],
  },
  {
    title: "Every change gets scored",
    description:
      "Candidates run against a versioned golden set, judged at temperature 0. Any case that drops past your allowed margin blocks the release.",
    center: { badge: "v2", title: "Candidate 4e1a07", subtitle: "48 trials scored" },
    chips: [
      { label: "Golden set", icon: Database01Icon, angle: -135, radius: 210 },
      { label: "Judge", icon: BalanceScaleIcon, angle: -28, radius: 190 },
      { label: "Regression gate", icon: CheckmarkCircle02Icon, angle: 122, radius: 170 },
    ],
  },
  {
    title: "Every release carries proof",
    description:
      "Results are bound to the commit, runtime and container that produced them, then exported as a bundle anyone can restore and verify offline.",
    center: { badge: "ZIP", title: "evidence.zip", subtitle: "Verified offline" },
    chips: [
      { label: "Commit", icon: GitCommitIcon, angle: -135, radius: 210 },
      { label: "Container", icon: ContainerIcon, angle: -28, radius: 190 },
      { label: "Fingerprint", icon: FingerPrintIcon, angle: 122, radius: 170 },
    ],
  },
]

export function WhyLedger() {
  return (
    <section id="why-ledger" className="scroll-mt-20 py-20 sm:py-28">
      <div className="mx-auto max-w-6xl px-5 sm:px-6">
        <Reveal>
          <SectionHeading
            eyebrow="Why Ledger"
            title="Spot-checks miss regressions. Ledger doesn't."
            description="Most teams ship model updates on a hunch. Cost is invisible until the invoice, and prompt injection is easy to ignore. Ledger turns every release into three steps you can prove."
          />
        </Reveal>

        <div className="mt-12 space-y-5 sm:mt-16 sm:space-y-6">
          {steps.map((step, i) => (
            <StepCard key={step.title} step={step} index={i} />
          ))}
        </div>
      </div>
    </section>
  )
}
