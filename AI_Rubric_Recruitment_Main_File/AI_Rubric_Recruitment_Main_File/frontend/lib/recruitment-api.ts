import { getStoredToken } from "./session";

const API_BASE = "/api/recruitment";

function filenameFromDisposition(header: string | null, fallback: string): string {
  if (!header) return fallback;
  const utfMatch = /filename\*=UTF-8''([^;]+)/i.exec(header);
  if (utfMatch) return decodeURIComponent(utfMatch[1].trim());
  const match = /filename="?([^";\n]+)"?/i.exec(header);
  return match ? match[1].trim() : fallback;
}

async function downloadResponseFile(res: Response, fallbackName: string): Promise<void> {
  const blob = await res.blob();
  const name = filenameFromDisposition(res.headers.get("content-disposition"), fallbackName);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getStoredToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Request failed");
  }
  if (res.headers.get("content-type")?.includes("text/plain")) {
    return (await res.text()) as T;
  }
  return res.json();
}

export interface JobDescription {
  title: string;
  company: string;
  location: string;
  employment_type: string;
  experience_level: string;
  salary_range: string;
  summary: string;
  responsibilities: string[];
  required_skills: string[];
  preferred_skills: string[];
  qualifications: string[];
  benefits: string[];
  about_company: string;
}

export interface JobPosting {
  id: number;
  title: string;
  jd: JobDescription;
  natural_language_input: string | null;
  status: string;
  created_at: string;
  updated_at: string | null;
}

export interface Platform {
  id: string;
  name: string;
  logo: string;
  description: string;
  supports_oauth?: boolean;
}

export interface PlatformConnection {
  platform: string;
  account_email: string;
  account_name: string | null;
  account_url: string | null;
  connected_at: string;
  is_oauth: boolean;
  can_post?: boolean;
}

export interface PlatformPost {
  id: number;
  platform: string;
  external_url: string | null;
  external_post_id: string | null;
  account_url: string | null;
  account_email: string | null;
  account_name: string | null;
  apply_url: string;
  status: string;
  posted_at: string;
  applicant_count: number;
  message?: string | null;
}

export interface Applicant {
  id: number;
  full_name: string;
  email: string;
  phone: string | null;
  platform: string;
  applied_at: string;
  has_resume: boolean;
  linkedin_url?: string | null;
  current_title?: string | null;
  current_company?: string | null;
  years_experience?: string | null;
  location?: string | null;
  resume_filename?: string | null;
}

export interface ApplicantDetail extends Applicant {
  resume_text: string | null;
  cover_letter?: string | null;
}

export const recruitmentApi = {
  generateJD: (natural_language: string) =>
    request<JobPosting>("/jd/generate", {
      method: "POST",
      body: JSON.stringify({ natural_language }),
    }),

  listJobs: () => request<JobPosting[]>("/jd"),

  getJob: (id: number) => request<JobPosting>(`/jd/${id}`),

  updateJob: (id: number, jd: JobDescription) =>
    request<JobPosting>(`/jd/${id}`, {
      method: "PUT",
      body: JSON.stringify({ jd }),
    }),

  downloadJob: async (id: number, title: string) => {
    const token = getStoredToken();
    const res = await fetch(`${API_BASE}/jd/${id}/download`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    const text = await res.text();
    const blob = new Blob([text], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${title.replace(/\s+/g, "_")}_JD.txt`;
    a.click();
    URL.revokeObjectURL(url);
  },

  getPlatforms: () => request<Platform[]>("/platforms"),
  getConnections: () => request<PlatformConnection[]>("/platforms/connections"),

  connectPlatform: async (platformId: string, email: string, password = "") => {
    const data = await request<
      PlatformConnection & { oauth_redirect?: string; message?: string }
    >(`/platforms/${platformId}/connect`, {
      method: "POST",
      body: JSON.stringify({ email: email.trim(), password }),
    });
    if (data.oauth_redirect) {
      window.location.assign(data.oauth_redirect);
      return new Promise<PlatformConnection>(() => {});
    }
    return data;
  },

  connectPlatformQuick: (platformId: string) =>
    request<PlatformConnection>(`/platforms/${platformId}/connect/quick`, {
      method: "POST",
    }),

  disconnectPlatform: (platformId: string) =>
    request<{ message: string }>(`/platforms/${platformId}/connect`, {
      method: "DELETE",
    }),

  postToPlatform: (jobId: number, platform: string, force = false) =>
    request<PlatformPost>(`/jd/${jobId}/post`, {
      method: "POST",
      body: JSON.stringify({ platform, force }),
    }),

  getPlatformPosts: (jobId: number) =>
    request<PlatformPost[]>(`/jd/${jobId}/posts`),

  getApplicants: (jobId: number) =>
    request<Applicant[]>(`/jd/${jobId}/applicants`),

  getApplicant: (jobId: number, applicantId: number) =>
    request<ApplicantDetail>(`/jd/${jobId}/applicants/${applicantId}`),

  downloadApplicantResume: async (jobId: number, applicantId: number, fullName: string) => {
    const token = getStoredToken();
    const res = await fetch(`${API_BASE}/jd/${jobId}/applicants/${applicantId}/resume`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || "Download failed");
    }
    await downloadResponseFile(res, `${fullName.replace(/\s+/g, "_")}_resume.docx`);
  },

  downloadApplicantApplication: async (jobId: number, applicantId: number, fullName: string) => {
    const token = getStoredToken();
    const res = await fetch(`${API_BASE}/jd/${jobId}/applicants/${applicantId}/application`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || "Download failed");
    }
    await downloadResponseFile(res, `${fullName.replace(/\s+/g, "_")}_application.docx`);
  },

  exportApplicants: async (jobId: number, title: string) => {
    const token = getStoredToken();
    const res = await fetch(`${API_BASE}/jd/${jobId}/applicants/export`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || "Export failed");
    }
    await downloadResponseFile(res, `${title.replace(/\s+/g, "_")}_applicants.csv`);
  },

  getLinkedInOAuthUrl: async (state: string) => {
    const token = getStoredToken();
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (token) headers.Authorization = `Bearer ${token}`;
    const res = await fetch(
      `/api/platforms/linkedin/oauth/go?state=${encodeURIComponent(state)}`,
      { headers }
    );
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || "Request failed");
    }
    return res.json() as Promise<{ auth_url: string }>;
  },

  startGoogleConnect: async (_platformId: string) => ({
    auth_url: null as string | null,
    mode: "quick" as const,
  }),
};
