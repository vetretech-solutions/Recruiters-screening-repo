"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { portalApi } from "@/lib/portal-api";
import { defaultRouteForRole } from "@/lib/portal-nav";
import { saveSession } from "@/lib/session";

export default function RegisterPage() {
  const router = useRouter();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (password !== confirm) {
      setError("Passwords do not match");
      return;
    }
    setError("");
    setLoading(true);
    try {
      const res = await portalApi.register({
        full_name: fullName,
        email,
        password,
      });
      saveSession(res.access_token, res.user);
      router.push(defaultRouteForRole(res.user.role));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-page">
      <div className="login-form-side">
        <div className="login-form-inner">
          <div className="login-card">
            <h2>Create Account</h2>
            <p className="subtitle">Sign up to start using AI Recruiter</p>

            <form onSubmit={handleSubmit}>
              <div className="form-group">
                <label className="label">Full Name</label>
                <input
                  className="input"
                  required
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                />
              </div>
              <div className="form-group">
                <label className="label">Email</label>
                <input
                  className="input"
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </div>
              <div className="form-group">
                <label className="label">Password</label>
                <input
                  className="input"
                  type="password"
                  required
                  minLength={8}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </div>
              <div className="form-group">
                <label className="label">Confirm Password</label>
                <input
                  className="input"
                  type="password"
                  required
                  minLength={8}
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                />
              </div>
              {error && <div className="alert alert-error">{error}</div>}
              <button className="btn btn-primary btn-full" disabled={loading}>
                {loading ? "Creating account..." : "Create Account"}
              </button>
            </form>

            <p className="login-register-link">
              Already have an account? <a href="/login">Sign in</a>
            </p>
            <p className="login-back-home">
              <a href="/">← Back to Home</a>
            </p>
          </div>
        </div>
      </div>

      <div className="login-hero">
        <div className="login-hero-content">
          <p className="login-hero-eyebrow">Get started today</p>
          <h1>Launch your AI recruitment workspace.</h1>
          <p>
            Create your account to publish jobs, screen resumes with AI, and
            manage your hiring pipeline — all in one secure platform.
          </p>
        </div>
      </div>
    </div>
  );
}
