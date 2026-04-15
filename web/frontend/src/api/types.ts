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
  created_at: string;
  updated_at: string;
  uploaded_at: string | null;
  uploaded_by: string | null;
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
}
