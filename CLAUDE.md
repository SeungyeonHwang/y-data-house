# Y-Data-House Claude 사용 가이드

## 프로젝트 개요
Y-Data-House는 YouTube 비디오 다운로더와 transcription 시스템으로, Obsidian vault 노트를 구조화된 메타데이터와 함께 자동 생성하는 도구입니다.

## 아키텍처 구조

### 기술 스택
- **Frontend**: React + TypeScript + Tauri
- **Backend**: Rust + Python CLI 
- **AI**: DeepSeek + ChromaDB for RAG
- **Storage**: Obsidian Vault + SQLite

### 주요 디렉토리 구조
```
y-data-house/
├── app/                    # Tauri 데스크톱 앱
│   ├── src/               # React 프론트엔드
│   └── src-tauri/         # Rust 백엔드
├── src/ydh/               # Python CLI 패키지
├── vault/                 # Obsidian 보관함
│   ├── 10_videos/         # 비디오 파일들
│   └── 90_indices/        # 벡터 DB
└── venv/                  # Python 가상환경
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

### 1. 비디오 다운로드
```bash
# CLI 명령어
python -m ydh ingest <channel_url>
python -m ydh batch run
```

### 2. 벡터 임베딩 생성
```bash
# Python 백엔드에서 ChromaDB 사용
python -m ydh embed --channels <channel_names>
```

### 3. RAG 시스템
- DeepSeek API 통합
- ChromaDB 벡터 검색
- 자연어 질의응답

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
# Python 환경
python -m venv venv
source venv/bin/activate
pip install -e .

# Tauri 개발
cd app
pnpm install
pnpm tauri dev
```

### 2. 빌드 및 배포
```bash
# Python 패키지 빌드
python -m build

# Tauri 앱 빌드
pnpm tauri build
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

### 1. DeepSeek 설정
```python
# 환경 변수 설정
DEEPSEEK_API_KEY="your_api_key_here"
```

### 2. ChromaDB 설정
```python
# 벡터 DB 경로
CHROMA_PATH="vault/90_indices/chroma"
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
- 네트워크 연결 확인
- YouTube URL 유효성 검사
- rate limiting 확인

### 2. 벡터 임베딩 오류
- ChromaDB 설정 확인
- 메모리 사용량 모니터링
- 배치 크기 조정

### 3. Tauri 앱 오류
- Rust 컴파일 오류 해결
- 권한 설정 확인
- 프로세스 통신 디버깅

---

## 마지막 업데이트
2024-12-20: 초기 설정 완료

## 연락처
프로젝트 관리자: Y-Data-House Team 