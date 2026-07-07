"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { portalApi } from "@/lib/portal-api";
import { defaultRouteForRole } from "@/lib/portal-nav";
import { hasValidSession, saveSession, getStoredUser } from "@/lib/session";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (hasValidSession()) {
      const user = getStoredUser();
      router.replace(defaultRouteForRole(user?.role || ""));
    }
  }, [router]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await portalApi.login(email, password);
      saveSession(res.access_token, res.user);
      router.push(defaultRouteForRole(res.user.role));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-page">
      <div className="login-form-side">
        <div className="login-form-inner">
          <div className="login-card">
            <h2>Sign In</h2>
            <p className="subtitle">Welcome back — sign in to your account</p>

            <form onSubmit={handleSubmit}>
              <div className="form-group">
                <label className="label">Email</label>
                <input
                  className="input"
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="Email *"
                />
              </div>
              <div className="form-group">
                <label className="label">Password</label>
                <div className="login-password-wrap">
                  <input
                    className="input"
                    type={showPassword ? "text" : "password"}
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Password *"
                  />
                  <button
                    type="button"
                    className="login-password-toggle"
                    onClick={() => setShowPassword((v) => !v)}
                    aria-label={showPassword ? "Hide password" : "Show password"}
                  >
                    {showPassword ? (
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                        <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94" />
                        <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19" />
                        <line x1="1" y1="1" x2="23" y2="23" />
                      </svg>
                    ) : (
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                        <circle cx="12" cy="12" r="3" />
                      </svg>
                    )}
                  </button>
                </div>
              </div>

              {error && <div className="alert alert-error">{error}</div>}

              <div className="login-actions-row">
                <button className="btn btn-primary" disabled={loading}>
                  {loading ? "Signing in..." : "Sign In"}
                </button>
                <a href="/contact" className="login-forgot-link">
                  Forgot Password?
                </a>
              </div>
            </form>

            <p className="login-register-link">
              Don&apos;t have an account? <a href="/register">Register And Sign In</a>
            </p>
            <p className="login-back-home">
              <a href="/">← Back to Home</a>
            </p>
          </div>
        </div>
      </div>

      <div className="login-hero">
        <div className="login-hero-content">
          <p className="login-hero-eyebrow">The future of hiring runs on decisions.</p>
          <h1>Trusted AI for smarter hiring decisions.</h1>
          <p>
            AI-powered recruitment, team collaboration, and intelligent resume
            screening — built for teams that demand speed without sacrificing quality.
          </p>
          <div className="login-features">
            <div className="login-feature">
              <div className="login-feature-icon">👥</div>
              <span>Role-based access for admins, recruiters &amp; screeners</span>
            </div>
            <div className="login-feature">
              <div className="login-feature-icon">📋</div>
              <span>AI job descriptions &amp; multi-platform posting</span>
            </div>
            <div className="login-feature">
              <div className="login-feature-icon">🤖</div>
              <span>Rubric-based resume screening at scale</span>
            </div>
          </div>
        </div>

        <div className="login-hero-visual" aria-hidden="true">
          <div className="login-phone-mock">
            <div className="login-phone-screen">
              <div className="login-phone-avatar" />
              <div className="login-phone-field" />
              <div className="login-phone-field login-phone-field--dots">•••••</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
