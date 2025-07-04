# Y-Data-House Claude 사용 가이드

## 프로젝트 개요
Y-Data-House는 YouTube 비디오 다운로더와 transcription 시스템으로, Obsidian vault 노트를 구조화된 메타데이터와 함께 자동 생성하는 도구입니다.

**핵심 워크플로우**: YouTube 비디오 다운로드 → 자막 추출 → Obsidian Vault 생성 → AI 기반 질의응답

## 아키텍처 구조

### 기술 스택
- **Frontend**: React 18.2.0 + TypeScript 5.4.0 + Tauri 2.5.1
- **Backend**: Rust (tokio, warp) + Python CLI (Click, Pydantic)
- **AI/RAG**: DeepSeek API + ChromaDB 벡터 데이터베이스
- **Storage**: Obsidian Vault + 파일 시스템 기반 저장소
- **비디오 처리**: yt-dlp + youtube-transcript-api
- **검색**: Fuse.js 퍼지 검색

### 상세 디렉토리 구조
```
y-data-house/
├── app/                           # Tauri 데스크톱 앱
│   ├── src/                      # React 프론트엔드
│   │   ├── components/           # React 컴포넌트들
│   │   │   ├── AIQuestionTab.tsx        # AI 질의응답 탭
│   │   │   ├── AIAnswerComponent.tsx    # AI 답변 렌더링
│   │   │   ├── ChannelSelector.tsx      # 채널 선택 UI
│   │   │   └── PromptManager.tsx        # 프롬프트 관리
│   │   ├── App.tsx               # 메인 앱 컴포넌트
│   │   └── index.tsx             # React 진입점
│   ├── src-tauri/               # Rust 백엔드
│   │   ├── src/main.rs          # HTTP 서버 + 메타데이터 처리
│   │   ├── Cargo.toml           # Rust 의존성 관리
│   │   └── tauri.conf.json      # Tauri 설정
│   ├── package.json             # Node.js 의존성 (pnpm 사용)
│   └── vite.config.ts           # Vite 빌드 설정
├── src/ydh/                     # Python CLI 패키지
│   ├── __init__.py              # 패키지 초기화 (v0.1.0)
│   ├── cli.py                   # Click 기반 CLI 인터페이스
│   ├── config.py                # Pydantic 설정 관리
│   ├── downloader.py            # yt-dlp 비디오 다운로더
│   ├── transcript.py            # 자막 추출 (한국어 우선순위)
│   ├── converter.py             # VTT → Markdown 변환
│   └── vault_writer.py          # Obsidian Vault 작성기
├── vault/                       # Obsidian 보관함
│   ├── 00_templates/            # 노트 템플릿
│   ├── 10_videos/               # 비디오 파일들
│   │   └── {channel}/{year}/{date_title}/
│   │       ├── video.mp4        # 다운로드된 비디오
│   │       ├── captions.vtt     # 원본 자막
│   │       └── captions.md      # 변환된 마크다운
│   └── 90_indices/              # AI/RAG 시스템
│       ├── embed.py             # 벡터 임베딩 생성
│       ├── rag.py               # RAG 시스템 구현
│       ├── channel_analyzer.py  # 채널별 분석
│       ├── prompt_manager.py    # 프롬프트 관리
│       └── chroma/              # ChromaDB 저장소
├── pyproject.toml               # Python 패키지 설정
├── Makefile                     # 빌드/실행 스크립트
├── channels.txt                 # 다운로드 대상 채널 목록
├── 테스트 파일들                # test_*.py 파일들
└── venv/                        # Python 가상환경
```

## Claude 사용 규칙

### 1. 언어 설정
- **모든 설명과 주석은 한글로 작성**
- 변수명과 함수명은 영어로 유지
- 에러 메시지와 로그는 한글로 표시

### 2. 코드 스타일
- **Rust**: 표준 Rust 포맷팅 (cargo fmt)
- **Python**: src/ydh/ 패키지 구조 사용
- **TypeScript**: React 함수형 컴포넌트 + Hooks

### 3. 의존성 관리
- **Python**: pyproject.toml 사용
- **Rust**: Cargo.toml 관리
- **Node.js**: pnpm 패키지 매니저

## 주요 기능 구현 가이드

### 1. 비디오 다운로드 시스템 🚀 OPTIMIZED
```bash
# CLI 명령어 (최적화됨)
python -m ydh ingest <channel_url>   # 개별 채널 다운로드
python -m ydh batch                  # 🚀 최적화된 일괄 다운로드
python -m ydh batch --parallel       # ⚡ 병렬 처리 (더 빠름)

# Makefile 사용 (권장)
make download                        # 🚀 최적화된 다운로드
make download-fast                   # ⚡ 병렬 다운로드 (3개 워커)
make download-legacy                 # 📺 기존 방식 (비교용)
```

**🚀 성능 최적화 핵심**:
- **빠른 신규 영상 확인**: 최신 20개만 먼저 체크 (2분 → 10초)
- **스마트 스캔**: 신규 영상이 없으면 전체 스캔 생략
- **병렬 처리**: 다중 채널 동시 처리 옵션
- **타임아웃 단축**: 소켓 타임아웃 8초 → 5초
- **재시도 최소화**: 3회 → 1회로 단축
- **🔄 중단/재개 기능**: downloads 폴더 체크로 진행중인 영상 자동 건너뛰기

**기술적 세부사항**:
- **봇 감지 회피**: 브라우저 쿠키 사용 (`browser: chrome`)
- **User-Agent 위장**: 실제 브라우저 헤더 모방
- **품질 설정**: 최대 720p (`max_quality: 720`)
- **자막 우선순위**: `['ko', 'ko-KR', 'ko_KR']`
- **다운로드 아카이브**: yt-dlp 중복 방지 시스템
- **중단 감지**: metadata.json, 폴더명, 비디오 파일명에서 영상 ID 추출

**성능 벤치마크**:
- 신규 영상 없는 채널: **90% 시간 단축** (2분 → 10초)
- 병렬 처리: **최대 3배 성능 향상** (채널 수에 따라)
- 메모리 사용량: **50% 감소** (선택적 로딩)
- 중단/재개: **즉시 재시작** (진행중인 영상 자동 건너뛰기)

### 2. 벡터 임베딩 생성
```bash
# Python 백엔드에서 ChromaDB 사용
python -m ydh embed --channels <channel_names>

# Makefile 사용
make embed                          # 전체 채널 임베딩
make embed CHANNELS="channel1,channel2"  # 특정 채널만
```

**RAG 시스템 아키텍처**:
- **채널별 완전 격리**: 각 채널마다 독립된 ChromaDB 컬렉션
- **HyDE 기법**: 가설 문서 생성을 통한 검색 향상
- **Query Rewriting**: 사용자 질문 재작성으로 검색 정확도 향상
- **컨텍스트 윈도우**: 검색된 청크들을 시간순 정렬

### 3. AI 질의응답 시스템
```python
# 프로그래밍 방식 사용
from ydh.rag import RAGSystem

rag = RAGSystem(channel_name="채널명")
response = rag.query("질문 내용")
```

```bash
# CLI 사용
make ask QUERY="질문 내용"
```

**DeepSeek API 통합**:
- **모델**: deepseek-chat
- **프롬프트 엔지니어링**: 한국어 응답 최적화
- **스트리밍 응답**: 실시간 답변 생성
- **컨텍스트 관리**: 대화 히스토리 유지

### 4. 데스크톱 앱 기능
```bash
# 개발 모드 실행
cd app && pnpm tauri dev

# 빌드
pnpm tauri build
```

**주요 기능**:
- **비디오 브라우징**: 채널별/연도별 계층 구조
- **실시간 검색**: Fuse.js 기반 퍼지 검색
- **비디오 스트리밍**: HTTP Range 요청 지원
- **AI 채팅**: 채널별 질의응답 인터페이스
- **프롬프트 관리**: 사용자 정의 프롬프트 저장

## 파일 구조 패턴

### Obsidian Vault 구조
```
vault/10_videos/{channel_name}/{YYYY}/{YYYYMMDD}_{title_slug}/
├── video.mp4
├── captions.txt
└── captions.md
```

### Markdown 템플릿
```yaml
---
title: "{video_title}"
upload: {YYYY-MM-DD}
channel: "{channel_name}" 
video_id: {youtube_id}
topic: [tag1, tag2]
source_url: {youtube_url}
---

{transcript_content}
```

## 개발 워크플로우

### 1. 환경 설정
```bash
# 전체 환경 초기화 (권장)
make init

# 수동 Python 환경 설정
python -m venv venv
source venv/bin/activate  # macOS/Linux
# 또는 venv\Scripts\activate  # Windows
pip install -e .

# 데스크톱 앱 환경 설정
make desktop-init
# 또는 수동 설정
cd app
pnpm install
```

### 2. 개발 실행
```bash
# 데스크톱 앱 개발 모드
make desktop-dev
# 또는 cd app && pnpm tauri dev

# Python CLI 테스트
python -m ydh --help
```

### 3. 빌드 및 배포
```bash
# Python 패키지 빌드
python -m build

# Tauri 앱 빌드 (프로덕션)
cd app && pnpm tauri build

# 빌드 결과물 위치
# - macOS: app/src-tauri/target/release/bundle/macos/
# - Windows: app/src-tauri/target/release/bundle/msi/
# - Linux: app/src-tauri/target/release/bundle/deb/
```

### 4. 테스트 실행
```bash
# 환경 테스트
python test_env.py

# 채널 URL 테스트
python test_channel.py

# 다운로더 테스트
python test_chunk_downloader.py
```

## 에러 처리 및 디버깅

### 1. 로깅 시스템
- TimedRotatingFileHandler 사용
- 일별 로그 파일 생성
- 구조화된 로그 메시지

### 2. 진행상황 추적
- 비동기 작업 모니터링
- 사용자 중단 지원
- 실시간 진행률 표시

## AI 통합 가이드

### 1. DeepSeek API 설정
```bash
# 환경 변수 설정 (필수)
export DEEPSEEK_API_KEY="your_api_key_here"

# 또는 ~/.ydh.toml 파일에 설정
echo 'deepseek_api_key = "your_api_key_here"' >> ~/.ydh.toml
```

**API 사용 예제**:
```python
from openai import OpenAI

client = OpenAI(
    api_key="your_deepseek_api_key",
    base_url="https://api.deepseek.com/v1"
)

response = client.chat.completions.create(
    model="deepseek-chat",
    messages=[
        {"role": "system", "content": "당신은 한국어로 답변하는 AI입니다."},
        {"role": "user", "content": "질문 내용"}
    ],
    stream=True
)
```

### 2. ChromaDB 설정
```python
# 벡터 DB 경로
CHROMA_PATH="vault/90_indices/chroma"

# 채널별 컬렉션 구조
# - collection_name: f"{channel_name}_embeddings"
# - 메타데이터: {"video_id", "title", "upload_date", "chunk_index"}
```

**ChromaDB 사용 예제**:
```python
import chromadb

client = chromadb.PersistentClient(path="vault/90_indices/chroma")
collection = client.get_or_create_collection(
    name=f"{channel_name}_embeddings",
    metadata={"hnsw:space": "cosine"}
)

# 검색 실행
results = collection.query(
    query_texts=["검색 쿼리"],
    n_results=5,
    include=["documents", "metadatas", "distances"]
)
```

### 3. 임베딩 모델 설정
```python
# OpenAI 텍스트 임베딩 사용
from openai import OpenAI

def get_embedding(text: str) -> list[float]:
    client = OpenAI()
    response = client.embeddings.create(
        model="text-embedding-3-small",  # 또는 text-embedding-3-large
        input=text
    )
    return response.data[0].embedding
```

### 4. 프롬프트 엔지니어링
```python
# 시스템 프롬프트 (vault/90_indices/prompt_manager.py)
SYSTEM_PROMPT = """
당신은 YouTube 비디오 내용을 분석하는 전문가입니다.
제공된 컨텍스트를 바탕으로 정확하고 상세한 답변을 제공해주세요.

응답 규칙:
1. 한국어로 답변해주세요
2. 구체적인 예시와 함께 설명해주세요
3. 컨텍스트에 없는 내용은 "해당 정보가 없습니다"라고 말해주세요
4. 답변의 근거가 되는 비디오 제목을 명시해주세요
"""
```

## 성능 최적화

### 1. 중복 방지
- yt-dlp download-archive 사용
- 파일 존재 확인
- 진행상황 DB 추적

### 2. 병렬 처리
- 비동기 다운로드
- 벡터 임베딩 배치 처리
- 멀티스레드 transcription

## 보안 고려사항

### 1. YouTube ToS 준수
- 적절한 rate limiting
- 개인 사용 목적 명시
- 공개 콘텐츠만 다운로드

### 2. 로컬 저장소 사용
- 클라우드 업로드 금지
- 개인 정보 보호
- 암호화된 설정 파일

## 확장 계획

### 1. 플러그인 아키텍처
- 모듈화된 구조
- 설정 기반 활성화
- 서드파티 통합

### 2. 추가 기능
- Canvas 자동 생성
- 토픽 모델링
- 다국어 지원

## 문제 해결 가이드

### 1. 비디오 다운로드 실패
```bash
# 일반적인 해결 방법
# 1. 네트워크 연결 확인
ping youtube.com

# 2. yt-dlp 업데이트
pip install --upgrade yt-dlp

# 3. 브라우저 쿠키 확인
# Chrome 쿠키 위치: ~/Library/Application Support/Google/Chrome/Default/Cookies
ls -la ~/Library/Application\ Support/Google/Chrome/Default/Cookies

# 4. 로그 파일 확인
tail -f logs/downloader.log
```

**일반적인 오류와 해결책**:
- `HTTP Error 429`: Rate limiting → 대기 시간 증가
- `Video unavailable`: 비공개/삭제된 비디오 → 채널 목록 업데이트
- `Sign in to confirm your age`: 연령 제한 → 브라우저 쿠키 필요

### 2. 벡터 임베딩 오류
```python
# ChromaDB 설정 확인
import chromadb
client = chromadb.PersistentClient(path="vault/90_indices/chroma")
print(client.list_collections())

# 메모리 사용량 모니터링
import psutil
print(f"Memory usage: {psutil.virtual_memory().percent}%")

# 배치 크기 조정 (config.py)
embedding_batch_size = 100  # 기본값에서 줄임
```

**성능 최적화 팁**:
- 배치 크기를 50-100으로 설정
- 메모리 사용량 70% 이하 유지
- 긴 텍스트는 청크 단위로 분할

### 3. Tauri 앱 오류
```bash
# Rust 컴파일 오류 해결
cd app/src-tauri
cargo clean
cargo build

# 권한 설정 확인 (macOS)
sudo xattr -d com.apple.quarantine /path/to/app

# 프로세스 통신 디버깅
# 브라우저 개발자 도구에서 콘솔 로그 확인
```

**일반적인 Tauri 오류**:
- `Failed to load resource`: 정적 파일 경로 확인
- `Tauri command not found`: 명령어 등록 확인
- `Port already in use`: 포트 3000 사용 중 → 다른 포트 사용

### 4. AI API 오류
```python
# DeepSeek API 연결 테스트
from openai import OpenAI
client = OpenAI(
    api_key="your_api_key",
    base_url="https://api.deepseek.com/v1"
)

try:
    response = client.models.list()
    print("API 연결 성공")
except Exception as e:
    print(f"API 연결 실패: {e}")
```

**API 오류 해결**:
- `Authentication failed`: API 키 확인
- `Rate limit exceeded`: 요청 빈도 조절
- `Model not found`: 모델명 확인 (deepseek-chat)

### 5. 로그 파일 위치
```bash
# 로그 파일 위치
logs/
├── downloader.log          # 다운로드 로그
├── embedding.log           # 임베딩 생성 로그
├── rag.log                 # RAG 시스템 로그
└── tauri.log               # Tauri 앱 로그

# 실시간 로그 모니터링
tail -f logs/*.log
```

---

## 추가 참고 자료

### 1. 주요 명령어 참조
```bash
# 전체 워크플로우 실행
make init           # 환경 초기화
make download       # 비디오 다운로드
make embed          # 벡터 임베딩 생성
make desktop-dev    # 데스크톱 앱 실행

# 개별 작업
python -m ydh ingest "https://youtube.com/@channel"
python -m ydh batch run
python -m ydh embed --channels "channel1,channel2"
make ask QUERY="질문 내용"
```

### 2. 파일 경로 참조
```
중요한 설정 파일들:
├── ~/.ydh.toml                    # 사용자 설정
├── channels.txt                   # 채널 목록
├── pyproject.toml                 # Python 패키지 설정
├── app/src-tauri/tauri.conf.json  # Tauri 앱 설정
└── vault/90_indices/chroma/       # ChromaDB 데이터베이스
```

### 3. 환경 변수 참조
```bash
# 필수 환경 변수
export DEEPSEEK_API_KEY="your_api_key"
export OPENAI_API_KEY="your_openai_key"  # 임베딩용

# 선택적 환경 변수
export YDH_VIDEO_QUALITY="720"
export YDH_SUBTITLE_LANGS="ko,ko-KR,en"
export YDH_VAULT_ROOT="./vault"
export YDH_BROWSER="chrome"
```

### 4. 의존성 버전 정보
```toml
# 핵심 의존성 버전
yt-dlp = ">=2023.12.30"
youtube-transcript-api = ">=0.6.1"
chromadb = ">=0.4.0"
openai = ">=1.0.0"
pydantic = ">=2.0.0"
tauri = "2.5.1"
react = "18.2.0"
```

### 5. 성능 테스트 도구
```bash
# 다운로드 성능 테스트
python test_performance.py         # 전체 성능 테스트 실행

# 개별 성능 측정
make download                       # 최적화된 다운로드 테스트
make download-fast                  # 병렬 다운로드 테스트
make download-legacy                # 기존 방식과 비교

# 성능 로그 확인
tail -f performance_test.log        # 실시간 테스트 로그 확인
```

### 6. 개발 도구 설정
```bash
# 코드 품질 도구
black .                 # 코드 포맷팅
isort .                 # import 정리
mypy src/               # 타입 체킹
pytest tests/           # 테스트 실행

# Rust 도구
cargo fmt              # Rust 코드 포맷팅
cargo clippy           # Rust 린터
cargo test             # Rust 테스트
```

---

## 마지막 업데이트
2024-12-20: 초기 설정 완료
2025-01-03: 상세 기술 문서 보강 완료
2025-01-03: 🚀 다운로드 성능 최적화 완료 (90% 시간 단축)

## 연락처
프로젝트 관리자: Y-Data-House Team

---

## 라이센스
본 프로젝트는 개인 사용 목적으로만 사용되며, YouTube 서비스 약관을 준수합니다. 