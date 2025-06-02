# 📊 Dataview 쿼리 모음

## 🎬 영상 통계

### 채널별 영상 수
```dataview
TABLE 
    length(rows) as "영상 수",
    sum(rows.duration_seconds) / 60 as "총 시간(분)"
FROM "10_videos"
GROUP BY channel
SORT length(rows) DESC
```

### 최근 업로드 영상 (30일)
```dataview
TABLE 
    title as "제목",
    channel as "채널", 
    upload as "업로드일",
    duration as "길이"
FROM "10_videos"
WHERE upload >= date(today) - dur(30 days)
SORT upload DESC
LIMIT 20
```

### 긴 영상 (30분 이상)
```dataview
TABLE 
    title as "제목",
    channel as "채널",
    duration as "길이",
    view_count as "조회수"
FROM "10_videos"
WHERE duration_seconds > 1800
SORT duration_seconds DESC
```

### 인기 영상 (조회수 기준)
```dataview
TABLE 
    title as "제목",
    channel as "채널",
    view_count as "조회수",
    upload as "업로드일"
FROM "10_videos"
WHERE view_count > 0
SORT view_count DESC
LIMIT 20
```

## 🏷️ 태그 분석

### 태그별 영상 수
```dataview
TABLE 
    length(rows) as "영상 수"
FROM "10_videos"
FLATTEN topic as tag
GROUP BY tag
SORT length(rows) DESC
```

### 특정 태그가 포함된 영상
```dataview
TABLE 
    title as "제목",
    channel as "채널",
    topic as "태그"
FROM "10_videos"
WHERE contains(topic, "부동산")
SORT upload DESC
```

## 📈 시간 분석

### 월별 업로드 통계
```dataview
TABLE 
    length(rows) as "영상 수",
    sum(rows.view_count) as "총 조회수"
FROM "10_videos"
GROUP BY dateformat(upload, "yyyy-MM") as 월
SORT 월 DESC
```

### 요일별 업로드 패턴
```dataview
TABLE 
    length(rows) as "영상 수"
FROM "10_videos"
GROUP BY dateformat(upload, "cccc") as 요일
SORT length(rows) DESC
```

## 🔍 검색 및 필터

### Excerpt 포함 영상 목록
```dataview
TABLE 
    title as "제목",
    excerpt as "요약" 
FROM "10_videos"
WHERE excerpt != ""
SORT upload DESC
LIMIT 10
```

### 특정 키워드 검색
```dataview
LIST
FROM "10_videos"
WHERE contains(title, "도쿄") OR contains(excerpt, "도쿄")
SORT upload DESC
```

---

💡 **사용법**: 
- 위 쿼리들을 복사해서 노트에 붙여넣기
- `"부동산"` 등의 검색어를 원하는 키워드로 변경
- 날짜 범위나 정렬 조건을 필요에 따라 수정

## 🎯 전략적 분석 (고급)

### 성과 분석: 조회수 대비 길이 효율성
```dataview
TABLE 
    title as "제목",
    view_count as "조회수",
    duration_seconds / 60 as "길이(분)",
    round(view_count / (duration_seconds / 60)) as "분당조회수"
FROM "10_videos"
WHERE view_count > 100 AND duration_seconds > 0
SORT round(view_count / (duration_seconds / 60)) DESC
LIMIT 15
```

### 콘텐츠 트렌드: 월별 토픽 변화
```dataview
TABLE 
    length(rows) as "영상수",
    join(rows.topic) as "주요태그"
FROM "10_videos"
GROUP BY dateformat(upload, "yyyy-MM") as 월
SORT 월 DESC
```

### 제목 키워드 빈도 분석
```dataview
TABLE 
    length(rows) as "등장횟수"
FROM "10_videos"
WHERE contains(title, "투자") OR contains(title, "원룸") OR contains(title, "맨션") OR contains(title, "수익률")
FLATTEN choice(contains(title, "투자"), "투자", choice(contains(title, "원룸"), "원룸", choice(contains(title, "맨션"), "맨션", "수익률"))) as 키워드
GROUP BY 키워드
SORT length(rows) DESC
```

### 시리즈/연관 콘텐츠 발굴
```dataview
TABLE 
    title as "제목",
    upload as "업로드일",
    view_count as "조회수"
FROM "10_videos"
WHERE contains(title, "18년차") OR contains(excerpt, "직장인")
SORT upload ASC
```

### 고성과 콘텐츠 패턴 분석
```dataview
TABLE 
    title as "제목",
    view_count as "조회수",
    choice(view_count > 5000, "🔥고성과", choice(view_count > 2000, "📈중성과", "📊일반")) as "성과등급",
    topic as "태그"
FROM "10_videos"
WHERE view_count > 0
SORT view_count DESC
```

## 🏗️ 콘텐츠 기획 인사이트

### 미활용 토픽 발굴 (적은 영상 수)
```dataview
TABLE 
    length(rows) as "영상수",
    "기회영역" as "비고"
FROM "10_videos"
FLATTEN topic as tag
GROUP BY tag
WHERE length(rows) <= 3
SORT length(rows) ASC
```

### 시간대별 성과 분석
```dataview
TABLE 
    dateformat(upload, "cccc") as "요일",
    length(rows) as "영상수",
    round(avg(rows.view_count)) as "평균조회수"
FROM "10_videos"
WHERE view_count > 0
GROUP BY dateformat(upload, "cccc")
SORT round(avg(rows.view_count)) DESC
```

### 제목 길이와 성과 상관관계
```dataview
TABLE 
    choice(length(title) < 30, "짧음(<30)", choice(length(title) < 50, "보통(30-50)", "김(50+)")) as "제목길이",
    length(rows) as "영상수",
    round(avg(rows.view_count)) as "평균조회수"
FROM "10_videos"
WHERE view_count > 0
GROUP BY choice(length(title) < 30, "짧음(<30)", choice(length(title) < 50, "보통(30-50)", "김(50+)"))
SORT round(avg(rows.view_count)) DESC
```

---

## 🧠 Obsidian 플러그인 추천

실제로 더 강력한 분석을 위해 설치 권장:

1. **Dataview** ✅ (이미 사용 중)
2. **Templater** - 동적 템플릿
3. **Graph Analysis** - 네트워크 분석  
4. **Tag Wrangler** - 태그 관리
5. **Advanced Tables** - 테이블 편집
6. **Text Generator** - AI 요약
7. **Canvas** - 시각적 맵핑
8. **Excalidraw** - 다이어그램 작성
