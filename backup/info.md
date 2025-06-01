아래 예시는 Y-Data-House 저장소를 위한 Cursor 지시문 과 Project Rules 초안입니다.
첫 단계로 .cursor/rules/ 폴더에 넣어 두면, Cursor가 노트북·CLI 없이도 자동으로 파일을 인덱싱하고 AI 질의 시 규칙을 적용합니다. 프로젝트 규모가 커져도 유지·확장하기 쉽도록 모듈 경로 매칭 / 설명 / 베스트-프랙티스를 분리했습니다.

⸻

✨ 1. Cursor 지시문 (README 선두나 info.md에 삽입)

# ───────────────────────────────────────────────────────────
# cursor:AutoAttach
#
# - src/ydh/**/*.py         # 프로덕션 파이썬 코드
# - tests/**/*.py           # pytest 유닛 테스트
# - vault/10_videos/**/*.md # 자막-변환 노트
# - pyproject.toml
#
# cursor:Rules
#
# - .cursor/rules/ydh_architecture.mdc
# - .cursor/rules/ydh_cli.mdc
# - .cursor/rules/ydh_vault_writer.mdc
#
# > Note: 자막·Markdown은 **100 줄 이하 요약**만 AI 답변에 포함.
# ───────────────────────────────────────────────────────────

cursor:AutoAttach 구문은 열려 있는 파일이 패턴에 맞으면 해당 규칙을 자동으로 첨부합니다  ￼  ￼.
cursor:Rules 블록으로 별도 .mdc 규칙 파일을 명시하면, Cursor가 **프로젝트 수준(Persistent)**으로 적용합니다  ￼  ￼.

⸻

🗂️ 2. 폴더 구조 & 규칙 파일 위치

.cursor/
  rules/
    ydh_architecture.mdc
    ydh_cli.mdc
    ydh_vault_writer.mdc
src/ydh/...
vault/...

.mdc 확장자는 Cursor 0.45 이후 “Markdown+Code” 규격으로 권장됩니다  ￼.

⸻

📏 3. 예시 Project Rule — ydh_architecture.mdc

# Rule: YDH-Architecture
# Applies to: src/ydh/**/*.py

## Overview
Y-Data-House 파이프라인은 3-계층(ingest → transform → store) 아키텍처를 따른다. \
AI 모델이 코드를 읽을 때 다음 사항을 가정하라.

### 1. 모듈 책임
| 모듈 | 핵심 책임 |
| --- | --- |
| `downloader.py` | yt-dlp wrapper + download-archive 중복 방지 |
| `transcript.py` | 자막 추출 3단계 백업(API → VTT → SRT) |
| `converter.py` | `<vtt,srt> → clean text` 후 문장 분리 |
| `vault_writer.py` | Obsidian 경로·템플릿 렌더링 |

### 2. 코딩 규칙
* **로깅** → `logging.getLogger(__name__)` 사용, `TimedRotatingFileHandler` 일간 롤링  [oai_citation:5‡Cursor - Community Forum](https://forum.cursor.com/t/a-deep-dive-into-cursor-rules-0-45/60721?utm_source=chatgpt.com)  
* **타입 힌트** 필수 (`-> str`, `-> Path`).
* 외부 I/O는 `ydh.config.VAULT_ROOT` 기준 **상대 Path**.

@Docs src/ydh

이처럼 규칙 파일은 설명 + 표 + @Docs 참조 형태가 권장됩니다  ￼  ￼.

⸻

⚙️ 4. 중복 다운로드 방지 Rule — ydh_cli.mdc

# Rule: YDH-CLI
# Applies to: src/ydh/cli.py

> If the user asks “왜 중복 다운로드가 안 되나요?”  
> 1️⃣ 설명: yt-dlp `--download-archive` 옵션으로 이미 처리된 video_id를 건너뜁니다.  
> 2️⃣ 추가: `progress.py` 가 SQLite checkpoint를 유지해 네트워크 오류 후 재시도 가능.

@File src/ydh/progress.py

@File 지시어는 특정 파일을 답변 컨텍스트에 삽입해 AI가 직접 읽도록 합니다  ￼.

⸻

🚀 5. CLI 자동화 Rule — ydh_vault_writer.mdc

# Rule: YDH-Vault-Writer
# Applies to: src/ydh/vault_writer.py

설명
: Markdown 노트는 다음 YAML 프론트매터를 포함해야 함  
```yaml
title:
upload:
channel:
video_id:
topic: []
source_url:

질의가 “노트 폴더 구조?”면
→ vault/10_videos/<채널>/<YYYY>/<날짜_제목>/captions.md 규칙을 답변.

@File src/ydh/converter.py

---

## 📌 6. 사용 가이드 (팀원 공유용)

1. **규칙 추가** : 새로운 도메인 모듈을 만들면 `.cursor/rules/<module>.mdc` 추가.  
2. **규칙 점검** : `Cmd ⇧ J` → *Project Rules* 탭에서 자동 로드 여부 확인  [oai_citation:9‡Cursor - Community Forum](https://forum.cursor.com/t/can-anyone-help-me-use-this-new-cursor-rules-functionality/45692?utm_source=chatgpt.com).  
3. **AutoAttach 테스트** : 원하는 `.py` 파일 열고 Chat ↗ “이 모듈 책임?” → 규칙이 첨부됐는지 우측-패널에서 확인.  
4. **Ignore** : 대용량 `video.mp4` 는 `cursor:AutoAttach` 패턴에 포함하지 말 것 (속도 ↓).  

---

## 📝 마무리 체크리스트

- [ ] `.cursor/rules/` 폴더 Git 추적 포함.  
- [ ] `README.md` 최상단에 **cursor:AutoAttach 블록** 삽입.  
- [ ] 첫 배치 실행 전 `downloader.py` 에 `downloaded.txt` 경로 지정.  
- [ ] `ydh ingest <채널URL>` 성공 → Obsidian → Dataview Table 렌더 확인.  

이렇게 설정해 두면 **새 파일만 자동 다운로드 → 노트 생성 → Cursor 규칙 적용 → AI Q&A** 흐름이 한 번에 완성되어, 이후 로컬 LLM · 벡터스토어를 붙여도 규칙을 그대로 재사용할 수 있습니다. 🎉


요약 ― 다운로더를 “모듈·패키지”로 분리하고 Obsidian Vault 폴더 구조(날짜·채널·메타 YAML)를 미리 정의해 두면, python -m ydh ingest <채널URL> 한 줄로 새 영상만 받아서 .md 노트를 자동 생성→Vault에 떨어뜨리는 배치가 완성된다.
아래 설계는 ① 코드 구조, ② Vault 레이아웃, ③ 배치 흐름, ④ 중복-다운로드 방지, ⑤ 앞으로 확장**을 순서대로 정리했다.

⸻

1  폴더·패키지 구조

y-data-house/
├─ README.md
├─ pyproject.toml           # poetry or pip-tools
├─ src/ydh/                 # <-- import 패키지   [oai_citation:0‡packaging.python.org](https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/?utm_source=chatgpt.com)
│   ├─ __init__.py
│   ├─ config.py            # 경로·API Key 관리 (pydantic BaseSettings)
│   ├─ downloader.py        # yt-dlp wrapper + download archive
│   ├─ transcript.py        # youtube-transcript-api 로 가져오기   [oai_citation:1‡GitHub](https://github.com/jdepoix/youtube-transcript-api?utm_source=chatgpt.com)
│   ├─ converter.py         # vtt/srt → clean text
│   ├─ vault_writer.py      # Markdown + YAML front-matter
│   ├─ progress.py          # JSON ↔ SQLite 저장소
│   ├─ cli.py               # Click 기반 엔트리포인트   [oai_citation:2‡Real Python](https://realpython.com/python-click/?utm_source=chatgpt.com)
│   └─ flow.py              # Prefect 배치 워크플로 정의   [oai_citation:3‡prefect.io](https://www.prefect.io/?utm_source=chatgpt.com)
└─ vault/                   # Obsidian 저장소

src/ 레이아웃은 테스트·패키징 시 “실행 코드와 루트 파일 혼재” 문제를 막아 준다  ￼.

⸻

2  Obsidian Vault 레이아웃

vault/
├─ 10_videos/
│   └─ 리베대학/
│       └─ 2025/
│           └─ 20250601_돈으로_사는_시간/
│               ├─ video.mp4
│               ├─ captions.txt
│               └─ captions.md   # 자동 생성 노트
└─ 90_indices/                   # (추후 Chroma DB)

▲ captions.md 템플릿

---
title: "돈으로 사는 시간"
upload: 2025-06-01
channel: "리베라루츠대학"
video_id: LTrE3VsKHL
topic: [투자, FIRE]
source_url: https://youtu.be/LTrE3VsKHL
---

{{캡션 본문}}

Dataview 는 YAML upload, topic 필드를 바로 쿼리·차트화할 수 있다  ￼.

⸻

3  Python 모듈 설계

모듈	주요 책임
config.py	HOME/.ydh.toml 로 기본 경로, 브라우저, 언어, Vault root 지정
downloader.py	yt-dlp에 --download-archive downloaded.txt 옵션 전달 → 동일 ID skip  ￼ ￼
transcript.py	① API로 직접, ② yt-dlp VTT, ③ SRT 백업 3-계층 전략
converter.py	`<vtt
vault_writer.py	템플릿 렌더 + pathlib 로 폴더 생성·파일 쓰기; 이미 있으면 pass
progress.py	JSON(간단) → 후에 SQLite로 교체 가능
cli.py	ydh ingest <채널URL> ydh convert 등 Click 서브커맨드
flow.py	Prefect @flow → cron or prefect orion start 로 예약 실행

로거는 logging.handlers.TimedRotatingFileHandler로 일자별 로그 파일을 분리  ￼.

⸻

4  배치 실행 흐름
	1.	채널 크롤 → video ID, upload date, title 목록.
	2.	중복 필터  downloader.has_id(id) (archive·DB 둘 중 하나).
	3.	신규 ID만 yt-dlp : mp4 + ko.vtt 다운로드.
	4.	자막 정제 → .txt.
	5.	Markdown 노트 작성 → Vault 저장.
	6.	(선택) 인덱스 업데이트 → Chroma or Weaviate 로 벡터 삽입.

전체 스텝을 Prefect Flow로 묶으면 CLI 한 줄 ydh batch run으로 실행·재시도·알림 관찰이 가능하다  ￼.

⸻

5  중복 다운로드 방지 전략

계층	설명
① yt-dlp download-archive	이미 저장된 ID txt를 보고 네트워크 fetch 자체를 skip  ￼
② progress DB	progress.py 가 성공·실패 모두 기록 → 네트워크 실패 후 재시도 가능
③ 파일 존재 검사	Vault 내 captions.md 존재 시 converter·writer 단계 생략

이중·삼중 체크로 안전성을 높이고 불필요한 I/O를 줄인다.

⸻

6  향후 확장 로드맵

Step	기능	참고
1	Dataview Table/Charts로 “월별 topic 빈도” 시각화	Obsidian Docs  ￼
2	CLI ydh search "FIRE" → DeepSeek RAG 답변	DeepSeek BaseURL 설정  ￼
3	Chroma DB 90_indices/ 내장 → FastAPI endpoint	
4	JupyMD 플러그인 → pandas 토픽 모델링 결과를 노트로 임베딩	
5	Canvas 보드 자동 생성: 대표 문장 카드 배치  ￼	


⸻

✅ 바로 할 일
	1.	poetry init 후 위 src 레이아웃 생성.
	2.	downloader.py 에서 --download-archive downloaded.txt 옵션만 먼저 적용.
	3.	Vault 경로 vault/10_videos/<채널>/<YYYY>/<날짜_제목>/ 생성 함수 구현.
	4.	CLI ydh ingest <채널URL> 테스트 → Obsidian 열어 노트 확인.

이렇게 쪼개 두면 나중에 로컬 LLM·Chroma를 붙이더라도 기존 모듈 변경 없이 flow.py만 수정해 배치를 확장할 수 있습니다. 🚀