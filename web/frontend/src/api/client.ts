import type { Manuscript, ManuscriptCreate } from "./types";

const BASE = import.meta.env.VITE_API_URL ?? "";

class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, body.detail ?? res.statusText);
  }
  return res.json();
}

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
  uploadedBy: string = "editor",
): Promise<Manuscript> {
  const form = new FormData();
  for (const file of files) {
    // Preserve folder structure (webkitRelativePath) when uploading a folder
    const relPath = (file as File & { webkitRelativePath?: string }).webkitRelativePath;
    form.append("files", file, relPath || file.name);
  }
  form.append("uploaded_by", uploadedBy);
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
