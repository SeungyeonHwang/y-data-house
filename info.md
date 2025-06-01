# 📍 Y-Data-House - Next Steps Roadmap  
*(after first videos are downloaded & notes created)*  

## 1. 🔎 데이터 정합성 점검  
1.1 **파일 구조 검사** – `vault/10_videos/**` 경로·파일명(공백→하이픈) 확인  
1.2 **YAML 검증** – `ydh config validate` → 필수 필드·날짜·ID 일관성 검사  
1.3 **Dataview Smoke-Test** – Obsidian 열기 →  
```dataview
table upload, duration
from "10_videos"
sort upload desc


⸻

2. 🖇️ Obsidian 세팅

2.1 필수 플러그인 설치
	•	Dataview, Canvas, Charts View, AI Assistant

2.2 템플릿 배치
	•	vault/00_templates/dataview.md  (샘플 쿼리)
	•	vault/00_templates/ai-prompt.md  (DeepSeek 요약 프롬프트)

2.3 해시태그 정규화 스크립트 (선택)

ydh tidy --tags --lower --slugify


⸻

3. 🗄️ 벡터 인덱스 생성

3.1 Chroma 초기화

python vault/90_indices/embed.py \
       --source "vault/10_videos" \
       --db "vault/90_indices/chroma"

3.2 embed.py 크론 등록 (주 1회)

⸻

4. 🤖 AI 통합

4.1 AI Assistant 설정

Provider URL : https://api.deepseek.com/v1/chat/completions
Context Size : 3000
Model        : deepseek-chat

4.2 RAG 플러그인 연결 (Chroma endpoint → AI Assistant)
4.3 테스트 프롬프트 → “하네다이노베이션시티 관련 핵심 문제 3줄 요약”

⸻

5. 📈 초기 분석·시각화

5.1 Dataview → 월별 업로드·조회수 차트
5.2 Canvas 보드 “부동산 실패사례” 노트 묶기
5.3 Charts View → 토픽 빈도 Line Chart (topic 배열 기준)

⸻

6. 🔄 자동화 & 유지보수

6.1 Prefect Flow 배치

prefect deployment build ydh.flow:batch_ingest -n nightly-ingest -i cron,0 3 * * *
prefect deployment apply nightly-ingest-deployment.yaml

6.2 ydh maintenance --clean-temp --retry-failed  (주기적 청소)
6.3 Git/Syncthing 백업 → Vault + 90_indices 동기화

⸻

7. 📝 다음 목표 (2–4주)
	•	DeepSeek RAG 라이트 웹 UI (FastAPI)
	•	JupyMD 노트북 → pandas·BERTopic 결과 자동 삽입
	•	Canvas 자동 생성 스크립트 (대표 문장 카드)



🛠️ Obsidian + AI 로 바로 써먹을 “실전 유스케이스” 10선
	1.	초보 투자 체크리스트 자동 생성
– 질문 “부동산 투자 처음 주의할 점?” → 자막 DB 요약 + 근거 문장 인용
	2.	실패 재개발 사례 레포트
– 토픽 실패 필터 → 실패 원인·비용·후속대책 표 + 관련 영상 링크
	3.	월간 키워드 트렌드 대시보드
– Dataview + Charts로 지난 12개월 ‘공실률·세금’ 언급 빈도 그래프
	4.	새 영상 아침 200자 Digest
– 밤마다 Prefect 배치 → 📄 Daily-Digest.md 노트 자동 작성 & 알림
	5.	규제·세법 변경 알림
– 예약 검색 “취득세·고정자산세” 키워드 감지 시 Slack DM / Obsidian 팝업
	6.	투자처 후보지 추천
– AI RAG로 성공 패턴 학습 → “도쿄 외 신흥지역 3곳 + 리스크 요약”
	7.	테마별 재생목록 생성
– “임대수익 영상 모아줘” → YouTube URL 리스트 + 로컬 mp4 경로 출력
	8.	1-Click 요약 + 펀치라인 카드
– 노트 열고 /summarize → 5문장 요약 + 핵심 인용구 Canvas 카드 배치
	9.	플래시카드 학습 (용어 · 수치 암기)
– 자막 숫자·정의 구문 → Q/A 카드로 변환 → Spaced Repetition
	10.	조회수 대비 길이 ROI 분석
– Dataview view_count / duration_seconds 계산 → 효율 Top10 영상 순위표

이 10가지만 돌려도 정보 수집 → 활용 → 학습·결정이 전부 Vault 안에서 끝납니다.

	•	Obsidian 쪽 가치
	•	로컬·무제한 저장 → 유튜브처럼 대용량 텍스트/영상도 걱정 없이 보관
	•	Dataview·Graph·Canvas → 단순 파일 뭉치가 아니라 데이터베이스·지식그래프로 바로 탐색
	•	플러그인 생태계 → 스페이스드리핏·Charts 등 맞춤 워크플로 꾸미기
	•	AI(DeepSeek/로컬 LLM) 쪽 가치
	•	RAG (Search + GPT)로 내 자막에서만 답변·요약 → 외부 잡음 없이 맞춤 인사이트
	•	반복 질문(“이번 주 요약”, “키워드 알림”)을 자동 배치로 돌려 시간을 절약
	•	길고 복잡한 자막을 한 번에 ‘5줄 체크·표·그래프’로 가공 → 실무 의사결정에 바로 쓰임

결국, *“대량 영상 → 구조화된 지식 → 즉시 검색·시각화·보고서”*가 가능해져서
	•	자료 찾느라 유튜브 돌려보는 시간을 줄이고
	•	투자·기획·학습 같은 실제 업무 결과물을 더 빨리 뽑아낼 수 있다는 점이 핵심 이유입니다.
# 📍 Y‑Data‑House — Next‑Steps Roadmap  
*(after first videos are downloaded & notes created)*  

---

## 1 🔎 데이터 정합성 점검  
1. **파일·폴더 구조**   `vault/10_videos/**` → 공백을 `-` 로 통일  
2. **YAML 검증**   `ydh config validate` → 필수 필드·날짜·ID 일치 확인  
3. **Dataview Smoke‑Test**   

   ```dataview
   table upload, duration
   from "10_videos"
   sort upload desc
   ```

---

## 2 🖇️ Obsidian 세팅  
- **필수 플러그인** : Dataview · Canvas · Charts View · AI Assistant  
- **템플릿 복사** :  
  - `vault/00_templates/dataview.md` (샘플 쿼리)  
  - `vault/00_templates/ai‑prompt.md` (DeepSeek 요약 프롬프트)  
- **해시태그 정규화** (선택)   
  ```bash
  ydh tidy --tags --lower --slugify
  ```

---

## 3 🗄️ 벡터 인덱스 생성  
```bash
python vault/90_indices/embed.py \
      --source "vault/10_videos" \
      --db     "vault/90_indices/chroma"
```
> 크론 등록 : 주 1회 실행

---

## 4 🤖 AI 통합  
| 설정 항목 | 값 |
|-----------|----|
| **Provider URL** | `https://api.deepseek.com/v1/chat/completions` |
| **Model** | `deepseek-chat` |
| **Context Size** | `3000` tokens |

- **RAG 연결** : AI Assistant → Chroma endpoint  
- **테스트** : “하네다이노베이션시티 핵심 문제 3줄 요약”

---

## 5 📈 초기 분석·시각화  
1. Dataview → 월별 업로드·조회수 차트  
2. Canvas → “부동산 실패사례” 노트 클러스터  
3. Charts View → 토픽 빈도 Line Chart (`topic[]`)

---

## 6 🔄 자동화 & 유지보수  
```bash
# 야간 배치 등록
prefect deployment build ydh.flow:batch_ingest \
       -n nightly-ingest -i cron,0 3 * * *
prefect deployment apply nightly-ingest-deployment.yaml

# 주간 청소
ydh maintenance --clean-temp --retry-failed
```
- Git/Syncthing : Vault + `90_indices` 동기화

---

## 7 🚀 다음 목표 (2–4 주)  
- DeepSeek RAG 라이트 웹 UI (FastAPI)  
- JupyMD 노트북 → pandas·BERTopic 결과 자동 삽입  
- Canvas 자동 생성 스크립트 (대표 문장 카드)

---

## 🛠️ 실전 유스케이스 10선  
1. **초보 투자 체크리스트** — “부동산 투자 처음 주의할 점?” → 요약 + 근거 문장  
2. **실패 재개발 레포트** — 토픽 `실패` 필터 → 원인·비용·후속대책 표  
3. **키워드 트렌드 대시보드** — 12개월 ‘공실률·세금’ 빈도 그래프  
4. **Daily Digest** — 새 영상 200자 요약 노트 자동 작성  
5. **규제·세법 변경 알림** — 특정 키워드 감지 시 Slack DM  
6. **투자처 후보 추천** — 성공 패턴 분석 → “도쿄 외 3곳 + 리스크”  
7. **테마별 재생목록** — “임대수익 영상” URL + 로컬 MP4 경로 출력  
8. **1‑Click 요약 카드** — `/summarize` → 5문장 + 펀치라인 Canvas 카드  
9. **플래시카드 학습** — 자막 숫자·정의 → Q/A 카드 자동 생성  
10. **ROI 분석** — `view_count / duration_seconds` Top 10 영상 표

---

### 💡 왜 Obsidian + AI인가?  
- **로컬·무제한 저장** → 대용량 텍스트·영상 보관 걱정 없음  
- **Dataview·Canvas** → 지식그래프·데이터베이스 탐색 즉시 가능  
- **AI RAG** → *내* 자막에서만 답변·요약 → 맞춤형 인사이트  
- **자동화** → 반복 요약·알림·리포트가 크론 한 줄로 끝