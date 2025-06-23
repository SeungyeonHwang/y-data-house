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
