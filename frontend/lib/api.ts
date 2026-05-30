/** Thin fetch wrapper around the FastAPI backend. */

export const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

export type Severity = "INFO" | "WARNING" | "CRITICAL";
export type OutputMode = "tracked" | "annotated" | "final";

export interface MatchIssue {
  type: string;
  severity: Severity;
  message: string;
  citation_raw?: string | null;
  reference_raw?: string | null;
  paragraph_index?: number | null;
  reference_index?: number | null;
}

export interface MatchReport {
  citations: unknown[];
  references: unknown[];
  issues: MatchIssue[];
  stats: Record<string, number>;
}

export interface Patch {
  id: string;
  kind: "reference_replace" | "citation_comment" | "doi_insert";
  target: {
    paragraph_index: number;
    char_start?: number | null;
    char_end?: number | null;
  };
  before: string;
  after: string;
  comment: string;
  confidence: number;
  source: "F1" | "F2" | "F3";
  severity: Severity;
}

export interface VerifiedItem {
  ref_id: string;
  status: string;
  confidence: number;
  suggested_doi?: string | null;
  doi_url?: string | null;
  doi_resolves?: boolean | null;
  title_matches?: boolean | null;
  matched_title?: string | null;
  severity: Severity;
  note: string;
}

export interface JobResult {
  job_id: string;
  filename: string;
  original_format: string;
  status: string;
  match_report: MatchReport;
  formatted: Record<string, string>;
  verified: Record<string, VerifiedItem>;
  patches: Patch[];
  critics?: Record<string, unknown>;
  hitl_queue?: unknown[];
  llm_used?: boolean;
}

async function parseError(resp: Response): Promise<string> {
  try {
    const body = await resp.json();
    return body.detail ?? `${resp.status}`;
  } catch {
    return `${resp.status}`;
  }
}

export async function uploadForReview(file: File): Promise<JobResult> {
  const form = new FormData();
  form.append("file", file);
  const resp = await fetch(`${BACKEND_URL}/jobs`, { method: "POST", body: form });
  if (!resp.ok) throw new Error(`Upload failed: ${await parseError(resp)}`);
  return resp.json();
}

export async function getJob(id: string): Promise<JobResult> {
  const resp = await fetch(`${BACKEND_URL}/jobs/${id}`);
  if (!resp.ok) throw new Error(`Job lookup failed: ${await parseError(resp)}`);
  return resp.json();
}

export async function applyPatches(
  id: string,
  acceptedPatchIds: string[],
  mode: OutputMode,
): Promise<{ job_id: string; applied: number; download_url: string }> {
  const resp = await fetch(`${BACKEND_URL}/jobs/${id}/apply`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ accepted_patch_ids: acceptedPatchIds, mode }),
  });
  if (!resp.ok) throw new Error(`Apply failed: ${await parseError(resp)}`);
  return resp.json();
}

export function downloadUrl(id: string): string {
  return `${BACKEND_URL}/jobs/${id}/download`;
}
