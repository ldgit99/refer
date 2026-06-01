# context.md — refer 프로젝트 작업 컨텍스트

> 최종 갱신: 2026-05-31
> 목적: 지금까지 진행된 모든 작업 사항을 한 문서로 정리(인계/재개용).
> 사양 출처: [research.md](research.md)(설계 source of truth), [plan.md](plan.md)(M0~M7 마일스톤), [docs/architecture.md](docs/architecture.md)(구현 매핑).

---

## 1. 프로젝트 개요

**refer** = 논문(DOCX / HWP / HWPX)의 본문 인용(in-text citation)과 참고문헌 목록을 검토하는 멀티 에이전트 웹앱.

- **F1** 인용 ↔ 레퍼런스 정합성(orphan citation/reference, year mismatch, et al. 규칙)
- **F2** APA 7판 재포맷 + 원본과 diff
- **F3** Crossref / OpenAlex로 실재·DOI 검증, 누락 DOI 자동 보완
- **D1** 채택한 patch만 반영해 원본 포맷(tracked/annotated)으로 다운로드

설계 원칙: **결정론(regex/citeproc/API) 우선, LLM은 모호 케이스·critic에만**. specialist(S1~S7) + critic(C1~C4) + HITL 게이트. LLM 키가 없으면 결정론 파이프라인만으로도 완전 동작.

---

## 2. 배포 현황 (라이브)

| 구성 | URL | 상태 |
|------|-----|------|
| Frontend (Next.js) | https://refer-frontend-jade.vercel.app | ✅ 200 |
| Backend API (FastAPI) | https://refer-backend.vercel.app | ✅ healthz ok |
| Health | https://refer-backend.vercel.app/healthz | `{"status":"ok","llm_enabled":true,"llm_provider":"openai","f3_enabled":true,"formats":{...}}` |
| API 문서 | https://refer-backend.vercel.app/docs | ✅ |
| 소스 리포 | https://github.com/ldgit99/refer (PUBLIC) | ✅ |

- 둘 다 **Vercel**(계정 `ldgit99`, team `ldgit99s-projects`)에 배포. 프로젝트명 `refer-frontend`, `refer-backend`.
- **주의**: `refer-frontend.vercel.app`(별칭 없는 기본)은 무관한 Vite 사이트가 선점 → 실제 프론트 별칭은 **`-jade`** 접미사.
- E2E 검증됨: docx 업로드 → F1 orphan_citation/orphan_reference 탐지 + critic C1~C4 + hitl_queue 라이브 동작 확인.

### 배포 시 겪은 함정 (재배포 시 주의)
1. **Vercel이 `next@15.1.6`을 CVE-2025-66478로 빌드 거부** → `next@^15.5.18`로 업그레이드해야 배포됨.
2. **`backend/vercel.json`에 `builds` 키를 넣으면 라우팅이 깨짐(NOT_FOUND)** → `rewrites`만 사용(`/(.*) → /api/index`). FastAPI ASGI 앱은 `backend/api/index.py`의 `app` 객체를 `@vercel/python`이 자동 감지.
3. `NEXT_PUBLIC_BACKEND_URL`은 **빌드타임 인라인** → 값 바꾸면 프론트 재배포 필요.

### Vercel 환경변수 (production, 현재 설정)
- backend: `OPENAI_API_KEY`(설정됨), `LLM_PROVIDER=auto`→openai, `F3_ENABLED=true`, `CORS_ORIGINS=https://refer-frontend-jade.vercel.app`
- frontend: `NEXT_PUBLIC_BACKEND_URL=https://refer-backend.vercel.app`
- 현재 라이브 healthz: `llm_enabled:true, llm_provider:"openai", f3_enabled:true`. healthz는 `formats` 블록(docx/hwpx/hwp별 parse·write·download_format 가용성)도 반환 — 서버리스라 hwpx `skill_available:false`(submodule 미포함)·hwp `parse:false`.

---

## 3. 기술 스택

- **Backend**: Python 3.12, FastAPI, python-docx, lxml, rapidfuzz, httpx, tenacity, pydantic(-settings). uv 관리.
  - optional extras: `agents`(langgraph, langchain-anthropic), `queue`(redis, arq), `format`(citeproc-py)
  - LLM: **OpenAI / Anthropic 둘 다 지원** (`LLM_PROVIDER=auto`면 OpenAI 우선, 없으면 Anthropic, 둘 다 없으면 결정론)
- **Frontend**: Next.js 15.5.18, React 19, TypeScript, Tailwind CSS. (pnpm 미설치 → **npm** 사용)
- **HWPX/HWP**: `jkf87/hwpx-skill` git submodule (`backend/vendor/hwpx-skill`, MIT)
- **배포**: Vercel(현재) + Fly.io/Docker(전체 HWP 변환용, 구성만 준비됨)
- **CI**: GitHub Actions (backend-ci, frontend-ci, harness-diff) — 모두 green

---

## 4. 구현 마일스톤 (전부 완료 — plan.md M0~M7)

- **M0** 스캐폴드: backend(uv/FastAPI `/healthz`), frontend(Next.js/Tailwind), CI 3종, README/LICENSE(MIT)/.gitignore
- **M1** DOCX MVP: 파서 + 인용 추출기(저자-연도/한글/번호/narrative 4종) + 참고문헌 파서 + F1 매처 + 동기 `/jobs`
- **M2** F2/F3/Writer: CSL 모델, APA7 포맷터, Crossref/OpenAlex 검증(respx 테스트), Patch 모델 + DOCX tracked/annotated writer, job API(apply/download/events SSE), JobStore(TTL 24h)
- **M3** LangGraph + critic: graph 래퍼(미설치 시 graceful fallback), C1 CitationAuditor / C2 APAStyleCritic / C3 EvidenceCritic / C4 ConsistencyAuditor, 모델 라우팅, M2≡M3 동치 회귀 테스트
- **M4** HWPX/HWP: hwpx-skill submodule 통합. 파서/라이터가 `scripts/{text_extract,clone_form,convert_hwp,fix_namespaces}.py` 호출(CLI 정렬 완료: clone_form `--map`, convert_hwp `-o`). submodule 없으면 내장 ZIP fallback
- **M5** 프론트 전·후 비교 UI: DiffViewer / PatchRow(✅/❌) / StickyApplyBar / SSE 진행률 / 업로드(HWP 동의)
- **M6** HITL 충돌 큐 API+UI, idempotent apply, config 임계치 집약
- **M7** Dockerfile(LibreOffice+ko)/fly.toml, vercel.json, harness-diff CI, 10건 회귀 corpus + 러너, architecture.md

---

## 5. 추가 구현 (M7 이후, 본 세션 + 후속 작업)

배포 및 품질 개선으로 다음이 추가됨 (git log 기준 `dcc80c2`~`28f7f11`):

- **Vercel 서버리스 어댑터**: `backend/api/index.py`, `backend/requirements.txt`, `backend/vercel.json`, `backend/.vercelignore`
- **OpenAI 지원**: `app/llm/` 패키지 신설
  - `openai_client.py` — OpenAI 호출 클라이언트
  - `reference_parser.py` — LLM 기반 reference 파싱 정교화(한글/한자 혼합)
  - `health.py` — LLM 헬스체크(에러 sanitize)
  - `app/config.py`에 `openai_api_key`, `llm_provider`(auto/openai/anthropic), OpenAI 모델 라우팅(`gpt-4.1`, `gpt-4.1-mini`), `active_llm_provider` 프로퍼티
- **`app/capabilities.py`** — 런타임 기능 가용성 스냅샷(llm_enabled, llm_provider, f3_verification, hwpx_skill, hwp_conversion, libreoffice, docx) → API/UI graceful degradation
- **LLM 헬스 체크 엔드포인트** 추가, **DOI 검증 개선**: DOI 입력 정규화, redirect 검증, 링크 vs 메타데이터 검증 분리, 헬스에 DOI 검증 상태 노출
- **healthz 확장**: `llm_enabled`/`llm_provider`/`f3_enabled` + `formats`(docx/hwpx/hwp별 parse·write·download_format 가용성) 반환. `app/capabilities.py`의 `document_capabilities()`가 vendor 스크립트·soffice 존재를 런타임 점검
- **프론트 UI**: DOI 검증 패널 컴팩트화, Flip7 영감 절제된 스타일링
- **README 전면 재작성**(mojibake 제거, 영문 정리 + 라이브 데모 URL/검증 절차/환경변수 표)

---

## 6. 저장소 구조 (현재)

```
refer/
├── README.md, research.md, plan.md, context.md(본문서), LICENSE
├── docs/architecture.md
├── .github/workflows/{backend-ci,frontend-ci,harness-diff}.yml
├── backend/
│   ├── pyproject.toml, uv.lock, requirements.txt
│   ├── Dockerfile, fly.toml, vercel.json, .vercelignore
│   ├── api/index.py                  # Vercel 서버리스 진입점
│   ├── app/
│   │   ├── main.py, config.py, capabilities.py, pipeline.py, review.py
│   │   ├── parsers/{base,docx_parser,hwp_parser,hwpx_parser}.py
│   │   ├── citation/{extractor,references,ref_to_csl,matcher,formatter,csl}.py
│   │   ├── verifier/{crossref,openalex,verify}.py
│   │   ├── writers/{base,docx_writer,hwpx_writer,hwp_writer,registry}.py
│   │   ├── agents/{state,routing,critics,hitl,graph}.py
│   │   ├── llm/{openai_client,reference_parser,health}.py   # ← 후속 추가
│   │   ├── api/{routes,schemas}.py
│   │   └── storage/files.py          # JobStore TTL 24h
│   ├── vendor/hwpx-skill/            # git submodule
│   └── tests/{unit,integration,fixtures}/
└── frontend/
    ├── package.json(next 15.5.18), vercel.json
    ├── app/{layout,page,globals.css, jobs/[id]/{page, review/page, hitl/page}}.tsx
    ├── components/{DiffViewer,PatchRow,StickyApplyBar}.tsx
    └── lib/{api,sse}.ts
```

---

## 7. 환경변수

| 변수 | 용도 | 필수 |
|------|------|------|
| `OPENAI_API_KEY` | OpenAI critic/routing 활성화 | 선택 |
| `ANTHROPIC_API_KEY` | Anthropic critic/routing 활성화 | 선택 |
| `LLM_PROVIDER` | `auto`/`openai`/`anthropic` (auto는 둘 다 있으면 OpenAI 우선) | 선택 |
| `F3_ENABLED` | Crossref/OpenAlex DOI 외부 검증 on/off | 선택 |
| `CROSSREF_POLITE_EMAIL` | Crossref polite pool | 권장 |
| `LANGSMITH_API_KEY` | 개발 트레이스 | 선택 |
| `REDIS_URL` | 향후 큐/체크포인트/캐시 | 선택 |
| `NEXT_PUBLIC_BACKEND_URL` | 프론트 → 백엔드 주소 | 배포 프론트 필수 |

> 키는 코드에 넣지 않고 Vercel(또는 GitHub Secrets/Fly.io secrets) 환경변수로 주입. API 키를 채팅/커밋에 노출하지 말 것.

---

## 8. 로컬 개발 / 검증

```powershell
# Backend
cd backend
uv sync --extra format --extra agents
uv run uvicorn app.main:app --reload --port 8000   # /healthz, /docs
uv run pytest -q          # 테스트
uv run ruff check .       # 린트 (vendor/ 제외 설정됨)

# Frontend
cd frontend
npm install
npm run dev               # http://localhost:3000
cmd /c npm run build      # PowerShell npm.ps1 정책 이슈 시 cmd /c 사용
```

- 테스트는 `tests/conftest.py`가 `F3_ENABLED=false`로 네트워크 차단. F3 테스트는 respx 모킹.
- ruff/mypy는 `pyproject.toml`에서 `vendor/`(hwpx-skill) 제외.

---

## 9. 알려진 제약 / 남은 작업

**서버리스(Vercel) 제약**
- in-memory JobStore는 워밍된 컨테이너 내에서만 유지 → 다중 인스턴스 분산 시 job 조회 실패 가능(단일 사용자 데모엔 충분). 확장 시 Redis 백엔드로 교체.
- LibreOffice/hwpx subprocess 미설치 → **HWP/HWPX 전체 변환 경로는 서버리스에서 제한**, ZIP fallback만. 전체 기능은 **Fly.io/Docker**(Dockerfile에 libreoffice 포함) 배포 필요.
- F3(레퍼런스별 외부 호출)은 hobby 10초 제한 초과 위험 → 현재 데모는 `F3_ENABLED=false`.

**남은 작업 (선택)**
1. ~~F3/LLM 켜기~~ — **이미 완료**(production에 OpenAI 키 + `F3_ENABLED=true` 설정됨, healthz로 확인). 단 서버리스 F3는 reference 수가 많으면 10초 제한 주의.
2. HWP/HWPX 전체 기능 원하면 Fly.io 배포(`cd backend; fly launch` — flyctl 설치 필요). 현재 서버리스 배포엔 hwpx-skill submodule이 빠져 있어(`skill_available:false`) HWPX는 ZIP fallback, HWP는 parse 불가.
3. 실제 KCI/SCI 샘플 문서 기반 품질 검증(회귀 corpus는 합성 10건만 존재).
4. 커스텀 도메인 또는 `refer-frontend.vercel.app` 별칭 점유 해제.
5. `plan.md`/`research.md`의 mojibake(깨진 한글) 정리 — README는 이미 정리됨.

---

## 10. Git 상태

- 리포: `github.com/ldgit99/refer`, 기본 브랜치 `main`, 공개.
- 최근 커밋(HEAD 부근): `28f7f11 Normalize DOI inputs before verification` … `dcc80c2 Support OpenAI keys and improve HWPX parsing`.
- git user: `ldgit99` / `dongkuklee99@gmail.com`.
- 커밋 메시지 말미 규약: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- 작업 디렉터리에 무관한 `flip7-card-game-DESIGN.md`가 untracked로 존재(이 프로젝트와 별개).

---

## 11. 환경 특이사항 (개발 시 주의)

- 프로젝트 루트 `d:\OneDrive\Agent\refer`는 **OneDrive 동기화 폴더** → 쉘 결과 전달이 지연/배칭됨. 신뢰할 출력은 `C:\Users\user\*.txt`로 리다이렉트 후 Read.
- **배치 취소 함정**: 한 메시지에 여러 tool을 보낼 때 하나라도 non-zero exit면 나머지가 취소됨 → git/ruff/find 등 위험 명령은 Write/Edit와 분리.
- 일부 작업(공개 리포 생성, 외부 submodule add, 토큰 파일 탐색)은 안전 분류기가 차단 → 사용자가 직접 실행하거나 명시 승인 필요.
