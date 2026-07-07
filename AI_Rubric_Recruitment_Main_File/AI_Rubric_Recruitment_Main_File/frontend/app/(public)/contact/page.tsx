"use client";

import { useState } from "react";
import { submitContactForm } from "@/lib/portal-api";

export default function ContactPage() {
  const [submitted, setSubmitted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [company, setCompany] = useState("");
  const [message, setMessage] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      await submitContactForm({
        full_name: name,
        email,
        company: company || undefined,
        message,
      });
      setSubmitted(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send message");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="contact-page">
      <div className="contact-hero">
        <h1>Get in touch</h1>
        <p>
          Have questions about AI Recruiter for your organization? Our team is here to
          help you evaluate the platform and plan your rollout.
        </p>
      </div>

      <div className="contact-layout">
        <div className="contact-info">
          <h2>Contact information</h2>
          <div className="contact-info-item">
            <span className="contact-info-label">Sales &amp; demos</span>
            <a href="mailto:sales@airecruiter.com">sales@airecruiter.com</a>
          </div>
          <div className="contact-info-item">
            <span className="contact-info-label">Support</span>
            <a href="mailto:support@airecruiter.com">support@airecruiter.com</a>
          </div>
          <div className="contact-info-item">
            <span className="contact-info-label">Office hours</span>
            <span>Monday – Friday, 9:00 AM – 6:00 PM EST</span>
          </div>

          <div className="contact-highlights">
            <h3>What we can help with</h3>
            <ul>
              <li>Platform demos and pilot programs</li>
              <li>Enterprise onboarding and security reviews</li>
              <li>AI screening rubric design</li>
              <li>Integration with your ATS workflow</li>
            </ul>
          </div>
        </div>

        <div className="contact-form-card">
          {submitted ? (
            <div className="contact-success">
              <div className="contact-success-icon">✓</div>
              <h2>Thank you for reaching out</h2>
              <p>We&apos;ve received your message and will get back to you within one business day.</p>
            </div>
          ) : (
            <>
              <h2>Send us a message</h2>
              <p className="contact-form-sub">Fill out the form and we&apos;ll respond shortly.</p>
              {error && <div className="alert alert-error">{error}</div>}
              <form onSubmit={handleSubmit}>
                <div className="form-group">
                  <label className="label">Full Name</label>
                  <input
                    className="input"
                    required
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="Jane Smith"
                  />
                </div>
                <div className="form-group">
                  <label className="label">Work Email</label>
                  <input
                    className="input"
                    type="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@company.com"
                  />
                </div>
                <div className="form-group">
                  <label className="label">Company / Organization</label>
                  <input
                    className="input"
                    value={company}
                    onChange={(e) => setCompany(e.target.value)}
                    placeholder="Acme Corp"
                  />
                </div>
                <div className="form-group">
                  <label className="label">Message</label>
                  <textarea
                    className="input contact-textarea"
                    required
                    rows={5}
                    value={message}
                    onChange={(e) => setMessage(e.target.value)}
                    placeholder="Tell us about your recruitment needs..."
                  />
                </div>
                <button type="submit" className="btn btn-primary btn-full" disabled={submitting}>
                  {submitting ? "Sending..." : "Send Message"}
                </button>
              </form>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
