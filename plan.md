# 구현 계획 (plan.md)

> 작성일: 2026-05-30
> 토대: [research.md](research.md) (사양·설계 결정의 source of truth)
> 목적: 논문 인용·래퍼런스 검토 멀티 에이전트 웹앱을 **GitHub 공개 저장소 + Next.js(Vercel) + FastAPI(Fly.io)** 구성으로 출시하기 위한 단계별 실행 계획.

---

## 0. 한눈에 보는 마일스톤

| # | 마일스톤 | 핵심 산출물 | 예상 소요 | 누적일 |
|---|----------|------------|----------|--------|
| M0 | 환경/스캐폴드 | 빈 레포 + CI + harness 베이스라인 | 1d | 1 |
| M1 | DOCX MVP (F1만) | DOCX 업로드 → 인용 매칭 리포트 (단일 endpoint) | 3d | 4 |
| M2 | F2 + F3 + DOCX writer | APA 변환 + DOI 검증 + tracked-changes 다운로드 | 5d | 9 |
| M3 | LangGraph + Critic | 멀티 에이전트 런타임 + revision loop | 4d | 13 |
| M4 | HWPX/HWP 지원 | hwpx-skill 통합 + HWP → HWPX 변환 | 2d | 15 |
| M5 | Frontend 전·후 비교 UI | 핵심 UX(반영 버튼 포함) 완성 | 4d | 19 |
| M6 | HITL + 모델 라우팅 | 충돌 큐 + Haiku/Sonnet/Opus 분기 | 2d | 21 |
| M7 | 배포 + 회귀 셋 | Vercel/Fly.io + KCI 10건 검증 | 3d | 24 |

총 약 **24영업일(≈5주)** 1인 풀타임 기준. 일정은 buffer 20% 미포함.

---

## 1. 기술 스택 락인

| 영역 | 선택 | 버전 |
|------|------|------|
| Backend 언어 | Python | 3.12+ |
| Backend 프레임워크 | FastAPI + uvicorn[standard] | latest stable |
| 에이전트 오케스트레이션 | LangGraph + LangChain | latest |
| 작업 큐 | arq (Redis 기반, 경량) | latest |
| 캐시/체크포인트 | Redis 7 | - |
| DB | SQLite (단일 사용자) → Postgres (확장) | - |
| 문서 파싱 | python-docx, pyhwp, **jkf87/hwpx-skill** | latest |
| 인용 처리 | rapidfuzz, citeproc-py, lxml | latest |
| LLM | Anthropic Claude (Haiku 4.5 / Sonnet 4.6 / Opus 4.7) | API |
| 외부 메타데이터 | Crossref, OpenAlex, DOI content negotiation | REST |
| Frontend 프레임워크 | Next.js 15 (App Router) + TypeScript | 15.x |
| Frontend UI | Tailwind + shadcn/ui | latest |
| 텍스트 diff | react-diff-viewer-continued | latest |
| 설계 메타툴 | revfactory/harness (Claude Code 플러그인) | latest |
| 배포 | Vercel (frontend) + Fly.io (backend) | - |
| 관찰성 | LangSmith (개발), OpenTelemetry (옵션) | - |
| CI/CD | GitHub Actions | - |

---

## 2. 레포지토리 초기 구조

```
refer/
├── README.md                     # 소개 + 데모 GIF
├── research.md                   # 사양/설계 (변경 시 함께 갱신)
├── plan.md                       # 본 문서
├── .github/
│   └── workflows/
│       ├── backend-ci.yml
│       ├── frontend-ci.yml
│       └── harness-diff.yml      # M7 단계, 설계 누락 자동 감지
├── .claude/                      # harness 산출물 (개발 보조 에이전트)
│   ├── agents/
│   └── skills/
├── backend/
│   ├── pyproject.toml            # uv 또는 poetry
│   ├── Dockerfile                # Fly.io 배포용, libreoffice 포함
│   ├── fly.toml
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── parsers/
│   │   │   ├── base.py           # ParsedDocument 공통 스키마
│   │   │   ├── docx_parser.py
│   │   │   ├── hwp_parser.py
│   │   │   └── hwpx_parser.py    # hwpx-skill wrapper
│   │   ├── citation/
│   │   │   ├── extractor.py      # in-text regex
│   │   │   ├── matcher.py        # F1 결정론 로직
│   │   │   └── formatter.py      # F2 citeproc-py
│   │   ├── verifier/
│   │   │   ├── crossref.py
│   │   │   └── openalex.py
│   │   ├── writers/
│   │   │   ├── base.py           # Patch, Writer 프로토콜
│   │   │   ├── docx_writer.py
│   │   │   ├── hwpx_writer.py    # hwpx-skill clone_form + fix_namespaces
│   │   │   └── hwp_writer.py     # HWP → HWPX 변환 경유
│   │   ├── agents/
│   │   │   ├── state.py          # ReviewState TypedDict
│   │   │   ├── graph.py          # LangGraph StateGraph 정의
│   │   │   ├── specialists/      # S1~S7
│   │   │   ├── critics/          # C1~C4
│   │   │   ├── hitl.py
│   │   │   └── routing.py        # Haiku/Sonnet/Opus 분기
│   │   ├── jobs/
│   │   │   ├── queue.py          # arq 설정
│   │   │   └── tasks.py
│   │   ├── api/
│   │   │   ├── routes.py
│   │   │   ├── sse.py            # 진행률 스트리밍
│   │   │   └── schemas.py        # Pydantic
│   │   └── storage/
│   │       └── files.py          # TTL 24h 임시 파일 관리
│   ├── vendor/
│   │   └── hwpx-skill/           # git submodule (MIT)
│   └── tests/
│       ├── fixtures/             # 샘플 docx/hwp/hwpx (KCI 10건)
│       ├── unit/
│       └── integration/
└── frontend/
    ├── package.json
    ├── next.config.ts
    ├── vercel.json
    ├── app/
    │   ├── layout.tsx
    │   ├── page.tsx              # 업로드
    │   ├── jobs/[id]/
    │   │   ├── page.tsx          # 진행률 + 결과
    │   │   ├── review/
    │   │   │   └── page.tsx      # 전·후 비교 + 반영 버튼 ⭐
    │   │   └── hitl/
    │   │       └── page.tsx      # 충돌 큐
    │   └── api/                  # BFF (선택)
    ├── components/
    │   ├── ui/                   # shadcn
    │   ├── DiffViewer.tsx
    │   ├── PatchRow.tsx
    │   └── StickyApplyBar.tsx
    └── lib/
        ├── api.ts                # fetch wrapper
        └── sse.ts                # EventSource hook
```

---

## 3. 마일스톤 상세

### M0. 환경/스캐폴드 (1d)

**목표**: 빈 레포에 부팅 가능한 두 서비스 + harness 베이스라인.

**작업**
1. `gh repo create dongkuklee99/refer --public --license mit` (또는 사용자 선호 organization).
2. `backend/` `uv init`, FastAPI hello world, `/healthz` endpoint.
3. `frontend/` `pnpm create next-app@latest` (TS, App Router, Tailwind 활성화), shadcn 초기화.
4. `.github/workflows/`: backend(ruff + mypy + pytest), frontend(tsc + eslint + next build).
5. **harness 설치**:
   ```
   claude /plugin marketplace add revfactory/harness
   claude /plugin install harness@harness-marketplace
   export CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1
   ```
6. Claude Code 세션에서 `Build a harness for "academic citation review with multi-format document I/O (docx, hwp, hwpx)"` 실행 → `.claude/agents/` 베이스라인 산출 후 커밋.
7. README에 1줄 설명 + 데모 placeholder.

**완료 기준**: GitHub Actions 양쪽 green, `curl /healthz` 200, `/` 페이지 200.

### M1. DOCX MVP (3d)

**목표**: docx 파일 1개 업로드 → 인용 매칭 리포트 JSON 응답. UI는 미니멈.

**작업**
1. `parsers/base.py` `ParsedDocument`, `Paragraph` TypedDict. 오프셋 보존.
2. `parsers/docx_parser.py` python-docx로 단락 추출, reference section 헤딩 정규식으로 절단.
3. `citation/extractor.py` 본문에서 in-text citation 추출 (영문 저자-연도 + 한글 저자-연도 + 번호식 + narrative 4종 regex).
4. `citation/matcher.py` F1 결정론 매칭 (rapidfuzz 0.85 임계). orphan citation / orphan reference / year mismatch / author count mismatch 4종 출력.
5. `api/routes.py` `POST /jobs` (multipart upload) → 동기 처리 후 JSON. **이 단계는 큐 없이 동기**.
6. Frontend `app/page.tsx`에 파일 업로드 폼, 결과 JSON을 `<pre>`로 표시.
7. `tests/unit/test_matcher.py` — 10건 픽스처.

**완료 기준**: KCI 샘플 1건 docx 업로드 → orphan/mismatch 항목이 콘솔에서 확인 가능.

### M2. F2 + F3 + DOCX writer (5d)

**목표**: 인용 검토에 그치지 않고 **APA 변환 + DOI 검증 + tracked-changes 다운로드**까지 한 번에.

**작업**
1. `citation/formatter.py` citeproc-py + `apa.csl` 통합. CSLItem dataclass 정의.
2. `verifier/crossref.py` httpx + tenacity, polite pool 헤더. `/works/{doi}` HEAD + `/works?query.bibliographic=...` 검색.
3. `verifier/openalex.py` 보조 검증 (제목 한국어인 경우 우선 사용).
4. `writers/base.py` `Patch` 모델:
   ```python
   class Patch(TypedDict):
       id: str
       kind: Literal["reference_replace", "citation_comment", "doi_insert"]
       target: ParagraphRef   # paragraph_idx + char range
       before: str
       after: str
       confidence: float
       source: Literal["F1", "F2", "F3"]
       severity: Literal["INFO", "WARNING", "CRITICAL"]
   ```
5. `writers/docx_writer.py` python-docx + lxml로 tracked changes 삽입:
   - reference section 단락 replace는 `w:ins` + `w:del`.
   - 인용 경고는 `w:comment` 추가 (별도 part `word/comments.xml` 갱신).
6. `jobs/queue.py` arq + Redis 셋업 (이 단계부터 비동기).
7. `api/routes.py`:
   - `POST /jobs` → job_id 반환 + 비동기 처리.
   - `GET /jobs/{id}` → 상태.
   - `POST /jobs/{id}/apply` → accepted_patch_ids 적용, output_file 생성.
   - `GET /jobs/{id}/download` → 편집된 docx.
   - `GET /jobs/{id}/events` → SSE 진행률.
8. Frontend 진행률 표시 + accept-all 임시 버튼 + 다운로드 링크 (M5에서 본격 UI).
9. `tests/integration/test_doi_verify.py` — Crossref 응답 픽스처로 hallucination 방지 회귀.

**완료 기준**:
- DOCX 업로드 → tracked changes 적용된 DOCX 다운로드 가능.
- Word에서 열어 "변경 내용 추적" 검토 가능.
- DOI 1개 누락된 reference에 자동 보완 patch가 만들어짐.

### M3. LangGraph + Critic 에이전트 (4d)

**목표**: M2까지의 함수형 파이프라인을 **multi-agent + Generator-Critic 패턴**으로 전환.

**작업**
1. `agents/state.py` ReviewState 정의 (research.md §7.6 그대로).
2. `agents/graph.py` LangGraph StateGraph:
   - 노드: S1 Parser → (S2 Citation + S3 Reference 병렬) → S4 Matcher → (C1 CitationAuditor revision loop) → S5 Formatter → (C2 APAStyleCritic) → S6 Verifier (fan-out) → (C3 EvidenceCritic) → C4 ConsistencyAuditor → (HITL or S7 Writer).
   - Redis checkpoint (`langgraph.checkpoint.redis`).
3. `agents/specialists/*.py` 기존 함수 → LangChain `Runnable`/agent 노드로 wrap.
4. `agents/critics/*.py`:
   - **C1 CitationAuditor** — 결정론, 더 엄격한 et al. 규칙.
   - **C2 APAStyleCritic** — citeproc-py 룰 + LLM(Sonnet) 비표준 타입.
   - **C3 EvidenceCritic** — Crossref 원본 응답 fetch → 독립 비교. LLM(Sonnet) 제목 의미 동등성.
   - **C4 ConsistencyAuditor** — 단계 간 모순 탐지.
5. Revision loop:
   - `revision_counts` 가드, max 3.
   - critic이 revision_request 발행 → specialist가 동일 노드로 재진입.
6. `agents/routing.py` 모델 라우팅 (trivial→Haiku, semantic→Sonnet, final→Opus).
7. LangSmith 트레이스 활성화, 개발 중에만 켜고 키 환경변수로 분리.

**완료 기준**:
- 같은 입력에 대해 M2 함수형 vs M3 LangGraph 결과가 동일 (회귀 테스트).
- C3가 hallucinated DOI 1건을 실제로 잡아내는 unit test 통과.
- revision loop가 3회 초과 시 HITL queue로 escalation되는 통합 테스트 통과.

### M4. HWPX/HWP 지원 (2d)

**목표**: hwpx-skill 통합으로 한글 논문 입출력 완성.

**작업**
1. `git submodule add https://github.com/jkf87/hwpx-skill backend/vendor/hwpx-skill`.
2. `parsers/hwpx_parser.py`:
   - hwpx-skill `text_extract.py` 호출 (subprocess 또는 모듈 import).
   - 출력을 ParsedDocument 스키마로 변환.
3. `parsers/hwp_parser.py`:
   - 1순위: hwpx-skill `convert_hwp.py`로 임시 HWPX 변환 → HWPX 파서 위임. 변환 metadata에 `original_format="hwp"` 기록.
   - 2순위 fallback: pyhwp + ODT 경유.
4. `writers/hwpx_writer.py`:
   - Patch 목록 → `replacements.json` 직렬화.
   - `clone_form.py` subprocess 호출 → 출력.
   - `fix_namespaces.py` **반드시** 마지막에 실행. 누락 검증 테스트 추가.
5. `writers/hwp_writer.py`:
   - 1순위: HWPX writer 결과를 그대로 반환 (확장자 변경 modal로 사용자 사전 동의).
   - 2순위 fallback: LibreOffice headless `soffice --headless --convert-to hwp`.
   - Dockerfile에 `libreoffice` 패키지 추가.
6. `fixtures/`에 한글 KCI 샘플 1건 추가, end-to-end 통합 테스트.

**완료 기준**:
- hwpx 업로드 → annotated 모드로 hwpx 다운로드, 한글에서 정상 열림.
- hwp 업로드 → hwpx로 다운로드, 사용자 동의 modal 동작.

### M5. Frontend 전·후 비교 + 반영 버튼 UI ⭐ (4d)

**목표**: research.md §9.3의 핵심 UX 완성.

**작업**
1. `app/page.tsx` 업로드 UI:
   - 드래그앤드롭 (shadcn `<Card>` + `react-dropzone`).
   - 출력 모드 라디오 (tracked/annotated).
   - HWP인 경우 "HWPX로 변환됩니다" 동의 modal.
2. `app/jobs/[id]/page.tsx` 진행률 대시보드:
   - SSE EventSource로 phase별 상태 표시.
   - LangGraph 노드 단위 progress (Parser → Citation → Reference → Matcher → ...).
3. `app/jobs/[id]/review/page.tsx` **핵심 화면**:
   - 탭: F1 인용 매칭 / F2 APA 변환 / F3 DOI 검증.
   - 행 단위 `PatchRow`: 좌(원본) | 우(수정 제안) | ✅/❌ 토글 | critic 코멘트.
   - `react-diff-viewer-continued`로 word-level diff.
   - default 선체크: critic confidence ≥ 0.9.
   - **`StickyApplyBar`**: 하단 고정, 채택 N건/거절 M건/`반영하기` 버튼.
4. 반영 버튼 동작:
   ```ts
   await fetch(`/api/jobs/${id}/apply`, {
     method: "POST",
     body: JSON.stringify({ accepted_patch_ids, mode })
   });
   // SSE "applied" 이벤트 수신 후 다운로드 버튼 표시
   ```
5. Patch hover 시 본문 미니뷰에서 해당 단락 하이라이트 + scrollIntoView.
6. 시각 회귀 테스트(Playwright snapshot) 3개 시나리오.

**완료 기준**:
- 사용자가 모든 patch를 ✅로 두면 원본+모든 수정 반영된 파일이 다운로드됨.
- 일부만 ✅하면 채택된 것만 반영된 파일.
- 모두 ❌하면 원본 그대로 다운로드되고 변경 0건 메시지.

### M6. HITL + 모델 라우팅 마무리 (2d)

**목표**: 충돌 큐 UI + 비용 최적화.

**작업**
1. `app/jobs/[id]/hitl/page.tsx`:
   - critic vs specialist 양쪽 근거 side-by-side.
   - 사용자 선택 후 `POST /jobs/{id}/hitl/resolve` → ReviewState 갱신.
2. `agents/routing.py` 마무리:
   - trivial classification → Haiku 4.5.
   - 한국어 reference 파싱 / semantic 비교 → Sonnet 4.6.
   - C4 ConsistencyAuditor → Opus 4.7.
   - 모델 호출 로그(토큰·비용)를 LangSmith로 모니터.
3. `config.py`에 임계치 일괄 노출:
   ```python
   FUZZY_MATCH_THRESHOLD = 0.85
   DOI_TITLE_CONFIDENCE = 0.92
   CRITIC_REVISION_MAX = 3
   HITL_CONFIDENCE_GATE = 0.7
   ```
4. patch idempotency 보강 — `accepted_patches` set으로 관리, 중복 호출 무시.

**완료 기준**: 충돌 케이스 1건 처리 → 사용자 결정에 따라 다른 patch가 적용되는 통합 테스트.

### M7. 배포 + 회귀 셋 (3d)

**목표**: 공개 운영 + 학술 도구로서의 신뢰성 검증.

**작업**
1. **Backend 배포 (Fly.io)**:
   - Dockerfile: python:3.12-slim base, libreoffice + libreoffice-l10n-ko 설치, hwpx-skill submodule 빌드, uvicorn 실행.
   - `fly launch` → 256~512MB 인스턴스로 시작, Redis는 Upstash 무료 티어.
   - Secrets: `ANTHROPIC_API_KEY`, `LANGSMITH_API_KEY` (선택), `CROSSREF_POLITE_EMAIL`.
2. **Frontend 배포 (Vercel)**:
   - GitHub 연동, main → production, PR → preview.
   - `NEXT_PUBLIC_BACKEND_URL` 환경변수.
3. **CORS** — backend는 `https://*.vercel.app` + 운영 도메인 화이트리스트.
4. **CI 강화**:
   - `harness-diff.yml` — Claude Code agent 산출물 vs `app/agents/` 카탈로그 diff. 누락 시 warning (block은 아님).
   - 회귀 테스트 fixtures(KCI 10건)로 main push마다 end-to-end 실행.
5. **회귀 셋 큐레이션**:
   - KCI 한국어 논문 5건, SCI 영어 논문 3건, hwp 2건, 문제 케이스(DOI 오류·연도 mismatch·한자 병기) 2건.
   - 각 픽스처에 expected `MatchReport` JSON 동봉.
6. **README 보강** — 데모 GIF, 한 줄 설치, demo 인스턴스 URL.

**완료 기준**:
- GitHub Pages가 아닌 Vercel 도메인에서 모르는 사용자가 docx/hwpx 업로드 → 다운로드까지 1분 이내 완료.
- KCI 10건 회귀 테스트 F1 score ≥ 0.9.

---

## 4. 즉시 시작하기 위한 첫 명령 시퀀스 (M0)

```powershell
# 1. 디렉터리 준비
cd d:\OneDrive\Agent\refer
git init
gh repo create refer --public --license mit --source . --remote origin

# 2. Backend
mkdir backend
cd backend
uv init --name refer-backend
uv add fastapi "uvicorn[standard]" python-docx pyhwp httpx tenacity rapidfuzz `
       citeproc-py lxml redis arq langgraph langchain-anthropic pydantic
uv add --dev pytest ruff mypy
# main.py에 FastAPI hello world + /healthz

# 3. hwpx-skill submodule
mkdir vendor
cd vendor
git submodule add https://github.com/jkf87/hwpx-skill
cd ../..

# 4. Frontend
pnpm create next-app@latest frontend --ts --tailwind --app --src-dir=false `
       --eslint --import-alias "@/*" --use-pnpm
cd frontend
pnpm dlx shadcn@latest init -d
pnpm dlx shadcn@latest add button card table tabs dialog badge progress
pnpm add react-diff-viewer-continued

# 5. CI 파일 작성
# .github/workflows/backend-ci.yml, frontend-ci.yml

# 6. Harness 베이스라인
claude /plugin marketplace add revfactory/harness
claude /plugin install harness@harness-marketplace
$env:CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS = "1"
# Claude Code 세션에서: "Build a harness for academic citation review..."

# 7. 첫 커밋
git add -A
git commit -m "M0: scaffold backend, frontend, harness baseline"
git push -u origin main
```

---

## 5. 위험 요소와 대응

| 위험 | 영향 | 대응 |
|------|------|------|
| hwpx-skill의 `clone_form.py`가 본 프로젝트 patch 모델에 100% 맞지 않을 수 있음 | M4 지연 | submodule 대신 vendor fork → 필요한 patch kind 추가 + upstream PR. annotated 모드 우선 출시. |
| LibreOffice headless 변환 품질 저하 | HWP fallback 불가 | M4에서 LibreOffice 경로는 명시적 "experimental" 라벨. 기본은 HWPX 다운로드. |
| Crossref rate limit (50 req/s polite pool) | 회귀 셋 실행 시 429 | tenacity backoff + Redis 24h 캐시 + polite pool 헤더(`mailto:`) 필수. |
| LangSmith 비용 | 운영 부담 | 개발/스테이징에서만 ON, 프로덕션은 OpenTelemetry + Grafana Cloud 무료 티어로 대체. |
| Anthropic API 비용 폭주 | 운영 부담 | 모델 라우팅 + 토큰 캐싱 + 일일 사용량 알람. 데모 인스턴스는 anthropic 키 환경변수 미설정 시 critic LLM 호출 skip(결정론만 작동). |
| 한국어 reference의 한자 병기 / 영문 부제 혼합 | F1/F2 정확도 저하 | M3에서 ReferenceParserAgent LLM fallback + confidence < 0.7 자동 HITL. M7 회귀 셋에 해당 케이스 포함. |
| GDPR / 논문 유출 우려 | 신뢰도 손상 | 원본 파일은 처리 직후 삭제, 결과 파일 TTL 24h, 명시적 비공유 정책 README. |

---

## 6. 완료(Definition of Done) 기준

각 마일스톤은 다음을 모두 충족해야 main 머지 가능:

1. **기능**: 마일스톤 "완료 기준" 항목 모두 충족.
2. **테스트**: 신규 코드 unit test coverage ≥ 70%, 통합 테스트 1개 이상.
3. **CI**: backend-ci + frontend-ci green.
4. **문서**: research.md / plan.md에 변경된 결정 사항 반영. README의 마일스톤 체크박스 갱신.
5. **회귀**: 기존 마일스톤의 통합 테스트가 깨지지 않음.
6. **메모리**: 중요한 결정이 바뀌었으면 `~/.claude/projects/.../memory/project_refer_agent.md` 갱신.

---

## 7. 보류 사항 (사용자 확인 필요)

| # | 항목 | 기본값 | 결정 시점 |
|---|------|-------|----------|
| Q1 | 데모 인스턴스 공개 도메인 명 | `refer-demo.vercel.app` | M7 |
| Q2 | Postgres로 언제 전환 | 동시 사용자 ≥ 5명 발생 시 | M7 이후 |
| Q3 | 인증 도입 시점 | 데모는 무인증, GitHub 1k stars 도달 시 NextAuth | 미래 |
| Q4 | KCI Open API 사용 여부 (한국 논문 검증 강화) | M7에서 회귀 셋 결과로 결정 | M7 |
| Q5 | hwpx-skill을 submodule vs vendor | 일단 submodule, patch 필요 시 vendor fork로 전환 | M4 |
| Q6 | Frontend도 GitHub Pages 백업 배포 둘지 | 미정, 기본은 Vercel 단일 | M7 |

---

## 8. 다음 액션 (지금 바로)

1. `gh repo create` 로 빈 레포 생성 (사용자 확인 필요).
2. M0의 첫 명령 시퀀스 실행 → 백엔드 hello + 프론트엔드 hello + CI green.
3. M1 진입 — `parsers/docx_parser.py`부터 작성.

→ **사용자에게 확인할 것**: 레포 이름(`refer`로 진행할지), GitHub org/user(`dongkuklee99` 개인 계정으로 진행할지), 데모용 Anthropic API 키 확보 여부.
