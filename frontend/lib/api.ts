/** Thin fetch wrapper around the FastAPI backend. */

export const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

export interface MatchIssue {
  type: string;
  severity: "INFO" | "WARNING" | "CRITICAL";
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

export interface JobResult {
  filename: string;
  original_format: string;
  match_report: MatchReport;
}

export async function uploadForReview(file: File): Promise<JobResult> {
  const form = new FormData();
  form.append("file", file);
  const resp = await fetch(`${BACKEND_URL}/jobs`, {
    method: "POST",
    body: form,
  });
  if (!resp.ok) {
    let detail = `${resp.status}`;
    try {
      const body = await resp.json();
      detail = body.detail ?? detail;
    } catch {
      // ignore non-JSON error bodies
    }
    throw new Error(`업로드 실패: ${detail}`);
  }
  return resp.json();
}
