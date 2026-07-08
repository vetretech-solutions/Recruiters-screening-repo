/**
 * Local dev: browser calls `/api/...` (Next.js proxy → BACKEND_URL).
 * Vercel: server passes BACKEND_URL at render time (see BackendConfig in layout).
 * Also supports NEXT_PUBLIC_BACKEND_URL when set at build time.
 */
let runtimeBackendUrl = "";

export function configureBackendUrl(url: string) {
  runtimeBackendUrl = url.replace(/\/$/, "");
}

function resolveBackendBase(): string {
  return (
    runtimeBackendUrl ||
    process.env.NEXT_PUBLIC_BACKEND_URL?.trim().replace(/\/$/, "") ||
    ""
  );
}

export function apiUrl(path: string): string {
  const base = resolveBackendBase();
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  if (base) return `${base}${normalizedPath}`;
  return normalizedPath;
}

export function getPortalApiBase(): string {
  return apiUrl("/api");
}

export function getRecruitmentApiBase(): string {
  return apiUrl("/api/recruitment");
}

export function getScreeningApiBase(): string {
  return apiUrl("/api/screening");
}
