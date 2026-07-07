"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import BrandMark from "@/components/BrandMark";

type PublicShellProps = {
  children: React.ReactNode;
  variant?: "default" | "auth";
};

const NAV_LINKS = [
  { href: "/", label: "Home" },
  { href: "/contact", label: "Contact" },
];

export default function PublicShell({ children, variant = "default" }: PublicShellProps) {
  const pathname = usePathname();
  const isAuth = variant === "auth";

  function isActive(href: string) {
    if (href === "/") return pathname === "/";
    return pathname.startsWith(href);
  }

  return (
    <div className={`public-site${isAuth ? " public-site--auth" : ""}`}>
      <header className="public-header">
        <div className="public-header-inner">
          <BrandMark />

          <nav className="public-nav" aria-label="Main navigation">
            {NAV_LINKS.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                className={`public-nav-link${isActive(link.href) ? " active" : ""}`}
              >
                {link.label}
              </Link>
            ))}
          </nav>

          <div className="public-header-actions">
            <Link href="/login" className="public-icon-btn" title="Sign in" aria-label="Sign in">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                <circle cx="12" cy="7" r="4" />
              </svg>
            </Link>
            {!isAuth && (
              <Link href="/register" className="public-btn-outline">
                Sign Up
              </Link>
            )}
            {pathname !== "/" && pathname !== "/login" && pathname !== "/register" && (
              <Link href="/login" className="public-btn-primary">
                Sign In
              </Link>
            )}
          </div>
        </div>

        <div className="public-subheader">
          <div className="public-subheader-inner">
            <span className="public-subheader-label">AI Recruitment Solutions</span>
            <Link href="/login" className="public-subheader-cta">
              Get Started
            </Link>
          </div>
        </div>
      </header>

      <main className="public-main">{children}</main>

      <footer className="public-footer">
        <p>
          Powered by AI Recruiter Software &nbsp;|&nbsp; © {new Date().getFullYear()}. All rights reserved.
        </p>
      </footer>
    </div>
  );
}
