/**
 * Local dev: browser calls `/api/...` (Next.js proxy → BACKEND_URL).
 * Vercel/production: set NEXT_PUBLIC_BACKEND_URL to your Railway URL so
 * uploads and long screening streams bypass Vercel's ~10s serverless limit.
 */
function normalizeBase(url: string): string {
  return url.replace(/\/$/, "");
}

export function apiUrl(path: string): string {
  const direct = process.env.NEXT_PUBLIC_BACKEND_URL?.trim();
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  if (direct) return `${normalizeBase(direct)}${normalizedPath}`;
  return normalizedPath;
}

export const PORTAL_API_BASE = apiUrl("/api");
export const RECRUITMENT_API_BASE = apiUrl("/api/recruitment");
export const SCREENING_API_BASE = apiUrl("/api/screening");
