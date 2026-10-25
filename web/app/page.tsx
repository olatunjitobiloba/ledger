import { Faq } from "@/components/site/faq";
import { Features } from "@/components/site/features";
import { Footer } from "@/components/site/footer";
import { Header } from "@/components/site/header";
import { Hero } from "@/components/site/hero";
import { WhyLedger } from "@/components/site/why-ledger";

export default function Home() {
  return (
    <>
      <Header />
      <main className="flex-1">
        <Hero />
        <Features />
        <WhyLedger />
        <Faq />
      </main>
      <Footer />
    </>
  );
}
