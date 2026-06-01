# 기능별 개선 사항 (2026-06-01)

`feat/improvements` 브랜치에서 적용한 기능별 개선 내역. 백엔드 **ruff clean + 99 tests pass**, 프론트 tsc clean.

## F3 — DOI·실재 검증

| 개선 | 내용 | 위치 |
|------|------|------|
| **레퍼런스별 병렬 검증** | 순차 루프 → `asyncio.gather` + Semaphore(`F3_CONCURRENCY`, 기본 8). 서버리스 10초 제한 완화. | `verifier/verify.py:verify_references` |
| **검증 결과 캐싱** | DOI/제목 시그니처 키 in-proc TTL LRU 캐시(24h). 동일 DOI 재검증 제거(research §12.8). | `verifier/cache.py`, `verify_reference_cached` |
| **OpenAlex 보조 검증** | Crossref 미스 시 OpenAlex 제목 검색으로 보강(한국어 제목 강점). `CSLItem.from_openalex` 추가. | `verifier/openalex.py:search_title`, `verify.py` |
| **KCI fallback** | `KCI_API_KEY` 설정 시 KCI Open API로 국내 논문 확인 → `verified_external`. 키 없으면 no-op. | `verifier/kci.py` |
| **검증 출처 노출** | `VerifiedItem.source`(crossref/doi.org/openalex/kci) 추가, UI 배지로 표시. | `verify.py`, `frontend` |
| **★ 링크 실패 오탐 제거** | Crossref-first 판정 + 단계화 임계값(verified/verified_weak/mismatch). 살아있는 DOI가 "링크 실패/0%"로 뜨던 핵심 버그 수정. 상세는 아래 별도 절. | `verify.py`, `config.py`, `agents/critics.py` |

## F1 — 인용↔레퍼런스 정합성

| 개선 | 내용 | 위치 |
|------|------|------|
| **후보 점수화 매칭** | 첫 저자만 보던 `candidates[0]` → 저자 유사도+연도 가중 점수로 최적 후보 선택. 같은 저자 다년도 오탐 제거. | `matcher.py:_candidate_score` |
| **역방향 et al. 위반** | 3인↑ 전체나열뿐 아니라 **2인↓인데 et al. 사용**도 탐지. | `matcher.py` |
| **중복 레퍼런스 탐지** | 동일 (첫저자, 연도) 재등재 시 `duplicate_reference` 경고. | `matcher.py` |
| **번호식/무번호 혼합** | 명시적 `[n]` 우선, 위치 키와 충돌 방지. | `matcher.py` |
| **회귀 F1 스코어러** | 합성 corpus 기준 micro-F1 ≥ 0.9 게이트 테스트 추가. | `tests/integration/test_regression_f1_score.py` |

## LLM 보강

| 개선 | 내용 | 위치 |
|------|------|------|
| **Anthropic 경로** | OpenAI 전용이던 LLM 보강을 provider-agnostic `app.llm.chat_json`으로 통합(OpenAI/Anthropic 자동 선택). | `llm/__init__.py`, `llm/anthropic_client.py` |
| **40개 초과 청킹** | reference 40개 초과분 손실 → 배치 분할 후 동시 파싱(최대 ~240개). | `llm/reference_parser.py` |
| **C3 LLM 재검증** | EvidenceCritic의 제목 의미 동등성 LLM 판정 분기(hallucination 가드). | `agents/evidence_llm.py` |

## 멀티 에이전트

| 개선 | 내용 | 위치 |
|------|------|------|
| **bounded revision loop** | C3 critic↔verifier 재검 루프(`critic_revision_max`회). LLM이 다른 문헌으로 판정 시 verified→doi_mismatch 강등 후 재평가, `revision_counts` 기록. | `agents/graph.py:_evidence_revision_loop` |

## D1 — Writer

| 개선 | 내용 | 위치 |
|------|------|------|
| **진짜 Word 코멘트** | highlight 대체 → `word/comments.xml` 실제 `w:comment` + `commentRangeStart/End` + `commentReference`. Word 검토 창에 표시. | `writers/docx_writer.py:_CommentsPart` |

## 인프라 / 안정성

| 개선 | 내용 | 위치 |
|------|------|------|
| **JobStore 유실 수정** | 서버리스 다중 인스턴스에서 apply/download 404 위험 → `REDIS_URL`(비-localhost) 지정 시 Redis 백엔드, 미가용 시 in-memory 자동 fallback. | `storage/files.py:RedisJobStore` |

## UX / 프론트엔드

| 개선 | 내용 | 위치 |
|------|------|------|
| **신규 이슈 타입 표기** | `duplicate_reference` 등 한글 라벨, DOI `verified_external` 라벨. | `app/page.tsx` |
| **검증 출처 배지** | DoiRow에 Crossref/OpenAlex/KCI 출처 배지. | `app/page.tsx` |
| **stats 헬퍼** | 매칭율·검증 수 요약 `reviewStats()`. | `lib/api.ts` |

## 새 환경변수

| 변수 | 용도 | 기본 |
|------|------|------|
| `KCI_API_KEY` | KCI Open API fallback(국내 논문) | 없음(비활성) |
| `F3_CONCURRENCY` | F3 병렬 검증 동시성 | 8 |
| `OPENALEX_ENABLED` | OpenAlex 보조 검증 on/off | true |

> `REDIS_URL`을 실제 인스턴스로 설정하면 서버리스에서도 job 상태가 인스턴스 간 공유됩니다(미설정 시 기존 in-memory 동작 유지).
