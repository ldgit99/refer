# 논문 인용·래퍼런스 검토 에이전트 — 기술 조사

> 작성일: 2026-05-30
> 목적: 논문(DOCX / HWP / HWPX)의 본문 인용과 참고문헌을 자동 검토하는 웹 에이전트를 설계하기 위한 사전 조사.

---

## 1. 시스템 개요

### 1.1 핵심 기능
| # | 기능 | 설명 |
|---|------|------|
| F1 | **인용↔래퍼런스 정합성 검증** | 본문에 등장하는 in-text citation(예: `(Lee, 2024)`, `[12]`)이 참고문헌 목록에 빠짐없이 등장하는지, 반대로 참고문헌 목록에만 있고 본문에 인용되지 않은 항목이 있는지 양방향 검증. |
| F2 | **APA 7th 스타일 재포맷** | 추출된 참고문헌을 표준 APA 7판 형식으로 자동 변환하여 사용자에게 제시 (기존 문헌과 diff). |
| F3 | **실재 검증 + DOI 정확성** | 각 참고문헌이 실제로 존재하는 문헌인지 외부 학술 메타데이터 API로 검색하고, 명시된 DOI가 해당 문헌과 일치하는지 확인. DOI 누락 시 자동 보완. |
| **D1** | **원본 포맷으로 다운로드** | 사용자가 업로드한 `.docx` / `.hwp` / `.hwpx`에 검토 결과(APA 변환된 references, 인용 경고 코멘트, DOI 보완)를 반영해 **동일 포맷의 파일로 다운로드** 제공. 자세한 쓰기 전략은 §2.5. |

### 1.2 입력·출력 포맷
- **`.docx`** — Microsoft Word (Open Office XML). 읽기·**쓰기 모두 안정적**.
- **`.hwp`** — 한컴오피스 구버전 바이너리 (OLE 컴파운드 도큐먼트). **쓰기 비공식**, §2.5에서 우회 전략 제시.
- **`.hwpx`** — 한컴오피스 신규 표준 (ZIP+XML, OOXML 유사). **별도 스킬로 처리 예정** — 스킬이 쓰기까지 지원해야 in-place 출력 가능 (미지원 시 DOCX 변환 fallback).
- 출력 파일 정책: **항상 업로드 포맷과 동일한 확장자**로 다운로드(원칙). 포맷별 쓰기 제약이 있는 경우 §2.5의 fallback 룰에 따라 사용자에게 사전 고지.

### 1.3 아키텍처(권장)
논문은 잘못된 결과의 비용이 크므로 **멀티 에이전트 + 상호 검토(critic)** 패턴으로 구성한다. 자세한 토폴로지·역할·합의 규칙은 §7 참조.

```
┌──────────────────┐    multipart/form-data    ┌──────────────────────────────────────┐
│  Web Frontend    │ ────────────────────────► │           FastAPI Backend            │
│  (Next.js +      │ ◄──── SSE 진행률/리포트 ─── │  (LangGraph Orchestrator + arq)      │
│   shadcn/ui)     │                            └──────┬───────────────────────────────┘
└──────────────────┘                                   │
                                                       ▼
                                  ┌──────────────────────────────────────────┐
                                  │  Multi-Agent Layer (LangGraph StateGraph) │
                                  │                                           │
                                  │  Specialists ──┐         ┌── Critics      │
                                  │   Parser       │         │  CitationAudit │
                                  │   CitationExt  │ ◄────►  │  APAStyleCritic│
                                  │   ReferenceExt │ commit  │  EvidenceCritic│
                                  │   Matcher (F1) │ /review │                │
                                  │   Formatter(F2)│         │  Conflict →    │
                                  │   Verifier (F3)│         │  HITL escalate │
                                  │   Writer  (D1) │         │                │
                                  └──────────┬────────────────────────────────┘
                                             │
              ┌──────────────────────────────┼──────────────────────────┐
              ▼                              ▼                          ▼
     ┌─────────────────┐            ┌──────────────────┐       ┌──────────────────┐
     │ Document Parser │            │ Deterministic    │       │  Metadata APIs   │
     │ docx (python-   │            │ Toolbox          │       │ - Crossref       │
     │  docx) / hwp    │            │ - regex extractor│       │ - OpenAlex       │
     │  (pyhwp) / hwpx │            │ - rapidfuzz      │       │ - DOI.org HEAD   │
     │  (사용자 스킬)  │            │ - citeproc-py    │       │ - KCI fallback   │
     └─────────────────┘            └──────────────────┘       └──────────────────┘
```

---

## 2. 문서 파싱·재작성 레이어

### 2.1 DOCX
- **[`python-docx`](https://pypi.org/project/python-docx/)** — 사실상 표준. 단락·런(run)·표를 객체로 노출. 본문 텍스트 추출은 단순하나, 인용 위치(괄호 안의 텍스트) 보존을 위해 **문단 순서·run 단위로 처리**하는 게 안전.
- 보완: 수식·각주(footnote)는 별도 XML 파트에 존재 → `docx.oxml`로 직접 접근 필요.

### 2.2 HWP (구버전 바이너리)
- **[`pyhwp`](https://pypi.org/project/pyhwp/)** — HWP v5 포맷 파서. CLI `hwp5txt`로 plain text 추출 가능. Python 3 호환 fork(`mete0r/pyhwp`) 사용 권장.
- **[`rhwp-python`](https://github.com/DanMeon/rhwp-python)** — Rust 기반 PyO3 바인딩. GIL 해제 + 빠른 텍스트 추출 + PDF/SVG 렌더링. **신규 프로젝트라면 1순위 후보**.
- 백업: `olefile` + LibreOffice headless 변환(`soffice --convert-to docx`)을 fallback로 두면 견고함.

### 2.3 HWPX — `jkf87/hwpx-skill` 채택
사용자가 지정한 스킬 [**jkf87/hwpx-skill**](https://github.com/jkf87/hwpx-skill)을 HWPX 처리의 정식 통로로 사용한다.

- **정체성**: Claude AI 에이전트를 위한 한글(HWPX) 문서 생성·편집 스킬 모음. MCP 서버가 아니라 **Python 스크립트/모듈 + Claude `SKILL.md`** 형태. MIT 라이선스.
- **읽기·쓰기 모두 지원** ✅ — 본 프로젝트의 D1(다운로드) 요구를 만족.
- **HWP → HWPX 변환 내장** ✅ — `convert_hwp.py`가 레거시 HWP를 받아 HWPX로 변환 (§2.4 HWP 쓰기 전략의 핵심 경로).
- **8가지 워크플로**:
  | # | 기능 | 본 프로젝트에서의 활용 |
  |---|------|------------------------|
  | A | Markdown/Text/URL → HWPX 생성 | 검토 보고서 부록 자동 생성에 활용 가능 |
  | B | 템플릿 placeholder 치환 | 사용 안 함 |
  | C | **기존 HWPX 편집 (unpack → 수정 → pack)** | **D1 핵심** — APA-formatted references / 인용 코멘트 삽입 |
  | D | 레퍼런스 기반 새 문서 생성 | 사용 안 함 |
  | E | **HWPX 텍스트 추출** | S1 ParserAgent 입력 |
  | F | 양식 복제 (테이블/이미지/스타일 보존) | 원본 레이아웃 보존 시 활용 |
  | G | 2025 개정 공문서 작성법 준수 | 보고서 부록 작성 시 |
  | H | **HWP → HWPX 변환** | §2.4 HWP 쓰기 fallback 1순위 |
- **주요 스크립트/모듈**
  ```
  scripts/text_extract.py      # 텍스트 추출 (markdown 포맷 옵션)
  scripts/clone_form.py        # 양식 복제 + 치환 (편집 핵심)
  scripts/convert_hwp.py       # HWP → HWPX 변환
  scripts/build_hwpx.py        # 템플릿+XML → HWPX 조립
  scripts/fix_namespaces.py    # ★ 모든 빌드 후 필수 실행 (네임스페이스 후처리)
  scripts/analyze_template.py  # 심층 분석
  hwpx_helpers.py              # 임포트 가능한 헬퍼 라이브러리
  ```
- **의존성**: `python-hwpx`, `lxml`, (HWP 변환 추가) `pyhwp5`, `olefile`.
- **운영 규칙 (스킬 문서에 명시된 강제 규칙)**
  1. 모든 HWPX 빌드/편집 후 `fix_namespaces.py` 실행 — 누락 시 한글에서 파일 손상 처리될 수 있음.
  2. 템플릿 간 스타일 ID 호환 불가 — 한 문서 내에서만 스타일 재사용.
- **본 프로젝트 통합 방법**
  - `backend/app/parsers/hwpx_parser.py` (S1 입력측) → `hwpx_helpers.py` import + `text_extract` 호출로 `ParsedDocument` 생성.
  - `backend/app/writers/hwpx_writer.py` (S7 출력측) → `clone_form.py` 로직 wrapping. patch 모델을 `replacements.json` 포맷으로 직렬화 후 호출 → 마지막에 `fix_namespaces.py` 자동 실행.
  - 스킬 자체는 git submodule로 포함하거나, MIT 라이선스이므로 필요한 모듈만 vendor.
- **공통 출력 스키마** (다른 파서와 동일):
  ```python
  class ParsedDocument(TypedDict):
      full_text: str                 # 본문 평문 (인용 마커 보존)
      paragraphs: list[Paragraph]    # 단락 단위 + 오프셋
      references_section: str | None # 참고문헌 절 원문
  ```
  → docx/hwp/hwpx 파서가 모두 이 스키마로 통일.

### 2.4 참고문헌 절(section) 추출 전략
1. 한국어/영어 헤딩 정규식: `^(참고\s*문헌|References|REFERENCES|Bibliography)\s*$`
2. 헤딩 발견 후 EOF 또는 다음 1수준 헤딩까지를 reference block으로 절단.
3. block 내부에서 한 개 항목을 분리:
   - 번호식: `^\s*\[?\d+\]?\.?\s+` (IEEE/Vancouver)
   - 행간 빈 줄 + 들여쓰기(hanging indent) (APA/저자식)

### 2.5 출력(쓰기) 전략 — D1 다운로드 기능

업로드 포맷을 그대로 보존하면서 검토 결과를 원본 문서에 반영해 다운로드하게 한다. **원본 레이아웃을 깨지 않는 최소 침습 편집**이 원칙.

#### 2.5.1 공통 편집 항목 (포맷 무관)
| 편집 | 어디에 | 내용 |
|------|--------|------|
| **참고문헌 절 재작성** | reference section block | F2 결과(APA 7판 string)로 치환 — 단, 사용자가 UI에서 항목별 accept/reject 가능 |
| **인용 경고 마킹** | 본문 내 in-text citation 위치 | F1에서 orphan/mismatch로 판정된 인용에 코멘트/하이라이트 |
| **DOI 보완** | reference 항목 끝 | F3에서 자동 보완한 DOI를 `https://doi.org/...` 링크로 삽입, EvidenceCritic이 WARNING으로 강등한 경우 코멘트 첨부 |
| **요약 리포트 부록(선택)** | 문서 맨 끝 | 검토 통계(총 인용 수, 매칭율, 검증 실패 수) — 사용자가 UI에서 on/off |

#### 2.5.2 DOCX 쓰기 — `python-docx` + `lxml`
- **표준 라이브러리**: `python-docx`로 단락·런(run) 수정, `lxml`로 OOXML 직접 패치(코멘트·tracked changes는 python-docx가 직접 미지원이므로 OOXML 조작 필요).
- **참고문헌 치환**: reference section 단락 전체를 제거하고 APA-formatted 단락을 hanging indent 스타일로 재삽입.
- **인용 경고**: `w:comment` 요소를 `word/comments.xml`에 추가하고 본문에 `w:commentRangeStart/End` + `w:commentReference`로 연결. 또는 더 간단히 **하이라이트(`w:highlight`)**로 표시.
- **Tracked changes(선택)**: `w:ins`/`w:del`로 삽입/삭제 표시 → 사용자가 Word에서 검토/수락 가능. 학술 워크플로에서 가장 자연스러움.
- 위험: 표 안의 reference, 각주(footnote) 안의 인용은 단락 트리 외부에 있어 별도 처리 필요.

#### 2.5.3 HWPX 쓰기 — `jkf87/hwpx-skill` 사용
§2.3에서 채택한 hwpx-skill의 `clone_form.py` + `build_hwpx.py` + `fix_namespaces.py` 조합으로 in-place 편집을 수행한다. **쓰기 fallback 불필요.**

- **편집 흐름**
  1. 원본 HWPX를 임시 디렉터리에 unpack (스킬이 제공).
  2. 사용자가 채택한 patch 목록을 `replacements.json`(또는 동등한 dict)로 직렬화.
  3. `clone_form.py original.hwpx output.hwpx --map replacements.json` 호출 — 참고문헌 절 치환·인용 코멘트 삽입.
  4. `fix_namespaces.py output.hwpx` **필수 실행** (생략 시 한글에서 손상 처리될 수 있음).
- **권장 패치 모델** (내부 표현, 이후 스킬 호출용으로 직렬화):
  ```python
  class HwpxPatch(TypedDict):
      kind: Literal["replace_section", "annotate_range", "insert_comment", "append_block"]
      target: HwpxLocation       # paragraph_id + char range
      content: str | HwpxBlock
      style: dict | None         # hanging indent, color 등
  ```
- **제약**: 한글의 "변경 내용 추적" 기능은 DOCX의 tracked changes만큼 표준화되어 있지 않음 → HWPX 출력은 **annotated 모드(코멘트/하이라이트)** 를 기본값으로 권장. tracked changes 호환은 §11에서 추후 확인.

#### 2.5.4 HWP(레거시 바이너리) 쓰기 — hwpx-skill 경유
HWP v5 바이너리는 직접 쓰기 가능한 오픈소스 라이브러리가 사실상 없으나, hwpx-skill의 `convert_hwp.py`가 **HWP → HWPX 변환**을 제공하므로 다음 경로가 가능해짐.

**기본 경로 (권장)** ⭐
```
input.hwp
  ↓ convert_hwp.py (hwpx-skill)
intermediate.hwpx
  ↓ §2.5.3 HWPX 편집 파이프라인 (clone_form + fix_namespaces)
output.hwpx
  ↓ 사용자에게 다운로드 (확장자 변경 안내 modal)
```

- **장점**: 자체 변환기로 일관된 품질, LibreOffice 의존성 제거 가능.
- **제약**: HWPX → HWP 역변환은 hwpx-skill에 없음 → 다운로드는 **`.hwpx`로 제공**. 한글 2014 이후 버전은 HWPX를 정상 열람·저장 가능하므로 실사용 지장 없음. UI에서 "원본은 `.hwp`였으나 `.hwpx`로 다운로드됩니다"를 명시.

**Fallback 경로 (사용자가 반드시 `.hwp`로 받고자 하는 경우)**
1. LibreOffice headless: `soffice --headless --convert-to hwp output.hwpx`
   - 표·수식·도형 일부 손상 가능, 사전 동의 modal 필수.
2. 편집 없이 별도 "검토 보고서 PDF/DOCX" 동봉 — 원본 HWP는 무변경.
3. ~~Hancom Office COM 자동화~~ — Windows + 라이선스 필수, SaaS 부적합으로 배제.

업로드 시 UI 라디오 버튼: ① HWPX로 변환해서 받기(권장) / ② 원본 HWP는 그대로, 검토 보고서만 별도 받기.

#### 2.5.5 편집 정책 — 사용자 컨트롤
다운로드 전 사용자가 UI에서 **편집 항목별 accept/reject** 가능해야 함. 모든 specialist+critic 판정이 자동 반영되면 위험 → "한 번 더 사람 확인" 단계는 학술 도구의 신뢰성에 필수.

```
검토 리포트 (UI)
   │
   ├── 사용자가 항목별 ✅/❌ 체크
   │
   ▼
DocumentWriterAgent (§7.3 S7)
   - 채택된 항목만 patch 객체로 변환
   - 포맷별 writer 호출 (docx_writer / hwpx_writer / hwp_writer)
   │
   ▼
편집된 파일 → SSE 완료 → /download/{job_id}/file.{ext}
```

#### 2.5.6 출력 모드 (사용자 선택)
| 모드 | 동작 | 권장 |
|------|------|------|
| **Tracked changes** | 변경분을 Word의 "변경 내용 추적" 형태로 표시 → 사용자가 검토 후 수락/거부 | DOCX 기본값 ⭐ |
| **Annotated** | 원본은 유지, 코멘트·하이라이트만 추가 | HWPX/HWP 기본값 (tracked changes 호환성 불확실) |
| **Final** | 모든 변경을 silently 적용 | 비권장 — 검토 도구의 정체성에 반함 |

---

## 3. F1 — 인용↔래퍼런스 정합성

### 3.1 in-text citation 패턴
| 스타일 | 정규식 (단순화) | 예시 |
|--------|-----------------|------|
| 저자-연도 (APA) | `\(([A-Z][^()]+?),\s*(\d{4}[a-z]?)\)` | `(Kim, 2023)`, `(Lee & Park, 2024a)` |
| 한글 저자-연도 | `\(([가-힣]{2,4}(?:\s*,\s*[가-힣]{2,4})*)[\s,]+(\d{4})\)` | `(이동국, 2024)` |
| 번호식 (IEEE) | `\[(\d+(?:[\-,\s]\d+)*)\]` | `[12]`, `[3, 5-7]` |
| narrative | `[A-Z][a-z]+\s+\((\d{4})\)` | `Smith (2020) reported …` |

### 3.2 매칭 알고리즘
1. **추출**: 본문에서 위 패턴으로 raw citation 토큰 모두 수집 → `{author_key, year, location}`.
2. **정규화**: 저자-연도식은 `(저자 last name set, year)`로 키 생성; 번호식은 reference 목록 인덱스와 직접 매핑.
3. **비교**:
   - **Type A (Orphan citation)** — 본문에 인용했으나 reference에 없음.
   - **Type B (Orphan reference)** — reference에 있으나 본문 인용 없음.
   - **Type C (Year mismatch)** — 본문 `(Lee, 2023)` vs reference `Lee (2024)`.
   - **Type D (Author count mismatch)** — `et al.` 사용 규칙 위반 (APA: 저자 3인 이상 시 첫 인용부터 `et al.`).
4. **퍼지 매칭**: 저자명 표기 변형(`Kim, S.-H.` vs `Kim S H`)은 `rapidfuzz`의 token-set ratio로 0.85+ 임계.

### 3.3 활용 가능한 도구
- **[`refextract`](https://pypi.org/project/refextract/)** — CERN/Invenio 출신, 정규식+pdftotext 기반. reference list 파싱에 강함.
- **[GROBID](https://github.com/kermitt2/grobid)** — CRF 기반, reference 추출 F1 ≈ 0.79로 오픈소스 최고 수준. Docker로 띄워 REST 호출. **PDF 입력 전용** → DOCX/HWP는 plain text 변환 후 reference 블록만 GROBID `processCitationList`에 전달하는 방식.
- **[AnyStyle](https://anystyle.io/)** — Ruby 기반 CRF. GROBID와 함께 양대 산맥. Python에서는 서브프로세스/HTTP로 호출.
- 직접 구현 시 `rapidfuzz` + 위 정규식 조합으로도 한국어 논문 80%+ 커버 가능.

---

## 4. F2 — APA 7판 재포맷팅

### 4.1 라이브러리 옵션
| 라이브러리 | 특징 | 권장도 |
|------------|------|--------|
| **[`citeproc-py`](https://github.com/citation-style-language/citeproc-py)** | CSL(Citation Style Language) 처리 엔진. `apa.csl` 스타일 파일을 그대로 사용 → 표준 보장. CSL JSON 입력 필요. | ★★★★★ |
| **[`citationlib`](https://pypi.org/project/citationlib/)** | DOI / arXiv / PubMed / URL → APA/MLA/Chicago 등 변환. 간편함. | ★★★★ |
| **[`APA-Toolkit`](https://github.com/LYK-love/APA-Toolkit)** | APA 7판 전용, 생성+검증. Markdown 출력. | ★★★ |

### 4.2 권장 파이프라인
```
원본 reference string
    ↓ (GROBID/AnyStyle 또는 regex)
구조화된 CSL JSON  {type, author[], issued, container-title, DOI, ...}
    ↓ (Crossref/OpenAlex로 메타 보강)
완성된 CSL JSON
    ↓ (citeproc-py + apa.csl)
APA 7판 포맷 문자열
    ↓ (diff with 원본)
사용자에게 변경점 하이라이트
```

### 4.3 CSL JSON 스키마 핵심 필드
```json
{
  "type": "article-journal",
  "author": [{"family": "Kim", "given": "Soo"}],
  "issued": {"date-parts": [[2024]]},
  "title": "...",
  "container-title": "...",
  "volume": "12", "issue": "3", "page": "45-67",
  "DOI": "10.1000/xyz123"
}
```

---

## 5. F3 — 실재 검증 & DOI 정확성

### 5.1 사용할 외부 API
| API | 용도 | 무료 | Rate Limit |
|-----|------|------|------------|
| **[Crossref REST API](https://api.crossref.org/swagger-ui/index.html)** | DOI 조회·검색의 1차 소스. `/works/{doi}` HEAD 요청으로 존재 여부 즉시 확인. | ✅ | 50 req/s polite pool (이메일 헤더 권장) |
| **[OpenAlex API](https://docs.openalex.org/)** | Crossref + 추가 enrichment(인용·저자 disambiguation). 2025년 기준 월 15억 호출, Crossref 능가. | ✅ | 100k/day (이메일 헤더로 polite pool) |
| **DOI.org content negotiation** | `curl -LH "Accept: application/vnd.citationstyles.csl+json" https://doi.org/{doi}` → CSL JSON 직반환. | ✅ | 명시적 제한 없음 |
| **Semantic Scholar Graph API** | 보강용 (영향력·인용 수). | ✅ | 1 req/s (no key) |

### 5.2 검증 알고리즘
```
for ref in extracted_references:
    # ① DOI가 있으면 우선 검증
    if ref.doi:
        meta = crossref.get(ref.doi)        # 404면 invalid DOI
        if meta is None: flag("INVALID_DOI")
        else: compare_metadata(ref, meta)   # 제목/저자/연도 fuzzy match
    # ② DOI가 없으면 검색으로 채우기
    else:
        candidates = crossref.search(
            query_bibliographic=ref.raw,
            rows=5
        )
        best = pick_best(candidates, ref)   # 제목 fuzzy + 저자/연도 가중
        if best.score > 0.92:
            ref.doi = best.DOI              # 자동 보완 제안
        else:
            flag("NOT_FOUND")
```

### 5.3 메타데이터 비교 규칙
- **제목**: 소문자화 + 구두점 제거 후 `rapidfuzz.WRatio` ≥ 90
- **저자**: 첫 저자 family name 정확 일치 + 저자 수 일치
- **연도**: ±1년까지 허용(온라인 선공개 vs 출판년도 차이)
- **불일치 시 Severity 분류**: `CRITICAL`(저자 다름), `WARNING`(제목 일부 다름), `INFO`(연도 1년차)

### 5.4 주의사항
- DOI에는 대소문자 구분 없음 (RFC 3986 §6.2.2.1) → 소문자화 후 비교.
- preprint(arXiv, bioRxiv)는 별도 식별자 — `arxiv:` prefix, `10.1101/` DOI 패턴 식별.
- 한국연구재단(KCI) 논문은 Crossref에 없는 경우 多 → **KISTI / KCI Open API**를 fallback으로 추가 권장.

---

## 6. 백엔드 스택

### 6.1 권장
- **언어**: Python 3.12+ (문서 파싱/학술 API 라이브러리 생태계가 압도적)
- **프레임워크**: **FastAPI** — async 기본, Pydantic으로 응답 스키마 자동 검증, OpenAPI 자동 문서화.
- **작업 큐**: 업로드된 문서 파싱·외부 API 호출이 길어질 수 있음 → **Celery + Redis** 또는 **arq**(경량). 진행상황은 **Server-Sent Events**로 프론트에 스트리밍.
- **저장**: 결과 캐싱용 SQLite(개인 도구) / Postgres(다중 사용자). 파일 자체는 임시 디렉터리 + TTL.

### 6.2 핵심 의존성 초기 후보
```
fastapi          uvicorn[standard]
python-docx      pyhwp (또는 rhwp-python)
refextract       rapidfuzz
citeproc-py      lxml
httpx            tenacity   # Crossref/OpenAlex 호출 + 재시도
pydantic v2      redis      arq
```

---

## 7. 멀티 에이전트 시스템 설계

논문 인용 검토는 잘못된 판단의 비용이 큰 작업이다(논문 reject, 표절 의심, 잘못된 DOI 인용). 단일 LLM 호출이나 단일 파이프라인은 hallucination·실수가 누적될 위험이 있어, **분업하는 specialist**와 **독립적으로 검토하는 critic**을 함께 두고, 의견 충돌은 명시적으로 합의(또는 사용자에게 에스컬레이션)하는 구조로 설계한다.

### 7.1 설계 원칙

| 원칙 | 의미 |
|------|------|
| **Deterministic-first** | 가능한 작업은 LLM 없이 정규식/citeproc-py/API 호출 같은 결정론적 도구로 처리. LLM은 모호한 케이스(한국어 reference 분리, 제목 의미 동등성 판단)와 critic 단계에만 사용. |
| **Information asymmetry** | Critic 에이전트는 specialist의 **결론만** 받고 동일 입력을 재처리. 결론에 끌려가지 않도록 specialist의 reasoning trace는 의도적으로 숨김. |
| **Evidence-bound output** | 모든 에이전트의 출력은 근거(원문 오프셋, Crossref response JSON, CSL rule id)를 함께 첨부. 근거 없는 주장은 자동 reject. |
| **Bounded loops** | Critic ↔ specialist revision은 최대 N회(기본 3회). 임계 초과 시 충돌을 그대로 사용자에게 노출(HITL). |
| **Token-thrift** | Subagent는 자신의 작업에 필요한 컨텍스트만 받고, 결과 요약만 반환. 부모 컨텍스트 오염 방지. |

### 7.2 에이전트 토폴로지

```
                          ┌────────────────────────┐
                          │   OrchestratorAgent    │  (LangGraph StateGraph)
                          │   - 상태 머신/체크포인트│
                          │   - 라우팅/리트라이    │
                          └────────────┬───────────┘
                                       │ dispatch
        ┌──────────────────────────────┼──────────────────────────────┐
        ▼                              ▼                              ▼
   [Phase 1: Ingest]            [Phase 2: Analyze]            [Phase 3: Verify]
   ParserAgent                  CitationExtractorAgent        VerifierAgent (F3)
   (deterministic)              ReferenceParserAgent             │
        │                       MatcherAgent (F1)                ▼
        ▼                       FormatterAgent (F2)        EvidenceCritic
   ParsedDocument                    │                          │
                                     ▼                          ▼
                              CitationAuditor              검증 리포트
                              APAStyleCritic                 │
                                     │                          │
                                     └──────────┬───────────────┘
                                                ▼
                                        ConsistencyAuditor
                                        (전체 리포트 교차 점검)
                                                │
                                                ▼
                                        FinalReport → SSE → UI
```

### 7.3 에이전트 카탈로그

#### Specialist (분업)
| # | 에이전트 | 입력 | 출력 | LLM 사용 | 도구 |
|---|----------|------|------|----------|------|
| S1 | **ParserAgent** | 업로드 파일 | `ParsedDocument` | ❌ (한국어 헤딩 모호할 때만) | python-docx, pyhwp, hwpx 스킬 |
| S2 | **CitationExtractorAgent** | 본문 텍스트 | `list[InTextCitation]` (저자/연도/오프셋) | ⚠️ 한국어 narrative만 | regex, rapidfuzz |
| S3 | **ReferenceParserAgent** | reference block | `list[CSLItem]` | ✅ 한국어/한자 혼합 항목 | GROBID, AnyStyle, LLM fallback |
| S4 | **MatcherAgent (F1)** | citations + references | `MatchReport` (orphan/mismatch) | ❌ | 결정론적 매칭 알고리즘 |
| S5 | **FormatterAgent (F2)** | CSLItem | APA 7판 string | ❌ | citeproc-py + apa.csl |
| S6 | **VerifierAgent (F3)** | CSLItem | `VerifiedItem` (DOI/존재 여부) | ⚠️ 후보 ranking 동률일 때 | Crossref, OpenAlex, DOI.org HEAD |
| **S7** | **DocumentWriterAgent (D1)** | 원본 파일 + 사용자가 accept한 patch 목록 | 편집된 동일 포맷 파일 (bytes) | ❌ | python-docx/lxml, hwpx 스킬 writer, LibreOffice headless |

#### Critic (상호 검토)
| # | 에이전트 | 검토 대상 | 역할 | LLM |
|---|----------|-----------|------|-----|
| C1 | **CitationAuditor** | S4 MatchReport | 더 엄격한 기준으로 F1 재실행 + et al. 규칙 위반 추가 검출 | ❌ |
| C2 | **APAStyleCritic** | S5 출력 | APA 7판 룰북(hanging indent, italic, `&` vs `and`, 저자 표기, 연도 표기)로 정합성 검증 | ⚠️ 비표준 문서 타입만 |
| C3 | **EvidenceCritic** | S6 VerifiedItem | Crossref 원본 응답을 보고 메타데이터 일치/불일치 판정을 독립적으로 재산정 (hallucination 방지) | ✅ 제목 의미 동등성 |
| C4 | **ConsistencyAuditor** | 전체 리포트 | 단계별 결과가 서로 모순되지 않는지 (예: F1이 매칭이라고 한 항목을 F3은 NOT_FOUND로 표시?) 교차 점검 | ⚠️ 충돌 요약만 |

#### Orchestration
| # | 에이전트 | 역할 |
|---|----------|------|
| O1 | **OrchestratorAgent** | LangGraph StateGraph로 phase 진행, 체크포인트, 재시도. Specialist↔Critic revision loop 관리. |
| O2 | **HITL Gate** | Critic-specialist 충돌이 N회 후에도 해소 안 되면 사용자에게 결정 요청. |

### 7.4 Specialist ↔ Critic 상호 검토 프로토콜

**Generator-Critic 패턴**을 채택. 학술 검증 분야 연구에서 verifier 에이전트가 fabrication을 52%까지 검출하고, 4회 반복으로 평균 79% 품질 향상이 보고됨(Perseverance Composition Engine 사례).

```
1. Specialist 결과 produce
       │
       ▼
2. Critic이 동일 입력으로 독립 검증
       │
       ├── 동의 ──────────────────► commit
       │
       └── 이의 제기 ──► revision request (구체적 근거 첨부)
                              │
                              ▼
                       Specialist revise
                              │
                              ▼
                         재검토 (max 3회)
                              │
                              └── 미해결 ──► HITL escalate
```

**구체 예시 — F3 VerifierAgent vs EvidenceCritic**
- VerifierAgent: "DOI `10.1000/xyz`는 reference의 논문이 맞다 (score 0.93)"
- EvidenceCritic: Crossref 응답을 받아 제목/저자/연도를 **독립적으로** 비교 → "저자 family name이 'Lee'인데 응답엔 'Yi'다. 동일인일 가능성은 있으나 자동 commit하지 말고 WARNING으로 강등하라."
- → 사용자 UI에 ⚠️ 표시로 노출.

### 7.5 프레임워크 선택: LangGraph

| 프레임워크 | 적합도 | 비고 |
|------------|--------|------|
| **LangGraph** ⭐ | 매우 높음 | StateGraph로 phase·revision loop 모델링이 자연스럽고, **checkpointing/streaming/HITL이 기본 제공**. LangSmith로 각 에이전트 호출 추적·디버깅 가능. FastAPI에 그대로 임베드. |
| CrewAI | 중간 | Role-based가 직관적이나 long-running revision loop의 체크포인트가 약하고, 결정론적 도구와의 혼합이 LangGraph보다 번잡함. PoC 단계라면 빠른 시작 가능. |
| AutoGen | 낮음 | Microsoft가 **maintenance mode**로 전환(2026), 후속은 Microsoft Agent Framework. 신규 채택 비권장. |
| Claude Agent SDK (subagents) | 높음 | Supervisor + fan-out 패턴을 native 지원하고 Anthropic 모델과 궁합 최적. 다만 본 프로젝트는 LLM 호출이 일부 단계에만 필요 → LangGraph로 결정론 + LLM 혼합이 더 유연. |

**채택: LangGraph (Python).** FastAPI 백엔드에 `langgraph` 패키지로 임베드, 각 에이전트는 LangGraph node로 구현. LLM은 Anthropic Claude (Haiku 4.5는 critic/단순 분류, Sonnet 4.6은 모호한 reference 파싱, Opus 4.7은 최종 ConsistencyAuditor) 모델을 task 난이도별로 라우팅.

### 7.6 상태 모델 (LangGraph State)

```python
class ReviewState(TypedDict):
    # Phase 1
    document: ParsedDocument
    # Phase 2
    citations: list[InTextCitation]
    references: list[CSLItem]
    match_report: MatchReport            # S4
    match_report_critic: CriticVerdict   # C1
    formatted: dict[str, str]            # ref_id -> APA string (S5)
    formatted_critic: CriticVerdict      # C2
    # Phase 3
    verified: dict[str, VerifiedItem]    # S6
    verified_critic: CriticVerdict       # C3
    # Final
    consistency: ConsistencyReport       # C4
    hitl_queue: list[ConflictItem]       # 사용자에게 보낼 충돌
    revision_counts: dict[str, int]      # bounded loop guard
    # D1 (다운로드)
    patch_proposals: list[Patch]         # specialist+critic이 만든 모든 변경 후보
    accepted_patches: list[str]          # 사용자가 UI에서 "반영" 체크한 patch id 목록
    output_mode: Literal["tracked", "annotated", "final"]
    output_file_path: str | None         # DocumentWriterAgent(S7) 산출물
```

### 7.7 비용·성능 가드레일

| 항목 | 설계 |
|------|------|
| **LLM 호출 최소화** | S1·S4·S5는 LLM 0회. critic도 결정론 룰 우선, LLM은 모호 케이스만. 평균 reference 30개 논문 기준 LLM 호출 100~200회 이내 목표. |
| **모델 라우팅** | trivial classification → Haiku 4.5, semantic compare → Sonnet 4.6, final cross-check → Opus 4.7. |
| **병렬화** | S6 VerifierAgent는 reference 별로 fan-out (asyncio + Crossref polite pool 헤더). |
| **체크포인트** | LangGraph checkpoint를 Redis에 저장 → 실패 시 phase 단위 재개. |
| **관찰성** | LangSmith trace에 각 에이전트 input/output/판정 근거 기록. 사용자 리포트에 "어느 critic이 무엇을 잡았는지" 노출 가능. |

### 7.8 실패 모드와 방어

| 실패 | 방어 |
|------|------|
| Critic이 specialist에 끌려가 같은 실수를 반복 | Critic은 specialist의 reasoning이 아닌 **원본 입력 + 결론만** 수신. 별도 프롬프트/모델로 분리. |
| 무한 revision loop | `revision_counts[agent] >= 3` 시 강제 종료 → HITL queue로 이관. |
| 외부 API 일시 실패 | tenacity exponential backoff + Crossref↔OpenAlex 이중 조회로 단일 장애점 제거. |
| LLM hallucinated DOI/메타데이터 | EvidenceCritic이 항상 **원본 API 응답을 fetch**하여 specialist 주장을 재검증. specialist의 자체 생성 메타데이터는 신뢰하지 않음. |
| 한국어 reference 잘못 분리 | ReferenceParserAgent 출력에 confidence score를 두고 0.7 미만은 자동으로 HITL queue로 라우팅. |

---

## 8. Harness Engineering 적용 방안

> 참조: [revfactory/harness](https://github.com/revfactory/harness) — Claude Code 플러그인으로, 도메인을 입력하면 **에이전트 팀 + 스킬 정의**를 자동 생성하는 "Team-Architecture Factory". 6가지 팀 패턴과 6단계 워크플로를 메타-디자인 원리로 제공.

### 8.1 왜 harness인가
§7에서 설계한 멀티 에이전트 구조를 **임의로 만들었다고 끝**이 아니라, 검증된 팀 패턴에 매핑·정당화·점진적 보강할 수 있어야 신뢰성이 올라간다. Harness는 다음을 제공:

- 6가지 팀 패턴(Pipeline / Fan-out·Fan-in / Expert Pool / Producer-Reviewer / Supervisor / Hierarchical Delegation)으로 우리 설계를 카테고라이즈.
- 6단계 워크플로(Domain Analysis → Team Architecture Design → Agent Definition → Skill Generation → Integration & Orchestration → Validation & Testing)로 구현 절차를 표준화.
- Claude Code의 `.claude/agents/`, `.claude/skills/` 자동 생성 → **개발 단계의 에이전트(코드 리뷰·테스트·문서 검토)도 동일 방법론으로 구축** 가능.

### 8.2 핵심 결정: 런타임은 LangGraph, 설계·개발 도구는 Harness
| 영역 | 사용 도구 | 이유 |
|------|-----------|------|
| **프로덕션 런타임** (S1~S7, C1~C4 실행) | LangGraph (Python) | checkpoint·HITL·streaming·LangSmith 트레이스가 FastAPI 환경에 통합되어야 함. Harness는 Claude Code agent 정의를 생성하므로 우리 백엔드의 런타임은 아님. |
| **설계 방법론** (팀 패턴 매핑·검증) | Harness 6패턴/6단계 | §7 토폴로지가 어느 패턴 조합인지 명시 → 누락된 critic·HITL 게이트를 체크리스트로 검증. |
| **개발 보조 에이전트** (코드 리뷰·회귀 테스트·문서 검토) | Harness 생성 산출물(`.claude/agents/`) | Claude Code 환경에서 직접 실행. PR 리뷰·CI 게이트·HWPX 샘플 회귀 테스트 자동화. |

→ **두 갈래로 분리**: 사용자가 받는 검토 결과는 LangGraph 런타임이 만들고, 개발자가 받는 코드 리뷰/QA는 Harness가 만든 Claude Code 팀이 수행.

### 8.3 §7 설계의 패턴 분해 (Harness 어휘로 재기술)

| §7 컴포넌트 | Harness 패턴 | 비고 |
|-------------|--------------|------|
| Phase 1 → 2 → 3 단계 진행 | **Pipeline** | OrchestratorAgent가 phase boundary를 제어 |
| Specialist ↔ Critic 검토 루프 | **Producer-Reviewer** | revision max 3회 (§7.4) |
| Reference 항목별 Verifier 병렬 호출 | **Fan-out / Fan-in** | asyncio + Crossref polite pool |
| ReferenceParserAgent의 LLM fallback 분기 | **Expert Pool** | regex 실패 시 LLM 전문가 호출 |
| OrchestratorAgent의 전체 라우팅·재시도 | **Supervisor** | LangGraph StateGraph가 supervisor 역할 |
| 해당 없음 | ~~Hierarchical Delegation~~ | 본 프로젝트 규모에선 과도, 미사용 |

→ 6패턴 중 **5개를 의도적으로 사용**, 1개(Hierarchical)는 의도적으로 배제. 이를 README/CONTRIBUTING에 명시해 후속 변경 시 패턴 정당화를 강제.

### 8.4 6단계 워크플로를 본 프로젝트에 적용

| Harness 단계 | 본 프로젝트의 산출물 | 위치 |
|--------------|----------------------|------|
| 1. Domain Analysis | §1.1 핵심 기능 표 (F1~F3, D1) | `research.md` |
| 2. Team Architecture Design | §7.2 토폴로지 + §8.3 패턴 매핑 | `research.md` |
| 3. Agent Definition Generation | §7.3 카탈로그 → `backend/app/agents/specialists/*.py` 스켈레톤 | 코드 |
| 4. Skill Generation | jkf87/hwpx-skill 채택 (§2.3) + writers/ 모듈 (§9 디렉터리) | 코드 |
| 5. Integration & Orchestration | LangGraph StateGraph (§7.6 상태 모델) | 코드 |
| 6. Validation & Testing | 한국어 KCI 논문 회귀 셋 + critic 임계치 튜닝 (§11) | 테스트 |

### 8.5 개발 단계에서 Harness를 실제로 쓰는 방법

1. **레포 초기화 직후 `/plugin install harness@harness-marketplace` 실행**, `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` 활성화.
2. `Build a harness for "academic citation review with multi-format document I/O"` 트리거 → 베이스라인 `.claude/agents/` 산출물 생성.
3. 생성된 정의를 §7.3 카탈로그와 **diff** → 누락된 critic·HITL 게이트가 있는지 검증. 우리 설계가 더 풍부하면 Harness 결과를 참고만 하고, 누락 항목이 발견되면 §7에 추가.
4. Harness가 생성한 `dev-reviewer`, `qa-runner` 류 에이전트는 **개발 보조용**으로 `.claude/agents/`에 유지 — PR 리뷰·테스트 실행·HWPX 회귀 검사에 활용.
5. 프로덕션 런타임 에이전트는 LangGraph Python 코드로 별도 작성하되, 정의의 책임 분리는 Harness 산출물과 1:1 대응을 유지(이름·역할·도구 목록 일치).

### 8.6 한계와 결정

- Harness는 Claude Code experimental 기능(`AGENT_TEAMS`)에 의존 → 향후 GA 전까지 프로덕션 런타임으로 채택하기엔 리스크가 큼.
- Harness의 "+60% quality improvement" 주장은 저자 자체 A/B(n=15)로, 본 프로젝트 도메인에 일반화된다고 보지 않음. 설계 정당화 도구로만 사용하고 성능 주장은 자체 회귀 셋으로 측정.
- Apache 2.0 라이선스 → vendor 시 NOTICE 파일 필수.

---

## 9. 프론트엔드 선택지 비교

| 옵션 | 장점 | 단점 | 추천 시나리오 |
|------|------|------|---------------|
| **Next.js (App Router) + Tailwind + shadcn/ui** | • 풀스택(라우팅·서버 액션·SSR) 단일 코드베이스<br>• Vercel 무료 호스팅, GitHub 연동 자동 배포<br>• 파일 업로드/스트리밍 UI 자료 풍부<br>• 추후 인증·DB 붙이기 쉬움 | • 초기 학습량 다소<br>• GitHub Pages 정적 호스팅과는 궁합 (Vercel/Cloudflare Pages 권장) | **본격 서비스화 / 포트폴리오용** ⭐ |
| **React + Vite + Tailwind + shadcn/ui** | • SPA에 최적, 빌드 빠름<br>• 정적 빌드 결과물을 **GitHub Pages**에 그대로 배포 가능<br>• 백엔드(FastAPI)는 별도 호스팅 | • SSR/메타데이터/SEO 약함 (도구 앱이라 문제는 없음)<br>• 라우팅은 직접 (`react-router`) | **GitHub Pages에 프론트 호스팅을 꼭 하고 싶을 때** |
| **Streamlit** | • 100% Python, 백엔드와 동일 언어<br>• 파일 업로드/표 표시 위젯 즉시 사용<br>• 프로토타입 1일이면 완성 | • 디자인 자유도 낮음<br>• GitHub Pages 배포 불가 (Streamlit Community Cloud 또는 직접 호스팅 필요)<br>• 멀티유저 동시성 약함 | **개인용 프로토타입 / 빠른 데모** |
| **SvelteKit** | • 번들 가벼움, 문법 간결<br>• SSR도 지원 | • 생태계가 React보다 작음<br>• shadcn 대안(skeleton.dev)은 컴포넌트 적음 | 가볍게 만들고 싶을 때 |

### 9.1 추천: **Next.js 15 (App Router) + Tailwind + shadcn/ui**
**근거**
1. 업로드된 문서를 비동기로 처리하면서 **진행률·결과 스트리밍**을 표시하기에 SSE/RSC가 잘 맞음.
2. shadcn/ui로 `<Table>`(인용 매칭 결과), `<Diff viewer>`(APA 변환 전후), `<Badge>`(검증 상태) 등 핵심 UI를 빠르게 조립.
3. GitHub 저장 시 **Vercel + GitHub 연동**으로 PR 단위 preview 배포가 자동 — 학술 도구 협업에 유리.
4. 백엔드(FastAPI)는 **Fly.io / Railway / Render** 등에 별도 배포하거나, Next.js Route Handler에서 Python 서버리스(Vercel Python Functions)로 얇은 프록시만 두는 구성도 가능.

### 9.2 대안 — 처음부터 가볍게 시작하고 싶다면
**Streamlit으로 PoC → 확정 후 Next.js로 마이그레이션** 이중 단계가 실용적. Streamlit에서 `st.file_uploader`로 docx/hwp/hwpx 받고 결과를 `st.dataframe`으로 그리면 1일 안에 동작.

### 9.3 핵심 UI 화면 (최소 5개)
1. **업로드 / 분석 대시보드** — 파일 드래그앤드롭, 출력 모드(tracked changes / annotated) 선택, **각 에이전트의 진행 단계 실시간 표시** (LangGraph node 단위).
2. **검토 리포트(통합) — 전·후 비교 + 반영 버튼** ⭐ 핵심 UX
   - 좌측: **원본(Before)**, 우측: **수정 제안(After)**.
   - 행 단위로 ✅ 채택 / ❌ 거절 토글 (default: critic이 confidence ≥ 0.9로 추천한 항목만 선체크).
   - 인용 매칭(F1) / APA 변환(F2) / DOI 검증(F3)을 같은 화면에서 탭으로 전환, **각 행마다 critic 코멘트 인라인 표시**.
   - 하단 sticky bar: 채택 N건 / 거절 M건 표시 + **`반영하기` 버튼** (검토 결과를 원본 문서에 적용).
   - 반영 버튼 클릭 시 흐름: 채택된 patch 목록 → DocumentWriterAgent(S7) → writers/ → 동일 포맷 파일 생성 → 자동 다운로드 + "다운로드 받기" 영구 링크.
3. **인용 매칭 디테일** — orphan citation/reference 테이블 (행 클릭 시 원본 문서의 해당 단락으로 점프 미니뷰).
4. **DOI 검증 디테일** — Crossref/OpenAlex 응답 원본, EvidenceCritic 강등 사유, DOI 자동 보완 제안.
5. **HITL 충돌 큐** — Critic-specialist 합의 실패 케이스를 사용자가 직접 결정. 양쪽 근거를 나란히 보여줌. 결정 후 ②번 화면의 해당 항목이 갱신됨.

#### 9.3.1 "반영하기" 버튼 동작 명세
```
사용자 클릭
   ↓
프론트 → POST /jobs/{id}/apply
        body: { accepted_patch_ids: [...], mode: "tracked" | "annotated" }
   ↓
백엔드 → ReviewState.accepted_patches 갱신
   ↓
LangGraph → DocumentWriterAgent (S7) 노드 진입
   ↓
포맷별 writer 호출 (docx_writer / hwpx_writer / hwp_writer)
   ↓
편집된 파일 임시 저장 (TTL 24h) + presigned URL 생성
   ↓
SSE "applied" 이벤트 → UI에 다운로드 버튼 활성화
```

#### 9.3.2 전·후 비교 컴포넌트 권장 스택
- **텍스트 diff**: `react-diff-viewer-continued` 또는 `diff2html` — 단락 단위 word-level diff.
- **레퍼런스 항목 비교**: 좌우 카드 페어로 표시(원본 string vs APA 7판 string), critic 강등 사유를 빨강 badge로.
- **인용 위치 강조**: 본문 미니뷰는 `react-pdf`-style 가상 스크롤 + offset 기반 하이라이트. 행 클릭 시 scrollIntoView.

---

## 10. 저장소 구조 제안

```
refer/
├── README.md
├── research.md                  ← (본 문서)
├── docs/
│   └── architecture.md
├── backend/
│   ├── pyproject.toml
│   ├── app/
│   │   ├── main.py              # FastAPI entry
│   │   ├── parsers/
│   │   │   ├── base.py          # ParsedDocument 공통 스키마
│   │   │   ├── docx_parser.py
│   │   │   ├── hwp_parser.py
│   │   │   └── hwpx_parser.py   # 사용자 제공 스킬 wrapper
│   │   ├── citation/
│   │   │   ├── extractor.py     # in-text 정규식
│   │   │   ├── matcher.py       # F1 결정론 로직
│   │   │   └── formatter.py     # F2 (citeproc-py)
│   │   ├── verifier/
│   │   │   ├── crossref.py      # F3
│   │   │   └── openalex.py
│   │   ├── writers/             # D1 다운로드 (§2.5)
│   │   │   ├── base.py          # Patch 모델, Writer 프로토콜
│   │   │   ├── docx_writer.py   # python-docx + lxml (tracked changes)
│   │   │   ├── hwpx_writer.py   # 사용자 스킬 wrapper
│   │   │   └── hwp_writer.py    # LibreOffice headless 라운드트립
│   │   ├── agents/              # 멀티 에이전트 (LangGraph)
│   │   │   ├── state.py         # ReviewState TypedDict
│   │   │   ├── graph.py         # StateGraph 정의 (entry point)
│   │   │   ├── specialists/
│   │   │   │   ├── parser_agent.py
│   │   │   │   ├── citation_extractor_agent.py
│   │   │   │   ├── reference_parser_agent.py
│   │   │   │   ├── matcher_agent.py
│   │   │   │   ├── formatter_agent.py
│   │   │   │   ├── verifier_agent.py
│   │   │   │   └── writer_agent.py     # S7 — accepted patches → writers/
│   │   │   ├── critics/
│   │   │   │   ├── citation_auditor.py
│   │   │   │   ├── apa_style_critic.py
│   │   │   │   ├── evidence_critic.py
│   │   │   │   └── consistency_auditor.py
│   │   │   ├── hitl.py          # 충돌 escalation
│   │   │   └── routing.py       # 모델 라우팅 (Haiku/Sonnet/Opus)
│   │   └── api/
│   │       └── routes.py        # SSE 진행률 + 결과
│   └── tests/
└── frontend/                    # Next.js
    ├── package.json
    ├── app/
    │   ├── page.tsx             # 업로드
    │   ├── report/[id]/page.tsx # 결과
    │   └── api/                 # BFF (optional)
    └── components/ui/           # shadcn
```

---

## 11. 개발 로드맵 (제안)

| 단계 | 산출물 | 기간(목표) |
|------|--------|-----------|
| 0. 환경 구축 | repo 초기화, FastAPI hello, Next.js 스캐폴드, LangGraph 의존성, **harness 플러그인 설치 + 베이스라인 산출(.claude/agents)** | 1d |
| 1. DOCX 파서 + ParsedDocument 스키마 | docx → text + reference block (S1 ParserAgent) | 1d |
| 2. F1 결정론 코어 | 본문 정규식 추출 + reference 항목 분리 + 매칭 리포트 (S2/S3/S4) | 2d |
| 3. F3 (Crossref/OpenAlex 연동) | S6 VerifierAgent — DOI 검증 + 검색 보완 | 1.5d |
| 4. F2 (APA 변환) | S5 FormatterAgent — citeproc-py + CSL JSON 매핑 | 2d |
| 5. **D1 DOCX writer (tracked changes)** | S7 DocumentWriterAgent + `writers/docx_writer.py` + patch 모델 | 2d |
| 6. **LangGraph 통합** | OrchestratorAgent + ReviewState(patch_proposals 포함) + phase routing | 1.5d |
| 7. **Critic 에이전트 추가** | CitationAuditor / APAStyleCritic / EvidenceCritic / ConsistencyAuditor + revision loop | 2.5d |
| 8. **HITL queue + 모델 라우팅** | 충돌 escalation API, Haiku/Sonnet/Opus 분기 | 1.5d |
| 9. **jkf87/hwpx-skill 통합** | HWPX 읽기/쓰기 wrapper + HWP → HWPX 변환 경로 + `fix_namespaces.py` 자동 실행 | 2d |
| 10. **Frontend UI** — 업로드/대시보드 + 진행 표시 | shadcn 베이스 + SSE 스트리밍 + 출력 모드 라디오 | 2d |
| 11. **Frontend UI — ⭐ 전·후 비교 + 반영 버튼** | react-diff-viewer 통합, 항목별 ✅/❌, sticky bar, `/jobs/{id}/apply` 호출, 다운로드 링크 | 3d |
| 12. Frontend UI — HITL 충돌 큐 | 충돌 결정 UI + ReviewState 갱신 연동 | 1.5d |
| 13. 배포 (Vercel + Fly.io) | GitHub Actions CI, preview deploy, LangSmith 연결, LibreOffice headless 컨테이너 | 1.5d |
| 14. 한국어 KCI 회귀 셋 + 튜닝 | 실 논문 10건, critic 임계치/HITL 임계치 결정 | 2d |
| 15. (optional) Harness 산출물 ↔ 실제 카탈로그 diff 회귀 | 설계 누락 자동 감지 CI 잡 | 1d |

---

## 12. 미해결 과제 / 추후 결정 사항

1. **PDF 입력도 받을지** — 현 요구사항엔 없지만, 학술 워크플로 특성상 자주 요청됨. → GROBID 사용 시 거의 무료로 추가 가능.
2. **한국어 reference 자동 분리** — 한글 저자 + 한문 병기 + 영문 부제 혼합 케이스는 정규식만으론 한계. → ReferenceParserAgent의 LLM fallback로 흡수하되, confidence < 0.7는 HITL queue.
3. **사용자 인증** — 다중 사용자/이력 저장 필요 시 NextAuth + Postgres 추가.
4. **GitHub Pages 단독 배포 가능성** — 백엔드 없이는 F3(외부 API 호출)·멀티 에이전트 오케스트레이션 불가능. CORS 문제로 직접 호출도 어려움. → **별도 백엔드 호스팅 필수**.
5. **하이라이트/오프셋 추적** — 본문 내 인용의 정확한 문자 오프셋(파라그래프 idx + char range)을 유지해야 UI에서 원문 점프 가능 → 파서 단계부터 메타데이터 보존 설계.
6. **Critic 임계치 튜닝** — revision loop max 횟수, fuzzy match threshold, confidence cutoff 등 하이퍼파라미터는 실제 KCI/SCI 논문 샘플로 회귀 테스트하며 결정. 너무 엄격하면 HITL queue가 폭발, 너무 느슨하면 critic 무력화.
7. **LangSmith 비용** — 자체 호스팅 OpenTelemetry로 대체 가능한지 검토 (학술 오픈소스 도구 특성상 호스팅 비용 민감).
8. **에이전트 결과 캐싱** — 같은 DOI를 여러 번 검증하지 않도록 Redis로 VerifierAgent 결과 24h TTL 캐시 권장.
9. **HWPX tracked-changes 호환성** — 한컴오피스 변경 내용 추적 기능과 hwpx-skill `clone_form.py` 패치의 호환성 미확인. 우선 annotated 모드(코멘트/하이라이트)를 기본값으로 두고, 한글 2024+ 실측 후 결정.
10. **HWP → HWPX 변환 시 확장자 변경 UX** — 원본이 `.hwp`였는데 `.hwpx`로 다운로드되는 점에 대해 사용자가 거부감 가질 가능성. 업로드 시 명시적 동의 step 또는 모드 선택 라디오로 완화.
11. **Harness experimental 의존성** — `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`에 의존 → 향후 비활성화/스키마 변경 시 개발 보조 에이전트 영향. 프로덕션 런타임은 LangGraph로 분리되어 있어 사용자 영향은 없음.
12. **patch idempotency** — 사용자가 같은 항목을 두 번 "반영"하거나 부분 반영 후 추가 반영할 때 patch가 중복 적용되지 않도록 patch id 기반 멱등 처리 필요.
13. **편집된 파일 보관 정책** — TTL 24h 권장, GDPR/개인정보 고려해 원본 파일은 처리 직후 삭제, 결과 파일도 다운로드 후 자동 만료.

---

## 부록 A. 참고 자료

### 라이브러리 / 도구
- python-docx — https://pypi.org/project/python-docx/
- pyhwp — https://pypi.org/project/pyhwp/ , https://github.com/mete0r/pyhwp
- rhwp-python — https://github.com/DanMeon/rhwp-python
- **jkf87/hwpx-skill** (채택, MIT) — https://github.com/jkf87/hwpx-skill
- python-hwpx (hwpx-skill 의존) — https://pypi.org/project/python-hwpx/
- refextract — https://pypi.org/project/refextract/
- GROBID — https://github.com/kermitt2/grobid
- AnyStyle — https://anystyle.io/
- citeproc-py — https://github.com/citation-style-language/citeproc-py
- CSL Styles (apa.csl) — https://github.com/citation-style-language/styles
- citationlib — https://pypi.org/project/citationlib/
- APA-Toolkit — https://github.com/LYK-love/APA-Toolkit
- rapidfuzz — https://github.com/rapidfuzz/RapidFuzz

### API 문서
- Crossref REST API — https://api.crossref.org/swagger-ui/index.html
- Crossref tips & tricks — https://www.crossref.org/documentation/retrieve-metadata/rest-api/tips-for-using-the-crossref-rest-api/
- OpenAlex — https://docs.openalex.org/
- DOI content negotiation — https://citation.crosscite.org/docs.html
- Semantic Scholar — https://api.semanticscholar.org/

### 프론트엔드
- Next.js — https://nextjs.org/docs
- shadcn/ui — https://ui.shadcn.com/
- Vite — https://vitejs.dev/
- Streamlit — https://docs.streamlit.io/

### 멀티 에이전트 프레임워크 / 패턴
- **revfactory/harness** (Apache 2.0, 채택 — 설계 메타툴) — https://github.com/revfactory/harness
- LangGraph — https://langchain-ai.github.io/langgraph/
- LangSmith (관찰성) — https://docs.smith.langchain.com/
- CrewAI — https://docs.crewai.com/
- Claude Agent SDK (subagents/agent teams) — https://code.claude.com/docs/en/agent-teams
- Anthropic Managed Agents (multi-agent sessions) — https://platform.claude.com/docs/en/managed-agents/multi-agent
- Multi-Agent Orchestration: 5 Patterns That Work — https://www.digitalapplied.com/blog/multi-agent-orchestration-5-patterns-that-work
- Verifier Pattern in Multi-Agent Systems — https://www.mindstudio.ai/blog/verifier-pattern-multi-agent-systems-independent-review
- Generator-Critic / Critique Agent 개요 — https://www.emergentmind.com/topics/critique-agent
- Research Reviewer Agents (literature review automation) — https://medium.com/@boyuanwu01/research-reviewer-agents-building-a-multi-agent-system-for-automating-literature-reviews-f3515c1b3693

### 연구 / 평가
- Comparing Free Reference Extraction Pipelines — https://zenodo.org/records/10582214
- Structured references from PDF articles — https://arxiv.org/pdf/2205.14677
- Identifying and correcting invalid citations due to DOI errors in Crossref — https://arxiv.org/pdf/2111.11263
- LLM feedback for review quality (ICLR 2025, 20K reviews) — https://arxiv.org/pdf/2504.09737
- Multi-Agent Critique & Revision — https://www.emergentmind.com/topics/multi-agent-critique-and-revision
