"use client";

import { useState } from "react";
import {
  applyPatches,
  downloadUrl,
  uploadForReview,
  type JobResult,
  type OutputMode,
  type Patch,
} from "@/lib/api";

const SEVERITY_STYLES: Record<string, string> = {
  CRITICAL: "bg-red-100 text-red-800",
  WARNING: "bg-yellow-100 text-yellow-800",
  INFO: "bg-blue-100 text-blue-800",
};

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<JobResult | null>(null);
  const [selectedPatchIds, setSelectedPatchIds] = useState<Set<string>>(new Set());
  const [mode, setMode] = useState<OutputMode>("tracked");
  const [downloadHref, setDownloadHref] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState<string>("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    setLoading(true);
    setError("");
    setResult(null);
    setDownloadHref("");
    try {
      const nextResult = await uploadForReview(file);
      setResult(nextResult);
      setSelectedPatchIds(
        new Set(
          nextResult.patches
            .filter((patch) => patch.confidence >= 0.9)
            .map((patch) => patch.id),
        ),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  function togglePatch(id: string) {
    setSelectedPatchIds((current) => {
      const next = new Set(current);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }

  async function handleApply() {
    if (!result?.job_id) return;
    setApplying(true);
    setError("");
    try {
      await applyPatches(result.job_id, Array.from(selectedPatchIds), mode);
      setDownloadHref(downloadUrl(result.job_id));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setApplying(false);
    }
  }

  return (
    <main className="mx-auto max-w-5xl px-6 py-10 pb-28">
      <header>
        <h1 className="text-3xl font-bold text-gray-950">refer</h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-gray-600">
          Upload a DOCX, HWP, or HWPX paper to check citation-reference matches,
          review APA/DOI suggestions, and download an edited copy.
        </p>
      </header>

      <form
        onSubmit={handleSubmit}
        className="mt-8 grid gap-4 rounded border border-gray-200 bg-white p-4 shadow-sm"
      >
        <label className="text-sm font-medium text-gray-800" htmlFor="paper">
          Paper file
        </label>
        <input
          id="paper"
          type="file"
          accept=".docx,.hwp,.hwpx"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          className="block w-full rounded border border-gray-300 p-2 text-sm"
        />
        <div className="flex flex-wrap items-center gap-3">
          <label className="text-sm font-medium text-gray-800" htmlFor="mode">
            Output mode
          </label>
          <select
            id="mode"
            value={mode}
            onChange={(e) => setMode(e.target.value as OutputMode)}
            className="rounded border border-gray-300 px-3 py-2 text-sm"
          >
            <option value="tracked">Tracked changes</option>
            <option value="annotated">Annotated</option>
            <option value="final">Final</option>
          </select>
          <button
            type="submit"
            disabled={!file || loading}
            className="ml-auto rounded bg-gray-950 px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
          >
            {loading ? "Reviewing..." : "Start review"}
          </button>
        </div>
      </form>

      {error && (
        <p className="mt-4 rounded bg-red-50 p-3 text-sm text-red-700">{error}</p>
      )}

      {result && (
        <section className="mt-8 space-y-6">
          <div>
            <h2 className="text-lg font-semibold text-gray-950">
              Review result: {result.filename}
            </h2>
            <div className="mt-2 flex flex-wrap gap-3 text-sm text-gray-600">
              <span>{result.match_report.stats.citations ?? 0} citations</span>
              <span>{result.match_report.stats.references ?? 0} references</span>
              <span>{result.match_report.stats.issues ?? 0} issues</span>
              <span>{result.patches.length} patch suggestions</span>
              <span>{result.hitl_queue?.length ?? 0} HITL conflicts</span>
            </div>
          </div>

          <IssueList result={result} />
          <DoiVerification result={result} />
          <PatchReview
            patches={result.patches}
            selectedPatchIds={selectedPatchIds}
            onToggle={togglePatch}
          />
        </section>
      )}

      {result && (
        <div className="fixed inset-x-0 bottom-0 border-t border-gray-200 bg-white/95 px-6 py-3 shadow-lg backdrop-blur">
          <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-3">
            <span className="text-sm text-gray-700">
              {selectedPatchIds.size} accepted,{" "}
              {Math.max(result.patches.length - selectedPatchIds.size, 0)} rejected
            </span>
            <button
              type="button"
              onClick={handleApply}
              disabled={applying || !result.job_id}
              className="ml-auto rounded bg-gray-950 px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
            >
              {applying ? "Applying..." : "Apply selected"}
            </button>
            {downloadHref && (
              <a
                href={downloadHref}
                className="rounded border border-gray-300 px-4 py-2 text-sm font-medium text-gray-900"
              >
                Download file
              </a>
            )}
          </div>
        </div>
      )}
    </main>
  );
}

function IssueList({ result }: { result: JobResult }) {
  return (
    <section>
      <h3 className="text-sm font-semibold uppercase tracking-wide text-gray-500">
        Citation issues
      </h3>
      <ul className="mt-3 space-y-2">
        {result.match_report.issues.map((issue, i) => (
          <li key={i} className="rounded border border-gray-200 p-3 text-sm">
            <span
              className={`mr-2 rounded px-2 py-0.5 text-xs font-medium ${
                SEVERITY_STYLES[issue.severity] ?? "bg-gray-100"
              }`}
            >
              {issue.type}
            </span>
            {issue.message}
          </li>
        ))}
        {result.match_report.issues.length === 0 && (
          <li className="rounded bg-green-50 p-3 text-sm text-green-700">
            No citation-reference consistency issues were found.
          </li>
        )}
      </ul>
    </section>
  );
}

function DoiVerification({ result }: { result: JobResult }) {
  const items = Object.values(result.verified ?? {});

  return (
    <section>
      <h3 className="text-sm font-semibold uppercase tracking-wide text-gray-500">
        DOI verification
      </h3>
      <div className="mt-3 space-y-2">
        {items.map((item) => (
          <article key={item.ref_id} className="rounded border border-gray-200 p-3 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <span
                className={`rounded px-2 py-0.5 text-xs font-medium ${
                  SEVERITY_STYLES[item.severity] ?? "bg-gray-100"
                }`}
              >
                {item.status}
              </span>
              {item.doi_url && (
                <a
                  href={item.doi_url}
                  target="_blank"
                  rel="noreferrer"
                  className="break-all text-blue-700 underline"
                >
                  {item.doi_url}
                </a>
              )}
            </div>
            <div className="mt-2 flex flex-wrap gap-3 text-xs text-gray-600">
              <span>link {formatBool(item.doi_resolves)}</span>
              <span>title {formatBool(item.title_matches)}</span>
              <span>confidence {(item.confidence * 100).toFixed(0)}%</span>
            </div>
            {item.matched_title && (
              <p className="mt-2 text-gray-800">Matched title: {item.matched_title}</p>
            )}
            {item.note && <p className="mt-2 text-gray-600">{item.note}</p>}
          </article>
        ))}
        {items.length === 0 && (
          <p className="rounded bg-gray-50 p-3 text-sm text-gray-600">
            No DOI metadata was returned for this review.
          </p>
        )}
      </div>
    </section>
  );
}

function formatBool(value: boolean | null | undefined) {
  if (value === true) return "ok";
  if (value === false) return "failed";
  return "n/a";
}

function PatchReview({
  patches,
  selectedPatchIds,
  onToggle,
}: {
  patches: Patch[];
  selectedPatchIds: Set<string>;
  onToggle: (id: string) => void;
}) {
  return (
    <section>
      <h3 className="text-sm font-semibold uppercase tracking-wide text-gray-500">
        Patch review
      </h3>
      <div className="mt-3 space-y-3">
        {patches.map((patch) => (
          <article key={patch.id} className="rounded border border-gray-200 bg-white p-4">
            <div className="flex flex-wrap items-center gap-2">
              <input
                type="checkbox"
                checked={selectedPatchIds.has(patch.id)}
                onChange={() => onToggle(patch.id)}
                aria-label={`Accept ${patch.id}`}
                className="h-4 w-4"
              />
              <span
                className={`rounded px-2 py-0.5 text-xs font-medium ${
                  SEVERITY_STYLES[patch.severity] ?? "bg-gray-100"
                }`}
              >
                {patch.source}
              </span>
              <span className="rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-700">
                {patch.kind}
              </span>
              <span className="text-xs text-gray-500">
                confidence {(patch.confidence * 100).toFixed(0)}%
              </span>
            </div>
            <div className="mt-3 grid gap-3 md:grid-cols-2">
              <DiffBlock label="Before" text={patch.before || "(no existing text)"} />
              <DiffBlock label="After" text={patch.after || patch.comment} />
            </div>
            {patch.comment && (
              <p className="mt-3 rounded bg-gray-50 p-3 text-sm text-gray-700">
                {patch.comment}
              </p>
            )}
          </article>
        ))}
        {patches.length === 0 && (
          <p className="rounded bg-gray-50 p-3 text-sm text-gray-600">
            No document edits were proposed.
          </p>
        )}
      </div>
    </section>
  );
}

function DiffBlock({ label, text }: { label: string; text: string }) {
  return (
    <div className="rounded border border-gray-200 bg-gray-50 p-3">
      <div className="text-xs font-semibold uppercase tracking-wide text-gray-500">
        {label}
      </div>
      <p className="mt-2 whitespace-pre-wrap break-words text-sm leading-6 text-gray-900">
        {text}
      </p>
    </div>
  );
}
