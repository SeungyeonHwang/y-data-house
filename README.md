# Y-Data-House

YouTube 비디오 다운로드 및 Obsidian Vault 자동 생성 도구

## 📖 개요

Y-Data-House는 YouTube 채널의 영상을 자동으로 다운로드하고, 자막을 추출하여 Obsidian에서 사용할 수 있는 구조화된 마크다운 노트를 생성하는 도구입니다.

### 주요 기능

- 🎥 **YouTube 영상 자동 다운로드** - yt-dlp 기반으로 고품질 영상 다운로드
- 📝 **자막 추출 및 정리** - VTT/SRT → 깔끔한 텍스트 변환
- 📚 **Obsidian Vault 자동 생성** - YAML frontmatter가 포함된 마크다운 노트
- 🔄 **중복 다운로드 방지** - 3단계 중복 체크 시스템
- 📊 **진행 상황 추적** - JSON 기반 진행상황 관리 (SQLite 마이그레이션 준비)
- 🚀 **Prefect 워크플로우** - 자동화된 배치 처리
- 🏷️ **자동 태그 생성** - 채널별 태그 및 해시태그 추출

## 🚀 빠른 시작

### 설치 및 초기 설정

```bash
# 저장소 클론
git clone https://github.com/y-data-house/ydh.git
cd ydh

# 환경 설정 (가상환경 생성, 의존성 설치, 초기 파일 생성)
make init
```

### 기본 사용법

```bash
# 1. channels.txt 파일에 다운로드할 채널 URL 추가
echo "https://www.youtube.com/@리베라루츠대학" >> channels.txt
echo "https://www.youtube.com/@채널명2" >> channels.txt

# 2. 모든 채널에서 새 영상 다운로드
make download
```

### 고급 사용법

```bash
# 개별 채널 처리
python -m ydh ingest "https://www.youtube.com/@채널명"

# 다운로드만 (Vault 생성 없이)
python -m ydh batch --no-vault

# 기존 파일을 Vault로 변환만
python -m ydh batch --vault-only

# 통계 확인
make status

# 설정 확인
make config

# 시스템 유지보수
make maintenance
```

### 주요 Make 명령어

| 명령어 | 설명 |
|--------|------|
| `make init` | 환경 설정 (최초 한 번) |
| `make download` | 채널 리스트의 새 영상 다운로드 |
| `make status` | 다운로드 통계 표시 |
| `make config` | 현재 설정 표시 |
| `make maintenance` | 시스템 유지보수 |
| `make clean` | 가상환경 삭제 |

## 📁 프로젝트 구조

```
y-data-house/
├─ src/ydh/                    # 메인 패키지
│   ├─ __init__.py
│   ├─ config.py               # Pydantic 설정 관리
│   ├─ downloader.py           # yt-dlp 래퍼
│   ├─ transcript.py           # 자막 추출
│   ├─ converter.py            # VTT/SRT → 텍스트 변환
│   ├─ vault_writer.py         # Obsidian 노트 생성
│   ├─ progress.py             # 진행상황 추적
│   ├─ cli.py                  # Click CLI
│   └─ flow.py                 # Prefect 워크플로우
├─ vault/                      # Obsidian Vault
│   ├─ 10_videos/              # 영상 저장소
│   │   └─ {채널명}/
│   │       └─ {연도}/
│   │           └─ {YYYYMMDD}_{제목}/
│   │               ├─ video.mp4
│   │               ├─ captions.txt
│   │               └─ captions.md
│   └─ 90_indices/             # 인덱스 (향후 벡터DB)
├─ pyproject.toml
├─ README.md
├─ Makefile                    # 빌드 및 실행 스크립트
├─ channels.txt                # 다운로드할 채널 목록
└─ channels.example.txt        # 채널 목록 예시 파일
```

## 🗂️ Obsidian Vault 구조

### 마크다운 노트 템플릿

```yaml
---
title: "비디오 제목"
upload: 2025-01-15
channel: "채널명"
video_id: abc123
topic: [투자, FIRE, 경제]
source_url: https://www.youtube.com/watch?v=abc123
duration_seconds: 1200
view_count: 50000
created_date: 2025-01-15 10:30:00
---

## 📹 비디오 정보

- **제목**: 비디오 제목
- **채널**: 채널명
- **업로드**: 2025-01-15
- **길이**: 20분 0초
- **조회수**: 50,000회
- **링크**: [https://www.youtube.com/watch?v=abc123](https://www.youtube.com/watch?v=abc123)

## 📝 자막 내용

정리된 자막 내용이 여기에 표시됩니다...

## 🏷️ 태그

#투자 #FIRE #경제

## 💭 노트

*여기에 개인적인 생각이나 메모를 추가하세요.*
```

## ⚙️ 설정

### 채널 목록 설정

```bash
# channels.txt 파일에서 채널 URL 관리
# 주석으로 시작하는 줄은 무시됩니다

# 경제/투자 관련 채널
https://www.youtube.com/@리베라루츠대학
https://www.youtube.com/@한국경제신문

# 기술/개발 관련 채널
https://www.youtube.com/@코딩애플
# https://www.youtube.com/@노마드코더NomadCoders  # 주석 처리된 채널
```

### 환경변수 설정 (선택사항)

```bash
# ~/.ydh.toml 파일 생성
vault_root = "/path/to/your/obsidian/vault"
download_path = "./downloads"
browser = "chrome"
language = "ko"
max_quality = "1080p"
delete_vtt_after_conversion = true
```

### 채널별 태그 설정

```python
# config.py에서 설정
channel_tags = {
    "리베라루츠대학": ["투자", "FIRE", "경제"],
    "개발자채널": ["프로그래밍", "기술", "개발"],
}
```

## 🔄 워크플로우

### Prefect 플로우 사용

```python
from ydh.flow import run_channel_ingest, run_batch_process, run_maintenance

# 채널 인제스트
result = run_channel_ingest("https://www.youtube.com/@채널명")

# 일괄 처리
result = run_batch_process("./downloads", "채널명")

# 유지보수
result = run_maintenance(retry_failed=True, cleanup_files=True)
```

### 스케줄링

```bash
# Prefect 서버 시작
prefect server start

# 일일 유지보수 스케줄 등록
prefect deployment build ydh.flow:daily_maintenance_flow -n "daily-maintenance"
prefect deployment apply daily_maintenance_flow-deployment.yaml
```

## 🛠️ CLI 명령어

| Make 명령어 | Python 명령어 | 설명 |
|-------------|---------------|------|
| `make init` | - | 환경 설정 (가상환경, 의존성, 초기 파일) |
| `make download` | `python -m ydh batch` | channels.txt의 모든 채널 처리 |
| `make status` | `python -m ydh stats` | 다운로드 통계 |
| `make config` | `python -m ydh config-show` | 현재 설정 표시 |
| `make maintenance` | `python -m ydh maintenance` | 시스템 유지보수 |
| - | `python -m ydh ingest <URL>` | 개별 채널 처리 |
| - | `python -m ydh convert <PATH>` | 자막 파일 변환 |

## 🔧 고급 사용법

### 중복 방지 시스템

1. **yt-dlp download-archive**: 네트워크 레벨에서 중복 방지
2. **Progress DB**: 성공/실패 이력 관리로 재시도 지원
3. **파일 존재 검사**: Vault 파일 존재 시 처리 생략

### 자막 추출 전략

1. **YouTube Transcript API**: 직접 API 호출
2. **자막 목록 조회**: 사용 가능한 언어 확인 후 추출
3. **yt-dlp 백업**: API 실패 시 yt-dlp로 VTT 다운로드

### 브라우저 쿠키 활용

YouTube 로그인 상태의 브라우저 쿠키를 사용하여 접근 제한된 영상도 처리 가능합니다.

## 🎯 향후 계획

### 단기 계획
- [ ] SQLite 진행상황 DB 마이그레이션
- [ ] 자막 품질 개선 (문장 분리, 노이즈 제거)
- [ ] 채널별 설정 프로파일

### 중기 계획
- [ ] Dataview 쿼리 템플릿 제공
- [ ] Chroma DB 벡터 인덱싱 (`90_indices/`)
- [ ] FastAPI 웹 인터페이스

### 장기 계획
- [ ] DeepSeek RAG 시스템 통합
- [ ] JupyMD 플러그인으로 분석 노트북 생성
- [ ] Obsidian Canvas 자동 생성

## 🤝 기여하기

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 라이센스

MIT License - 자세한 내용은 [LICENSE](LICENSE) 파일을 참조하세요.

## 🙏 감사의 말

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) - 강력한 YouTube 다운로더
- [youtube-transcript-api](https://github.com/jdepoix/youtube-transcript-api) - 자막 추출 API
- [Obsidian](https://obsidian.md) - 지식 관리 도구
- [Prefect](https://www.prefect.io) - 워크플로우 오케스트레이션

---

**Y-Data-House**로 YouTube 영상을 체계적으로 수집하고 분석해보세요! 🚀 