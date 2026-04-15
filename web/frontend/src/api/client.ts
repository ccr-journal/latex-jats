import type { CurrentUser, Manuscript, ManuscriptCreate } from "./types";

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

export function downloadUrl(doiSuffix: string): string {
  return `${BASE}/api/manuscripts/${doiSuffix}/download`;
}

export function outputUrl(doiSuffix: string, path: string): string {
  return `${BASE}/api/manuscripts/${doiSuffix}/output/${path}`;
}

export { ApiError };
