export type ManuscriptStatus =
  | "draft"
  | "queued"
  | "processing"
  | "ready"
  | "failed"
  | "published";

export interface Manuscript {
  doi_suffix: string;
  title: string;
  ojs_submission_id: number | null;
  status: ManuscriptStatus;
  created_at: string;
  updated_at: string;
  uploaded_at: string | null;
  uploaded_by: string | null;
  job_log: string;
  job_started_at: string | null;
  job_completed_at: string | null;
}

export interface ManuscriptCreate {
  title: string;
  doi_suffix: string;
  ojs_submission_id?: number;
}
