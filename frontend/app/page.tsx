"use client";

import { useState } from "react";
import { uploadForReview, type JobResult } from "@/lib/api";

const SEVERITY_STYLES: Record<string, string> = {
  CRITICAL: "bg-red-100 text-red-800",
  WARNING: "bg-yellow-100 text-yellow-800",
  INFO: "bg-blue-100 text-blue-800",
};

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<JobResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    setLoading(true);
    setError("");
    setResult(null);
    try {
      setResult(await uploadForReview(file));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto max-w-3xl px-6 py-12">
      <h1 className="text-3xl font-bold">refer</h1>
      <p className="mt-2 text-sm text-gray-500">
        논문(DOCX)을 업로드하면 인용↔참고문헌 정합성을 검토합니다. HWP/HWPX는 추후 지원.
      </p>

      <form onSubmit={handleSubmit} className="mt-8 space-y-4">
        <input
          type="file"
          accept=".docx,.hwp,.hwpx"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          className="block w-full rounded border border-gray-300 p-2 text-sm"
        />
        <button
          type="submit"
          disabled={!file || loading}
          className="rounded bg-black px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
        >
          {loading ? "검토 중…" : "검토 시작"}
        </button>
      </form>

      {error && (
        <p className="mt-4 rounded bg-red-50 p-3 text-sm text-red-700">{error}</p>
      )}

      {result && (
        <section className="mt-8">
          <h2 className="text-lg font-semibold">
            검토 결과 — {result.filename}
          </h2>
          <div className="mt-2 flex flex-wrap gap-3 text-sm text-gray-600">
            <span>인용 {result.match_report.stats.citations ?? 0}건</span>
            <span>참고문헌 {result.match_report.stats.references ?? 0}건</span>
            <span>이슈 {result.match_report.stats.issues ?? 0}건</span>
          </div>

          <ul className="mt-4 space-y-2">
            {result.match_report.issues.map((issue, i) => (
              <li
                key={i}
                className="rounded border border-gray-200 p-3 text-sm"
              >
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
                발견된 정합성 문제가 없습니다. ✅
              </li>
            )}
          </ul>
        </section>
      )}
    </main>
  );
}
