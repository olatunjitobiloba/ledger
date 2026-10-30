import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion"
import { Reveal } from "@/components/site/reveal"

const faqs = [
  {
    q: "Will Ledger slow down my AI responses?",
    a: "No. The SDK fires and forgets: the ingest endpoint returns 202 Accepted and queues the work. Delivery failures are ignored on purpose, so observability can never slow down or fail your app's response.",
  },
  {
    q: "What exactly does the evaluation gate check?",
    a: "Each candidate is scored against a versioned answer key by a judge model at temperature 0. The gate compares per-case means with the baseline under an allowed absolute drop, and any case beyond it blocks the release. The release policy also checks a quality floor, security scan coverage and evidence completeness.",
  },
  {
    q: "Do you store my prompts and responses?",
    a: "Only if you want to. With capture_prompt set to false, payloads are never stored, while tokens, latency, model and cost are still recorded. When capture is on, regex redaction runs before anything is persisted, and the SDK can redact before data leaves your host. API keys are stored as SHA-256 hashes.",
  },
  {
    q: "Is a high injection score proof of an attack?",
    a: "No. Injection monitoring is heuristic: a match means suspicious wording worth a human look, not proof of an attack, and a zero score is not proof of safety. Flags request review; they never block requests.",
  },
  {
    q: "How accurate are the cost numbers?",
    a: "Ledger uses provider-reported cost when it's available and falls back to configurable per-model token pricing otherwise, so treat estimates as approximate.",
  },
  {
    q: "Can someone verify a release without access to our database?",
    a: "Yes. Evidence bundles are bound to the commit, runtime and container that produced them, and can be exported, restored and verified offline on another machine.",
  },
]

export function Faq() {
  return (
    <section id="faq" className="scroll-mt-20 py-20 sm:py-28">
      <Reveal className="mx-auto grid max-w-6xl gap-10 px-5 sm:px-6 lg:grid-cols-[1fr_1.6fr] lg:gap-16">
        <div className="lg:sticky lg:top-28 lg:self-start">
          <h2
            data-reveal
            className="text-3xl leading-[1.1] font-semibold tracking-[-0.03em] sm:text-5xl"
          >
            Questions
          </h2>
        </div>

        <Accordion data-reveal className="px-5 sm:px-7">
          {faqs.map((item) => (
            <AccordionItem key={item.q} value={item.q}>
              <AccordionTrigger className="py-5 cursor-pointer text-[0.9375rem] font-medium hover:no-underline sm:text-base">
                {item.q}
              </AccordionTrigger>
              <AccordionContent className="pb-5 text-[0.9375rem] leading-relaxed text-muted-foreground">
                <p>{item.a}</p>
              </AccordionContent>
            </AccordionItem>
          ))}
        </Accordion>
      </Reveal>
    </section>
  )
}
