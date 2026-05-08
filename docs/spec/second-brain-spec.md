# Second Brain System[Metis Prime] — 스펙 문서(Spec)

> **이 문서의 용도**: 비전·아키텍처·데이터 모델·운영 규칙을 정의하는 **SPEC**. 직접 구현 플랜으로 사용하지 말 것.
> 구현 플랜은 Phase별로 `docs/superpowers/plans/` 아래에 별도 작성된다.
> 각 Phase plan은 superpowers `writing-plans` skill 표준을 따르며, 이 문서를 SPEC으로 참조한다.

---

## 목차

1. [프로젝트 개요](#1-프로젝트-개요)
2. [아키텍처](#2-아키텍처)
3. [기술 스택](#3-기술-스택)
4. [저장소 구조](#4-저장소-구조)
5. [단계별 구현 계획](#5-단계별-구현-계획)
   - Phase 1: Foundation
   - Phase 2: LLM Router (LiteLLM + vLLM)
   - Phase 3: LLM Wiki Pattern (Karpathy)
   - Phase 4: Graphify Integration
   - Phase 5: LangGraph Multi-Agent Orchestration
   - Phase 6: Capture Layer
   - Phase 7: UI & Mobile (선택)
6. [핵심 구성 파일](#6-핵심-구성-파일)
7. [운영 규칙 (Schema)](#7-운영-규칙-schema)
8. [테스트 전략](#8-테스트-전략)
9. [보안 / 프라이버시 체크리스트](#9-보안--프라이버시-체크리스트)
10. [운영 가이드](#10-운영-가이드)
11. [부록](#부록)

---

## 1. 프로젝트 개요

### 프로젝트명
: Metis Prime (metis-prime)

### 비전
Andrej Karpathy의 "LLM Wiki" 패턴을 기반으로, **PC/Laptop에서 일어나는 작업·지식·태스크를 마크다운으로 자동 축적·합성·관리하는 개인용 Second Brain**을 구축한다. RAG, 멀티 에이전트, 지식 그래프(Graphify) 등 최신 AI 패턴을 통합하되, **사용자의 데이터 주권**(로컬 우선, 프라이빗 데이터의 외부 송출 금지)을 최우선 원칙으로 한다.

### 핵심 원칙

1. **Markdown is the source of truth.** 모든 지식은 평문 마크다운으로 저장된다. DB 종속성 없음.
2. **Three-layer separation.** `raw/`(불변 원본) · `wiki/`(LLM 합성) · `schema`(운영 규칙) 분리.
3. **Privacy-aware routing.** 모델 선택은 작업의 민감도/비용/품질을 함께 고려해 동적으로 결정한다.
4. **Provenance everywhere.** 모든 주장에는 `extracted` / `inferred` / `ambiguous` 태그를 부여한다.
5. **Git-versioned.** 모든 변경은 커밋 단위로 추적되어 롤백 가능해야 한다.
6. **Compounding, not chatting.** 같은 질문을 두 번 던지지 않게, 답변은 위키에 환원된다.

### 성공 기준 (Definition of Done)

- [ ] vLLM(Qwen3 AWQ) + Cloud API(OpenAI/Anthropic/Gemini)를 단일 인터페이스로 호출할 수 있다.
- [ ] `raw/inbox/`에 파일을 떨어뜨리면 자동으로 wiki 페이지가 생성/병합된다.
- [ ] 자연어 질문에 wiki + graphify 그래프 + (폴백) RAG로 합성 답변을 받을 수 있다.
- [ ] 매주 자동 lint이 깨진 링크/모순/고립 페이지 리포트를 생성한다.
- [ ] 민감도 태그가 붙은 데이터는 클라우드 API로 송출되지 않는다 (회로 차단기).
- [ ] Obsidian에서 그래프 뷰로 위키 구조를 시각화할 수 있다.
- [ ] 위키 페이지 1,000개 규모에서도 ingest/query가 합리적인 시간 내에 동작한다.

---

## 2. 아키텍처

### 4축 구성

```
┌─────────────────────────────────────────────────────────────┐
│  CAPTURE LAYER                                               │
│  watchdog · web clipper · whisper · clipboard · activity log │
└──────────────────────┬──────────────────────────────────────┘
                       │ raw/inbox/
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  AGENT LAYER (LangGraph)                                     │
│  ingest │ query │ lint │ task-extract │ weekly-review        │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  LLM ROUTER (LiteLLM Proxy)                                  │
│  ┌──────────┬──────────┬──────────┬──────────┐               │
│  │ vLLM     │ Anthropic│ OpenAI   │ Gemini   │               │
│  │ Qwen-AWQ │ Claude   │ GPT      │          │               │
│  └──────────┴──────────┴──────────┴──────────┘               │
└──────────────────────┬──────────────────────────────────────┘
                       │ writes
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  STORAGE LAYER                                               │
│  raw/ │ wiki/ │ tasks/ │ journal/ │ graph/ (graphify)        │
│  + LanceDB (벡터 폴백, 선택)                                  │
└──────────────────────┬──────────────────────────────────────┘
                       │ reads
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  PRESENTATION LAYER                                          │
│  Obsidian (primary) │ Claude Code (CLI) │ MCP servers        │
│  (선택) Telegram bot │ Static site                            │
└─────────────────────────────────────────────────────────────┘
```

### 데이터 흐름의 황금 규칙

- `raw/`는 **append-only**. 어떠한 에이전트도 raw 파일을 수정/삭제하지 않는다.
- `wiki/`는 **LLM이 자유롭게 수정**하되, 모든 변경은 git commit으로 기록되며 페이지 frontmatter에 출처(`sources`)와 신뢰도(`provenance`)가 남는다.
- `graph/`는 **derived data**. 언제든 `wiki/`로부터 재생성 가능해야 한다.

---

## 3. 기술 스택

### 필수 (Phase 1-5)

| 컴포넌트 | 라이브러리 / 도구 | 용도 |
|---|---|---|
| Python | 3.11+ | 런타임 |
| 패키지 관리 | `uv` | 빠른 의존성 관리 |
| LLM 라우터 | `litellm[proxy]` | 멀티 프로바이더 통합 |
| 로컬 LLM 서빙 | `vllm` | Qwen3 AWQ 서빙 (OpenAI 호환) |
| 에이전트 오케스트레이션 | `langgraph`, `langchain-core` | 상태 머신 기반 멀티 에이전트 |
| 지식 그래프 | `graphifyy` (PyPI 패키지명) | NetworkX 기반 그래프 + Leiden clustering |
| 파일 감시 | `watchdog` | inbox 자동 감시 |
| 음성 변환 | `faster-whisper` | 로컬 STT |
| 마크다운 처리 | `mistletoe`, `python-frontmatter` | 파싱 / frontmatter |
| 검증 | `pydantic` v2 | 스키마 검증 |
| CLI | `typer`, `rich` | 사용자 명령 |
| 테스트 | `pytest`, `pytest-asyncio` | 테스트 |
| 로깅 | `structlog` | 구조화 로깅 |
| Git | `pygit2` | 자동 커밋 |
| 큐 | `arq` 또는 `dramatiq` | 백그라운드 잡 (Phase 6+) |

### 선택 (Phase 6-7)

| 컴포넌트 | 라이브러리 | 용도 |
|---|---|---|
| 벡터 DB | `lancedb` | RAG 폴백 |
| 웹 프레임워크 | `fastapi`, `uvicorn` | 모바일/원격 API |
| 텔레그램 | `python-telegram-bot` | 모바일 인터페이스 |
| 활동 추적 | ActivityWatch | OS 레벨 활동 |

### 외부 도구

- **Obsidian** (메인 뷰어, 데스크톱 앱)
- **Obsidian Web Clipper** (브라우저 익스텐션)
- **Claude Code** (개발 + 일상 운영)

### 모델 가이드 (실제 모델명은 사용 시점에 최신으로 갱신)

- **로컬**: Qwen3 8B AWQ (또는 사용자 환경에 맞는 양자화 모델). vLLM 0.6+ 권장
- **클라우드**: 최신 Claude Opus / GPT / Gemini 2.5 Pro (라우팅 정책에 명시)

---

## 4. 저장소 구조

### 모노레포 레이아웃

프로젝트 코드와 vault(데이터)를 **분리**한다. Vault는 별도 git 저장소.

```
~/code/second-brain/                  ← 이 코드베이스 (이 프로젝트)
├── pyproject.toml
├── README.md
├── second-brain-implementation-plan.md  ← 이 문서
├── src/
│   └── second_brain/
│       ├── __init__.py
│       ├── cli.py                    ← typer 진입점
│       ├── config.py                 ← pydantic 설정
│       ├── router/
│       │   ├── __init__.py
│       │   └── litellm_client.py     ← LLM 라우팅
│       ├── agents/
│       │   ├── __init__.py
│       │   ├── ingest.py             ← LangGraph: ingest
│       │   ├── query.py              ← LangGraph: query
│       │   ├── lint.py               ← LangGraph: lint
│       │   ├── task.py               ← LangGraph: task extraction
│       │   └── shared/
│       │       ├── state.py          ← shared state types
│       │       └── prompts/          ← .md 프롬프트 템플릿
│       ├── storage/
│       │   ├── vault.py              ← vault 추상화
│       │   ├── frontmatter.py        ← YAML frontmatter
│       │   └── git_ops.py            ← 자동 커밋
│       ├── graph/
│       │   ├── builder.py            ← graphify 래퍼
│       │   └── query.py              ← graph traversal
│       ├── capture/
│       │   ├── watcher.py            ← watchdog
│       │   ├── transcribe.py         ← whisper
│       │   └── clipper_endpoint.py   ← web clipper 수신
│       └── mcp/
│           └── server.py             ← MCP 서버 (Phase 4+)
├── tests/
│   ├── test_router.py
│   ├── test_ingest.py
│   ├── test_query.py
│   └── fixtures/
├── configs/
│   ├── litellm_config.yaml           ← LLM 라우팅 정책
│   └── prompts/                      ← 시스템 프롬프트
├── scripts/
│   ├── start_vllm.sh
│   ├── start_litellm.sh
│   └── nightly_lint.sh
└── docker/
    ├── docker-compose.yml            ← vLLM + LiteLLM
    └── Dockerfile
```

### Vault 레이아웃 (별도 git 저장소)

```
~/second-brain-vault/                 ← 데이터 저장소
├── .git/
├── .obsidian/                        ← Obsidian 설정 (커밋 안 함)
├── _meta/
│   ├── schema.md                     ← LLM 운영 규칙 (a.k.a. CLAUDE.md)
│   ├── taxonomy.md                   ← 통제 어휘 (태그)
│   ├── routing-policy.md             ← 모델 라우팅 정책
│   └── changelog.md                  ← 위키 구조 변경 이력
├── raw/                              ← APPEND-ONLY
│   ├── inbox/                        ← 자동 캡처 도착지
│   ├── clips/                        ← 웹 클리핑
│   ├── transcripts/                  ← 음성 변환
│   ├── screenshots/
│   └── archived/                     ← ingest 완료 후 이동
├── wiki/
│   ├── concepts/
│   ├── projects/
│   ├── people/
│   ├── places/
│   ├── refs/                         ← 참고 자료 메타 (책, 논문, 영상)
│   └── maps/                         ← 허브 노트 (진입점)
├── tasks/                            ← Obsidian Tasks 호환
│   ├── inbox.md
│   ├── active.md
│   └── archive/
├── journal/
│   └── 2026/
│       └── 2026-05-06.md             ← 일일 활동 로그
└── graph/                            ← graphify 산출물 (gitignore 대상)
    ├── graph.json
    ├── graph.html
    ├── GRAPH_REPORT.md
    └── cache/
```

### `.gitignore` (vault)

```
graph/
.obsidian/workspace*
.obsidian/cache
.DS_Store
```

---

## 5. 단계별 구현 계획

각 Phase는 끝에 **Acceptance Criteria**가 있다. Claude Code는 모든 항목이 통과해야 다음 Phase로 진행한다.

---

### Phase 1: Foundation

**목표**: 빈 vault + 코드베이스 골격을 만들고, 기본 CLI로 vault에 노트를 쓸 수 있게 한다.

#### Tasks

1. **프로젝트 초기화**
   - `uv init second-brain` 으로 프로젝트 생성
   - `pyproject.toml`에 필수 의존성 추가 (위 표 참조, Phase 1 범위만)
   - `pre-commit` 훅 설정 (ruff, mypy, pytest)
   - GitHub Actions(또는 GitLab CI) 기본 워크플로 추가

2. **Vault 초기화 스크립트**
   - `second-brain init <vault-path>` 명령 구현
   - 위 디렉토리 구조 생성
   - `_meta/schema.md` 템플릿 작성 ([섹션 7](#7-운영-규칙-schema) 참조)
   - `_meta/taxonomy.md`에 초기 태그 셋 작성
   - vault에 git init + 초기 커밋

3. **설정 시스템**
   - `pydantic-settings` 기반 `Settings` 클래스
   - 환경 변수, `.env`, `~/.config/second-brain/config.toml` 우선순위
   - vault 경로, 모델 라우팅 정책, 로깅 레벨 등

4. **저장소 추상화 (`storage/vault.py`)**
   - `Vault` 클래스: read/write/list 페이지
   - `WikiPage` 모델 (frontmatter + 본문)
   - 자동 커밋 로직 (`git_ops.py`)
   - **불변성 강제**: `raw/` 경로 쓰기 시 `RuntimeError`

5. **기본 CLI**
   - `second-brain init`
   - `second-brain status` (vault 헬스 체크)
   - `second-brain note add <path>` (수동으로 페이지 생성)

#### Acceptance Criteria

- [ ] `uv run second-brain init ~/test-vault` 실행 시 모든 디렉토리 생성됨
- [ ] `uv run pytest` 통과
- [ ] `uv run mypy src/` 에러 없음
- [ ] `raw/`에 쓰기를 시도하면 예외가 발생함 (테스트로 검증)
- [ ] git 자동 커밋이 동작함

---

### Phase 2: LLM Router (LiteLLM + vLLM)

**목표**: 4개 프로바이더(Qwen 로컬, Claude, OpenAI, Gemini)를 단일 인터페이스로 호출하고, 작업 메타데이터에 따라 동적 라우팅한다.

#### Tasks

1. **vLLM 서빙 셋업**
   - `scripts/start_vllm.sh` 작성. 예시:
     ```bash
     vllm serve Qwen/Qwen3-8B-Instruct-AWQ \
       --host 0.0.0.0 --port 8000 \
       --quantization awq \
       --max-model-len 32768 \
       --served-model-name qwen3-local
     ```
   - GPU 메모리 부족 시 fallback 옵션 문서화
   - Health check 엔드포인트 확인 (`/v1/models`)

2. **LiteLLM 프록시 셋업**
   - `configs/litellm_config.yaml` 작성 ([섹션 6](#6-핵심-구성-파일) 참조)
   - 4개 논리 모델: `local-fast`, `smart-cloud`, `vision-cheap`, `bulk`
   - Fallback 체인 설정
   - `scripts/start_litellm.sh` 작성

3. **라우터 클라이언트 (`router/litellm_client.py`)**
   - `LLMRouter` 클래스
   - 메서드: `complete(messages, *, task_type, sensitivity, **kwargs)`
   - 정책 기반 모델 선택:
     ```
     task_type=ingest_summary, sensitivity=normal     → bulk
     task_type=ingest_summary, sensitivity=private    → local-fast (강제)
     task_type=synthesis_complex                      → smart-cloud
     task_type=vision                                 → vision-cheap
     task_type=lint_check                             → bulk
     ```
   - **회로 차단기**: `sensitivity=private`인데 라우팅 결과가 비-로컬이면 즉시 raise
   - 호출 메트릭 수집 (latency, tokens, cost)

4. **Docker Compose**
   - `docker/docker-compose.yml`에 vLLM + LiteLLM 정의
   - GPU 패스스루 옵션 문서화
   - 로컬 개발 시 사용

5. **CLI 통합**
   - `second-brain llm test` — 모든 모델에 ping 보내고 응답 확인
   - `second-brain llm route --task ingest --sensitivity private` — 라우팅 결과 출력 (dry-run)

#### Acceptance Criteria

- [ ] vLLM이 OpenAI 호환 엔드포인트로 응답함 (`curl localhost:8000/v1/models`)
- [ ] LiteLLM 프록시가 4개 모델 모두 라우팅함
- [ ] `sensitivity=private` 호출이 절대 클라우드로 가지 않음 (단위 테스트)
- [ ] 폴백이 동작함 (smart-cloud 끊으면 bulk로 자동 전환)
- [ ] `second-brain llm test` 모든 프로바이더 통과

---

### Phase 3: LLM Wiki Pattern (Karpathy)

**목표**: Karpathy의 ingest/query/lint 3대 연산을 단일 에이전트(아직 LangGraph 아님, 단순 함수)로 구현한다. **이 단계의 목표는 동작하는 최소 LLM Wiki를 갖는 것이다.**

#### Tasks

1. **Schema (`_meta/schema.md`) 완성**
   - [섹션 7](#7-운영-규칙-schema)의 템플릿 기반으로 vault에 작성
   - 각 위키 페이지의 frontmatter 필드 정의:
     ```yaml
     ---
     title: ...
     type: concept | project | person | ref | map
     status: draft | active | archived
     tags: []
     sources: []          # raw/ 안의 파일 경로들
     provenance:
       extracted: 70      # %
       inferred: 25
       ambiguous: 5
     created: 2026-05-06
     updated: 2026-05-06
     ---
     ```

2. **Ingest 함수 (`agents/ingest.py`, 단순 버전)**
   - 입력: `raw/` 안의 단일 파일 경로
   - 절차:
     1. 파일 타입 판정 (markdown / pdf / html / image / audio)
     2. 추출기 호출 (PDF → unstructured, audio → faster-whisper, html → readability)
     3. LLM 호출 (`task_type=ingest_summary`):
        - 핵심 개념 추출
        - 기존 wiki와 비교 (similar pages 검색 — 단순 키워드 + 임베딩 옵션)
        - 결정: 신규 페이지 / 기존 병합 / 패스
     4. 위키 페이지 생성/수정 (`[[wikilink]]` 자동 삽입)
     5. raw 파일을 `raw/archived/`로 이동
     6. git 커밋 (메시지: `ingest: <source-name>`)
   - **결정적인 부분(파일 이동, 링크 삽입)은 LLM이 아닌 코드로 처리**

3. **Query 함수 (`agents/query.py`, 단순 버전)**
   - 입력: 자연어 질문
   - 절차:
     1. 질문 임베딩 → 유사 wiki 페이지 top-K 검색 (간단히 BM25 + cosine)
     2. 페이지들 + 질문 → LLM (`task_type=synthesis_complex`)
     3. 출처 인용 포함 답변 반환
   - 답변은 stdout, 옵션으로 `journal/`에 자동 기록

4. **Lint 함수 (`agents/lint.py`, 단순 버전)**
   - 검사 항목:
     - 깨진 wikilink (대상 페이지 없음)
     - 고립 페이지 (양방향 링크 0개)
     - 30일 이상 미수정 + status=draft 페이지
     - frontmatter 검증 (pydantic)
     - **Provenance drift**: `inferred` 비율이 70% 초과인 페이지 (LLM 환각 가능)
   - 출력: `journal/lint-YYYY-MM-DD.md`

5. **CLI 명령**
   - `second-brain ingest <path>` — 단일 파일
   - `second-brain ingest --inbox` — `raw/inbox/` 전체
   - `second-brain query "<질문>"`
   - `second-brain lint`

#### Acceptance Criteria

- [ ] 마크다운 파일을 `raw/inbox/`에 넣고 `ingest --inbox`를 실행하면 `wiki/`에 페이지가 생성됨
- [ ] 동일한 주제의 두 번째 파일을 ingest하면 **새 페이지를 만들지 않고 기존 페이지에 병합**되거나 cross-link됨
- [ ] `query`로 질문하면 wiki 페이지를 인용한 답변을 받음
- [ ] `lint`가 인위적으로 만든 깨진 링크를 정확히 탐지함
- [ ] 모든 위키 변경이 git에 커밋되어 `git log`에 추적됨

---

### Phase 4: Graphify Integration

**목표**: graphify를 `wiki/`(및 옵션으로 `raw/`) 위에 돌려 그래프 백엔드를 구축하고, MCP 서버로 에이전트가 그래프를 직접 탐색할 수 있게 한다.

#### Tasks

1. **graphify 설치 및 설정**
   ```bash
   uv add "graphifyy[mcp]"
   ```
   - `.graphifyignore` 작성 (`raw/archived/`, `_meta/` 등 제외)
   - `graphify` CLI가 LiteLLM 프록시를 사용하도록 환경 변수 세팅:
     ```bash
     export ANTHROPIC_API_KEY=dummy
     export ANTHROPIC_BASE_URL=http://localhost:4000  # LiteLLM
     ```
   - **중요**: graphify의 LLM 추출 단계가 절대 raw 클라우드로 직접 가지 않도록 검증

2. **그래프 빌더 래퍼 (`graph/builder.py`)**
   - `GraphBuilder` 클래스
   - `build(scope: 'wiki' | 'raw' | 'all', incremental: bool = True)`
   - 내부적으로 `graphify` CLI 호출 (`subprocess` 또는 Python API)
   - 산출물 위치: `~/second-brain-vault/graph/`
   - **graphify의 `--wiki` 옵션으로 마크다운 export도 함께 생성** → Obsidian이 바로 읽음

3. **그래프 쿼리 인터페이스 (`graph/query.py`)**
   - `GraphQuery` 클래스, `graph.json` 로드
   - 메서드:
     - `find_node(name) -> Node`
     - `neighbors(node, depth=1) -> List[Node]`
     - `shortest_path(from_node, to_node)`
     - `god_nodes(top_n=10)` — 가장 연결 많은 노드
     - `community_summary(community_id)` — Leiden 커뮤니티 요약
     - `surprising_connections(top_n=5)` — 예상 외 연결

4. **Query 에이전트 업그레이드**
   - 기존 Phase 3 query를 다음 순서로 변경:
     1. graphify로 질문에서 엔티티 추출 → 관련 노드 찾기
     2. 노드의 이웃을 따라가며 연결된 wiki 페이지들 수집
     3. 페이지 부족 시 BM25/embedding으로 보강
     4. LLM 합성 단계로 전달
   - **Token 절감 효과 측정**: 같은 질문에 대해 wiki-only vs graph-augmented 비교 메트릭

5. **MCP 서버 등록**
   - graphify가 제공하는 MCP 서버 (`query_graph`, `get_node`, `get_neighbors`, `shortest_path`)를 띄우는 스크립트
   - Claude Desktop/Code 설정에 등록하는 가이드 작성 (`docs/mcp-setup.md`)

6. **자동 그래프 갱신**
   - vault에 새 commit이 들어올 때마다 graphify의 `--update` 모드로 incremental 빌드
   - git post-commit hook 옵션 제공

#### Acceptance Criteria

- [ ] `second-brain graph build` 실행 시 `graph/graph.json`, `graph.html`, `GRAPH_REPORT.md` 생성됨
- [ ] graphify의 LLM 추출 호출이 LiteLLM 프록시를 거침 (로그로 검증)
- [ ] `second-brain graph query "X" --depth 2` 실행 시 X 주변 노드/엣지 출력
- [ ] MCP 서버를 띄우고 Claude Code에서 `query_graph` 도구로 그래프 탐색 가능
- [ ] Confidence 태그(`extracted`/`inferred`/`ambiguous`)가 그래프 엣지에 보존됨
- [ ] 동일 질문에 대해 graph-augmented가 wiki-only 대비 **컨텍스트 토큰 30% 이상 감소** (벤치마크)

---

### Phase 5: LangGraph Multi-Agent Orchestration

**목표**: Phase 3의 단순 함수들을 LangGraph 상태 머신으로 재구성하고, 4개 핵심 그래프(ingest, query, lint, task)를 본격 멀티 에이전트로 만든다.

#### Tasks

1. **공유 상태 정의 (`agents/shared/state.py`)**
   - `IngestState`, `QueryState`, `LintState`, `TaskState` (TypedDict 또는 pydantic)
   - 공통 필드: `messages`, `model_used`, `cost_usd`, `errors`

2. **Ingest Graph 재설계**
   ```
   START
     ├─► classify (파일 타입 판정)
     ├─► extract (타입별 추출기 분기)
     ├─► dedupe (graphify로 중복/유사 검색)
     │     ├─► [신규] generate_page
     │     ├─► [병합] merge_into_existing
     │     └─► [중복] skip
     ├─► cross_link (관련 페이지에 양방향 링크)
     ├─► validate (frontmatter, provenance 비율)
     │     └─► [실패] human_review 큐로 이동
     └─► commit
   END
   ```
   - 각 노드는 `task_type`을 명시해 라우터가 적절한 모델 선택

3. **Query Graph 재설계**
   ```
   START
     ├─► classify_intent (사실 검색 / 합성 / 작업 명령)
     ├─► [사실]   graph_lookup → page_fetch → answer
     ├─► [합성]   graph_neighborhood → multi_page_fetch → reason → answer
     ├─► [작업]   route_to_task_graph
     └─► record (질문/답변을 journal에 기록)
   END
   ```
   - **답변은 옵션으로 wiki에 환원**: 사용자가 `--archive`를 주면 새 wiki 페이지 생성

4. **Lint Graph (스케줄 실행)**
   ```
   START
     ├─► scan_links (병렬)
     ├─► scan_orphans (병렬)
     ├─► scan_provenance (병렬)
     ├─► scan_contradictions (LLM, smart-cloud)
     ├─► aggregate
     └─► report (journal/lint-YYYY-MM-DD.md)
   END
   ```
   - **로컬 cron으로 실행** (원격 에이전트는 vault에 접근 불가). macOS는 `launchd`, Linux는 `systemd timer` 사용 가이드 작성

5. **Task Graph (신규)**
   ```
   START
     ├─► extract_actionables (journal과 ingest 결과에서 TODO 추출)
     ├─► dedupe_with_existing
     ├─► classify_priority
     ├─► assign_due_date (선택)
     └─► append_to_tasks
   END
   ```
   - Obsidian Tasks 호환 포맷 사용 (`- [ ] task @due(2026-05-10) #context`)

6. **공통 인프라**
   - 휴먼-인-더-루프 인터럽트: `human_review/` 디렉토리에 페이지를 두면 사용자가 검토 후 `accepted/rejected`로 이동
   - 비용 트래킹: 각 그래프 실행마다 실제 LLM 비용 누적 → `journal/cost-YYYY-MM.md`
   - 재시도/폴백: LangGraph의 retry edges 활용

#### Acceptance Criteria

- [ ] 4개 그래프가 LangGraph로 동작하고, 각 노드가 라우터를 통해 모델 선택함
- [ ] Ingest 시 중복 감지율이 Phase 3 대비 향상됨 (테스트 코퍼스로 측정)
- [ ] Lint cron이 매주 자동 실행되어 리포트 생성됨
- [ ] 인터럽트로 인한 휴먼 리뷰가 동작함
- [ ] 월간 비용 리포트가 정확함

---

### Phase 6: Capture Layer

**목표**: 사용자의 PC 활동을 자동으로 `raw/inbox/`에 흘려 넣는다.

#### Tasks

1. **파일 감시자 (`capture/watcher.py`)**
   - `watchdog`으로 사용자가 지정한 디렉토리(들) 감시
   - 새 파일 / 수정 파일 → `raw/inbox/`로 심볼릭 링크 또는 복사
   - 정책: `.md`, `.pdf`, `.txt`, 이미지는 자동, 그 외는 화이트리스트
   - `second-brain capture watch start/stop` 데몬

2. **Web Clipper 수신부**
   - Obsidian Web Clipper는 마크다운으로 vault에 직접 저장 가능. 단, **반드시 `raw/clips/`로** 가도록 Obsidian 설정 가이드 작성
   - 또는 자체 HTTP 엔드포인트 (`capture/clipper_endpoint.py`, FastAPI) — 모바일 공유 시트에서 POST

3. **음성 캡처 (`capture/transcribe.py`)**
   - 사용자가 `.m4a`, `.wav` 파일을 `raw/inbox/audio/`에 떨어뜨림
   - 워커가 faster-whisper로 변환 → `raw/transcripts/<original>.md` 생성
   - Frontmatter에 원본 파일 경로 보존

4. **클립보드 캡처 (선택)**
   - 글로벌 단축키로 클립보드 → `raw/inbox/clip-YYYY-MM-DD-HHMMSS.md` 저장
   - macOS는 `pbpaste`, Linux는 `xclip` 사용

5. **활동 로그 (선택, 고급)**
   - ActivityWatch 연동: 일일 활동(앱 사용, 창 제목)을 `journal/YYYY-MM-DD.md`에 자동 추가
   - **민감 데이터 필터링** (비밀번호 매니저, 시크릿 창 제외)

#### Acceptance Criteria

- [ ] 감시 디렉토리에 파일을 만들면 5초 내에 inbox에 도착
- [ ] Obsidian Web Clipper로 클리핑한 페이지가 `raw/clips/`에 저장됨
- [ ] 음성 파일을 inbox에 넣으면 transcript가 생성됨
- [ ] 일일 journal이 활동 로그와 함께 자동 생성됨

---

### Phase 7: UI & Mobile (선택)

**목표**: 모바일에서도 second brain에 접근 가능하게 한다.

#### Tasks

1. **Telegram 봇**
   - `python-telegram-bot` 기반
   - 메시지 → query 그래프 실행 → 답변 반환
   - 파일/음성 첨부 → ingest 큐에 추가
   - 사용자 ID 화이트리스트로 접근 제어

2. **정적 사이트 생성**
   - `mkdocs-material` 또는 `quartz` 등으로 wiki를 정적 사이트로 빌드
   - 매일 cron으로 빌드 → 자체 호스팅 (Cloudflare Pages, Hetzner 등)
   - **검색은 클라이언트 사이드 인덱스**, 민감 페이지는 빌드 시 제외 (`status: private` 태그)

3. **MCP 통합 가이드**
   - Claude Desktop, Cursor에서 second-brain MCP 서버 사용 방법 문서화
   - `query_graph`, `read_page`, `list_pages` 도구 노출

#### Acceptance Criteria

- [ ] Telegram에서 질문/캡처 양방향 동작
- [ ] 정적 사이트가 모바일 브라우저에서 잘 렌더링됨
- [ ] Claude Desktop에서 MCP를 통해 위키 검색 가능

---

## 6. 핵심 구성 파일

### `configs/litellm_config.yaml` (예시)

```yaml
model_list:
  # 로컬 빠른 처리, 프라이버시 강제
  - model_name: local-fast
    litellm_params:
      model: openai/qwen3-local
      api_base: http://localhost:8000/v1
      api_key: dummy
      max_tokens: 4096

  # 복잡한 합성, 위키 페이지 생성
  - model_name: smart-cloud
    litellm_params:
      model: anthropic/claude-opus-4-7
      # Anthropic API key는 환경 변수 ANTHROPIC_API_KEY로

  # 멀티모달 (이미지 + 텍스트)
  - model_name: vision-cheap
    litellm_params:
      model: gemini/gemini-2.5-pro

  # 대량 저비용 (요약, 분류)
  - model_name: bulk
    litellm_params:
      model: openai/gpt-5-mini

router_settings:
  routing_strategy: simple-shuffle
  num_retries: 2
  timeout: 60
  fallbacks:
    - smart-cloud: ["bulk"]
    - vision-cheap: ["smart-cloud"]
  context_window_fallbacks:
    - bulk: ["smart-cloud"]   # 컨텍스트 초과 시 더 큰 모델로

litellm_settings:
  drop_params: true
  set_verbose: false
  cache: true
  cache_params:
    type: local
    ttl: 3600

general_settings:
  master_key: ${LITELLM_MASTER_KEY}
  database_url: sqlite:///./litellm.db
```

### `pyproject.toml` (핵심 부분)

```toml
[project]
name = "second-brain"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "litellm[proxy]>=1.50",
    "langgraph>=0.2",
    "langchain-core>=0.3",
    "graphifyy[mcp]",
    "watchdog>=4.0",
    "faster-whisper>=1.0",
    "python-frontmatter>=1.1",
    "mistletoe>=1.3",
    "pydantic>=2.7",
    "pydantic-settings>=2.4",
    "typer>=0.12",
    "rich>=13.7",
    "structlog>=24.1",
    "pygit2>=1.15",
]

[project.optional-dependencies]
mobile = ["fastapi", "uvicorn", "python-telegram-bot"]
rag = ["lancedb", "sentence-transformers"]
dev = ["pytest", "pytest-asyncio", "ruff", "mypy", "pre-commit"]

[project.scripts]
second-brain = "second_brain.cli:app"

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.mypy]
strict = true
```

### `scripts/start_vllm.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

MODEL="${VLLM_MODEL:-Qwen/Qwen3-8B-Instruct-AWQ}"
PORT="${VLLM_PORT:-8000}"

vllm serve "$MODEL" \
  --host 0.0.0.0 \
  --port "$PORT" \
  --quantization awq \
  --max-model-len 32768 \
  --served-model-name qwen3-local \
  --gpu-memory-utilization 0.9
```

### `scripts/start_litellm.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
litellm --config configs/litellm_config.yaml --port 4000
```

---

## 7. 운영 규칙 (Schema)

이 내용을 그대로 vault의 `_meta/schema.md`에 작성한다. **모든 LLM 에이전트는 작업 시작 시 이 파일을 먼저 읽는다.**

```markdown
# Second Brain — Operating Schema

## You are the wiki maintainer

You are an LLM agent maintaining a personal knowledge wiki. Your goal is to compile
incoming raw material into a structured, interlinked, human-readable markdown wiki.

## Core directories

- `raw/` — IMMUTABLE. Source material. NEVER modify or delete files here.
- `wiki/` — Your workspace. Create, edit, link freely.
- `_meta/` — Schema, taxonomy, policies. Edit only when explicitly asked.
- `tasks/`, `journal/` — Append-mostly. Modify only your own previous entries.

## Wiki page structure

Every wiki page MUST have frontmatter:

```yaml
---
title: <Title Case>
type: concept | project | person | place | ref | map
status: draft | active | archived
tags: [tag1, tag2]   # use only tags from _meta/taxonomy.md
sources: [raw/clips/2026-05-06-article.md, ...]
provenance:
  extracted: 70   # % from sources verbatim/paraphrase
  inferred: 25    # % your synthesis
  ambiguous: 5    # % sources disagree
created: 2026-05-06
updated: 2026-05-06
---
```

Body structure:

1. **One-sentence definition** (first line after frontmatter).
2. **Summary** (2-4 sentences).
3. **Sections** (markdown headings). Each claim either:
   - Cites a source: `... according to [[ref/some-paper]] ^[extracted]`
   - Tags inference: `... which suggests Y ^[inferred]`
   - Tags uncertainty: `... but [[ref/A]] and [[ref/B]] disagree ^[ambiguous]`
4. **Related** (auto-generated from wikilinks).

## Operations

### Ingest
1. Read the new source from `raw/`.
2. Extract atomic concepts.
3. For each concept: search existing wiki for similar pages.
   - If similar exists → merge (preserve both perspectives if conflicting).
   - If new → create page.
4. Add wikilinks to related pages (bi-directional where natural).
5. Move source to `raw/archived/` after successful ingest.
6. Commit with message: `ingest: <source-name>`.

### Query
1. Classify intent (factual / synthesis / task).
2. Use graph traversal first (graphify), wiki text second, raw source last.
3. Always cite sources in answers.
4. If answer required reading 3+ pages, suggest creating a new "synthesis" page.

### Lint
1. Find broken wikilinks.
2. Find orphan pages (no incoming/outgoing links).
3. Find pages with `inferred > 70%` (possible hallucination).
4. Find contradictions across pages on same topic.
5. Output report to `journal/lint-YYYY-MM-DD.md`.

## Routing rules (which model to call)

| Task                    | Model         | Reason                          |
|-------------------------|---------------|----------------------------------|
| ingest summary          | bulk          | Volume; Qwen falls back local    |
| ingest of `private` tag | local-fast    | Privacy; never cloud             |
| concept synthesis       | smart-cloud   | Quality matters most             |
| lint contradiction scan | bulk          | Volume                           |
| vision/PDF extraction   | vision-cheap  | Multimodal                       |
| graphify LLM extraction | bulk          | Volume                           |

NEVER use cloud models when sensitivity=private. Caller must pass this flag.

## Hard rules

- NEVER write to `raw/`.
- NEVER delete a wiki page without user confirmation.
- NEVER guess a wikilink target — verify the page exists or mark `^[ambiguous]`.
- ALWAYS update frontmatter `updated:` field on edit.
- ALWAYS commit after edits with descriptive message.
- If contradiction found, DO NOT silently choose — record both with `^[ambiguous]`.

## Style

- Crisp, encyclopedic. No marketing fluff.
- Past-tense for events, present-tense for concepts.
- Prefer concrete examples over abstract definitions.
- Code blocks for commands; LaTeX for math.
- One concept per page, but link liberally.
```

---

## 8. 테스트 전략

### 단위 테스트 (`tests/`)

- **router**: 각 라우팅 정책 분기 검증, private 차단기 동작 검증
- **vault**: raw 쓰기 차단, frontmatter 파싱, git 커밋
- **ingest**: 가짜 소스 → 예상되는 wiki 페이지 구조
- **lint**: 인위적으로 만든 깨진 링크/고립/모순을 모두 탐지

### 통합 테스트

- **E2E ingest→query 사이클**: 알려진 답이 있는 코퍼스(예: 위키피디아 5개 문서)로 ingest 후 정확한 답변 받는지
- **그래프 정확성**: 알려진 관계가 있는 코퍼스로 graphify 빌드 후 `god_nodes`, `shortest_path` 검증

### 회귀 벤치마크

- `tests/benchmark/`: 동일 질문 100개에 대해 다음을 측정
  - 정확도(소스 인용이 실제 sources에 있는지)
  - 토큰 사용량
  - 지연시간
- 매주 자동 실행하고 추이를 `journal/benchmark.md`에 기록

### 스모크 테스트 명령

```bash
second-brain doctor   # vault 헬스 체크 (Phase 1)
second-brain llm test # 모든 모델 ping (Phase 2)
second-brain bench    # 미니 벤치마크 (Phase 5+)
```

---

## 9. 보안 / 프라이버시 체크리스트

- [ ] **Private tag enforcement**: 라우터에 단위 테스트로 영구 보장
- [ ] **API 키 관리**: `.env`는 절대 커밋 금지, `pre-commit`에 `detect-secrets` 추가
- [ ] **graphify의 LLM 호출 검증**: 실제 트래픽이 LiteLLM 프록시를 거치는지 로그 확인
- [ ] **로컬-only 모드**: `SECOND_BRAIN_LOCAL_ONLY=1` 환경 변수 시 클라우드 라우팅 자체를 raise
- [ ] **Vault 백업**: git remote 설정 (private repo). 추가로 매주 `tar.gz` → 외장 디스크
- [ ] **민감 폴더 필터**: 캡처 시 `~/.ssh/`, password manager 디렉토리, secrets 디렉토리 화이트리스트 차단
- [ ] **로깅 redaction**: structlog에 키/토큰 마스킹 프로세서 추가
- [ ] **MCP 노출 범위**: MCP 서버는 localhost만 바인딩, 외부 노출 금지 (Phase 7에서 별도 인증)

---

## 10. 운영 가이드

### 일상 워크플로

```bash
# 아침
second-brain status              # 어제 무슨 변화가 있었나
cat ~/vault/journal/$(date +%F).md   # 오늘 자 저널

# 작업 중
# (Web Clipper로 기사 클립 → 자동으로 raw/clips/ 적재)
# (음성 메모 → raw/inbox/audio/ 적재)

# 작업 마무리 / 점심 후
second-brain ingest --inbox      # 누적된 inbox 처리

# 질문
second-brain query "OAuth와 OIDC 차이가 내 메모에 어떻게 정리되어 있지?"

# 매주 일요일 (자동)
second-brain lint
second-brain graph build --update
```

### 스케줄러 설정 (Linux/systemd 예시)

`~/.config/systemd/user/second-brain-lint.timer`:

```ini
[Unit]
Description=Weekly second-brain lint

[Timer]
OnCalendar=Sun 03:00
Persistent=true

[Install]
WantedBy=timers.target
```

### 백업

- vault git remote: 사설 저장소 (GitHub private / Gitea 자가 호스팅)
- 매일 자동 push (post-commit hook)
- 매주 `tar.gz` 스냅샷을 외장 디스크에

### 모니터링

- `journal/cost-YYYY-MM.md` — 모델별 비용
- `journal/lint-YYYY-MM-DD.md` — vault 헬스
- `journal/benchmark.md` — 정확도/속도 추이

### 트러블슈팅

| 증상 | 진단 | 조치 |
|---|---|---|
| ingest가 끝없이 돈다 | LLM 응답 무한 루프 | `--max-iterations 5` 옵션 강제 |
| graphify가 클라우드로 호출 | `ANTHROPIC_BASE_URL` 미설정 | LiteLLM 환경변수 재설정 |
| 위키 페이지가 마구 만들어짐 | dedupe 임계값 낮음 | `configs/dedup.yaml` 임계값 0.85→0.75 |
| Obsidian이 wikilinks 깨진 것으로 표시 | 페이지 이동 후 링크 미갱신 | `second-brain refactor link-fix` |

---

## 부록

### 부록 A: Phase 1 완료 후 폴더 트리

(Claude Code는 Phase 1 완료 시 이 트리와 일치하는지 검증해야 한다.)

```
second-brain/
├── pyproject.toml
├── README.md
├── .gitignore
├── .pre-commit-config.yaml
├── .env.example
├── src/second_brain/
│   ├── __init__.py
│   ├── cli.py
│   ├── config.py
│   └── storage/
│       ├── __init__.py
│       ├── vault.py
│       ├── frontmatter.py
│       └── git_ops.py
├── tests/
│   ├── conftest.py
│   ├── test_vault.py
│   └── test_cli.py
└── configs/
    └── (Phase 2부터 추가)
```

### 부록 B: 자주 쓰는 명령어 모음

```bash
# 초기화
second-brain init ~/vault

# 상태 확인
second-brain status
second-brain doctor

# 캡처
second-brain capture watch start
second-brain capture watch stop

# 처리
second-brain ingest <file>
second-brain ingest --inbox

# 검색
second-brain query "..."
second-brain graph query "..." --depth 2

# 유지보수
second-brain lint
second-brain graph build [--update]
second-brain refactor link-fix

# 모델 테스트
second-brain llm test
second-brain llm route --task ingest --sensitivity private

# 비용
second-brain cost --month 2026-05
```

### 부록 C: 참고 자료

- Karpathy의 LLM Wiki gist: 3계층 패턴, ingest/query/lint 연산의 원형
- Graphify 공식 문서: NetworkX + Leiden + tree-sitter, MCP 서버 사양
- LiteLLM Proxy 문서: 라우팅 정책, fallback, 비용 트래킹
- LangGraph: 상태 머신 기반 멀티 에이전트, 휴먼 인 더 루프
- Obsidian Tasks: 태스크 markdown 포맷 사양

### 부록 D: 자주 묻는 결정 사항 (Claude Code 참고)

**Q. 새 위키 페이지를 만들지 기존에 병합할지 모호할 때?**
A. 다음 알고리즘:
1. graphify로 가장 가까운 노드 찾기
2. 코사인 유사도 > 0.85 → 병합
3. 0.70 ~ 0.85 → 새 페이지 + 강한 양방향 링크
4. < 0.70 → 새 페이지 (약한 링크만)

**Q. 같은 사실에 대해 두 소스가 모순될 때?**
A. **양쪽 모두 보존하고 `^[ambiguous]` 태그**. 절대로 LLM이 임의로 한쪽을 선택하지 않는다. lint이 향후 휴먼 리뷰 큐에 올린다.

**Q. 위키 페이지를 정말 삭제해야 하는 경우?**
A. 사용자가 `second-brain page archive <name>`을 명시적으로 호출했을 때만. 삭제가 아닌 `wiki/_archived/`로 이동 + frontmatter `status: archived`.

**Q. raw 파일이 잘못 들어와서 다시 처리하고 싶을 때?**
A. `second-brain ingest --reprocess <archived-path>`. raw는 여전히 불변, 결과 wiki 페이지만 갱신.

**Q. graphify와 wiki가 불일치하면?**
A. wiki가 source of truth. graphify는 derived. `second-brain graph rebuild --full`로 처음부터.

---

## 이 문서를 받은 Claude Code에게

1. **먼저** 이 문서를 끝까지 읽고, 모르는 라이브러리는 공식 문서를 확인하세요.
2. Phase는 순서대로 진행하되, 각 Phase의 **Acceptance Criteria를 먼저 테스트로 작성**하고 시작하세요 (TDD).
3. 모든 디자인 결정은 본 문서의 **핵심 원칙 6개**에 비추어 검토하세요.
4. 모호한 부분이 있으면 `_meta/decisions/YYYY-MM-DD-<topic>.md`로 ADR(Architecture Decision Record)을 만들어 사용자에게 확인 요청하세요.
5. **본 문서를 정답이 아니라 출발점으로** 보세요. 더 좋은 방법이 있으면 ADR로 제안하고 사용자 승인 후 진행하세요.
6. 한국어 주석/문서, 영어 코드/식별자 — 한국 개발자 코드베이스의 일반적 컨벤션입니다.

---

*문서 버전: 1.0 — 2026-05-06*
*다음 리뷰 예정: Phase 3 완료 시*
