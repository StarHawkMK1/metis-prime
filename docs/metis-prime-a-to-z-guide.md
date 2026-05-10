# Metis Prime A-to-Z 사용 가이드

이 문서는 Phase 6까지 구현된 Metis Prime, 즉 `second-brain` 시스템을 처음 설치하는 순간부터 일상 운영, 캡처, ingest, query, graph, MCP, 비용 추적, 자동화, 문제 해결까지 한 번에 따라갈 수 있도록 정리한 운영자용 가이드입니다.

Metis Prime은 Markdown vault를 중심으로 동작하는 local-first 개인 지식 관리 시스템입니다. 원본 자료를 보존하고, LLM과 LangGraph 기반 파이프라인으로 wiki 페이지를 만들고, 지식 그래프와 질의 응답, 작업 추출, lint, 비용 리포트를 함께 제공합니다.

## 1. 전체 구조 이해하기

Metis Prime에는 두 개의 저장소가 있습니다.

| 구분 | 의미 | 예시 |
|---|---|---|
| 코드 저장소 | 지금 이 프로젝트 코드 | `D:\python-workspace\metis-prime` |
| Vault 저장소 | 사용자의 실제 지식 데이터 | `~/second-brain-vault` |

코드는 앱이고, vault는 데이터입니다. vault는 별도의 Git 저장소로 초기화되며 Obsidian에서도 그대로 열 수 있습니다.

큰 흐름은 다음과 같습니다.

```text
capture layer
  -> raw/inbox, raw/clips, raw/transcripts
  -> ingest graph
  -> wiki/
  -> query, lint, task, graph, MCP
  -> journal/, tasks/, human_review/, cost reports
```

핵심 규칙은 다음과 같습니다.

- `raw/`: 원본 자료입니다. 일반 wiki 쓰기 API로는 수정할 수 없습니다.
- `wiki/`: LLM과 사용자가 정리한 지식 페이지입니다.
- `graph/`: graphify 결과물입니다. 언제든 다시 만들 수 있는 derived data입니다.
- `journal/`: 일일 기록, query archive, lint report, cost report가 쌓입니다.
- `tasks/` 또는 `wiki/tasks.md`: 추출된 작업 항목을 관리합니다.
- `human_review/`: 자동 생성 결과가 불확실할 때 사람이 검토하는 큐입니다.

## 2. 설치 전 준비물

필수:

- Python 3.11 이상
- `uv`
- Git
- Windows PowerShell 또는 Bash

선택:

- Obsidian
- Obsidian Web Clipper
- vLLM, 로컬 GPU
- LiteLLM proxy
- capture extra: `faster-whisper`, `fastapi`, `uvicorn`, `pyperclip`

## 3. 의존성 설치

프로젝트 루트에서 실행합니다.

```powershell
uv sync --dev
```

캡처 기능까지 설치하려면:

```powershell
uv sync --dev --extra capture
```

LiteLLM proxy 기능까지 설치하려면:

```powershell
uv sync --dev --extra proxy
```

둘 다 설치하려면:

```powershell
uv sync --dev --extra capture --extra proxy
```

제한된 환경에서 `uv`가 사용자 홈 캐시에 쓰지 못하면, 현재 프로젝트 안에 캐시를 두고 실행합니다.

```powershell
$env:UV_CACHE_DIR = "$PWD\.uv-cache"
uv run second-brain --help
```

## 4. 환경 변수 설정

`.env.example`을 복사합니다.

```powershell
Copy-Item .env.example .env
```

주요 설정:

```env
SECOND_BRAIN_VAULT_PATH=~/second-brain-vault
SECOND_BRAIN_LOG_LEVEL=INFO
SECOND_BRAIN_LOCAL_ONLY=false

SECOND_BRAIN_LITELLM_BASE_URL=http://localhost:4000
SECOND_BRAIN_LITELLM_MASTER_KEY=sk-your-master-key

ANTHROPIC_API_KEY=
OPENAI_API_KEY=
GEMINI_API_KEY=
LITELLM_MASTER_KEY=sk-your-master-key
```

캡처 관련 설정:

```env
SECOND_BRAIN_CAPTURE_WATCH_DIRS=["C:/Users/you/Downloads","C:/Users/you/Documents/inbox"]
SECOND_BRAIN_CLIPPER_HOST=127.0.0.1
SECOND_BRAIN_CLIPPER_PORT=7331
SECOND_BRAIN_WHISPER_MODEL_SIZE=base
```

중요한 보안 설정:

- `SECOND_BRAIN_LOCAL_ONLY=true`: cloud 모델로 가는 호출을 차단합니다.
- `--sensitivity private`: 항상 `local-fast`로 라우팅됩니다.
- clipper server 기본 host는 `127.0.0.1`입니다. 외부 네트워크에 노출되지 않습니다.

## 5. Vault 초기화

새 vault를 만듭니다.

```powershell
uv run second-brain init ~/second-brain-vault
```

현재 세션에서 vault 경로를 지정합니다.

```powershell
$env:SECOND_BRAIN_VAULT_PATH = "$HOME\second-brain-vault"
```

상태를 확인합니다.

```powershell
uv run second-brain status
```

생성되는 주요 디렉터리:

```text
second-brain-vault/
  _meta/
    schema.md
    taxonomy.md
    routing-policy.md
    changelog.md
  raw/
    inbox/
      audio/
    clips/
    transcripts/
    screenshots/
    archived/
  wiki/
    concepts/
    projects/
    people/
    places/
    refs/
    maps/
  tasks/
  journal/
  graph/
  human_review/
    pending/
    accepted/
    rejected/
```

Obsidian을 쓴다면 이 vault 폴더를 그대로 열면 됩니다.

## 6. 수동 wiki 페이지 만들기

직접 wiki 페이지를 만들 수 있습니다.

```powershell
uv run second-brain note add wiki/concepts/python.md --title "Python" --type concept
```

사용 가능한 page type:

- `concept`
- `project`
- `person`
- `place`
- `ref`
- `map`

주의: `note add`로 `raw/` 아래에 쓰면 실패합니다. `raw/`는 원본 자료 영역이므로 capture 명령이나 직접 파일 배치로만 다루는 것이 원칙입니다.

## 7. LLM 라우팅

Metis Prime은 실제 provider 모델명을 직접 여기저기 쓰지 않고, logical model 이름으로 라우팅합니다.

| Task type | normal | private |
|---|---|---|
| `ingest_summary` | `bulk` | `local-fast` |
| `synthesis_complex` | `smart-cloud` | `local-fast` |
| `vision` | `vision-cheap` | `local-fast` |
| `lint_check` | `bulk` | `local-fast` |
| `graph_traversal` | `bulk` | `local-fast` |
| `task_extract` | `bulk` | `local-fast` |
| `lint_contradiction` | `bulk` | `local-fast` |

라우팅만 확인하려면:

```powershell
uv run second-brain llm route --task synthesis_complex --sensitivity private
```

LLM router를 실제로 ping하려면:

```powershell
uv run second-brain llm test
```

`llm test`는 LiteLLM proxy가 실행 중이어야 합니다.

### vLLM과 LiteLLM 실행

vLLM 실행:

```powershell
bash infra/start_vllm.sh
```

LiteLLM proxy 실행:

```powershell
bash infra/start_litellm.sh
```

기본 포트:

| 서비스 | 주소 |
|---|---|
| vLLM | `http://localhost:8000` |
| LiteLLM | `http://localhost:4000` |

설정 파일:

```text
configs/litellm_config.yaml
```

## 8. Capture Layer 사용법

Capture layer는 자료를 vault의 raw 영역으로 넣는 입구입니다.

### 8.1 폴더 감시

감시할 폴더를 지정합니다.

```powershell
$env:SECOND_BRAIN_CAPTURE_WATCH_DIRS='["C:/Users/you/Downloads"]'
```

watcher를 실행합니다.

```powershell
uv run second-brain capture watch
```

이 명령은 foreground에서 계속 실행됩니다. 종료는 `Ctrl+C`입니다.

동작 방식:

- 허용된 확장자만 복사합니다.
- 오디오 파일은 `raw/inbox/audio/`로 들어갑니다.
- 일반 파일은 `raw/inbox/`로 들어갑니다.
- 같은 이름의 파일이 있으면 timestamp suffix로 중복을 피합니다.
- symlink는 복사하지 않습니다.
- `.ssh`, `.aws`, `credentials`, `password`, `private_key`, `secret` 등이 포함된 경로는 차단합니다.

### 8.2 클립보드 캡처

현재 클립보드 텍스트를 `raw/inbox/`에 저장합니다.

```powershell
uv run second-brain capture clip
```

생성 예:

```text
raw/inbox/clip-YYYY-MM-DD-HHMMSS.md
```

클립보드가 비어 있으면 실패합니다.

### 8.3 Web Clipper 서버

FastAPI 기반 clipper endpoint를 실행합니다.

```powershell
uv run second-brain capture serve
```

기본 주소:

```text
http://127.0.0.1:7331
```

health check:

```powershell
Invoke-RestMethod http://127.0.0.1:7331/health
```

clip 저장 테스트:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:7331/clip `
  -ContentType "application/json" `
  -Body '{"title":"Example","url":"https://example.com","content":"Article body"}'
```

저장 위치:

```text
raw/clips/
```

주의: `ingest --inbox`는 `raw/inbox/`만 스캔합니다. `raw/clips/`에 저장된 clip은 개별 path로 ingest합니다.

```powershell
uv run second-brain ingest raw/clips/<clip-file>.md
```

Obsidian Web Clipper 설정은 별도 문서도 참고하세요.

```text
docs/obsidian-web-clipper-setup.md
```

### 8.4 오디오 전사

단일 파일 전사:

```powershell
uv run second-brain capture transcribe C:\path\to\memo.wav
```

`raw/inbox/audio/` 전체 처리:

```powershell
uv run second-brain capture transcribe
```

전사 결과:

```text
raw/transcripts/<audio-stem>.md
```

필요한 extra:

```powershell
uv sync --extra capture
```

### 8.5 일일 journal 생성

오늘 journal 생성 또는 조회:

```powershell
uv run second-brain capture journal
```

특정 날짜:

```powershell
uv run second-brain capture journal --date 2026-05-10
```

저장 위치:

```text
journal/<YEAR>/<YYYY-MM-DD>.md
```

이미 파일이 있으면 덮어쓰지 않습니다. 새로 만들 때는 vault Git log를 참고해 Activity 섹션을 채웁니다.

## 9. Ingest 사용법

ingest는 raw 자료를 wiki 페이지로 바꾸는 LangGraph 파이프라인입니다.

원본을 inbox에 넣습니다.

```powershell
Copy-Item .\some-note.md "$env:SECOND_BRAIN_VAULT_PATH\raw\inbox\some-note.md"
```

단일 파일 ingest:

```powershell
uv run second-brain ingest raw/inbox/some-note.md
```

inbox 전체 ingest:

```powershell
uv run second-brain ingest --inbox
```

민감 자료 ingest:

```powershell
uv run second-brain ingest raw/inbox/private-note.md --sensitivity private
```

ingest graph 흐름:

1. 원본 파일에서 텍스트를 추출합니다.
2. 기존 wiki와 유사도를 검색합니다.
3. LLM에게 create, merge, skip 결정을 요청합니다.
4. provenance를 검증합니다.
5. wiki 페이지를 생성하거나 기존 페이지를 병합합니다.
6. wikilink와 backlink를 보강합니다.
7. 원본 파일을 `raw/archived/`로 이동합니다.
8. vault Git commit을 생성합니다.

inferred provenance가 너무 높으면 wiki에 바로 쓰지 않고 다음 위치로 보냅니다.

```text
human_review/pending/
```

## 10. Human Review

검토 대기:

```text
human_review/pending/
```

승인하려면 파일을 다음 위치로 옮깁니다.

```text
human_review/accepted/
```

그 다음 처리합니다.

```powershell
uv run second-brain review process
```

승인된 파일은 `wiki/concepts/`로 이동합니다.

거절하려면 파일을 다음 위치로 옮깁니다.

```text
human_review/rejected/
```

그리고 같은 명령을 실행합니다.

```powershell
uv run second-brain review process
```

거절된 파일은 review queue에서 삭제됩니다.

## 11. Query 사용법

wiki 기반으로 질문합니다.

```powershell
uv run second-brain query "OAuth와 OIDC의 차이는 무엇인가?"
```

민감 질의:

```powershell
uv run second-brain query "내 개인 프로젝트 노트를 요약해줘" --sensitivity private
```

답변을 journal에 저장:

```powershell
uv run second-brain query "RAG에 대해 내가 정리한 핵심은?" --archive
```

query graph 흐름:

1. 질문 의도를 factual, synthesis, task-like로 분류합니다.
2. factual 질문은 graph lookup을 우선 사용합니다.
3. synthesis 질문은 더 넓은 multi-page retrieval을 사용합니다.
4. graph context가 없으면 BM25 wiki search로 fallback합니다.
5. 답변에는 `[[page-stem]]` 형태의 citation이 포함됩니다.
6. `--archive`를 쓰면 `journal/queries.md`에 Q&A가 추가됩니다.

## 12. Lint 사용법

vault 건강 상태를 검사합니다.

```powershell
uv run second-brain lint
```

검사 항목:

- 깨진 wikilink
- orphan page
- 30일 이상 오래된 draft
- inferred provenance 70% 초과
- 제한된 수의 contradiction 후보

보고서:

```text
journal/lint-YYYY-MM-DD.md
```

## 13. Task 추출

텍스트에서 작업 항목을 추출합니다.

```powershell
uv run second-brain task extract "TODO: 금요일까지 PR 리뷰하고 문서 업데이트하기"
```

파일에서 작업 추출:

```powershell
uv run second-brain task extract C:\path\to\meeting-notes.md
```

민감 자료:

```powershell
uv run second-brain task extract C:\path\to\private-notes.md --sensitivity private
```

TaskGraph 동작:

1. actionable item을 추출합니다.
2. Obsidian Tasks 형식으로 정리합니다.
3. 기존 `wiki/tasks.md`를 읽습니다.
4. 중복 작업을 제거합니다.
5. 새 작업만 append합니다.

작업 형식 예:

```markdown
- [ ] Write project summary @due(2026-05-12) #writing
```

## 14. Knowledge Graph

graphify 기반 지식 그래프를 빌드합니다.

```powershell
uv run second-brain graph build --vault "$env:SECOND_BRAIN_VAULT_PATH"
```

증분 업데이트:

```powershell
uv run second-brain graph build --vault "$env:SECOND_BRAIN_VAULT_PATH" --update
```

scope 선택:

```powershell
uv run second-brain graph build --vault "$env:SECOND_BRAIN_VAULT_PATH" --scope wiki
uv run second-brain graph build --vault "$env:SECOND_BRAIN_VAULT_PATH" --scope raw
uv run second-brain graph build --vault "$env:SECOND_BRAIN_VAULT_PATH" --scope all
```

결과물:

```text
graph/graphify-out/graph.json
graph/graphify-out/graph.html
GRAPH_REPORT.md
```

graph 기반 query:

```powershell
uv run second-brain graph query "Python과 data science는 어떻게 연결되어 있나?" `
  --vault "$env:SECOND_BRAIN_VAULT_PATH" `
  --depth 2
```

중요한 privacy note:

- 앱 내부 LLM 호출은 `LLMRouter`가 private routing을 강제합니다.
- graphify는 외부 CLI이므로 환경 변수 기반 라우팅을 사용합니다.
- private raw 자료에 대해 `--scope raw` 또는 `--scope all`을 사용할 때는 LiteLLM proxy가 local route로 동작하는지 별도로 확인하세요.

## 15. MCP 서버

먼저 graph를 빌드합니다.

```powershell
uv run second-brain graph build --vault "$env:SECOND_BRAIN_VAULT_PATH"
```

MCP 서버 실행:

```powershell
$env:SECOND_BRAIN_VAULT_PATH = "$HOME\second-brain-vault"
sh scripts/start_mcp_server.sh
```

직접 실행:

```powershell
python -m graphify.serve "$env:SECOND_BRAIN_VAULT_PATH\graph\graphify-out\graph.json"
```

Claude Code 등록 방법은 다음 문서를 참고하세요.

```text
docs/mcp-setup.md
```

사용 가능한 MCP tool 예:

- `query_graph`
- `get_node`
- `get_neighbors`
- `shortest_path`

## 16. 비용 추적

LLM 호출 metrics는 월별 JSONL로 저장됩니다.

```text
journal/.metrics/YYYY-MM.jsonl
```

월간 비용 보고서 생성:

```powershell
uv run second-brain cost report
```

보고서 위치:

```text
journal/cost-YYYY-MM.md
```

보고서는 model별, task type별 비용을 보여줍니다. 로컬 모델과 unknown model은 0달러로 계산됩니다.

## 17. 자동화

### 17.1 Windows weekly lint

설치:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install-lint-cron.ps1 `
  -VaultPath "$env:SECOND_BRAIN_VAULT_PATH"
```

확인:

```powershell
Get-ScheduledTask -TaskName "MetisPrime-WeeklyLint"
```

즉시 실행:

```powershell
Start-ScheduledTask -TaskName "MetisPrime-WeeklyLint"
```

삭제:

```powershell
Unregister-ScheduledTask -TaskName "MetisPrime-WeeklyLint" -Confirm:$false
```

### 17.2 Windows daily journal

설치:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install-capture-cron.ps1
```

기본 실행 시간은 매일 06:00입니다.

시간 변경:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install-capture-cron.ps1 -TriggerTime "08:00"
```

확인:

```powershell
Get-ScheduledTask -TaskName "MetisPrime-DailyJournal"
```

### 17.3 Graph post-commit hook

설치:

```powershell
uv run python scripts/install_hooks.py
```

hook은 vault commit 후 graph 증분 업데이트를 시도합니다. graph 업데이트 실패는 non-fatal이며 Git commit 자체는 성공합니다.

동작 조건:

- `SECOND_BRAIN_VAULT_PATH`가 설정되어 있어야 합니다.
- `second-brain` CLI가 PATH에서 실행 가능해야 합니다.
- `graph/graphify-out/graph.json`이 이미 있어야 합니다.

## 18. 일상 운영 루틴

추천 루틴:

```powershell
# 아침
uv run second-brain capture journal
uv run second-brain status

# 작업 중
uv run second-brain capture watch

# 캡처 후
uv run second-brain capture transcribe
uv run second-brain ingest --inbox

# raw/clips 아래의 web clip은 개별 ingest
uv run second-brain ingest raw/clips/<clip-file>.md

# 질문
uv run second-brain query "오늘 아키텍처 결정에서 기억해야 할 점은?"

# 작업 추출
uv run second-brain task extract "$env:SECOND_BRAIN_VAULT_PATH\journal\2026\2026-05-10.md"

# 유지보수
uv run second-brain lint
uv run second-brain graph build --vault "$env:SECOND_BRAIN_VAULT_PATH" --update
uv run second-brain cost report
```

## 19. 주간 유지보수 체크리스트

매주 확인하면 좋은 항목:

- `second-brain lint`
- `second-brain graph build --update`
- `second-brain cost report`
- `human_review/pending/`
- `journal/lint-YYYY-MM-DD.md`
- `GRAPH_REPORT.md`
- vault Git status
- vault remote backup 여부

명령 예:

```powershell
uv run second-brain lint
uv run second-brain graph build --vault "$env:SECOND_BRAIN_VAULT_PATH" --update
uv run second-brain cost report
git -C "$env:SECOND_BRAIN_VAULT_PATH" status
```

## 20. Vault 편집 규칙

수동 편집이나 에이전트 작업 시 지켜야 할 규칙:

- `raw/` 원본은 임의로 수정하거나 삭제하지 않습니다.
- 정리된 지식은 `wiki/`에 둡니다.
- wiki 페이지에는 frontmatter를 유지합니다.
- `sources`는 원본 파일을 가리켜야 합니다.
- `provenance`는 정직하게 기록합니다.
- 모순되는 정보가 있으면 한쪽을 임의로 선택하지 말고 ambiguity를 남깁니다.
- inferred 비율이 높으면 human review를 거칩니다.

wiki frontmatter 예:

```yaml
---
title: Example Concept
type: concept
status: draft
tags: [learning]
sources: [raw/archived/example.md]
provenance:
  extracted: 70
  inferred: 25
  ambiguous: 5
created: 2026-05-10
updated: 2026-05-10
---
```

## 21. 문제 해결

### `uv run`이 cache 초기화에 실패함

프로젝트 내부 cache를 지정합니다.

```powershell
$env:UV_CACHE_DIR = "$PWD\.uv-cache"
uv run second-brain --help
```

uv가 Python 설치 디렉터리를 사용자 홈 아래에 만들려고 하다가 실패하면, Python 3.11을 별도로 설치하거나 uv Python directory를 writable 위치로 설정하세요.

### `llm test`가 실패함

확인할 것:

- LiteLLM proxy가 `SECOND_BRAIN_LITELLM_BASE_URL`에서 실행 중인지
- `LITELLM_MASTER_KEY`와 `SECOND_BRAIN_LITELLM_MASTER_KEY`가 일치하는지
- cloud 모델을 쓴다면 provider API key가 있는지
- `local-fast`를 쓴다면 vLLM이 실행 중인지

### private 자료가 cloud로 갈까 걱정됨

route를 먼저 확인합니다.

```powershell
uv run second-brain llm route --task ingest_summary --sensitivity private
```

예상 결과는 `local-fast`입니다.

graphify는 외부 CLI이므로 private raw 자료를 graphify에 넣을 때는 LiteLLM proxy routing도 별도로 확인하세요.

### `capture watch`가 watch directory 없다고 함

환경 변수를 지정합니다.

```powershell
$env:SECOND_BRAIN_CAPTURE_WATCH_DIRS='["C:/Users/you/Downloads"]'
uv run second-brain capture watch
```

### `capture transcribe`가 faster-whisper 없다고 함

capture extra를 설치합니다.

```powershell
uv sync --extra capture
```

### `capture clip`이 clipboard empty라고 함

텍스트를 먼저 복사하세요. 이 명령은 binary clipboard content를 처리하지 않습니다.

### `graph build`가 실패함

확인할 것:

- `graphify`가 설치되어 있는지
- LiteLLM proxy가 실행 중인지
- `SECOND_BRAIN_LITELLM_BASE_URL`이 올바른지
- `--vault` path가 실제 vault를 가리키는지

### ingest가 archive 단계에서 실패함

흔한 원인:

- 파일이 이미 `raw/inbox/`에서 이동됨
- 같은 이름의 파일이 이미 `raw/archived/`에 있음
- path가 vault 밖으로 escape하려고 함

같은 이름 충돌이면 원본 파일명을 바꾼 뒤 다시 ingest하세요.

### Obsidian에서 wikilink가 깨져 보임

lint를 실행합니다.

```powershell
uv run second-brain lint
```

보고서를 확인합니다.

```text
journal/lint-YYYY-MM-DD.md
```

### cost report가 비어 있음

현재 월의 metrics 파일이 있는지 확인하세요.

```text
journal/.metrics/YYYY-MM.jsonl
```

CLI를 통해 LLM을 호출한 기록이 없으면 report는 0 call로 나올 수 있습니다.

## 22. 명령어 빠른 참조

기본:

```powershell
uv run second-brain init <vault-path>
uv run second-brain status
uv run second-brain ingest [path] [--inbox] [--sensitivity normal|private]
uv run second-brain query "question" [--sensitivity normal|private] [--archive]
uv run second-brain lint
```

노트:

```powershell
uv run second-brain note add <vault-relative-path> --title "Title" [--type concept]
```

LLM:

```powershell
uv run second-brain llm route --task <task-type> --sensitivity normal
uv run second-brain llm test
```

Graph:

```powershell
uv run second-brain graph build --vault <vault-path> [--update] [--scope wiki|raw|all]
uv run second-brain graph query "question" --vault <vault-path> [--depth 2]
```

Task:

```powershell
uv run second-brain task extract "text or file path" [--sensitivity normal|private]
```

Review:

```powershell
uv run second-brain review process
```

Cost:

```powershell
uv run second-brain cost report
```

Capture:

```powershell
uv run second-brain capture watch
uv run second-brain capture transcribe [audio-path]
uv run second-brain capture serve [--host 127.0.0.1] [--port 7331]
uv run second-brain capture clip
uv run second-brain capture journal [--date YYYY-MM-DD]
```

## 23. 첫 실행 추천 시나리오

새 환경에서 최소 확인을 하려면:

```powershell
uv sync --dev --extra capture --extra proxy

Copy-Item .env.example .env
$env:SECOND_BRAIN_VAULT_PATH = "$HOME\second-brain-vault"

uv run second-brain init "$env:SECOND_BRAIN_VAULT_PATH"
uv run second-brain status

"# First Source`n`nMetis Prime is my personal knowledge system." |
  Set-Content "$env:SECOND_BRAIN_VAULT_PATH\raw\inbox\first-source.md"

uv run second-brain llm route --task ingest_summary --sensitivity private
uv run second-brain capture journal
uv run second-brain lint
```

실제 ingest와 query를 하려면 LiteLLM proxy와 필요한 model backend를 먼저 실행하세요.

## 24. 추가로 읽을 문서

- `README.md`: 최소 설치와 개발 명령.
- `docs/obsidian-web-clipper-setup.md`: Obsidian Web Clipper 설정.
- `docs/mcp-setup.md`: Graph MCP 서버 설정.
- `docs/superpowers/plans/2026-05-10-phase-6-capture-layer.md`: Phase 6 구현 계획.
- `docs/superpowers/plans/2026-05-08-phase-5-langgraph-orchestration.md`: LangGraph orchestration 구현 계획.
- `docs/spec/second-brain-spec.md`: 원본 시스템 스펙.
