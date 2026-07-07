import Link from "next/link";

const FEATURES = [
  {
    icon: "🤖",
    title: "Rubric Screening",
    description:
      "Score and rank candidates automatically with customizable rubrics trained on your hiring criteria.",
  },
  {
    icon: "📋",
    title: "Smart Job Descriptions",
    description:
      "Generate polished, bias-aware job postings and publish them across recruitment platforms in minutes.",
  },
  {
    icon: "👥",
    title: "Team Collaboration",
    description:
      "Role-based access for admins, recruiters, and screeners — manage your hiring workflow in one secure workspace.",
  },
  {
    icon: "⚡",
    title: "Faster Decisions",
    description:
      "Surface top talent sooner with intelligent resume parsing, matching, and pipeline visibility.",
  },
];

const STATS = [
  { value: "10×", label: "Faster resume review" },
  { value: "85%", label: "Reduction in manual screening" },
  { value: "24/7", label: "AI-assisted hiring pipeline" },
];

export default function HomePage() {
  return (
    <>
      <section className="landing-hero">
        <div className="landing-hero-inner">
          <p className="landing-eyebrow">The future of hiring runs on decisions.</p>
          <h1 className="landing-headline">
            AI Recruiter delivers trusted AI for smarter, faster recruitment.
          </h1>
          <p className="landing-lead">
            From job description creation to rubric-based resume screening, our platform
            helps recruitment teams make confident hiring decisions — at scale, with
            transparency, and without sacrificing quality.
          </p>
          <div className="landing-cta-row">
            <Link href="/login" className="landing-cta-primary">
              Explore AI recruitment solutions
            </Link>
            <Link href="/contact" className="landing-cta-secondary">
              Talk to our team
            </Link>
          </div>
        </div>
      </section>

      <section className="landing-stats">
        <div className="landing-stats-inner">
          {STATS.map((stat) => (
            <div key={stat.label} className="landing-stat">
              <span className="landing-stat-value">{stat.value}</span>
              <span className="landing-stat-label">{stat.label}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="landing-features">
        <div className="landing-features-inner">
          <div className="landing-section-header">
            <h2>Built for modern recruitment teams</h2>
            <p>
              Everything your organization needs to attract, evaluate, and hire top
              talent — powered by enterprise-grade AI.
            </p>
          </div>
          <div className="landing-feature-grid">
            {FEATURES.map((feature) => (
              <article key={feature.title} className="landing-feature-card">
                <div className="landing-feature-icon">{feature.icon}</div>
                <h3>{feature.title}</h3>
                <p>{feature.description}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="landing-cta-band">
        <div className="landing-cta-band-inner landing-cta-band-inner--stacked">
          <div>
            <h2>Ready to transform your hiring process?</h2>
            <p>Sign in to your account to get started today.</p>
          </div>
          <Link href="/login" className="landing-cta-primary">
            Sign In
          </Link>
        </div>
      </section>
    </>
  );
}
