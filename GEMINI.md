# Y-Data-House Gemini CLI 사용 가이드

## 프로젝트 컨텍스트

Y-Data-House는 YouTube 비디오 다운로더와 transcription 시스템으로, Obsidian vault 노트를 구조화된 메타데이터와 함께 자동 생성하는 도구입니다. 이 프로젝트는 현재 DeepSeek API를 주력으로 사용하고 있으며, Gemini CLI는 개발 도구로서 추가 AI 지원을 제공합니다.

## 기술 스택 및 아키텍처

### 핵심 기술
- **Frontend**: React 18.2.0 + TypeScript 5.4.0 + Tauri 2.5.1
- **Backend**: Rust (tokio, warp) + Python CLI (Click, Pydantic)
- **AI/RAG**: DeepSeek API (주력) + ChromaDB 벡터 데이터베이스
- **비디오 처리**: yt-dlp + youtube-transcript-api
- **Storage**: Obsidian Vault + 파일 시스템 기반 저장소

### 주요 디렉토리
```
y-data-house/
├── app/                    # Tauri 데스크톱 앱
│   ├── src/               # React 프론트엔드
│   └── src-tauri/         # Rust 백엔드
├── src/ydh/               # Python CLI 패키지
│   ├── cli.py            # Click 기반 CLI
│   ├── config.py         # Pydantic 설정
│   └── downloader.py     # yt-dlp 다운로더
├── vault/                 # Obsidian 보관함
│   ├── 10_videos/        # 다운로드된 비디오
│   └── 90_indices/       # AI/RAG 시스템
└── pyproject.toml        # Python 패키지 설정
```

## 현재 AI 통합 상태

### 1. DeepSeek API (주력)
- **위치**: `vault/90_indices/rag.py`
- **역할**: 채널별 RAG 검색 및 답변 생성
- **모델**: `deepseek-chat`
- **기능**: HyDE 검색, Query Rewriting, 채널별 프롬프트 맞춤화

### 2. OpenAI API
- **위치**: 임베딩 생성 (`vault/90_indices/embed.py`)
- **역할**: 벡터 임베딩 생성
- **모델**: `text-embedding-3-small`

### 3. ChromaDB
- **위치**: `vault/90_indices/chroma/`
- **역할**: 벡터 데이터베이스
- **특징**: 채널별 완전 격리 구조

## Gemini CLI 사용 용도

### 1. 개발 보조 도구
- 코드 리뷰 및 버그 분석
- 새로운 기능 설계 및 구현 조언
- 문서화 및 주석 작성 지원

### 2. 프로젝트 이해 및 분석
- 복잡한 코드 구조 분석
- 아키텍처 개선 제안
- 성능 최적화 조언

### 3. 테스트 및 디버깅
- 테스트 케이스 작성 지원
- 오류 진단 및 해결 방안 제시
- 로그 분석 및 모니터링

## 프로젝트 특성 및 제약사항

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

### 4. YouTube ToS 준수
- 적절한 rate limiting 적용
- 개인 사용 목적 명시
- 공개 콘텐츠만 다운로드

## 주요 기능 및 워크플로우

### 1. 비디오 다운로드 시스템
```bash
# CLI 명령어
python -m ydh ingest <channel_url>   # 개별 채널 다운로드
python -m ydh batch run              # 일괄 다운로드
make download                        # Makefile 사용
```

### 2. 벡터 임베딩 생성
```bash
python -m ydh embed --channels <channel_names>
make embed                          # 전체 채널 임베딩
```

### 3. AI 질의응답 시스템
```bash
make ask QUERY="질문 내용"         # CLI 사용
```

### 4. 데스크톱 앱 실행
```bash
cd app && pnpm tauri dev            # 개발 모드
pnpm tauri build                    # 빌드
```

## 개발 환경 설정

### 1. 환경 변수
```bash
# AI API 키 설정
export DEEPSEEK_API_KEY="your_api_key_here"
export OPENAI_API_KEY="your_openai_key"

# 선택적 설정
export YDH_VIDEO_QUALITY="720"
export YDH_SUBTITLE_LANGS="ko,ko-KR,en"
export YDH_VAULT_ROOT="./vault"
export YDH_BROWSER="chrome"
```

### 2. 프로젝트 초기화
```bash
make init                           # 전체 환경 초기화
python -m venv venv                 # Python 가상환경 생성
source venv/bin/activate            # 가상환경 활성화
pip install -e .                    # 패키지 설치
```

### 3. 개발 도구
```bash
# 코드 품질 도구
black .                             # Python 코드 포맷팅
isort .                             # import 정리
mypy src/                           # 타입 체킹
cargo fmt                           # Rust 코드 포맷팅
cargo clippy                        # Rust 린터
```

## 파일 구조 패턴

### 1. Obsidian Vault 구조
```
vault/10_videos/{channel_name}/{YYYY}/{YYYYMMDD}_{title_slug}/
├── video.mp4
├── captions.txt
└── captions.md
```

### 2. Markdown 템플릿
```yaml
---
title: "{video_title}"
upload: {YYYY-MM-DD}
channel: "{channel_name}" 
video_id: {youtube_id}
topic: [tag1, tag2]
source_url: {youtube_url}
---
```

## 일반적인 문제 해결

### 1. 비디오 다운로드 실패
- 네트워크 연결 확인
- yt-dlp 업데이트 필요
- 브라우저 쿠키 설정 확인
- Rate limiting 대응

### 2. 벡터 임베딩 오류
- ChromaDB 설정 확인
- 메모리 사용량 모니터링
- 배치 크기 조정 (50-100)
- 긴 텍스트 청크 분할

### 3. AI API 오류
- API 키 확인
- 요청 빈도 조절
- 모델명 확인 (deepseek-chat)
- 네트워크 연결 상태 점검

## 로그 파일 위치
```
logs/
├── downloader.log          # 다운로드 로그
├── embedding.log           # 임베딩 생성 로그
├── rag.log                 # RAG 시스템 로그
└── tauri.log               # Tauri 앱 로그
```

## 성능 최적화 팁

### 1. 다운로드 최적화
- 중복 방지 시스템 활용
- 병렬 처리 사용
- 적절한 품질 설정 (720p 권장)

### 2. RAG 시스템 최적화
- 채널별 격리 구조 활용
- HyDE 기법 사용
- Query Rewriting 적용
- LLM Re-Ranking 활용

### 3. 메모리 관리
- 벡터 임베딩 배치 처리
- 컨텍스트 윈도우 제한
- 적절한 청크 크기 설정

## 추가 개발 계획

### 1. 플러그인 아키텍처
- 모듈화된 구조
- 설정 기반 활성화
- 서드파티 통합

### 2. 추가 기능
- Canvas 자동 생성
- 토픽 모델링
- 다국어 지원
- 더 나은 검색 알고리즘

---

## 중요 참고 사항

이 프로젝트는 **개인 사용 목적**으로만 사용되며, **YouTube 서비스 약관을 준수**합니다. 모든 개발은 이 원칙을 기반으로 진행되어야 합니다.

현재 AI 통합은 **DeepSeek API가 주력**이며, Gemini CLI는 **개발 보조 도구**로 활용됩니다. 기존 AI 시스템을 대체하지 않고 **보완적 역할**을 수행합니다.

---

마지막 업데이트: 2025-01-03