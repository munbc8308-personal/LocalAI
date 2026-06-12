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
| **웹 검색** | SearXNG (자체 호스팅) + Tavily API 폴백 |
| **Telegram 봇** | 채팅, 파일 업로드(RAG 자동 인덱싱), 대화 히스토리 |
| **Discord 봇** | 채널별 세션, `!clear` 명령어 |
| **브리핑 스케줄** | 웹 UI에서 주제·시각 등록 → 매일 자동 조사 후 Telegram 전송 |

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
  │    ├─ "code"       → Code Agent         │
  │    ├─ "rag+search" → RAG + Search       │
  │    └─ "direct"     → 바로 응답          │
  │  Synthesize → 컨텍스트 합성             │
  │  Judge → 품질 평가 (재시도 최대 2회)    │
  └─────────────────────────────────────────┘
        │
        ▼
  MLX-LM 모델 (core/)          ChromaDB (rag/)
  Gemma 4 26B-A4B (2개 인스턴스)  nomic-embed-text-v1.5
```

### 에이전트별 모델 할당

| 에이전트 | 역할 | 모델 |
|---|---|---|
| Orchestrator | 쿼리 분석 · 라우팅 | gemma-4-26B-A4B-it-OptiQ-4bit |
| Code | 코드 생성 | gemma-4-26B-A4B-it-OptiQ-4bit (공유) |
| RAG | 문서 기반 답변 | gemma-4-26b-a4b-it-4bit |
| Judge | 응답 품질 평가 | gemma-4-26b-a4b-it-4bit (공유) |
| Search | 검색 결과 요약 | gemma-4-26b-a4b-it-4bit (공유) |
| Summary | 최종 합성 | gemma-4-26b-a4b-it-4bit (공유) |
| Embedding | 문서 임베딩 | nomic-ai/nomic-embed-text-v1.5 |

메모리 사용량: **~15.5 GB** (128 GB 중)

---

## 요구사항

- macOS (Apple Silicon) — M1 이상
- Python 3.11+
- Docker Desktop (SearXNG 실행용)
- HuggingFace 계정 (모델 다운로드)

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
EMBEDDING_MODEL=nomic-ai/nomic-embed-text-v1.5

# API 서버
API_HOST=0.0.0.0
API_PORT=8000

# 검색
SEARXNG_URL=http://localhost:8080
TAVILY_API_KEY=              # SearXNG 미응답 시 폴백

# 메신저 봇 (선택)
TELEGRAM_BOT_TOKEN=
DISCORD_BOT_TOKEN=

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
│   └── embeddings.py     # EmbeddingManager (nomic)
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
│   ├── client.py         # UnifiedSearchClient
│   └── searxng.py        # SearXNG 어댑터
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

- **mlx-lm 0.31.3**: Gemma 4 MoE 26B-A4B 계열만 호환. Dense 모델(e4b, 31b)은 k/v projection 아키텍처 불일치로 미동작.
- **동시 요청**: MLX GPU 스트림이 thread-local이므로 동일 모델은 직렬 처리됨.
- **SearXNG**: Docker가 실행 중이어야 검색 기능 사용 가능. 미실행 시 Tavily로 자동 폴백.

---

## 변경 이력

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
