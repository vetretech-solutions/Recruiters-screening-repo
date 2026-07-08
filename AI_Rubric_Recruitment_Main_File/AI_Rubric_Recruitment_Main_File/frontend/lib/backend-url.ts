/**
 * Local dev: browser calls `/api/...` (Next.js proxy → BACKEND_URL).
 * Vercel: layout injects window.__BACKEND_URL__ at request time.
 */
let runtimeBackendUrl = "";

declare global {
  interface Window {
    __BACKEND_URL__?: string;
  }
}

export function configureBackendUrl(url: string) {
  runtimeBackendUrl = url.replace(/\/$/, "");
}

function resolveBackendBase(): string {
  if (typeof window !== "undefined" && window.__BACKEND_URL__) {
    return window.__BACKEND_URL__.replace(/\/$/, "");
  }
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
