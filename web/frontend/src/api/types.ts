export type ManuscriptStatus =
  | "draft"
  | "uploaded"
  | "queued"
  | "processing"
  | "ready"
  | "failed"
  | "published";

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
  abstract: string | null;
  keywords: string[] | null;
  doi: string | null;
  volume: string | null;
  issue_number: string | null;
  year: number | null;
  authors: OjsAuthor[];
  fix_source: boolean;
  created_at: string;
  updated_at: string;
  uploaded_at: string | null;
  uploaded_by: string | null;
  upload_file_count: number | null;
  job_log: string;
  job_started_at: string | null;
  job_completed_at: string | null;
  pipeline_steps: PipelineStep[] | null;
}

export interface ManuscriptCreate {
  doi_suffix: string;
  ojs_submission_id?: number;
}

export interface CurrentUser {
  orcid: string;
  name: string | null;
  role: "editor" | "author";
}

export interface OjsAuthor {
  orcid: string;
  name: string | null;
  order: number;
}

export interface OjsSubmission {
  submission_id: number;
  doi_suffix: string;
  title: string;
  authors: OjsAuthor[];
  already_imported: boolean;
}
