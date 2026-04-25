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

export interface LoginResponse {
  token: string;
  user: CurrentUser;
}

export async function login(
  username: string,
  password: string,
): Promise<CurrentUser> {
  const res = await fetch(`${BASE}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, body.detail ?? res.statusText);
  }
  const data: LoginResponse = await res.json();
  setSessionToken(data.token);
  return data.user;
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

// ── Meta ──────────────────────────────────────────────────────────────────────

export function getVersion(): Promise<{ version: string; ccr_cls_version: string }> {
  return apiFetch("/api/version");
}

// ── Manuscripts ───────────────────────────────────────────────────────────────

export function listManuscripts(includeArchived = false): Promise<Manuscript[]> {
  const qs = includeArchived ? "?include_archived=true" : "";
  return apiFetch(`/api/manuscripts${qs}`);
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
  data: {
    fix_source?: boolean;
    use_canonical_ccr_cls?: boolean;
    main_file?: string;
  },
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

export function deleteManuscript(doiSuffix: string): Promise<void> {
  return apiFetch(`/api/manuscripts/${doiSuffix}`, { method: "DELETE" });
}

export function archiveManuscript(doiSuffix: string): Promise<Manuscript> {
  return apiFetch(`/api/manuscripts/${doiSuffix}/archive`, { method: "POST" });
}

export function unarchiveManuscript(doiSuffix: string): Promise<Manuscript> {
  return apiFetch(`/api/manuscripts/${doiSuffix}/unarchive`, { method: "POST" });
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
  useCanonicalCcrCls: boolean = false,
): Promise<Manuscript> {
  const form = new FormData();
  form.append("fix", fix ? "true" : "false");
  form.append("use_canonical_ccr_cls", useCanonicalCcrCls ? "true" : "false");
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

// ── Upstream source (Issue #7) ───────────────────────────────────────────────

export interface UpstreamLinkInput {
  url: string;
  token?: string;      // omit to leave existing token untouched
  clear_token?: boolean; // set true to drop the stored token
  ref?: string;
  subpath?: string;
  main_file?: string;
}

export function linkUpstream(
  doiSuffix: string,
  input: UpstreamLinkInput,
): Promise<Manuscript> {
  return apiFetch(`/api/manuscripts/${doiSuffix}/upstream`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export function unlinkUpstream(doiSuffix: string): Promise<Manuscript> {
  return apiFetch(`/api/manuscripts/${doiSuffix}/upstream`, {
    method: "DELETE",
  });
}

export function syncUpstream(doiSuffix: string): Promise<Manuscript> {
  return apiFetch(`/api/manuscripts/${doiSuffix}/upstream/sync`, {
    method: "POST",
  });
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

export interface Recipient {
  name: string;
  email: string;
}

export interface InviteTemplate {
  subject: string;
  body: string;
  recipients: Recipient[];
}

export interface InviteResult {
  sent: string[];
}

export function getInviteTemplate(doiSuffix: string): Promise<InviteTemplate> {
  return apiFetch(`/api/manuscripts/${doiSuffix}/invite-authors`);
}

export function inviteAuthors(
  doiSuffix: string,
  data: { subject: string; body: string; recipients: Recipient[] },
): Promise<InviteResult> {
  return apiFetch(`/api/manuscripts/${doiSuffix}/invite-authors`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

// ── OJS ───────────────────────────────────────────────────────────────────────

export type OjsStage = "copyediting" | "production";

export function listOjsSubmissions(
  stage: OjsStage = "copyediting",
): Promise<OjsSubmission[]> {
  return apiFetch(`/api/ojs/submissions?stage=${stage}`);
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
