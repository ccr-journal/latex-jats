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
  use_canonical_class_file: boolean;
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
  is_quarto: boolean;
  last_synced_at: string | null;
  last_synced_sha: string | null;
  // Approval audit (Issue #9). Set when an author confirms camera-ready;
  // cleared on withdraw-approval.
  approved_at: string | null;
  approved_by: string | null;
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
  smtp_enabled: boolean;
  claude_api_enabled: boolean;
}

export interface DiagnosisMessage {
  role: "user" | "assistant";
  content: string;
  created_at: string;
  input_tokens?: number;
  output_tokens?: number;
  cache_read_tokens?: number;
}

export interface DiagnosisChat {
  id: string;
  manuscript_id: string;
  messages: DiagnosisMessage[];
  created_at: string;
  updated_at: string;
  is_stale: boolean;
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

export interface SiteConfig {
  journal_id: string;
  journal_title: string;
  issn_epub: string;
  issn_ppub: string;
  publisher_name: string;
  publisher_loc: string;
  copyright_holder: string;
  copyright_statement: string;
  license_type: string;
  license_url: string;
  license_text: string;
  doi_prefix: string;
  site_name: string;
  site_description: string;
  header_branding: string;
  class_file_url: string;
  quarto_extension_repo: string;
  configured_at: string | null;
  updated_at: string;
}

export type SiteConfigUpdate = Partial<Omit<SiteConfig, "configured_at" | "updated_at">>;
