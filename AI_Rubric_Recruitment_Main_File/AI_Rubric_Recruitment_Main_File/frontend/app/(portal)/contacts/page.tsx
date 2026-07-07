"use client";

import { useCallback, useEffect, useState } from "react";
import { ContactSubmission, portalApi } from "@/lib/portal-api";
import { defaultRouteForRole } from "@/lib/portal-nav";
import { getStoredUser } from "@/lib/session";
import { useRouter } from "next/navigation";

function formatDate(iso: string) {
  try {
    return new Date(iso).toLocaleString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function truncate(text: string, max = 80) {
  if (text.length <= max) return text;
  return `${text.slice(0, max).trim()}…`;
}

export default function ContactsPage() {
  const router = useRouter();
  const me = getStoredUser();
  const isSuperAdmin = me?.role === "super_admin";

  const [items, setItems] = useState<ContactSubmission[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(10);
  const [q, setQ] = useState("");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<ContactSubmission | null>(null);

  useEffect(() => {
    if (!isSuperAdmin) {
      router.replace(defaultRouteForRole(me?.role || ""));
    }
  }, [isSuperAdmin, router]);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await portalApi.listContactSubmissions(page, pageSize, search);
      setItems(res.items);
      setTotal(res.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load contact inquiries");
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, search]);

  useEffect(() => {
    if (isSuperAdmin) load();
  }, [isSuperAdmin, load]);

  if (!isSuperAdmin) return null;

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div>
      <h2 style={{ fontSize: "1.5rem", fontWeight: 700, marginBottom: "0.25rem" }}>
        Contact Inquiries
      </h2>
      <p style={{ color: "var(--muted)", marginBottom: "1rem" }}>
        Messages submitted from the public contact page
      </p>

      {error && <div className="alert alert-error">{error}</div>}

      <div className="users-toolbar">
        <input
          className="input"
          placeholder="Search by name, email, or company..."
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && (setPage(1), setSearch(q))}
          style={{ flex: 1, minWidth: 220 }}
        />
        <button className="btn btn-secondary" onClick={() => { setPage(1); setSearch(q); }}>
          Search
        </button>
      </div>

      {loading ? (
        <p>Loading...</p>
      ) : (
        <>
          <table className="data-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Email</th>
                <th>Company</th>
                <th>Message</th>
                <th>Submitted</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.length === 0 ? (
                <tr>
                  <td colSpan={6} style={{ textAlign: "center", color: "var(--muted)" }}>
                    No contact inquiries yet
                  </td>
                </tr>
              ) : (
                items.map((item) => (
                  <tr key={item.id}>
                    <td>{item.full_name}</td>
                    <td>
                      <a href={`mailto:${item.email}`}>{item.email}</a>
                    </td>
                    <td>{item.company || "—"}</td>
                    <td style={{ maxWidth: 280 }}>{truncate(item.message)}</td>
                    <td>{formatDate(item.created_at)}</td>
                    <td>
                      <button
                        className="btn btn-secondary"
                        style={{ padding: "0.35rem 0.65rem", fontSize: "0.8rem" }}
                        onClick={() => setSelected(item)}
                      >
                        View
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>

          <div className="pagination">
            <button
              className="btn btn-secondary"
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
            >
              Previous
            </button>
            <span style={{ color: "var(--muted)", fontSize: "0.9rem" }}>
              Page {page} of {totalPages} ({total} total)
            </span>
            <button
              className="btn btn-secondary"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </button>
          </div>
        </>
      )}

      {selected && (
        <div className="modal-overlay" onClick={() => setSelected(null)}>
          <div className="modal-card" onClick={(e) => e.stopPropagation()}>
            <h3 style={{ marginBottom: "0.5rem" }}>{selected.full_name}</h3>
            <p style={{ color: "var(--muted)", marginBottom: "1rem", fontSize: "0.9rem" }}>
              <a href={`mailto:${selected.email}`}>{selected.email}</a>
              {selected.company ? ` · ${selected.company}` : ""}
              <br />
              {formatDate(selected.created_at)}
            </p>
            <p style={{ whiteSpace: "pre-wrap", lineHeight: 1.6 }}>{selected.message}</p>
            <div style={{ marginTop: "1.25rem" }}>
              <button type="button" className="btn btn-secondary" onClick={() => setSelected(null)}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
