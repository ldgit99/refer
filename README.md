# refer

**논문 인용·레퍼런스 검토 멀티 에이전트 웹앱** — DOCX / HWP / HWPX 논문을 업로드하면 본문 인용(in-text citation)과 참고문헌의 정합성을 검증하고, APA 7판으로 재포맷하며, DOI 실재 여부를 외부 학술 메타데이터로 확인한 뒤, **원본 포맷 그대로** 검토 결과를 반영해 다운로드할 수 있는 도구입니다.

> 사양·설계의 source of truth는 [research.md](research.md), 실행 계획은 [plan.md](plan.md).

## 핵심 기능

| # | 기능 | 설명 |
|---|------|------|
| F1 | 인용 ↔ 레퍼런스 정합성 | 본문 인용과 참고문헌 목록의 양방향 매칭 (orphan / year mismatch / et al. 규칙) |
| F2 | APA 7판 재포맷 | citeproc-py + `apa.csl`로 표준 변환, 원본과 diff |
| F3 | 실재 검증 + DOI | Crossref / OpenAlex로 존재·DOI 일치 확인, 누락 DOI 자동 보완 |
| D1 | 원본 포맷 다운로드 | 검토 결과를 docx/hwpx에 반영(tracked changes / annotated)해 다운로드 |

## 아키텍처

- **Backend**: FastAPI + LangGraph (multi-agent: specialist + critic) + arq/Redis. → Fly.io
- **Frontend**: Next.js 15 (App Router) + Tailwind. → Vercel
- **LLM**: Anthropic Claude (Haiku/Sonnet/Opus 모델 라우팅). 키가 없으면 결정론 파이프라인만 동작.
- **HWPX**: [jkf87/hwpx-skill](https://github.com/jkf87/hwpx-skill) (MIT) 통합.

설계 세부는 [research.md](research.md) §7(멀티 에이전트), §2(파싱/쓰기) 참조.

## 개발 마일스톤

- [x] M0 — 환경/스캐폴드 (backend + frontend + CI)
- [ ] M1 — DOCX MVP (F1 인용 매칭)
- [ ] M2 — F2 APA + F3 DOI 검증 + DOCX writer
- [ ] M3 — LangGraph + Critic 멀티 에이전트
- [ ] M4 — HWPX/HWP 지원
- [ ] M5 — 전·후 비교 + 반영 버튼 UI
- [ ] M6 — HITL + 모델 라우팅
- [ ] M7 — 배포 + 회귀 셋

## 로컬 실행

### Backend
```powershell
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8000
# http://localhost:8000/healthz
```

### Frontend
```powershell
cd frontend
npm install
npm run dev
# http://localhost:3000
```

## 환경 변수 (GitHub Secrets / 로컬 `.env`)

| 변수 | 용도 | 필수 |
|------|------|------|
| `ANTHROPIC_API_KEY` | Claude LLM 호출 (없으면 결정론만) | 선택 |
| `CROSSREF_POLITE_EMAIL` | Crossref polite pool 헤더 | 권장 |
| `LANGSMITH_API_KEY` | 트레이스 (개발용) | 선택 |
| `REDIS_URL` | arq 큐 / 캐시 / 체크포인트 | M2+ |
| `NEXT_PUBLIC_BACKEND_URL` | 프론트 → 백엔드 주소 | 프론트 |

로컬은 `backend/.env.example`를 복사해 `backend/.env`로 사용하세요.

## 라이선스

MIT — [LICENSE](LICENSE). HWPX 처리는 [jkf87/hwpx-skill](https://github.com/jkf87/hwpx-skill)(MIT)을 통합합니다.

🤖 [Claude Code](https://claude.com/claude-code)로 구현 중입니다.
