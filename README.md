# refer

논문 문서(DOCX/HWP/HWPX)의 본문 인용과 참고문헌 목록을 검토하는 웹앱입니다.
업로드된 문서에서 citation-reference 매칭 문제를 찾고, APA/DOI 기반 수정 제안을 만든 뒤,
사용자가 선택한 patch만 반영한 편집본을 다운로드할 수 있게 하는 것이 목표입니다.

## Live Demo

- Frontend: https://refer-frontend-jade.vercel.app
- API: https://refer-backend.vercel.app
- Health: https://refer-backend.vercel.app/healthz
- API docs: https://refer-backend.vercel.app/docs

Vercel serverless 환경에서는 일부 HWP/HWPX 변환 경로가 제한될 수 있습니다.
전체 문서 변환 기능은 Docker/Fly.io 배포 구성을 기준으로 검증하는 것이 좋습니다.

## Current Status

- Backend: FastAPI API, in-memory job store, review/apply/download/HITL endpoints 구현
- Review core: citation extraction, reference parsing, matching, APA formatting, DOI verification 구현
- Writers: DOCX writer와 HWPX/HWP wrapper 경로 구현
- Frontend: upload, result summary, issue list, patch accept/reject, output mode, apply, download UI 구현
- Tests: backend unit/integration suite 통과

남은 주요 작업은 실제 샘플 문서 기반 품질 검증, 배포 환경별 HWP/HWPX 동작 확인, 문서화 보강입니다.

## Tech Stack

- Backend: Python 3.12, FastAPI, python-docx, lxml, rapidfuzz, httpx
- Optional backend layers: LangGraph, LangChain Anthropic, citeproc-py, Redis/arq
- Frontend: Next.js 15, React 19, TypeScript, Tailwind CSS
- HWPX/HWP: `jkf87/hwpx-skill` submodule

## Local Development

### Backend

```powershell
cd backend
uv sync --extra format --extra agents
uv run uvicorn app.main:app --reload --port 8000
```

Open:

- http://localhost:8000/healthz
- http://localhost:8000/docs

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

Open http://localhost:3000.

Set `NEXT_PUBLIC_BACKEND_URL=http://localhost:8000` in `frontend/.env.local` when needed.

## Verification

Backend:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check .
```

Frontend:

```powershell
cd frontend
cmd /c npm run typecheck
cmd /c npm run build
```

PowerShell may block `npm.ps1` depending on the execution policy; `cmd /c npm ...` avoids that local shell issue.

## Environment Variables

| Name | Purpose | Required |
| --- | --- | --- |
| `OPENAI_API_KEY` | Enables OpenAI-backed critic/routing paths | No |
| `ANTHROPIC_API_KEY` | Enables Anthropic-backed critic/routing paths | No |
| `LLM_PROVIDER` | `auto`, `openai`, or `anthropic`; `auto` prefers OpenAI when both keys exist | No |
| `CROSSREF_POLITE_EMAIL` | Crossref polite pool contact | Recommended |
| `LANGSMITH_API_KEY` | Development tracing | No |
| `REDIS_URL` | Future queue/checkpoint/cache backend | No |
| `NEXT_PUBLIC_BACKEND_URL` | Frontend API base URL | Yes for deployed frontend |

## Deployment

- Backend: `backend/Dockerfile` and `backend/fly.toml` are prepared for Fly.io-style deployment.
- Frontend: deploy `frontend/` to Vercel and configure `NEXT_PUBLIC_BACKEND_URL`.
- Vercel serverless backend files exist under `backend/api/` for lightweight demo deployment.

## Project Notes

- `research.md` is the original technical research/source-of-truth document.
- `plan.md` is the milestone execution plan.
- `docs/architecture.md` maps the implementation to the multi-agent architecture.

Some older planning files currently contain mojibake text and should be regenerated from the original Korean source before publication.

## License

MIT. HWPX processing integrates `jkf87/hwpx-skill` under its MIT license.
