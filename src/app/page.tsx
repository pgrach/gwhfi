import { Navbar } from "@/components/landing/navbar";
import { HeroSection } from "@/components/landing/sections/hero";
import { ProblemSection } from "@/components/landing/sections/problem";
import { SolutionSection } from "@/components/landing/sections/solution";
import { HowItWorksSection } from "@/components/landing/sections/how-it-works";
import { DashboardPreviewSection } from "@/components/landing/sections/dashboard-preview";
import { NumbersSection } from "@/components/landing/sections/numbers";
import { PartnersSection } from "@/components/landing/sections/partners";
import { AboutSection } from "@/components/landing/sections/about";
import { RoadmapSection } from "@/components/landing/sections/roadmap";
import { CTASection } from "@/components/landing/sections/cta";
import { Footer } from "@/components/landing/sections/footer";

export default function Home() {
    return (
        <div className="landing">
            <Navbar />
            <main>
                <HeroSection />
                <ProblemSection />
                <SolutionSection />
                <HowItWorksSection />
                <DashboardPreviewSection />
                <NumbersSection />
                <PartnersSection />
                <AboutSection />
                <RoadmapSection />
                <CTASection />
            </main>
            <Footer />
        </div>
    );
}
