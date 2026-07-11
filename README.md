# LocalAI

M5 Pro Mac에서 완전히 로컬로 동작하는 개인용 AI 서비스.  
OpenAI 호환 API, 멀티에이전트 하네스, RAG, 웹 검색, Telegram/Discord 봇을 하나의 서버에서 제공합니다.

---

## 기능

| 기능 | 설명 |
|---|---|
| **OpenAI 호환 API** | `/v1/chat/completions` — streaming / non-streaming |
| **멀티에이전트 하네스** | LangGraph 기반 Orchestrator → RAG / Search / Code / Synthesize → Judge |
| **RAG** | PDF·TXT·MD 문서 인덱싱 + ChromaDB 벡터 검색 |
| **웹 검색** | SearXNG → Tavily → DuckDuckGo 3단계 폴백 (API 키 불필요) |
| **Apple 앱 통합** | 캘린더·리마인더·날씨·노트·메시지·연락처·음악·위치 (orchard CLI) |
| **Google Workspace** | Sheets 읽기/쓰기/추가, Docs 읽기/편집, Drive 검색 (Service Account) |
| **Telegram 봇** | 채팅, 음성 메시지(STT), 파일 업로드(RAG 자동 인덱싱), 대화 히스토리 |
| **Discord 봇** | 채널별 세션, `!clear` 명령어 |
| **브리핑 스케줄** | 웹 UI에서 주제·시각 등록 → 매일 자동 조사 후 Telegram 전송 |
| **MCP 서버** | Claude Code에서 orchard 도구 직접 사용 (`~/.claude/settings.json` 등록) |

---

## 아키텍처

```
사용자 (Telegram / Discord / API 클라이언트)
        │
        ▼
  FastAPI 서버 (api/)
        │
        ▼
  LangGraph 하네스 (harness/)
  ┌─────────────────────────────────────────┐
  │  Orchestrator → route 결정              │
  │    ├─ "rag"        → Retriever (RAG)    │
  │    ├─ "search"     → SearXNG / Tavily   │
  │    │                 / DuckDuckGo       │
  │    ├─ "code"       → Code Agent         │
  │    ├─ "rag+search" → RAG + Search       │
  │    ├─ "tools"      → orchard (Apple 앱) │
  │    └─ "direct"     → 바로 응답          │
  │  Synthesize → 컨텍스트 합성             │
  │  Judge → 품질 평가 (재시도 최대 2회)    │
  └─────────────────────────────────────────┘
        │
        ▼
  MLX-LM 모델 (core/)          ChromaDB (rag/)
  Gemma 4 (여러 인스턴스)        nomic-embed-text-v2-moe
  mlx-whisper (STT)            orchard CLI (Apple 앱)
```

### 에이전트별 모델 할당

| 에이전트 | 역할 | 모델 |
|---|---|---|
| Orchestrator | 쿼리 분석 · 라우팅 | gemma-4-31b-it-4bit |
| Code | 코드 생성 | gemma-4-31b-it-4bit (공유) |
| RAG | 문서 기반 답변 | gemma-4-26b-a4b-it-4bit |
| Judge | 응답 품질 평가 | gemma-4-26b-a4b-it-4bit (공유) |
| Search | 검색 결과 요약 | gemma-4-26b-a4b-it-4bit (공유) |
| Summary | 최종 합성 | gemma-4-26b-a4b-it-4bit (공유) |
| Embedding | 문서 임베딩 | nomic-ai/nomic-embed-text-v2-moe |
| STT | 음성 → 텍스트 | mlx-community/whisper-large-v3-turbo |

메모리 사용량: **~30 GB** (128 GB 중)

---

## 요구사항

- macOS (Apple Silicon) — M1 이상
- Python 3.11+
- Docker Desktop (SearXNG 실행용)
- HuggingFace 계정 (모델 다운로드)
- ffmpeg (음성 메시지 STT용, `brew install ffmpeg`)

---

## 설치

```bash
# 1. 저장소 클론
git clone <repo-url>
cd LocalAI

# 2. 가상환경 생성 및 패키지 설치
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. 환경 변수 설정
cp .env.example .env
# .env 파일을 열어 토큰/API 키 입력

# 4. HuggingFace 로그인 (최초 1회)
huggingface-cli login

# 5. SearXNG 실행
docker compose -f docker/docker-compose.yml up -d
```

---

## 환경 변수 (.env)

```env
# 모델 (mlx-community HuggingFace — MoE 26B-A4B 계열만 mlx-lm 호환)
ORCHESTRATOR_MODEL=mlx-community/gemma-4-26B-A4B-it-OptiQ-4bit
CODE_MODEL=mlx-community/gemma-4-26B-A4B-it-OptiQ-4bit
RAG_MODEL=mlx-community/gemma-4-26b-a4b-it-4bit
JUDGE_MODEL=mlx-community/gemma-4-26b-a4b-it-4bit
SEARCH_MODEL=mlx-community/gemma-4-26b-a4b-it-4bit
SUMMARY_MODEL=mlx-community/gemma-4-26b-a4b-it-4bit
EMBEDDING_MODEL=nomic-ai/nomic-embed-text-v2-moe

# STT (음성 인식)
STT_MODEL=mlx-community/whisper-large-v3-turbo
STT_ENABLED=true

# API 서버
API_HOST=0.0.0.0
API_PORT=8000

# 검색
SEARXNG_URL=http://localhost:8080
TAVILY_API_KEY=              # SearXNG 미응답 시 폴백

# 사용자 컨텍스트 (쿼리에 자동 주입)
USER_LOCATION=서울, 한국        # 날씨·로컬 정보 쿼리에 활용

# 메신저 봇 (선택)
TELEGRAM_BOT_TOKEN=
DISCORD_BOT_TOKEN=

# Google Workspace (Service Account)
GOOGLE_CREDENTIALS_PATH=./data/google_credentials.json

# 데이터 경로
VECTOR_DB_PATH=./data/vectordb
MODELS_PATH=./data/models
```

---

## 실행

```bash
# 서버 시작
source .venv/bin/activate
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000

# 상태 확인
curl http://localhost:8000/health
```

macOS 부팅 시 자동 실행은 launchd 서비스로 등록되어 있습니다.  
서비스 관리는 `scripts/service.sh` 참조.

---

## API 엔드포인트

### 채팅

```bash
# Non-streaming
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "localai",
    "messages": [{"role": "user", "content": "안녕하세요"}],
    "stream": false
  }'

# Streaming (SSE)
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"localai","messages":[{"role":"user","content":"안녕"}],"stream":true}' \
  --no-buffer
```

세션 유지: `X-Session-ID: <uuid>` 헤더 추가

### 문서 (RAG)

```bash
# 파일 업로드 (PDF, TXT, MD)
curl -X POST http://localhost:8000/v1/documents/upload \
  -F "file=@document.pdf"

# 인덱스 통계
curl http://localhost:8000/v1/documents/stats

# 문서 삭제
curl -X DELETE http://localhost:8000/v1/documents/document.pdf
```

### 브리핑 스케줄

웹 UI: `http://localhost:8000/schedules`

```bash
# 스케줄 목록
curl http://localhost:8000/v1/schedules

# 스케줄 추가
curl -X POST http://localhost:8000/v1/schedules \
  -H "Content-Type: application/json" \
  -d '{
    "name": "미국 주식 브리핑",
    "topic": "어제 미국 주식 시장 브리핑을 한국어로 정리해줘.",
    "hour": 8,
    "minute": 45,
    "chat_id": "<telegram-chat-id>"
  }'

# 즉시 실행 (테스트)
curl -X POST http://localhost:8000/v1/schedules/1/run

# 활성/비활성 토글
curl -X PATCH http://localhost:8000/v1/schedules/1/toggle

# 삭제
curl -X DELETE http://localhost:8000/v1/schedules/1
```

### 기타

```bash
curl http://localhost:8000/health        # 서버 상태
curl http://localhost:8000/v1/models     # 로드된 모델 목록
curl http://localhost:8000/docs          # Swagger UI
```

---

## Telegram 봇

1. `@BotFather` 에서 봇 생성 후 토큰 발급
2. `.env` 의 `TELEGRAM_BOT_TOKEN` 설정
3. 서버 재시작

| 명령어 | 설명 |
|---|---|
| `/start` | 봇 시작 |
| `/help` | 도움말 |
| `/clear` | 대화 히스토리 초기화 |
| 텍스트 전송 | AI 답변 |
| PDF/TXT 파일 전송 | RAG 지식베이스에 자동 인덱싱 |
| 음성 메시지 전송 | mlx-whisper로 텍스트 변환 후 AI 답변 |

---

## 프로젝트 구조

```
LocalAI/
├── api/                  # FastAPI 서버
│   ├── main.py           # 앱 진입점 · lifespan
│   ├── routes/           # chat, documents, health, models
│   ├── schemas.py        # OpenAI 호환 Pydantic 스키마
│   └── dependencies.py   # 세션 의존성 주입
├── core/                 # MLX 모델 관리
│   ├── config.py         # 설정 (Pydantic Settings)
│   ├── model.py          # ModelManager · ModelInstance
│   ├── embeddings.py     # EmbeddingManager (nomic)
│   └── stt.py            # STTManager (mlx-whisper)
├── harness/              # LangGraph 멀티에이전트
│   ├── graph.py          # 그래프 빌드
│   ├── nodes.py          # 각 에이전트 노드
│   ├── state.py          # HarnessState TypedDict
│   ├── prompts.py        # 시스템 프롬프트
│   └── memory.py         # 대화 메모리 (세션별)
├── rag/                  # RAG 파이프라인
│   ├── chunker.py        # 문서 → 청크 분할
│   ├── indexer.py        # ChromaDB 인덱싱
│   └── retriever.py      # 코사인 유사도 검색
├── search/               # 웹 검색
│   ├── client.py         # UnifiedSearchClient (SearXNG→Tavily→DDG)
│   ├── searxng.py        # SearXNG 어댑터
│   ├── tavily.py         # Tavily 어댑터
│   └── ddg.py            # DuckDuckGo 어댑터 (API 키 불필요)
├── tools/                # 외부 시스템 통합
│   ├── orchard.py        # Apple 앱 dispatch() — 하네스·MCP 공유
│   └── google.py         # Google Workspace dispatch() — 하네스·MCP 공유
├── mcp/                  # MCP 서버 (Claude Code 연동)
│   ├── orchard_server.py # Apple 앱 FastMCP 서버
│   └── google_server.py  # Google Workspace FastMCP 서버
├── connectors/           # 메신저 연동
│   ├── base.py           # BaseConnector
│   ├── telegram.py       # aiogram 3.x
│   ├── discord.py        # discord.py 2.x
│   └── runner.py         # 커넥터 실행 관리
├── schedules/            # 브리핑 스케줄 관리
│   ├── db.py             # SQLite CRUD
│   ├── runner.py         # LocalAI API 호출 → Telegram 전송
│   ├── scheduler.py      # APScheduler — DB와 자동 동기화
│   └── router.py         # REST API + 웹 UI (/schedules)
├── docker/
│   ├── docker-compose.yml
│   └── searxng/settings.yml
├── scripts/
│   └── service.sh        # launchd 서비스 관리 스크립트
├── data/                 # 벡터DB · 스케줄DB · 모델 캐시 (gitignore)
├── .env                  # 환경 변수 (gitignore)
├── .env.example
├── requirements.txt
└── pyproject.toml
```

---

## 알려진 제약사항

- **mlx-lm 0.31.3**: `gemma4` 타입 호환 (`31b-it`, `26b-a4b` 계열). `gemma4_unified` 타입(12B QAT 계열)은 미지원.
- **동시 요청**: MLX GPU 스트림이 thread-local이므로 동일 모델은 직렬 처리됨.
- **SearXNG**: Docker가 실행 중이어야 검색 기능 사용 가능. 미실행 시 Tavily → DuckDuckGo 자동 폴백.

---

## 변경 이력

### 2026-07-11

**Google Workspace 통합 (Sheets / Docs / Drive)**

- `tools/google.py` 신규: Google Workspace dispatch 레이어 (Service Account 인증)
  - Sheets: 읽기(`sheets_read`), 전체 조회(`sheets_get_all`), 쓰기(`sheets_write`), 행 추가(`sheets_append`), 시트 목록(`sheets_list_sheets`), 새 시트 생성(`sheets_create`)
  - Docs: 읽기(`docs_read`), 텍스트 추가(`docs_append`)
  - Drive: 파일 검색(`drive_search`), 최근 파일 목록(`drive_list_recent`)
  - `spreadsheet_id`/`document_id`에 URL 전체 입력 가능 (자동 ID 추출)
- `mcp/google_server.py` 신규: FastMCP 서버 — Claude Code에서 위 10개 도구 직접 사용
- `~/.claude/settings.json`: `mcpServers.google` 등록
- `harness/nodes.py`: `tool_call` 노드에서 도구 이름으로 orchard/google 자동 분기
- `harness/prompts.py`: TOOLS_SYSTEM에 Google Workspace 도구 섹션 추가, ORCHESTRATOR에 Google 관련 few-shot 예시 3개 추가
- `core/config.py`: `GOOGLE_CREDENTIALS_PATH` 설정 추가 (기본: `./data/google_credentials.json`)
- 인증 설정: Google Cloud Console에서 서비스 계정 키 JSON 다운로드 → `data/google_credentials.json` 저장 → 대상 시트를 서비스 계정 이메일에 편집자 공유

**Telegram 음성 메시지 지원 (STT)**

- `core/stt.py` 신규: `STTManager` — mlx-whisper 래퍼
  - `whisper-large-v3-turbo` 모델 (한국어 우선, 속도·품질 최적 균형)
  - ogg/oga(Telegram 음성 포맷) → ffmpeg wav 변환 후 transcribe
  - numpy 무음 배열로 warmup — 서버 시작 시 모델 미리 로드
- `connectors/telegram.py`: 음성 핸들러 추가
  - `@dp.message(lambda m: m.voice or m.audio)` 등록
  - `_handle_voice()`: 파일 다운로드 → STT → 인식 텍스트 표시 → 하네스 처리
- `connectors/runner.py`: `stt=stt_manager` 파라미터 추가
- `connectors/base.py`: `HarnessState`에 `subquery_tools`, `tool_context`, `max_iterations` 누락 필드 추가 (latent bug fix)
- `api/main.py`: lifespan에 `STTManager.load()` 추가 — 서버 시작 시 STT 모델 로드
- `requirements.txt`: `mlx-whisper>=0.4.3` 추가
- 요구사항: `brew install ffmpeg` (ogg 변환용)

**패키지 업그레이드**

| 패키지 | 이전 | 이후 |
|---|---|---|
| mlx | 0.31.2 | **0.32.0** |
| langgraph | 1.2.2 | 1.2.9 |
| langchain | 1.3.2 | 1.3.13 |
| fastapi | 0.136.3 | 0.139.0 |
| aiogram | 3.28.2 | 3.29.1 |
| pypdf | 6.12.2 | 6.14.2 |
| mcp | 1.28.0 | 1.28.1 |
| APScheduler | 3.11.2 | 3.11.3 |

**모델 업그레이드**

- **Orchestrator/Code**: `gemma-4-26B-A4B-it-OptiQ-4bit` (MoE) → **`gemma-4-31b-it-4bit`** (Dense 31B)
  - mlx 0.32.0에서 `gemma4` 타입 Dense 모델 정상 동작 확인 (이전엔 k/v projection 불일치로 미동작)
  - 추론 품질 향상, 특히 복잡한 라우팅/코드 생성에서 개선
- **Embedding**: `nomic-embed-text-v1.5` → **`nomic-embed-text-v2-moe`**
  - 768차원 동일 → ChromaDB 재인덱싱 불필요
  - 100개 언어 지원, 한국어 임베딩 품질 개선
- **RAG/Judge/Search/Summary**: `gemma-4-26b-a4b-it-4bit` 유지
  - 12B QAT 계열(`gemma4_unified` 타입)은 mlx-lm 0.31.3 미지원으로 보류

---

### 2026-06-19

**orchard Apple 앱 통합 (tools 라우트)**

- `tools/orchard.py` 신규: orchard CLI `dispatch()` 공유 실행 레이어
  - 캘린더·리마인더·날씨·노트·메시지·연락처·음악·위치 17개 도구 지원
  - 하네스(LocalAI)와 MCP 서버(Claude Code) 양쪽에서 동일 코드 재사용
- `harness/state.py`: `tool_context`, `subquery_tools` 필드 추가
- `harness/prompts.py`: `TOOLS_SYSTEM` 프롬프트 추가 (의도 → tool+args JSON 변환), ORCHESTRATOR에 `"tools"` 라우트 및 few-shot 예시 7개 추가
- `harness/nodes.py`: `tool_call` 노드 추가
  - 소형 모델(Search)이 사용자 의도를 파싱해 tool+args JSON 결정
  - `orchard_dispatch()` 실행 후 결과를 `tool_context`로 전달
  - 복수 도구 동시 호출 지원 (`{"tools": [...]}`)
- `harness/graph.py`: `orchestrate → tool_call → synthesize` 경로 추가
- 동작 예시: "오늘 일정 알려줘" → `calendar_list_events`, "다음 곡 틀어줘" → `music_control(next)`

**orchard MCP 서버 (Claude Code 연동)**

- `mcp/orchard_server.py` 신규: `tools/orchard.py`를 FastMCP로 노출
- `~/.claude/settings.json`에 등록 — Claude Code 재시작 후 자동 연결
- 사용 가능 도구 (17개): `calendar_list_calendars`, `calendar_list_events`, `calendar_create_event`, `reminder_list`, `reminder_create`, `weather_get`, `notes_search`, `notes_get`, `notes_create`, `messages_list_chats`, `messages_read`, `messages_send`, `contacts_search`, `contacts_details`, `music_info`, `music_control`, `music_play`, `location_current`, `location_search`, `location_route`

---

### 2026-06-18

**브리핑 스케줄 안정성 수정 (주식 브리핑 미전송 버그)**

- **원인**: `INFERENCE_TIMEOUT = 300`초 — 27B 오케스트레이터 단독으로 5분+ 소요하므로 runner의 HTTP 클라이언트가 모델 추론 완료 전에 타임아웃 발생 → `"실패:"` 기록
- `schedules/runner.py`: `INFERENCE_TIMEOUT` 300 → **1200초(20분)** 로 증가
- `schedules/runner.py`: `max_iterations: 1` 파라미터 추가 — 스케줄 작업은 judge 재시도 없이 1회만 실행 (재시도 시 총 처리 시간 2배)
- `schedules/runner.py`: 예외 로깅에 `type(e).__name__` 포함 — 원인 불명 오류(`"실패:"`) 방지
- `schedules/scheduler.py`: `misfire_grace_time` 300 → **600초(10분)** — 재부팅 후 모델 로딩 중 놓친 스케줄 허용 범위 확대
- `api/schemas.py`: `ChatRequest`에 `max_iterations` 필드 추가 (기본값 2)
- `harness/state.py`: `HarnessState`에 `max_iterations` 필드 추가
- `harness/graph.py`: `_route_after_judge`에서 `state.max_iterations` 참조 — 요청별 반복 횟수 제어 가능

**DuckDuckGo 검색 폴백 추가**

- `search/ddg.py` 신규: API 키 없이 DuckDuckGo 검색 (`ddgs` 패키지)
- `search/client.py`: SearXNG → Tavily → **DuckDuckGo** 3단계 폴백 — Docker/API 키 없이도 항상 웹 검색 동작
- `requirements.txt`: `ddgs>=0.1.0` 추가

---

### 2026-06-13

**최신 정보 응답 개선**

- **현재 날짜 자동 주입**: `orchestrate` · `synthesize` 노드에서 매 쿼리마다 `[현재 날짜: YYYY년 MM월 DD일]`을 자동 삽입 — 모델이 학습 컷오프 이후 정보를 스스로 검색하도록 유도
- **시간민감 라우팅 강화**: `오늘/최근/현재/어제/뉴스/주가/금리/트렌드/출시/업데이트` 등 키워드 감지 시 `direct` 라우트를 `search`로 강제 오버라이드
- **ORCHESTRATOR 프롬프트 개선**: 날짜 컨텍스트 인식, "의심스러우면 search 선택" 규칙 명시, few-shot 예시 5개 → 8개 확대

**RSS 뉴스 자동 인덱싱**

- `schedules/news_indexer.py` 신규 추가: RSS 5개 피드 크롤 → ChromaDB 자동 인덱싱
  - Google뉴스 한국, BBC 코리아, Bloomberg Markets, WSJ World, HackerNews
- 서버 시작 시 즉시 1회 실행 + 이후 6시간 주기 반복 (APScheduler 연동)
- 7일 경과 뉴스 자동 삭제 — 인덱스를 항상 최신 상태로 유지
- RAG 검색 시 뉴스 기사가 문서와 동일한 하이브리드 파이프라인(BM25+벡터+리랭킹)으로 검색됨

**쿼리 컨텍스트 자동 주입 (위치·시각)**

- 모든 쿼리에 `[현재 날짜] [현재 시각] [사용자 위치]` 헤더를 자동 주입 — 날씨·로컬 정보 등 위치 의존 질문에 정확한 검색 쿼리 생성
- `USER_LOCATION` 환경 변수로 위치 설정 (기본: `서울, 한국`)
- ORCHESTRATOR가 위치를 인식해 `subquery_search`를 `"Seoul Korea weather today"` 형태로 자동 생성
- 날씨·로컬 맛집 등 위치 기반 예시 2개 추가

**Gemma 4 thinking 토큰 누출 버그 수정**

- `core/model.py`: `_strip_thinking()` 개선 — 닫힘 태그(`<channel|>`) 없이 끊긴 thinking 블록도 완전히 제거
- `core/config.py`: SUMMARY 8192 / SEARCH·RAG 6144 토큰으로 증가 — thinking + 실제 응답이 함께 생성될 공간 확보 (기존 4096에서 thinking이 전부 소진되던 문제 해결)
- `harness/nodes.py`: synthesize 노드 빈 응답 fallback 추가 — thinking 초과로 응답이 비어있을 때 재시도 루프 방지
- `harness/prompts.py`: SYNTHESIZE_SYSTEM · SEARCH_SYSTEM에 "주입된 날짜를 미래로 표현하지 말 것" 규칙 추가

---

### 2026-06-11

**launchd 서비스 안정성 개선**
- `scripts/start.sh`: Docker 데몬 미실행 시에도 서버가 정상 시작되도록 수정 (`set -e` 제거, Docker 오류 무시)
- `launchd/com.localai.server.plist`: `KeepAlive.Crashed` → `KeepAlive: true` — 종료 코드 무관하게 항상 30초 후 자동 재시작

**RAG 검색 품질 개선**
- **하이브리드 검색**: 벡터 검색 단독 → 벡터(top 20) + BM25(top 20) → RRF(Reciprocal Rank Fusion) 퓨전
- **Cross-encoder 리랭킹**: RRF 결과를 `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`(한국어 지원)로 재정렬 후 top 5 반환
- BM25 인덱스는 문서 추가/삭제 시 자동 재빌드 (평상시 overhead 없음)

**멀티에이전트 하네스 개선**
- **Judge 피드백 루프 수정**: 재시도 시 `judge_feedback`이 `synthesize` 노드에 전달되어 실질적인 품질 향상 반영 (기존에는 피드백이 버려지고 동일 응답 반복)
- **프롬프트 전면 개선**: 모든 에이전트 한국어 응답 명시, 결론 우선 응답 구조, Orchestrator에 few-shot 라우팅 예시 5개 추가, Judge pass 기준 0.8 → 0.75

**브리핑 스케줄 웹 UI**
- `schedules/` 모듈 신규 추가: SQLite(db.py) + APScheduler(scheduler.py) + Telegram 전송(runner.py) + FastAPI 라우터(router.py)
- 웹 UI(`http://localhost:8000/schedules`): 스케줄 추가·수정·삭제, 활성/비활성 토글, 즉시 실행, 마지막 실행 상태 표시
- REST API: `GET/POST /v1/schedules`, `PUT/DELETE/PATCH/POST /v1/schedules/{id}`
- launchd 기반 `daily_brief.py` 방식 폐기 → 웹 UI 방식으로 전환
