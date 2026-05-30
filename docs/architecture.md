# 아키텍처 (architecture.md)

> 사양의 source of truth는 [research.md](../research.md). 본 문서는 구현된 코드 구조와
> research.md §7 멀티 에이전트 설계의 매핑을 요약한다.

## 런타임 분리 (research.md §8.2)

| 영역 | 도구 | 위치 |
|------|------|------|
| 프로덕션 런타임 (S1~S7, C1~C4) | LangGraph + 결정론 함수 | `backend/app/` |
| 개발 보조 (코드 리뷰·QA) | Claude Code / harness | (선택) `.claude/` |

핵심 결정: **검토 로직은 전부 결정론 함수로 구현**되어 있고(`app.citation`,
`app.verifier`, `app.writers`), LangGraph(`app.agents.graph`)는 그 위에 얇게 얹혀
checkpoint·streaming·HITL을 제공한다. LLM 키가 없으면 LLM 분기는 skip되고 결정론
결과가 그대로 반환된다 — 데모/오프라인에서도 F1/F2/F3가 동작한다.

## 파이프라인 (research.md §7.2)

```
업로드 → parse_file (docx/hwpx/hwp)            [S1 Parser]
      → extract_citations                       [S2 CitationExtractor]
      → parse_references → reference_to_csl     [S3 ReferenceParser]
      → match (F1)                              [S4 Matcher]    ─┐
      → format_apa (F2)                         [S5 Formatter]  ─┼→ build_patches
      → verify_reference (F3, fan-out)          [S6 Verifier]   ─┘
      → run_all_critics (C1~C4)                 [Critics]
      → build_hitl_queue                        [O2 HITL Gate]
      → (사용자 accept) → writer.apply           [S7 DocumentWriter]
```

## Harness 패턴 매핑 (research.md §8.3)

| 컴포넌트 | Harness 패턴 | 구현 |
|----------|--------------|------|
| Phase 진행 | Pipeline | `app/agents/graph.py run_review_graph` |
| Specialist↔Critic | Producer-Reviewer | `app/agents/critics.py` |
| Verifier 병렬 | Fan-out/Fan-in | `review_with_verification` 루프 (asyncio 확장 지점) |
| Reference LLM fallback | Expert Pool | `ref_to_csl` (결정론) + M3 LLM 분기 자리 |
| 전체 라우팅 | Supervisor | LangGraph StateGraph |
| (미사용) | ~~Hierarchical~~ | 의도적 배제 |

## 모듈 책임

- `app/parsers/` — 파일 → `ParsedDocument` (오프셋 보존). docx 안정, hwpx/hwp는
  `vendor/hwpx-skill` submodule 필요.
- `app/citation/` — extractor(F1 입력), references/ref_to_csl(구조화),
  matcher(F1), formatter(F2, APA7), csl(공통 모델).
- `app/verifier/` — crossref/openalex 클라이언트 + verify(F3, hallucination 가드).
- `app/writers/` — Patch 모델 + docx/hwpx/hwp writer (tracked/annotated/final).
- `app/agents/` — state(ReviewState), critics(C1~C4), hitl, routing, graph.
- `app/api/` — FastAPI 라우트 + 스키마. `app/storage/` — JobStore(TTL 24h).
- `app/review.py` — 결정론 오케스트레이션(테스트의 single source of truth).

## 모델 라우팅 (research.md §7.7)

`app/agents/routing.py`: trivial→Haiku 4.5, semantic→Sonnet 4.6, final→Opus 4.7.
`ANTHROPIC_API_KEY` 없으면 `model_for()`가 None → 결정론 경로.

## 임계치 (plan.md M6 §3)

`app/config.py`: `fuzzy_match_threshold=0.85`, `doi_title_confidence=0.92`,
`critic_revision_max=3`, `hitl_confidence_gate=0.7`. 환경변수로 오버라이드 가능,
회귀 셋(`tests/fixtures/corpus.json`)으로 튜닝.
