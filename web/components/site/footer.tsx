import { Logo } from "@/components/site/logo"
import { navItems, site } from "@/lib/site"

const columns = [
  { title: "Product", links: navItems.map((n) => ({ ...n, external: false })) },
  {
    title: "Developers",
    links: [
      { label: "Quick start", href: site.links.quickStart, external: true },
      { label: "API contract", href: site.links.apiContract, external: true },
      { label: "Deployment", href: site.links.deployment, external: true },
    ],
  },
  {
    title: "Project",
    links: [
      { label: "GitHub", href: site.links.repo, external: true },
      { label: "Limitations", href: site.links.limitations, external: true },
    ],
  },
]

// Captured once into the static shell; refreshed whenever the page rebuilds.
async function currentYear() {
  "use cache"
  return new Date().getFullYear()
}

export async function Footer() {
  const year = await currentYear()
  return (
    <footer className="border-t">
      <div className="mx-auto max-w-6xl px-5 py-14 sm:px-6 sm:py-16">
        <div className="grid gap-10 sm:grid-cols-2 lg:grid-cols-[1.5fr_1fr_1fr_1fr]">
          <div className="max-w-xs">
            <Logo />
            <p className="mt-4 text-sm leading-relaxed text-muted-foreground">
              Observability, evaluation gates and portable release evidence for
              LLM applications.
            </p>
          </div>

          {columns.map((col) => (
            <nav key={col.title} aria-label={col.title}>
              <h3 className="text-sm font-medium">{col.title}</h3>
              <ul className="mt-4 space-y-3">
                {col.links.map((link) => (
                  <li key={link.label}>
                    <a
                      href={link.href}
                      {...(link.external && { target: "_blank", rel: "noreferrer" })}
                      className="text-sm text-muted-foreground transition-colors duration-150 hover:text-foreground"
                    >
                      {link.label}
                    </a>
                  </li>
                ))}
              </ul>
            </nav>
          ))}
        </div>

        <div className="mt-14 flex flex-col gap-2 border-t pt-6 text-[0.8125rem] text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
          <p>© {year} Ledger. Built for Rumpty Cloud.</p>
          <p className="inline-flex items-center gap-2">
            <span className="size-1.5 rounded-full bg-brand" />
            Every release, with evidence.
          </p>
        </div>
      </div>
    </footer>
  )
}
