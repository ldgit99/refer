"use client";

import { useMemo, useState } from "react";
import {
  applyPatches,
  downloadUrl,
  uploadForReview,
  type JobResult,
  type OutputMode,
  type Patch,
  type Severity,
  type VerifiedItem,
} from "@/lib/api";

type PatchFilter = "all" | "selected" | "critical" | "warning" | "F1" | "F2" | "F3";

const SEVERITY_STYLES: Record<Severity, string> = {
  CRITICAL: "border-red-200 bg-red-50 text-red-800",
  WARNING: "border-amber-200 bg-amber-50 text-amber-800",
  INFO: "border-blue-200 bg-blue-50 text-blue-800",
};

const FILTERS: Array<{ id: PatchFilter; label: string }> = [
  { id: "all", label: "전체" },
  { id: "selected", label: "선택됨" },
  { id: "critical", label: "긴급" },
  { id: "warning", label: "주의" },
  { id: "F1", label: "인용" },
  { id: "F2", label: "APA" },
  { id: "F3", label: "DOI" },
];

const MODE_LABELS: Record<OutputMode, string> = {
  tracked: "변경 추적",
  annotated: "주석",
  final: "최종본",
};

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<JobResult | null>(null);
  const [selectedPatchIds, setSelectedPatchIds] = useState<Set<string>>(new Set());
  const [activePatchId, setActivePatchId] = useState<string>("");
  const [filter, setFilter] = useState<PatchFilter>("all");
  const [mode, setMode] = useState<OutputMode>("tracked");
  const [downloadHref, setDownloadHref] = useState<string>("");
  const [copiedPatchId, setCopiedPatchId] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState<string>("");

  const visiblePatches = useMemo(() => {
    if (!result) return [];
    return result.patches.filter((patch) => {
      if (filter === "selected") return selectedPatchIds.has(patch.id);
      if (filter === "critical") return patch.severity === "CRITICAL";
      if (filter === "warning") return patch.severity === "WARNING";
      if (filter === "F1" || filter === "F2" || filter === "F3") {
        return patch.source === filter;
      }
      return true;
    });
  }, [filter, result, selectedPatchIds]);

  const activePatch = useMemo(() => {
    if (!result) return null;
    return (
      result.patches.find((patch) => patch.id === activePatchId) ??
      visiblePatches[0] ??
      result.patches[0] ??
      null
    );
  }, [activePatchId, result, visiblePatches]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    setLoading(true);
    setError("");
    setResult(null);
    setDownloadHref("");
    setActivePatchId("");
    try {
      const nextResult = await uploadForReview(file);
      const defaults = new Set(
        nextResult.patches
          .filter((patch) => patch.confidence >= 0.9)
          .map((patch) => patch.id),
      );
      setResult(nextResult);
      setSelectedPatchIds(defaults);
      setActivePatchId(nextResult.patches[0]?.id ?? "");
      setFilter("all");
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

  async function copyAfterText(patch: Patch) {
    await navigator.clipboard.writeText(patch.after || patch.comment);
    setCopiedPatchId(patch.id);
    window.setTimeout(() => setCopiedPatchId(""), 1400);
  }

  return (
    <main className="min-h-screen bg-slate-50 pb-28 text-slate-950">
      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        <header className="flex flex-col gap-4 border-b border-slate-200 pb-6 md:flex-row md:items-end md:justify-between">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight">refer</h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
              논문 문서의 본문 인용, 참고문헌, DOI 링크를 검토하고 선택한 수정 제안만
              반영한 검토본을 다운로드합니다.
            </p>
          </div>
          {result && (
            <div className="text-sm text-slate-500">
              <span className="font-medium text-slate-800">{result.filename}</span>
              <span className="ml-2 uppercase">{result.original_format}</span>
            </div>
          )}
        </header>

        <UploadPanel
          file={file}
          loading={loading}
          mode={mode}
          onFileChange={setFile}
          onModeChange={setMode}
          onSubmit={handleSubmit}
        />

        {error && (
          <p className="mt-4 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            {error}
          </p>
        )}

        {result && (
          <section className="mt-6 space-y-6">
            <SummaryBand result={result} selectedCount={selectedPatchIds.size} />

            <div className="grid gap-6 lg:grid-cols-[360px_minmax(0,1fr)]">
              <aside className="space-y-6">
                <IssuePanel result={result} />
                <DoiPanel items={Object.values(result.verified ?? {})} />
              </aside>

              <PatchWorkspace
                activePatch={activePatch}
                copiedPatchId={copiedPatchId}
                filter={filter}
                patches={visiblePatches}
                selectedPatchIds={selectedPatchIds}
                totalPatchCount={result.patches.length}
                onCopyAfter={copyAfterText}
                onFilterChange={setFilter}
                onPatchActivate={setActivePatchId}
                onTogglePatch={togglePatch}
              />
            </div>
          </section>
        )}
      </div>

      {result && (
        <ApplyBar
          applying={applying}
          downloadHref={downloadHref}
          mode={mode}
          rejectedCount={Math.max(result.patches.length - selectedPatchIds.size, 0)}
          selectedCount={selectedPatchIds.size}
          totalCount={result.patches.length}
          onApply={handleApply}
          onModeChange={setMode}
        />
      )}
    </main>
  );
}

function UploadPanel({
  file,
  loading,
  mode,
  onFileChange,
  onModeChange,
  onSubmit,
}: {
  file: File | null;
  loading: boolean;
  mode: OutputMode;
  onFileChange: (file: File | null) => void;
  onModeChange: (mode: OutputMode) => void;
  onSubmit: (e: React.FormEvent) => void;
}) {
  return (
    <form
      onSubmit={onSubmit}
      className="mt-6 grid gap-4 rounded-md border border-slate-200 bg-white p-4 shadow-sm md:grid-cols-[1fr_auto]"
    >
      <label
        htmlFor="paper"
        className="flex min-h-28 cursor-pointer flex-col justify-center rounded-md border border-dashed border-slate-300 bg-slate-50 px-4 py-3 transition hover:border-slate-400 hover:bg-white"
      >
        <span className="text-sm font-medium text-slate-900">
          {file ? file.name : "DOCX, HWP, HWPX 파일 선택"}
        </span>
        <span className="mt-1 text-xs leading-5 text-slate-500">
          참고문헌과 본문 인용을 함께 검토할 논문 파일을 업로드하세요.
        </span>
        <input
          id="paper"
          type="file"
          accept=".docx,.hwp,.hwpx"
          onChange={(e) => onFileChange(e.target.files?.[0] ?? null)}
          className="sr-only"
        />
      </label>

      <div className="flex min-w-64 flex-col justify-between gap-4">
        <ModeControl mode={mode} onModeChange={onModeChange} />
        <button
          type="submit"
          disabled={!file || loading}
          className="rounded-md bg-slate-950 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {loading ? "검토 중..." : "검토 시작"}
        </button>
      </div>
    </form>
  );
}

function SummaryBand({
  result,
  selectedCount,
}: {
  result: JobResult;
  selectedCount: number;
}) {
  const issueCount = result.match_report.stats.issues ?? result.match_report.issues.length;
  const doiItems = Object.values(result.verified ?? {});
  const doiFailed = doiItems.filter(
    (item) => item.doi_resolves === false || item.title_matches === false,
  ).length;

  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
      <SummaryTile label="본문 인용" value={result.match_report.stats.citations ?? 0} />
      <SummaryTile label="참고문헌" value={result.match_report.stats.references ?? 0} />
      <SummaryTile label="이슈" value={issueCount} tone={issueCount > 0 ? "warning" : "ok"} />
      <SummaryTile label="수정 제안" value={result.patches.length} />
      <SummaryTile
        label="선택됨 / DOI 경고"
        value={`${selectedCount} / ${doiFailed}`}
        tone={doiFailed > 0 ? "warning" : "ok"}
      />
      <SummaryTile
        label="LLM"
        value={result.llm_used ? "ON" : "OFF"}
        tone={result.llm_used ? "ok" : "neutral"}
      />
    </div>
  );
}

function SummaryTile({
  label,
  value,
  tone = "neutral",
}: {
  label: string;
  value: number | string;
  tone?: "neutral" | "ok" | "warning";
}) {
  const toneClass =
    tone === "ok"
      ? "border-emerald-200 bg-emerald-50"
      : tone === "warning"
        ? "border-amber-200 bg-amber-50"
        : "border-slate-200 bg-white";
  return (
    <div className={`rounded-md border p-4 shadow-sm ${toneClass}`}>
      <div className="text-xs font-medium uppercase tracking-wide text-slate-500">
        {label}
      </div>
      <div className="mt-2 text-2xl font-semibold text-slate-950">{value}</div>
    </div>
  );
}

function IssuePanel({ result }: { result: JobResult }) {
  return (
    <section className="rounded-md border border-slate-200 bg-white p-4 shadow-sm">
      <PanelTitle title="인용 이슈" count={result.match_report.issues.length} />
      <ul className="mt-3 space-y-2">
        {result.match_report.issues.map((issue, i) => (
          <li key={`${issue.type}-${i}`} className="rounded-md border border-slate-200 p-3">
            <div className="flex flex-wrap items-center gap-2">
              <SeverityBadge severity={issue.severity} label={issue.type} />
              {issue.paragraph_index !== null && issue.paragraph_index !== undefined && (
                <span className="text-xs text-slate-500">문단 {issue.paragraph_index + 1}</span>
              )}
            </div>
            <p className="mt-2 text-sm leading-6 text-slate-700">{issue.message}</p>
          </li>
        ))}
        {result.match_report.issues.length === 0 && (
          <li className="rounded-md bg-emerald-50 p-3 text-sm text-emerald-700">
            인용-참고문헌 정합성 문제가 발견되지 않았습니다.
          </li>
        )}
      </ul>
    </section>
  );
}

function DoiPanel({ items }: { items: VerifiedItem[] }) {
  return (
    <section className="rounded-md border border-slate-200 bg-white p-4 shadow-sm">
      <PanelTitle title="DOI 검증" count={items.length} />
      <div className="mt-3 space-y-2">
        {items.map((item) => (
          <article key={item.ref_id} className="rounded-md border border-slate-200 p-3">
            <div className="flex flex-wrap items-center gap-2">
              <SeverityBadge severity={item.severity} label={item.status} />
              <StatusPill ok={item.doi_resolves} label="링크" />
              <StatusPill ok={item.title_matches} label="제목" />
            </div>
            {item.doi_url && (
              <a
                href={item.doi_url}
                target="_blank"
                rel="noreferrer"
                className="mt-2 block break-all text-sm text-blue-700 underline"
              >
                {item.doi_url}
              </a>
            )}
            <p className="mt-2 text-xs text-slate-500">
              신뢰도 {(item.confidence * 100).toFixed(0)}%
            </p>
            {item.matched_title && (
              <p className="mt-2 line-clamp-3 text-sm leading-6 text-slate-700">
                {item.matched_title}
              </p>
            )}
            {item.note && <p className="mt-2 text-xs leading-5 text-slate-500">{item.note}</p>}
          </article>
        ))}
        {items.length === 0 && (
          <p className="rounded-md bg-slate-50 p-3 text-sm text-slate-600">
            DOI 메타데이터가 반환되지 않았습니다.
          </p>
        )}
      </div>
    </section>
  );
}

function PatchWorkspace({
  activePatch,
  copiedPatchId,
  filter,
  patches,
  selectedPatchIds,
  totalPatchCount,
  onCopyAfter,
  onFilterChange,
  onPatchActivate,
  onTogglePatch,
}: {
  activePatch: Patch | null;
  copiedPatchId: string;
  filter: PatchFilter;
  patches: Patch[];
  selectedPatchIds: Set<string>;
  totalPatchCount: number;
  onCopyAfter: (patch: Patch) => void;
  onFilterChange: (filter: PatchFilter) => void;
  onPatchActivate: (id: string) => void;
  onTogglePatch: (id: string) => void;
}) {
  return (
    <section className="rounded-md border border-slate-200 bg-white shadow-sm">
      <div className="border-b border-slate-200 p-4">
        <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
          <PanelTitle title="수정 제안" count={totalPatchCount} />
          <div className="flex flex-wrap gap-1">
            {FILTERS.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => onFilterChange(item.id)}
                className={`rounded-md px-3 py-1.5 text-xs font-medium transition ${
                  filter === item.id
                    ? "bg-slate-950 text-white"
                    : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                }`}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="grid min-h-[520px] lg:grid-cols-[320px_minmax(0,1fr)]">
        <div className="border-b border-slate-200 lg:border-b-0 lg:border-r">
          <div className="max-h-[640px] overflow-y-auto p-3">
            <PatchList
              activePatchId={activePatch?.id ?? ""}
              patches={patches}
              selectedPatchIds={selectedPatchIds}
              onPatchActivate={onPatchActivate}
              onTogglePatch={onTogglePatch}
            />
          </div>
        </div>

        <div className="p-4">
          {activePatch ? (
            <PatchDetail
              copied={copiedPatchId === activePatch.id}
              patch={activePatch}
              selected={selectedPatchIds.has(activePatch.id)}
              onCopyAfter={() => onCopyAfter(activePatch)}
              onToggle={() => onTogglePatch(activePatch.id)}
            />
          ) : (
            <p className="rounded-md bg-slate-50 p-4 text-sm text-slate-600">
              표시할 수정 제안이 없습니다.
            </p>
          )}
        </div>
      </div>
    </section>
  );
}

function PatchList({
  activePatchId,
  patches,
  selectedPatchIds,
  onPatchActivate,
  onTogglePatch,
}: {
  activePatchId: string;
  patches: Patch[];
  selectedPatchIds: Set<string>;
  onPatchActivate: (id: string) => void;
  onTogglePatch: (id: string) => void;
}) {
  if (patches.length === 0) {
    return (
      <p className="rounded-md bg-slate-50 p-3 text-sm text-slate-600">
        이 필터에 해당하는 수정 제안이 없습니다.
      </p>
    );
  }

  return (
    <ul className="space-y-2">
      {patches.map((patch) => {
        const active = patch.id === activePatchId;
        return (
          <li key={patch.id}>
            <button
              type="button"
              onClick={() => onPatchActivate(patch.id)}
              className={`w-full rounded-md border p-3 text-left transition ${
                active
                  ? "border-slate-900 bg-slate-50"
                  : "border-slate-200 bg-white hover:border-slate-300"
              }`}
            >
              <div className="flex items-start gap-2">
                <input
                  type="checkbox"
                  checked={selectedPatchIds.has(patch.id)}
                  onChange={(event) => {
                    event.stopPropagation();
                    onTogglePatch(patch.id);
                  }}
                  onClick={(event) => event.stopPropagation()}
                  aria-label={`${patch.id} 선택`}
                  className="mt-1 h-4 w-4"
                />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <SeverityBadge severity={patch.severity} label={patch.source} />
                    <span className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
                      {patch.kind}
                    </span>
                  </div>
                  <p className="mt-2 line-clamp-2 text-sm leading-5 text-slate-800">
                    {patch.comment || patch.after || patch.before || "수정 제안"}
                  </p>
                  <p className="mt-2 text-xs text-slate-500">
                    신뢰도 {(patch.confidence * 100).toFixed(0)}%
                  </p>
                </div>
              </div>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

function PatchDetail({
  copied,
  patch,
  selected,
  onCopyAfter,
  onToggle,
}: {
  copied: boolean;
  patch: Patch;
  selected: boolean;
  onCopyAfter: () => void;
  onToggle: () => void;
}) {
  return (
    <article>
      <div className="flex flex-col gap-3 border-b border-slate-200 pb-4 md:flex-row md:items-start md:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <SeverityBadge severity={patch.severity} label={patch.source} />
            <span className="rounded-md bg-slate-100 px-2 py-1 text-xs text-slate-700">
              {patch.kind}
            </span>
            <span className="text-xs text-slate-500">
              문단 {patch.target.paragraph_index + 1}
            </span>
          </div>
          <h3 className="mt-3 text-lg font-semibold text-slate-950">수정 제안 상세</h3>
          <p className="mt-1 text-sm text-slate-600">
            신뢰도 {(patch.confidence * 100).toFixed(0)}% · {patch.id}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={onCopyAfter}
            className="rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-800 hover:bg-slate-50"
          >
            {copied ? "복사됨" : "제안 복사"}
          </button>
          <button
            type="button"
            onClick={onToggle}
            className={`rounded-md px-3 py-2 text-sm font-medium ${
              selected
                ? "bg-slate-950 text-white hover:bg-slate-800"
                : "border border-slate-300 text-slate-800 hover:bg-slate-50"
            }`}
          >
            {selected ? "선택됨" : "선택"}
          </button>
        </div>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <DiffBlock label="Before" tone="before" text={patch.before || "(기존 텍스트 없음)"} />
        <DiffBlock label="After" tone="after" text={patch.after || patch.comment} />
      </div>

      {patch.comment && (
        <div className="mt-4 rounded-md border border-slate-200 bg-slate-50 p-4">
          <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            검토 메모
          </div>
          <p className="mt-2 text-sm leading-6 text-slate-700">{patch.comment}</p>
        </div>
      )}
    </article>
  );
}

function DiffBlock({
  label,
  text,
  tone,
}: {
  label: string;
  text: string;
  tone: "before" | "after";
}) {
  const toneClass =
    tone === "before"
      ? "border-red-100 bg-red-50/60"
      : "border-emerald-100 bg-emerald-50/70";
  return (
    <div className={`rounded-md border p-4 ${toneClass}`}>
      <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">
        {label}
      </div>
      <p className="mt-2 max-h-80 overflow-y-auto whitespace-pre-wrap break-words text-sm leading-6 text-slate-900">
        {text}
      </p>
    </div>
  );
}

function ApplyBar({
  applying,
  downloadHref,
  mode,
  rejectedCount,
  selectedCount,
  totalCount,
  onApply,
  onModeChange,
}: {
  applying: boolean;
  downloadHref: string;
  mode: OutputMode;
  rejectedCount: number;
  selectedCount: number;
  totalCount: number;
  onApply: () => void;
  onModeChange: (mode: OutputMode) => void;
}) {
  return (
    <div className="fixed inset-x-0 bottom-0 border-t border-slate-200 bg-white/95 px-4 py-3 shadow-[0_-8px_24px_rgba(15,23,42,0.08)] backdrop-blur">
      <div className="mx-auto flex max-w-7xl flex-col gap-3 sm:flex-row sm:items-center">
        <div className="text-sm text-slate-700">
          <span className="font-medium text-slate-950">{selectedCount}</span> 선택 ·{" "}
          <span>{rejectedCount}</span> 제외 · <span>{totalCount}</span> 전체
        </div>
        <div className="sm:ml-auto">
          <ModeControl compact mode={mode} onModeChange={onModeChange} />
        </div>
        <button
          type="button"
          onClick={onApply}
          disabled={applying}
          className="rounded-md bg-slate-950 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {applying ? "반영 중..." : "선택 항목 반영"}
        </button>
        {downloadHref && (
          <a
            href={downloadHref}
            className="rounded-md border border-slate-300 px-4 py-2 text-center text-sm font-medium text-slate-900 hover:bg-slate-50"
          >
            검토본 다운로드
          </a>
        )}
      </div>
    </div>
  );
}

function ModeControl({
  compact = false,
  mode,
  onModeChange,
}: {
  compact?: boolean;
  mode: OutputMode;
  onModeChange: (mode: OutputMode) => void;
}) {
  return (
    <div>
      {!compact && (
        <div className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">
          출력 방식
        </div>
      )}
      <div className="inline-flex rounded-md border border-slate-200 bg-slate-100 p-1">
        {(Object.keys(MODE_LABELS) as OutputMode[]).map((item) => (
          <button
            key={item}
            type="button"
            onClick={() => onModeChange(item)}
            className={`rounded px-3 py-1.5 text-xs font-medium transition ${
              mode === item
                ? "bg-white text-slate-950 shadow-sm"
                : "text-slate-600 hover:text-slate-950"
            }`}
          >
            {MODE_LABELS[item]}
          </button>
        ))}
      </div>
    </div>
  );
}

function PanelTitle({ count, title }: { count: number; title: string }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
        {title}
      </h2>
      <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600">
        {count}
      </span>
    </div>
  );
}

function SeverityBadge({ label, severity }: { label: string; severity: Severity }) {
  return (
    <span
      className={`inline-flex rounded-md border px-2 py-0.5 text-xs font-medium ${
        SEVERITY_STYLES[severity]
      }`}
    >
      {label}
    </span>
  );
}

function StatusPill({
  label,
  ok,
}: {
  label: string;
  ok: boolean | null | undefined;
}) {
  const className =
    ok === true
      ? "border-emerald-200 bg-emerald-50 text-emerald-700"
      : ok === false
        ? "border-red-200 bg-red-50 text-red-700"
        : "border-slate-200 bg-slate-50 text-slate-500";
  const suffix = ok === true ? "OK" : ok === false ? "실패" : "대기";
  return (
    <span className={`rounded-md border px-2 py-0.5 text-xs font-medium ${className}`}>
      {label} {suffix}
    </span>
  );
}
