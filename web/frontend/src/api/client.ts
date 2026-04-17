import type {
  CurrentUser,
  Manuscript,
  ManuscriptCreate,
  MetadataComparison,
  OjsSubmission,
} from "./types";

const BASE = import.meta.env.VITE_API_URL ?? "";
const SESSION_KEY = "ccr_session";

class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export class UnauthorizedError extends ApiError {
  constructor(message: string) {
    super(401, message);
  }
}

export function getSessionToken(): string | null {
  return localStorage.getItem(SESSION_KEY);
}

export function setSessionToken(token: string): void {
  localStorage.setItem(SESSION_KEY, token);
}

export function clearSessionToken(): void {
  localStorage.removeItem(SESSION_KEY);
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  const token = getSessionToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const res = await fetch(`${BASE}${path}`, { ...init, headers });
  if (res.status === 401) {
    clearSessionToken();
    throw new UnauthorizedError("Session expired — please sign in again");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, body.detail ?? res.statusText);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

// ── Auth ──────────────────────────────────────────────────────────────────────

export function orcidLoginUrl(): string {
  return `${BASE}/api/auth/orcid/login`;
}

export function getCurrentUser(): Promise<CurrentUser> {
  return apiFetch("/api/auth/me");
}

export async function logout(): Promise<void> {
  try {
    await apiFetch<void>("/api/auth/logout", { method: "POST" });
  } finally {
    clearSessionToken();
  }
}

// ── Manuscripts ───────────────────────────────────────────────────────────────

export function listManuscripts(): Promise<Manuscript[]> {
  return apiFetch("/api/manuscripts");
}

export function createManuscript(data: ManuscriptCreate): Promise<Manuscript> {
  return apiFetch("/api/manuscripts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export function getManuscript(doiSuffix: string): Promise<Manuscript> {
  return apiFetch(`/api/manuscripts/${doiSuffix}`);
}

export function updateManuscript(
  doiSuffix: string,
  data: { fix_source?: boolean },
): Promise<Manuscript> {
  return apiFetch(`/api/manuscripts/${doiSuffix}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export function approveManuscript(doiSuffix: string): Promise<Manuscript> {
  return apiFetch(`/api/manuscripts/${doiSuffix}/approve`, {
    method: "POST",
  });
}

export function withdrawApproval(doiSuffix: string): Promise<Manuscript> {
  return apiFetch(`/api/manuscripts/${doiSuffix}/withdraw-approval`, {
    method: "POST",
  });
}

export function getStatus(doiSuffix: string): Promise<Manuscript> {
  return apiFetch(`/api/manuscripts/${doiSuffix}/status`);
}

export async function uploadFiles(
  doiSuffix: string,
  files: File[],
): Promise<Manuscript> {
  const form = new FormData();
  for (const file of files) {
    const relPath = (file as File & { webkitRelativePath?: string }).webkitRelativePath;
    form.append("files", file, relPath || file.name);
  }
  return apiFetch(`/api/manuscripts/${doiSuffix}/upload`, {
    method: "POST",
    body: form,
  });
}

export async function startProcessing(
  doiSuffix: string,
  fix: boolean = false,
): Promise<Manuscript> {
  const form = new FormData();
  form.append("fix", fix ? "true" : "false");
  return apiFetch(`/api/manuscripts/${doiSuffix}/process`, {
    method: "POST",
    body: form,
  });
}

export function downloadUrl(doiSuffix: string, token?: string): string {
  const url = `${BASE}/api/manuscripts/${doiSuffix}/download`;
  return token ? `${url}?token=${encodeURIComponent(token)}` : url;
}

export function outputUrl(doiSuffix: string, path: string, token?: string): string {
  const url = `${BASE}/api/manuscripts/${doiSuffix}/output/${path}`;
  return token ? `${url}?token=${encodeURIComponent(token)}` : url;
}

export async function presign(doiSuffix: string): Promise<string> {
  const data = await apiFetch<{ token: string }>(`/api/manuscripts/${doiSuffix}/presign`);
  return data.token;
}

// ── Author tokens ────────────────────────────────────────────────────────────

export interface AuthorToken {
  token: string;
  url: string;
  created_at: string;
}

export function getAuthorToken(doiSuffix: string): Promise<AuthorToken> {
  return apiFetch(`/api/manuscripts/${doiSuffix}/author-token`);
}

export function regenerateAuthorToken(doiSuffix: string): Promise<AuthorToken> {
  return apiFetch(`/api/manuscripts/${doiSuffix}/author-token/regenerate`, {
    method: "POST",
  });
}

// ── Author invitations ──────────────────────────────────────────────────────

export interface InviteTemplate {
  subject: string;
  body: string;
}

export interface InviteResult {
  sent: string[];
  failed: string[];
  skipped: string[];
}

export function getInviteTemplate(doiSuffix: string): Promise<InviteTemplate> {
  return apiFetch(`/api/manuscripts/${doiSuffix}/invite-authors`);
}

export function inviteAuthors(
  doiSuffix: string,
  data: { subject: string; body: string },
): Promise<InviteResult> {
  return apiFetch(`/api/manuscripts/${doiSuffix}/invite-authors`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

// ── OJS ───────────────────────────────────────────────────────────────────────

export function listOjsSubmissions(): Promise<OjsSubmission[]> {
  return apiFetch("/api/ojs/submissions");
}

export function importOjsSubmission(submissionId: number): Promise<Manuscript> {
  return apiFetch(`/api/ojs/submissions/${submissionId}/import`, {
    method: "POST",
  });
}

export function reimportOjsMetadata(doiSuffix: string): Promise<Manuscript> {
  return apiFetch(`/api/manuscripts/${doiSuffix}/reimport-ojs`, {
    method: "POST",
  });
}

// ── Metadata comparison ──────────────────────────────────────────────────────

export function getMetadataComparison(
  doiSuffix: string,
): Promise<MetadataComparison[]> {
  return apiFetch(`/api/manuscripts/${doiSuffix}/output/metadata_comparison.json`);
}

export function syncOjsField(
  doiSuffix: string,
  field: string,
): Promise<MetadataComparison[]> {
  return apiFetch(`/api/manuscripts/${doiSuffix}/sync-ojs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ field }),
  });
}

export { ApiError };
