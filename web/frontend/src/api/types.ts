export type ManuscriptStatus =
  | "draft"
  | "uploaded"
  | "queued"
  | "processing"
  | "ready"
  | "approved"
  | "failed"
  | "archived";

export type StepStatus =
  | "pending"
  | "running"
  | "ok"
  | "warnings"
  | "errors"
  | "failed"
  | "skipped";

export interface StepLogEntry {
  name: string;
  content: string;
}

export interface PipelineStep {
  name: string;
  status: StepStatus;
  logs: StepLogEntry[];
  started_at: string | null;
  completed_at: string | null;
}

export interface Manuscript {
  doi_suffix: string;
  ojs_submission_id: number | null;
  status: ManuscriptStatus;
  title: string | null;
  subtitle: string | null;
  abstract: string | null;
  keywords: string[] | null;
  doi: string | null;
  volume: string | null;
  issue_number: string | null;
  year: number | null;
  date_received: string | null;
  date_accepted: string | null;
  date_published: string | null;
  authors: OjsAuthor[];
  fix_source: boolean;
  use_canonical_ccr_cls: boolean;
  created_at: string;
  updated_at: string;
  uploaded_at: string | null;
  uploaded_by: string | null;
  upload_file_count: number | null;
  job_log: string;
  job_started_at: string | null;
  job_completed_at: string | null;
  pipeline_steps: PipelineStep[] | null;
  // Upstream source linkage (Issue #7).
  // file:// URLs indicate an uploaded source; http(s)/git URLs are syncable.
  upstream_url: string | null;
  upstream_ref: string | null;
  upstream_subpath: string | null;
  upstream_has_token: boolean;
  main_file: string | null;
  last_synced_at: string | null;
  last_synced_sha: string | null;
}

export interface ManuscriptCreate {
  doi_suffix: string;
  ojs_submission_id?: number;
}

export interface CurrentUser {
  username: string | null;
  name: string | null;
  role: "editor" | "author";
  manuscript_token_scope: string | null;
}

export interface OjsAuthor {
  name: string | null;
  email: string | null;
  order: number;
  primary_contact: boolean;
}

export interface OjsSubmission {
  submission_id: number;
  doi_suffix: string;
  title: string;
  authors: OjsAuthor[];
  already_imported: boolean;
}

export interface MetadataComparison {
  field: string;
  status: "ok" | "mismatch";
  ojs: string | string[];
  latex: string | string[];
}
