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

### 개발 환경 설치

Y-Data-House는 Python 기반 CLI와 Tauri(Rust + React) 데스크톱 앱으로 구성되어 있습니다.
다음 도구가 필요합니다.

1. **Python 3.10+** – Ubuntu는 `sudo apt install python3 python3-venv` 로 설치하거나 [pyenv](https://github.com/pyenv/pyenv)를 사용할 수 있습니다.
2. **Rust toolchain** – `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh`
3. **Node.js 18+** 와 **pnpm** – `nvm install 18` 후 `npm install -g pnpm`

설치 후 아래 명령으로 가상환경과 의존성을 준비합니다.

```bash
make init                 # venv 및 기본 폴더 생성
source venv/bin/activate
make install              # Python 패키지 설치
```

데스크톱 앱 실행은 `app/` 폴더에서 다음과 같이 진행합니다.

```bash
cd app
pnpm install
pnpm tauri
```

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

## 🖥️ 데스크톱 앱 (Tauri)

`app/` 폴더에는 로컬에서 영상을 탐색하고 `rag.py`를 호출할 수 있는 Tauri + React 데스크톱 앱이 포함되어 있습니다.

### 준비물

- Rust toolchain
- Node.js 18 이상과 pnpm
- `vault/10_videos` 폴더의 영상과 `captions.md`

### 실행 방법

```bash
cd app
pnpm install          # 최초 1회 의존성 설치
pnpm tauri            # 개발 모드 실행
```

프로덕션 빌드를 생성하려면 `pnpm run build` 명령을 사용합니다.

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


현 파이프라인을 그대로 두고 **“서버 없이 로컬에서 영상 + 자막 동시 열람 · 검색 UI”**를 만드는 가장 실용적인 방법은 **(1) 가벼운 데스크톱 앱, (2) 완전 정적 사이트, (3) 파이썬 원-클릭 앱(Streamlit)** ― 세 가지 접근입니다.

아래에 각 옵션별 구조·필요 라이브러리·30 분 프로토타입 코드를 정리했으니, 취향과 배포 환경(Windows / macOS / Linux) 맞춰 골라 붙이면 됩니다.

---

## **1 Tauri + React ▶ 네이티브처럼 가벼운 데스크톱 앱 (추천)**

| **특징** | **이유·자료** |
| --- | --- |
| **Rust 백엔드 + WebView 프런트** → 배포 용량 5-10 MB, Electron의 1/10 무게 | 튜토리얼 영상 및 문서 다수 |
| 로컬 파일 권한 내장 → @tauri/fs, dialog.open() 으로 폴더 선택·썸네일 리스트 | Tauri API 가이드 |
| HTML5 <video> 태그에 track kind="subtitles" 연결 → 자막 동기 재생 | W3C media cues 표준 |
| 클라이언트 검색은 **Fuse.js / Lunr.js** (2-3 kB)로 즉시 필터 | Fuse.js 블로그 튜토리얼 , Lunr.js 실무 후기 |

### **📦 폴더 구조 예시**

```
src/
 ├─ App.tsx        # React ─ 상태: videoList, currentVideo
 ├─ components/
 │    ├─ Sidebar.tsx   # Fuse.js 실시간 필터 목록
 │    ├─ Player.tsx    # <video> + <track> + 현재 캡션 하이라이트
 │    └─ Transcript.tsx# 클릭→시크바 점프
 ├─ tauri.conf.json    # 파일권한 allow-all
public/
 └─ index.html
```

### **🔑 실전 팁**

- **싱크 스크롤** : video.currentTime 이벤트마다 activeCue 계산해 .scrollIntoView()
- **검색 성능** : 100편×수백 줄 JSON (≈ 200 KB) → Fuse.js 10 ms 내 응답.
- **빌드** : tauri build → OS별 dmg/exe 배포 끝.

---

## **2 정적 사이트 (Hugo·Vite 등) + Client-side Search**

| **장점** | **설명·자료** |
| --- | --- |
| **배포가 “폴더 복사” 끝** → GitHub Pages / local file:// 모두 작동 | Fuse.js 검색 아이디어 블로그 |
| HTML5 비디오 + WebVTT track 만으로 자막 표시 가능 |  |
| 필요 기술 = 순수 HTML·JS (React 불필요) |  |

### **핵심 스크립트 15 줄 예시**

```
<script src="fuse.min.js"></script>
<script>
const fuse = new Fuse(videoIndexJson, { keys:['title','captions'] });
searchInput.oninput = () => {
  const hits = fuse.search(searchInput.value);
  renderSidebar(hits.slice(0,20));
};
</script>
```

*검색 데이터* videoIndex.json 은 파이썬에서 1회 생성(자막 텍스트·경로 포함).

---

## **3 Streamlit 한 방 앱 (Python 만)**

| **장점** | **근거·자료** |
| --- | --- |
| **st.video(path)** 로 로컬 파일 바로 재생 | 공식 API 도큐먼트 |
| st.columns() 배치 → 왼쪽 비디오 / 오른쪽 Datatable(자막) 보기 | Streamlit 샘플 이슈 스레드 |
| st.text_input() + pandas filter → 실시간 검색 |  |

```
import streamlit as st, json, pandas as pd
data = json.load(open('videoIndex.json'))
df   = pd.DataFrame(data)
q = st.text_input("검색")
hits = df[df['all_text'].str.contains(q, case=False)]
for row in hits.itertuples():
    with st.expander(row.title):
        st.video(row.path)
        st.write(row.captions)
```

- 단점: 브라우저 기반 UI 치고는 동기 스크롤/하이라이트 구현이 번거롭지만, 1-페이지 데모엔 충분.

---

## **4 Electron or Ready-made Players (호환-만족용)**

- **PhreshPlayer** 같은 MIT Electron 미디어 플레이어를 포크 → SRT/VTT 패널 추가만 하면 끝 .
- Electron은 패키지 60+ MB, 메모리 200 MB… Tauri 대비 무겁지만 플러그인 생태계 풍부 .

---

## **5 오픈소스 “Transcript Player” 레퍼런스**

| **프로젝트** | **특징** | **참고** |
| --- | --- | --- |
| **Transcript-Seeker** | React + auto-scroll transcript, 클릭 점프, MIT | 데모·레포 |
| **Transcribee** | Collaborative 편집·실시간 sync 자막 편집 | GitHub 레포 |
| AblePlayer | 접근성 강화 오디오/비디오 플레이어, HTML만으로 삽입 | AblePlayer demo (Streamlit 이슈 링크) |

이 레포들을 **UI·싱크 로직 코드베이스**로 활용해 js 컴포넌트를 추출하면 개발 속도가 크게 단축됩니다.

---

## **6 추천 실행 단계**

1. **Tauri Init** → React 템플릿 선택 → 폴더 열람 권한 설정.
2. 파이썬 스크립트로 **videoIndex.json**(title, captions, path, % duration) 1회 생성.
3. React 사이드바 컴포넌트에 **Fuse.js search** + 썸네일 리스트.
4. <video> + <track src="captions.vtt"> + cuechange 리스너로 자막 하이라이트.
5. tauri build 로 mac .dmg / Windows .exe 완성.

*1~4 단계까지 주말 해킹톤 정도면 MVP 가능 — 서버·DB 전혀 필요 없음.*

---

## **7 결론**

- **Tauri + Fuse.js + HTML5 track** 조합이 가장 가볍고 빠르며,
- Streamlit은 “Python만” 환경에서 30 분 데모 만들기에 최적,
- 정적 Hugo 사이트 + Lunr/Fuse.js 는 배포·호스팅이 극히 단순.

지금 구축해 둔 **Chroma 인덱스 + 자막 JSON** 을 그대로 재활용할 수 있으니, 위 설계 중 하나 골라 바로 UI 레이어만 얹으면 “로컬-전용 동영상 + 자막 지식 하우스”가 완성됩니다. 🚀

- *요약 ** Obsidian을 설치하지 않고도 로컬-전용 데스크톱 앱 하나로 “영상 + 자막 뷰 + 全文 검색 + 노트” 기능을 구현할 수 있습니다. 가장 가벼운 조합은 **Tauri (Rust WebView) + React** 프런트엔드에 **Fuse.js** 또는 **Lunr.js** 같은 클라이언트-사이드 검색 라이브러리를 붙이는 방식입니다. 앱 용량은 5 ~ 10 MB, 메모리도 Electron의 1/5 수준이며 WebVTT 자막을 <track> 태그로 동기 재생할 수 있어 “영상·자막·노트”를 한 화면에서 다룹니다. 실제로 React·Tauri로 만든 Markdown 노트앱 예시·오픈소스 템플릿이 여럿 공개돼 있어(7 MB 배포 크기) 그대로 포크해 UI만 교체하면 주말 해킹톤 수준으로 MVP가 가능합니다.

---

## **1 왜 “Tauri + React + Fuse.js”가 Obsidian 대체에 적합한가**

### **경량·네이티브 배포**

- Tauri는 Rust 백엔드와 OS WebView를 쓰므로 **앱 크기 5~10 MB, 메모리 60 MB** 수준이다 .
- Electron 기반 대안은 60 MB 이상·RAM 200 MB 이상이라 휴대성이 떨어진다 .

### **로컬 파일 접근·보안**

- @tauri/fs API로 사용자가 지정한 폴더(예: vault/10_videos/)를 그대로 읽고 쓸 수 있다 .
- 서버 없이 동작하므로 민감한 투자 노트·자막이 외부로 나가지 않는다.

### **실시간 검색**

- Fuse.js·Lunr.js는 수십 KB 크기의 JS 라이브러리로 JSON 인덱스를 메모리에 올려 **100편×수백 라인 자막도 <10 ms** 내 fuzzy 검색이 가능하다 .

### **자막-동기 재생**

- HTML5 <video> + <track kind="subtitles"> 표준만으로 WebVTT 자막을 싱크할 수 있어 추가 라이브러리 없이 “재생 → 해당 문장 하이라이트” 구현이 쉽다.

---

## **2 오픈소스 예시 & 참고 레포**

| **레포/기사** | **핵심 포인트** |
| --- | --- |
| **Markdown Desktop App with Tauri**: 7 MB 완성본, Mac/Win/Linux 배포 | Tauri 설정·빌드 스크립트 참고 |
| **tauri-markdown**: Vue3+Vditor 노트앱 예시 | 파일 접근·Hot-reload 코드 참고 |
| **React Note-taking Tauri**(Reddit) | React Router 구조·썸네일 목록 구현 |
| **Fuse.js 블로그 튜토리얼** | 자막 JSON 실시간 필터 예시 |
| **Obsidian React Components 플러그인** | 기존 Obsidian 노트에 React 컴포넌트 삽입 사례—UI 아이디어 차용 용이 |

---

## **3 앱 아키텍처 제안**

### **3.1 디렉터리 구조**

```
my-player/
├─ src-tauri/          # Rust backend (Tauri CLI 생성)
├─ src/
│   ├─ App.tsx
│   ├─ components/
│   │   ├─ Sidebar.tsx      # Fuse 검색 + 썸네일
│   │   ├─ VideoPlayer.tsx  # <video> + track + cuechange
│   │   └─ Transcript.tsx   # 자막 리스트, 클릭→seek
│   └─ hooks/
│       └─ useFuse.ts        # index.json 로드 + Fuse 인스턴스
└─ videoIndex.json           # 1회 생성 (파이썬 스크립트)
```

### **3.2 주요 기능 흐름**

1. **인덱스 로드**: videoIndex.json = [{id,title,thumb,mp4,vtt,allText}].
2. **Fuse.js init** → 검색어 입력마다 fuse.search(q) → 사이드바 갱신.
3. 아이템 클릭 → VideoPlayer에 src={mp4} · track src={vtt} 주입.
4. oncuechange 이벤트로 현재 캡션 하이라이트 → Transcript 스크롤.
5. tauri dialog.open 으로 새 폴더 지정 → 인덱스 재로드.

---

## **4 비교: Obsidian vs 로컬 데스크톱 앱**

| **기능** | **Obsidian** | **Tauri 앱** |
| --- | --- | --- |
| Markdown 편집 | 기본 제공 | Vditor, Milkdown, MDE 등 자유 선택 |
| Graph View | Core 플러그인 | React - vis / Cytoscape로 구현 가능 |
| 영상 재생 | 직접 불가(링크) | <video> 내장 재생 |
| 자막 싱크 | 플러그인 필요 | HTML5 track 기본 |
| 용량·메모리 | 120 MB / 200 MB↑ | 7 MB / 60 MB↓ |
| 모바일 | Obsidian 모바일 앱 | Tauri 모바일 베타(실험) |

> 귀결
> 
> 
> **“영상-자막 연구 + 즉석 메모”**
> 

---

## **5 개발·배포 타임라인**

| **시간** | **할 일** |
| --- | --- |
| **0.5 d** | tauri init react → 폴더 접근 권한·Fuse.js PoC |
| **1 d** | VideoPlayer + Transcript 싱크·검색 사이드바 구현 |
| **0.5 d** | Vditor/Rich-markdown 편집기 넣고 “노트 저장” 기능 추가 |
| **0.5 d** | 빌드 (tauri build) → .dmg/.exe 배포·아이콘·업데이트 설정 |
| **합계 2–3일** | 개인용 MVP 완성 &∼10 MB 패키지 |

---

## **6 마무리 제안**

- **UI 초안**은 React-Obsidian 플러그인 레이아웃(좌 트리·우 편집)에서 색상·폰트만 변경해 친숙함 유지 .
- 검색 정확도는 Fuse.js threshold · distance 값으로 조정 가능 → 자막 오타가 많으면 0.4~0.5 권장.
- 추후 코퍼스가 1k 편↑ 로 커지면 **mini-lunr pre-built 인덱스**(100 kB)로 교체해 속도 유지.

> 결론
> 
> 
> **Tauri + React**
>

### 🔍 비교 포인트 한눈에

| 항목 | **Notebook LM** | **Obsidian + AI 플러그인/스크립트** |
| --- | --- | --- |
| 설치·준비 | 브라우저 접속 → 즉시 사용 | 로컬 Vault 생성 후 스크립트‧플러그인 설정 필요 |
| 데이터 용량 한계 | 노트북 당 **50개 소스 · 소스당 50만 단어 / 200 MB** (무료 기준)[Reddit](https://www.reddit.com/r/notebooklm/comments/1b0pav4/what_are_notebooklm_capabilities_when_it_comes_to/?utm_source=chatgpt.com)[Google Help](https://support.google.com/notebooklm/answer/14276468?hl=en&utm_source=chatgpt.com) | 로컬 저장 공간만큼 무제한 (대용량 채널도 OK) |
| AI 질의 응답 | 내장 LLM 사용, API 없음 → 자동화 제한 | ChatGPT API·로컬 LLM 연결 가능, 스크립트로 파이프라인 자동화 |
| 링크·네트워크 관점 | 기본 폴더 구조, 링크드 노트 X | 백링크·그래프 뷰·Dataview로 맥락 탐색 뛰어남 |
| 시각화·학습 도구 | 마인드맵·타임라인·퀴즈·팟캐스트 등 Studio 위젯 제공 | 커스텀 플러그인·Mermaid·Dataview Table 등 자유도 ↑ |
| 개인 정보·보안 | 구글 클라우드 저장·TOS 제한 | 완전 오프라인 저장 가능, 민감 정보 안전 |
| 비용 | Free/Plus (쿼리·소스 한도) | 기본 무료, OpenAI 요금·플러그인 구입은 선택 |

---

## 📌 언제 Notebook LM이 유리할까?

1. **빠른 요약·간단 Q&A**가 목적일 때
    - 소스 50개 이하로 나누어 업로드하면 즉시 요약·Mind Map·타임라인 생성 가능.
2. **코딩·플러그인 없이** 곧바로 AI와 대화하고 싶은 경우
    - 별도 세팅 없이 브라우저에서 작동.
3. **PDF·슬라이드·YouTube 링크**를 섞어가며 ad-hoc 학습 자료를 만들 때 유용.

> 단, 채널 영상이 수백 편이라면 여러 노트북으로 수동 분할해야 하며, API나 배치 업로드가 없어 대량 파이프라인 구축에는 한계가 있습니다.Reddit
> 

---

## 📌 언제 Obsidian이 더 적합할까?

1. *채널 전체(수백~수천 편) 스크립트를 ‘데이터 하우스’**로 장기 보관·확장하려면
    - 로컬 Markdown 파일로 저장 → 용량 제한 없음.
2. **AI 파이프라인을 자동화**하고 싶을 때
    - Python으로 YouTube API → .md 변환 → Vault 저장 → LlamaIndex / LangChain 임베딩 → Obsidian AI 플러그인(예: AI Assistant, Co-Pilot)으로 쿼리 가능.[Obsidian Forum](https://forum.obsidian.md/t/introducing-obsidian-ai-assistant-your-gateway-to-ai-models-in-obsidian-notes/59437?utm_source=chatgpt.com)[Medium](https://medium.com/%40petermilovcik/obsidian-ai-plugins-overview-a6747d52977e?utm_source=chatgpt.com)
3. **프라이버시·오프라인**이 중요할 때
    - 모델 호출을 로컬 LLM(LLama.cpp 등)로 전환하거나, 외부 API 키 관리가 자유로움.
4. **네트워크형 지식 그래프**가 필요할 때
    - 백링크·태그·Dataview 쿼리로 특정 인물·주제별 맥락을 빠르게 탐색.

---

## 🗂️ 추천 워크플로우 (하이브리드)

1. **1차 저장소**:
    - *yt-dl* 등으로 자막 일괄 추출 → Markdown 변환 → Obsidian Vault에 “videoID_제목.md” 형태로 저장.
2. **메타데이터 태깅**:
    - 업로드 날짜·카테고리·키워드 YAML 앞머리 추가 → Dataview로 통계·필터링.
3. **AI 질의**:
    - Obsidian 내 ChatGPT 플러그인으로 고급 쿼리(“지속가능한 투자 전략만 추출” 등).
    - 특정 프로젝트용으로 50편 이하 추려 **Notebook LM**에 임시 업로드 → 마인드맵·학습 가이드 등 빠른 시각화.
4. **결과 정리**: Notebook LM서 만든 Mind Map·타임라인을 이미지/PDF로 export → 다시 Obsidian 노트에 첨부하여 영구 보관.

---

## 🔑 결론

- **“규모·자동화·프라이버시”가 핵심**이면 **Obsidian + AI 플러그인·스크립트**가 더 적합합니다.
- *“설정 없이 바로 요약·시각화”**가 필요하거나 **프로젝트 단위(≤50 소스)** 로 다루면 **Notebook LM**이 간편합니다.

두 도구를 **보완적으로** 사용하면 대규모 지식 저장소(Obsidian) + 빠른 AI 리포트(Notebook LM)라는 최적의 조합을 만들 수 있어요. 🚀

## 🔑 최종 결론 (무료 API → ChatGPT 2단계 파이프라인 전제)

1. **대규모 스크립트 저장·정제·AI 파이프라인 자동화**
    - *Obsidian + 무료 LLM API(예: DeepSeek, HuggingFace Inference Free Tier)**로 1차 전처리·메타데이터 태깅·Markdown 변환 → 로컬 Vault에 무제한 보관.
    - Python 스크립트·GitHub Actions 등으로 **배치 처리** 가능.
    - 백링크·Dataview로 맥락 탐색, 추후 모델 재학습‧재임베딩도 자유롭게 확장.
2. **심화 분석·전략 제안 단계**
    - 정제된 노트를 **ChatGPT** 연결(Obsidian AI 플러그인 또는 직접 API 호출) → 고급 요약·비교·전략 생성.
    - 특정 프로젝트 자료(≤ 50편)는 **Notebook LM**에 임시로 올려 마인드맵·타임라인·퀴즈 등 빠른 시각화를 얻고, 결과를 다시 Obsidian에 첨부.
3. **Notebook LM 단독 사용은 부적합**
    - 무료 계정 기준 **소스·용량 한도**와 **API 미제공** 때문에 “무료 API → Notebook LM → ChatGPT” 파이프라인 구현 불가.
    - 대규모 채널(수백‧수천 편)은 노트북 다중 분할·수동 업로드가 필요해 관리 부담 ↑.

> 따라서:
> 
> - **주 저장소·자동화 허브** ➜ **Obsidian**
> - **빠른 시각화·학습 자료 생성** ➜ 필요 시 **Notebook LM** 보조
> - 무료 LLM API로 1차 정제 후 ChatGPT로 고도화하는 2단계 전략과 가장 궁합이 좋습니다. 🚀

네, **지금 생각하시는 “무료 LLM API 1차 정제 → Obsidian Vault 보관 → ChatGPT 심화 분석”** 흐름만으로도 목표(대규모 스크립트 기반 전략·인사이트 생성)는 충분히 달성됩니다.

- **Notebook LM은 자동화·대량 처리 API가 없고 소스·용량 제한**이 있으므로, 파이프라인에 억지로 넣어도 별다른 이득이 없습니다.
- 특히 배치 업로드·정기 갱신을 스크립트로 돌릴 예정이라면, **Notebook LM이 오히려 수작업 포인트**가 되어 복잡도를 높입니다.

> ✅ 따라서:
> 
> - **핵심 저장·분석 허브**: Obsidian + 무료 LLM API + ChatGPT
> - **Notebook LM**: 필요성을 느낄 때(빠른 마인드맵·타임라인을 한두 번 뽑고 싶을 때) **선택적으로** 열어 쓰는 정도면 충분합니다.

결론적으로, 현재 워크플로우에선 **Notebook LM을 제외해도 전혀 지장 없으며** 오히려 관리와 자동화가 더 깔끔해질 거예요. 😊

아요. **“코딩으로 파이프라인을 통째로 짤 수 있는 개발자”**라면 Notebook LM을 메인으로 두기보다는 직접 RAG(검색 + 생성) 파이프라인을 꾸려서 쓰는 편이 훨씬 강력합니다.

---

## 🔧 직접 구축이 유리한 핵심 이유

| 구분 | 직접 구축 | Notebook LM |
| --- | --- | --- |
| **규모·확장성** | 로컬‧클라우드 저장 한계만큼 무제한. 인덱스 세분화·샤딩도 자유 | 노트북 당 50 소스 제한·API X |
| **자동화** | 크론‧GitHub Actions로 **주기적 스크립트 실행** → 최신 자막 자동 반영 | 수동 업로드 필요, 대량 처리 불가 |
| **AI 모델 선택** | OpenAI·DeepSeek·Llama 3·Mixtral 등 **모델 교체·미세조정** 자유 | 내장 LLM 고정, 파라미터 제한 |
| **비용 제어** | 무료 API→고급 모델 단계적 호출, 토큰 절약 가능 | Plus 요금제를 써도 한도 있음 |
| **프라이버시** | 오프라인·VPC 내부 운영 가능 | 구글 서버 저장 필수 |
| **커스텀 기능** | 파인튜닝·Chain of Thought 로그·플러그 추가 등 원하는 대로 | 스튜디오 위젯 고정 |

---

## 🛠️ 추천 스택 & 워크플로우

1. **수집**
    - `yt-dlp` + YouTube Data API → 자막 (SRT/JSON) 일괄 다운로드
    - Python으로 **Markdown 변환** → Obsidian Vault 또는 S3 저장📂
2. **전처리 & 1차 요약**
    - 무료 LLM(DeepSeek, HuggingFace Inference)으로 문단 단위 초벌 요약
    - 메타데이터(YAML) 태깅: 영상 ID, 업로드 날짜, 키워드, 등장인물 등
3. **임베딩 & 검색 인덱스**
    - **Chroma / Weaviate / Qdrant** 선택 → chunk 단위 임베딩 생성&업로드
    - 필요 시 `langchain-text-splitters`로 슬라이딩 윈도우 분할
4. **고급 질의 / 전략 생성**
    - **ChatGPT**(gpt-4o 같은 상위 모델)로 RAG 호출
    - “~에 대한 투자 전략 요약” 같이 구체 프롬프트 → 후보 답변 비교·정제
5. **결과 관리**
    - Obsidian 노트에 백링크, Dataview 통계, Mermaid MindMap 삽입
    - PDF·HTML 리포트 자동 생성 → Notion·Slack 공유

> ⚙️ Tip: 파이프라인을 Docker Compose로 묶어두면 어느 서버에서도 docker compose up -d 한 줄로 재현 가능!
> 

---

## 언제 Notebook LM을 ‘보조 도구’로 쓸 만한가?

- **소규모 모듈 학습 자료**를 빨리 시각화해야 할 때 (타임라인, 퀴즈 등)
- 팀원이 비개발자라 **코드 없는 빠른 요약**을 원할 때
- “이 논문 10편만 Mind Map으로 뽑아줘”처럼 **단발성 과제**일 때

---

### 🚀 결론

- **개발 역량 + 자동화 욕구**가 있으면 **직접 구축**이 ROI·유연성 모두 최고입니다.
- Notebook LM은 **‘코드 작성 없이 빠른 시각화’가 필요할 때** 보조 수단으로만 쓰면 효율이 극대화됩니다.