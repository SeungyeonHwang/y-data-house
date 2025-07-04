# 🤖 Y-Data-House AI 질문 기능 고도화 개발 요청서

## 🎯 핵심 가치 제안: **완전 자동화된 AI 어시스턴트**

### 💡 **프롬프트 작성 불필요 시스템**
사용자가 수동으로 프롬프트를 작성할 필요가 **전혀 없는** 완전 자동화된 AI 질문 시스템 구축이 목표입니다.

#### 🔄 **워크플로우**
1. **벡터 임베딩 생성** (기존) → `make embed`
2. **자동 프롬프트 생성** (1회) → `python auto_prompt.py batch`
3. **즉시 사용** → 채널 선택 후 바로 AI 질문
4. **지속 활용** → 한 번 생성된 프롬프트로 계속 사용

#### 🎨 **자동 생성되는 요소들**
- **페르소나**: "10년차 일본 부동산 투자 전문가"
- **톤 & 스타일**: "친근하지만 전문적이고, 구체적 수치 중시"
- **답변 규칙**: "실제 경험과 사례 중심으로 설명"
- **출력 형식**: "🚀 요약 → 📊 데이터 → 📚 근거 → 📝 실행단계"

## 📋 프로젝트 개요
Y-Data-House는 YouTube 비디오 다운로더와 전사 시스템으로, 현재 **기본적인 DeepSeek RAG 시스템**이 구현되어 있습니다. 이를 **완전 자동화된 채널별 맞춤형 AI 어시스턴트**로 발전시켜, 사용자가 프롬프트 작성 없이도 각 채널의 특성에 맞는 전문적인 답변을 받을 수 있도록 하는 것이 목표입니다.

## 🎯 현재 상태 분석

### ✅ 이미 구현된 기능
1. **벡터 DB 구축 완료**: ChromaDB 기반 채널별 격리 임베딩
2. **기본 RAG 시스템**: `vault/90_indices/rag.py`에 HyDE + Query Rewriting 구현
3. **Tauri 백엔드**: `ask_rag` 함수로 Python 스크립트 호출
4. **React 프론트엔드**: 간단한 질문-답변 UI 구현
5. **채널별 데이터 관리**: 채널명으로 컬렉션 분리 저장

### 🚨 현재 문제점 및 개선 필요사항
1. **수동 프롬프트 작성**: 사용자가 직접 프롬프트를 작성해야 함 ❌
2. **채널 특성 무시**: 모든 채널에 동일한 일반적 프롬프트 사용 ❌
3. **단순한 질문-답변**: 채널 선택 없이 전체 통합 검색만 가능 ❌
4. **UI 제약**: 영상 링크 클릭, 타임스탬프 이동 등 인터랙션 부족 ❌

### ✅ **목표: Zero Manual Prompt Writing**
- **벡터 데이터 자동 분석** → 채널 특성 파악
- **AI 페르소나 자동 생성** → 전문가 캐릭터 설정
- **프롬프트 자동 작성** → 사용자 개입 불필요
- **1회 생성 후 지속 사용** → 계속 활용 가능

## 🎨 요구사항 명세

### 1. 채널별 프롬프트 시스템 구축 (파일 기반)

#### 1.1 프롬프트 파일 구조
```
vault/90_indices/prompts/
├── takaki_takehana/
│   ├── prompt_v1.json
│   ├── prompt_v2.json
│   └── active.txt          # 현재 활성 버전 번호
├── 도쿄부동산/
│   ├── prompt_v1.json
│   └── active.txt
└── default/
    └── prompt_v1.json      # 기본 프롬프트
```

#### 1.2 프롬프트 JSON 구조
```json
{
  "version": 1,
  "channel_name": "takaki_takehana",
  "created_at": "2024-01-15T10:30:00Z",
  "persona": "10년차 일본 부동산 투자 전문가이며 실전 경험이 풍부한 컨설턴트",
  "tone": "친근하지만 전문적이고, 구체적 수치와 사례를 중시하는 스타일",
  "system_prompt": "당신은 {{channel_name}} 채널을 대표하는 일본 부동산 투자 전문 AI입니다. 이 채널의 정보만을 활용하여 실용적이고 구체적인 조언을 제공하세요.",
  "rules": [
    "반드시 이 채널의 정보만 활용하여 답변",
    "모르는 내용은 추측 금지, '정보 부족' 명시",
    "답변 구조: BLUF → 근거 → 실행단계"
  ],
  "output_format": {
    "structure": "🚀 핵심 요약 → 📚 근거/출처 → 📝 실행 단계 → 💡 한줄 요약",
    "max_bullets": 5,
    "include_video_links": true
  },
  "examples": [
    {
      "question": "도쿄 원룸 투자 수익률은?",
      "expected_approach": "이 채널의 실제 사례 → 지역별 비교 → 위험요소 → 실행 가이드"
    }
  ]
}
```

### 2. 고도화된 RAG 파이프라인

#### 2.1 채널별 벡터 분석 및 자동 프롬프트 생성 (`vault/90_indices/channel_analyzer.py`)
```python
import chromadb
from collections import Counter
import re
from typing import Dict, List, Tuple

class ChannelAnalyzer:
    def __init__(self, chroma_path: Path):
        self.client = chromadb.PersistentClient(path=str(chroma_path))
    
    def analyze_channel_content(self, channel_name: str) -> Dict:
        """채널 벡터 데이터 분석하여 특성 추출"""
        collection_name = f"channel_{self._sanitize_name(channel_name)}"
        
        try:
            collection = self.client.get_collection(collection_name)
            data = collection.get(include=['documents', 'metadatas'])
            
            if not data['documents']:
                return {}
            
            # 1. 주요 키워드 추출
            keywords = self._extract_keywords(data['documents'])
            
            # 2. 콘텐츠 패턴 분석
            patterns = self._analyze_content_patterns(data['documents'])
            
            # 3. 채널 메타데이터 분석
            metadata_insights = self._analyze_metadata(data['metadatas'])
            
            # 4. 톤 & 스타일 분석
            tone_analysis = self._analyze_tone(data['documents'])
            
            return {
                'channel_name': channel_name,
                'keywords': keywords,
                'content_patterns': patterns,
                'metadata_insights': metadata_insights,
                'tone_analysis': tone_analysis,
                'total_videos': len(data['documents']),
                'analysis_timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            print(f"⚠️ 채널 분석 실패: {e}")
            return {}
    
    def _extract_keywords(self, documents: List[str]) -> Dict[str, int]:
        """문서에서 주요 키워드 추출"""
        all_text = ' '.join(documents)
        
        # 한글, 영문, 숫자 키워드 추출
        korean_keywords = re.findall(r'[가-힣]{2,}', all_text)
        english_keywords = re.findall(r'[A-Za-z]{3,}', all_text.lower())
        number_patterns = re.findall(r'\d+[년월일%억만원평]', all_text)
        
        # 빈도 계산
        keyword_counts = Counter(korean_keywords + english_keywords + number_patterns)
        
        # 상위 30개 키워드 반환
        return dict(keyword_counts.most_common(30))
    
    def _analyze_content_patterns(self, documents: List[str]) -> Dict:
        """콘텐츠 패턴 분석"""
        patterns = {
            'investment_terms': 0,
            'location_mentions': 0,
            'numerical_data': 0,
            'experience_sharing': 0,
            'analysis_depth': 'medium'
        }
        
        for doc in documents:
            # 투자 관련 용어
            investment_terms = ['투자', '수익률', '매매', '임대', '자산', '포트폴리오']
            patterns['investment_terms'] += sum(doc.count(term) for term in investment_terms)
            
            # 지역 언급
            locations = ['도쿄', '오사카', '교토', '요코하마', '시부야', '신주쿠']
            patterns['location_mentions'] += sum(doc.count(loc) for loc in locations)
            
            # 수치 데이터
            patterns['numerical_data'] += len(re.findall(r'\d+[%억만원평년]', doc))
            
            # 경험 공유 표현
            experience_words = ['경험', '실제로', '직접', '해보니', '느낀점']
            patterns['experience_sharing'] += sum(doc.count(word) for word in experience_words)
        
        # 분석 깊이 판단
        if patterns['numerical_data'] > 100 and patterns['investment_terms'] > 50:
            patterns['analysis_depth'] = 'deep'
        elif patterns['numerical_data'] < 20:
            patterns['analysis_depth'] = 'light'
        
        return patterns
    
    def _analyze_metadata(self, metadatas: List[Dict]) -> Dict:
        """메타데이터 분석"""
        insights = {
            'avg_video_length': 0,
            'upload_frequency': 'unknown',
            'popular_topics': [],
            'recent_trends': []
        }
        
        # 비디오 길이 평균
        durations = [m.get('duration_seconds', 0) for m in metadatas if m.get('duration_seconds')]
        if durations:
            insights['avg_video_length'] = sum(durations) / len(durations)
        
        # 인기 토픽
        all_topics = []
        for m in metadatas:
            if m.get('topic'):
                all_topics.extend(m['topic'])
        
        topic_counts = Counter(all_topics)
        insights['popular_topics'] = [topic for topic, _ in topic_counts.most_common(5)]
        
        return insights
    
    def _analyze_tone(self, documents: List[str]) -> Dict:
        """톤 & 스타일 분석"""
        tone_indicators = {
            'formal': ['습니다', '됩니다', '있습니다', '것입니다'],
            'casual': ['해요', '이에요', '거예요', '네요'],
            'expert': ['분석', '데이터', '지표', '전문적'],
            'practical': ['실제', '직접', '경험', '팁', '방법']
        }
        
        tone_scores = {tone: 0 for tone in tone_indicators.keys()}
        
        for doc in documents:
            for tone, indicators in tone_indicators.items():
                tone_scores[tone] += sum(doc.count(indicator) for indicator in indicators)
        
        # 주요 톤 결정
        primary_tone = max(tone_scores, key=tone_scores.get)
        
        return {
            'primary_tone': primary_tone,
            'tone_scores': tone_scores,
            'style_description': self._generate_style_description(primary_tone, tone_scores)
        }
    
    def _generate_style_description(self, primary_tone: str, tone_scores: Dict) -> str:
        """스타일 설명 생성"""
        style_map = {
            'formal': '정중하고 전문적인 어투',
            'casual': '친근하고 편안한 대화체',
            'expert': '분석적이고 데이터 중심적인 스타일',
            'practical': '실용적이고 경험 중심적인 접근'
        }
        
        return style_map.get(primary_tone, '균형잡힌 스타일')
    
    def generate_auto_prompt(self, channel_analysis: Dict) -> Dict:
        """채널 분석 결과를 바탕으로 자동 프롬프트 생성"""
        if not channel_analysis:
            return self._get_default_prompt()
        
        channel_name = channel_analysis['channel_name']
        keywords = list(channel_analysis.get('keywords', {}).keys())[:10]
        patterns = channel_analysis.get('content_patterns', {})
        tone_analysis = channel_analysis.get('tone_analysis', {})
        
        # 페르소나 생성
        persona = self._generate_persona(patterns, tone_analysis)
        
        # 전문 분야 결정
        expertise = self._determine_expertise(keywords, patterns)
        
        # 시스템 프롬프트 생성
        system_prompt = f"""당신은 {channel_name} 채널을 대표하는 {expertise} 전문 AI 어시스턴트입니다.

이 채널의 특징:
- 주요 키워드: {', '.join(keywords[:5])}
- 콘텐츠 스타일: {tone_analysis.get('style_description', '전문적')}
- 분석 깊이: {patterns.get('analysis_depth', 'medium')}

당신의 역할은 이 채널의 영상 내용만을 바탕으로 사용자에게 정확하고 실용적인 조언을 제공하는 것입니다."""

        # 답변 규칙 생성
        rules = self._generate_rules(patterns, tone_analysis)
        
        # 출력 형식 결정
        output_format = self._determine_output_format(patterns)
        
        return {
            "version": 1,
            "channel_name": channel_name,
            "created_at": datetime.now().isoformat(),
            "auto_generated": True,
            "persona": persona,
            "tone": tone_analysis.get('style_description', '전문적이고 실용적인 스타일'),
            "system_prompt": system_prompt,
            "rules": rules,
            "output_format": output_format,
            "expertise_keywords": keywords[:10],
            "analysis_metadata": {
                "total_videos": channel_analysis.get('total_videos', 0),
                "analysis_timestamp": channel_analysis.get('analysis_timestamp')
            }
        }
    
    def _generate_persona(self, patterns: Dict, tone_analysis: Dict) -> str:
        """패턴 분석을 바탕으로 페르소나 생성"""
        base_persona = "전문 컨텐츠 분석가"
        
        if patterns.get('investment_terms', 0) > 30:
            base_persona = "투자 전문가"
        
        if patterns.get('experience_sharing', 0) > 20:
            base_persona += "이며 실전 경험이 풍부한 컨설턴트"
        
        if patterns.get('analysis_depth') == 'deep':
            base_persona += "이며 데이터 기반 분석을 중시하는 전문가"
        
        return base_persona
    
    def _determine_expertise(self, keywords: List[str], patterns: Dict) -> str:
        """키워드와 패턴을 바탕으로 전문 분야 결정"""
        if any(keyword in ['부동산', '투자', '매매', '임대'] for keyword in keywords):
            return "부동산 투자"
        elif any(keyword in ['주식', '펀드', '자산'] for keyword in keywords):
            return "자산 관리"
        elif any(keyword in ['여행', '맛집', '문화'] for keyword in keywords):
            return "라이프스타일"
        else:
            return "종합 정보"
    
    def _generate_rules(self, patterns: Dict, tone_analysis: Dict) -> List[str]:
        """패턴에 따른 답변 규칙 생성"""
        rules = [
            "반드시 이 채널의 정보만 활용하여 답변",
            "모르는 내용은 추측 금지, '정보 부족' 명시"
        ]
        
        if patterns.get('numerical_data', 0) > 50:
            rules.append("구체적인 수치와 데이터를 포함하여 답변")
        
        if patterns.get('experience_sharing', 0) > 15:
            rules.append("실제 경험과 사례를 중심으로 설명")
        
        if tone_analysis.get('primary_tone') == 'practical':
            rules.append("실행 가능한 구체적 단계 제시")
        
        rules.append("답변 구조: 핵심 요약 → 근거 → 실행 단계")
        
        return rules
    
    def _determine_output_format(self, patterns: Dict) -> Dict:
        """패턴에 따른 출력 형식 결정"""
        if patterns.get('analysis_depth') == 'deep':
            return {
                "structure": "🚀 핵심 요약 → 📊 데이터 분석 → 📚 근거/출처 → 📝 실행 단계 → 💡 한줄 요약",
                "max_bullets": 7,
                "include_video_links": True
            }
        elif patterns.get('experience_sharing', 0) > 20:
            return {
                "structure": "🚀 핵심 요약 → 💼 실제 경험 → 📚 근거/출처 → 📝 실행 가이드 → 💡 한줄 요약",
                "max_bullets": 5,
                "include_video_links": True
            }
        else:
            return {
                "structure": "🚀 핵심 요약 → 📚 근거/출처 → 📝 실행 단계 → 💡 한줄 요약",
                "max_bullets": 5,
                "include_video_links": True
            }
    
    def _sanitize_name(self, name: str) -> str:
        """채널명 정리"""
        return re.sub(r'[^\w가-힣]', '_', name)[:50]
    
    def _get_default_prompt(self) -> Dict:
        """기본 프롬프트 반환"""
        return {
            "persona": "YouTube 비디오 내용 전문 분석가",
            "tone": "친근하고 도움이 되는 스타일",
            "system_prompt": "사용자의 질문에 대해 비디오 내용을 바탕으로 정확하고 유용한 답변을 제공하세요.",
            "rules": ["비디오 내용 기반 답변", "정확한 정보 제공", "친절한 톤 유지"],
            "output_format": {
                "structure": "답변 → 근거 → 요약",
                "max_bullets": 3,
                "include_video_links": False
            }
        }
```

#### 2.2 채널별 프롬프트 로더 (`vault/90_indices/prompt_manager.py`)
```python
import json
from pathlib import Path
from typing import Dict, Optional

class PromptManager:
    def __init__(self, prompts_dir: Path = None, chroma_path: Path = None):
        self.prompts_dir = prompts_dir or Path(__file__).parent / "prompts"
        self.prompts_dir.mkdir(exist_ok=True)
        self.analyzer = ChannelAnalyzer(chroma_path or Path(__file__).parent / "chroma")
    
    def get_channel_prompt(self, channel_name: str) -> Dict:
        """채널별 활성 프롬프트 로드"""
        channel_dir = self.prompts_dir / channel_name
        if not channel_dir.exists():
            return self._get_default_prompt()
        
        # 활성 버전 확인
        active_file = channel_dir / "active.txt"
        if active_file.exists():
            version = int(active_file.read_text().strip())
        else:
            version = 1
        
        # 프롬프트 파일 로드
        prompt_file = channel_dir / f"prompt_v{version}.json"
        if prompt_file.exists():
            return json.loads(prompt_file.read_text(encoding='utf-8'))
        
        return self._get_default_prompt()
    
    def save_channel_prompt(self, channel_name: str, prompt_data: Dict) -> int:
        """새 프롬프트 버전 저장"""
        channel_dir = self.prompts_dir / channel_name
        channel_dir.mkdir(exist_ok=True)
        
        # 새 버전 번호 계산
        existing_versions = [
            int(f.stem.split('_v')[1]) 
            for f in channel_dir.glob("prompt_v*.json")
        ]
        new_version = max(existing_versions, default=0) + 1
        
        # 프롬프트 저장
        prompt_data['version'] = new_version
        prompt_data['channel_name'] = channel_name
        prompt_data['created_at'] = datetime.now().isoformat()
        
        prompt_file = channel_dir / f"prompt_v{new_version}.json"
        prompt_file.write_text(
            json.dumps(prompt_data, ensure_ascii=False, indent=2),
            encoding='utf-8'
        )
        
        # 활성 버전 업데이트
        active_file = channel_dir / "active.txt"
        active_file.write_text(str(new_version))
        
        return new_version
    
    def auto_generate_channel_prompt(self, channel_name: str) -> int:
        """채널 벡터 데이터를 분석하여 자동으로 프롬프트 생성"""
        print(f"🔍 {channel_name} 채널 벡터 데이터 분석 중...")
        
        # 1. 채널 벡터 데이터 분석
        channel_analysis = self.analyzer.analyze_channel_content(channel_name)
        if not channel_analysis:
            print(f"❌ {channel_name} 채널의 벡터 데이터를 찾을 수 없습니다.")
            return 0
        
        print(f"📊 분석 완료: {channel_analysis['total_videos']}개 영상 분석")
        print(f"🔑 주요 키워드: {', '.join(list(channel_analysis['keywords'].keys())[:5])}")
        
        # 2. 자동 프롬프트 생성
        auto_prompt = self.analyzer.generate_auto_prompt(channel_analysis)
        
        # 3. 프롬프트 저장
        new_version = self.save_channel_prompt(channel_name, auto_prompt)
        
        print(f"✅ {channel_name} 채널 자동 프롬프트 v{new_version} 생성 완료!")
        print(f"📝 페르소나: {auto_prompt['persona']}")
        print(f"🎯 전문분야: {auto_prompt.get('expertise_keywords', [])[:3]}")
        
        return new_version
    
    def get_channel_analysis(self, channel_name: str) -> Dict:
        """채널 벡터 데이터 분석 결과 반환"""
        return self.analyzer.analyze_channel_content(channel_name)
    
    def list_available_channels_for_analysis(self) -> List[str]:
        """분석 가능한 채널 목록 반환"""
        try:
            collections = self.analyzer.client.list_collections()
            channels = []
            
            for collection in collections:
                if collection.name.startswith("channel_"):
                    try:
                        data = collection.get()
                        if data['metadatas'] and len(data['metadatas']) > 0:
                            channel_name = data['metadatas'][0].get('channel', 'Unknown')
                            if channel_name != 'Unknown':
                                channels.append(channel_name)
                    except Exception:
                        continue
            
            return sorted(list(set(channels)))
        except Exception as e:
            print(f"⚠️ 채널 목록 조회 실패: {e}")
            return []
    
    def batch_generate_prompts(self) -> Dict[str, int]:
        """모든 채널에 대해 자동 프롬프트 생성"""
        channels = self.list_available_channels_for_analysis()
        results = {}
        
        print(f"🚀 {len(channels)}개 채널에 대해 자동 프롬프트 생성 시작...")
        
        for channel in channels:
            try:
                version = self.auto_generate_channel_prompt(channel)
                results[channel] = version
                print(f"  ✅ {channel}: v{version}")
            except Exception as e:
                print(f"  ❌ {channel}: 실패 - {e}")
                results[channel] = 0
        
        print(f"🎉 자동 프롬프트 생성 완료: {len([v for v in results.values() if v > 0])}개 성공")
        return results
    
    def _get_default_prompt(self) -> Dict:
        """기본 프롬프트 반환"""
        return {
            "persona": "YouTube 비디오 내용 전문 분석가",
            "tone": "친근하고 도움이 되는 스타일",
            "system_prompt": "사용자의 질문에 대해 비디오 내용을 바탕으로 정확하고 유용한 답변을 제공하세요.",
            "rules": ["비디오 내용 기반 답변", "정확한 정보 제공", "친절한 톤 유지"],
            "output_format": {
                "structure": "답변 → 근거 → 요약",
                "max_bullets": 3,
                "include_video_links": false
            }
        }
```

#### 2.3 Multi-Stage Retrieval 강화 (`vault/90_indices/rag.py` 수정)
```python
class AdvancedChannelRAG(ChannelRAG):
    def __init__(self):
        super().__init__()
        self.prompt_manager = PromptManager()
    
    def enhanced_search(self, query: str, channel_name: str):
        """다단계 검색 시스템"""
        all_results = []
        
        # 1단계: 원본 질문
        results_1 = self.channel_search_basic(query, channel_name, n_results=3)
        if results_1:
            all_results.extend(self._format_results(results_1, "원본질문", channel_name))
        
        # 2단계: 채널 특화 HyDE
        channel_prompt = self.prompt_manager.get_channel_prompt(channel_name)
        hyde_doc = self.generate_channel_specific_hyde(query, channel_name, channel_prompt)
        if hyde_doc:
            results_2 = self.channel_search_basic(hyde_doc, channel_name, n_results=3)
            if results_2:
                all_results.extend(self._format_results(results_2, "채널특화HyDE", channel_name))
        
        # 3단계: Query Decomposition
        sub_queries = self.decompose_query(query, channel_name, channel_prompt)
        for i, sub_query in enumerate(sub_queries):
            results_3 = self.channel_search_basic(sub_query, channel_name, n_results=2)
            if results_3:
                all_results.extend(self._format_results(results_3, f"분해질문{i+1}", channel_name))
        
        # 중복 제거 및 LLM Re-ranking
        unique_results = self._deduplicate_results(all_results)
        if len(unique_results) > 5:
            filtered_results = self._llm_rerank_with_channel_context(
                query, unique_results[:8], channel_name, channel_prompt
            )
        else:
            filtered_results = unique_results
        
        return filtered_results[:5]
    
    def generate_channel_specific_hyde(self, query: str, channel_name: str, channel_prompt: Dict) -> str:
        """채널 특화 HyDE 문서 생성"""
        try:
            persona = channel_prompt.get('persona', '전문가')
            tone = channel_prompt.get('tone', '전문적인 스타일')
            
            prompt = f"""당신은 {channel_name} 채널의 {persona}입니다. 
{tone}로 다음 질문에 대한 완벽한 답변이 담긴 150토큰 내외의 가상 문서를 작성하세요.

질문: {query}

이 채널의 관점에서 구체적인 수치, 지역명, 전략이 포함된 답변을 작성해주세요."""

            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": f"당신은 {channel_name} 채널 전문가입니다."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=150,
                temperature=0.7
            )
            
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"⚠️ 채널 특화 HyDE 생성 실패: {e}")
            return None
    
    def generate_answer_with_channel_prompt(self, query: str, search_results: list, channel_name: str):
        """채널별 프롬프트를 활용한 답변 생성"""
        if not search_results:
            return f"죄송합니다. {channel_name} 채널에서 관련된 정보를 찾을 수 없습니다."
        
        # 채널별 프롬프트 로드
        channel_prompt = self.prompt_manager.get_channel_prompt(channel_name)
        
        # 컨텍스트 구성
        context_parts = []
        for i, result in enumerate(search_results):
            title = result['title']
            content_preview = result['content'][:600]
            context_parts.append(f"[영상 {i+1}] {title}\n{content_preview}")
        
        context = "\n\n".join(context_parts)
        
        # 채널별 맞춤 프롬프트 구성
        system_prompt = channel_prompt.get('system_prompt', '').replace('{{channel_name}}', channel_name)
        rules = "\n".join([f"- {rule}" for rule in channel_prompt.get('rules', [])])
        output_format = channel_prompt.get('output_format', {})
        structure = output_format.get('structure', '답변 → 근거 → 요약')
        
        final_prompt = f"""{system_prompt}

## 답변 규칙
{rules}

## 답변 구조
{structure}

## 검색된 컨텍스트 ({channel_name} 채널)
{context}

## 사용자 질문
{query}

위 규칙과 구조에 따라 {channel_name} 채널의 정보만을 바탕으로 답변해주세요."""

        try:
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": f"당신은 {channel_name} 채널 전문 AI 어시스턴트입니다."},
                    {"role": "user", "content": final_prompt}
                ],
                max_tokens=800,
                temperature=0.7
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            return f"답변 생성 중 오류가 발생했습니다: {e}"
```

### 3. 클릭형 인터랙티브 UI 개발

#### 3.1 채널 선택 UI (React 컴포넌트)
```typescript
// app/src/components/ChannelSelector.tsx
interface ChannelInfo {
  name: string;
  video_count: number;
  description?: string;
  last_updated?: string;
}

interface ChannelSelectorProps {
  onChannelSelect: (channel: string) => void;
  selectedChannel?: string;
}

const ChannelSelector: React.FC<ChannelSelectorProps> = ({ onChannelSelect, selectedChannel }) => {
  const [channels, setChannels] = useState<ChannelInfo[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadChannels();
  }, []);

  const loadChannels = async () => {
    try {
      const result = await invoke<ChannelInfo[]>('get_available_channels_for_ai');
      setChannels(result);
    } catch (err) {
      console.error('채널 목록 로드 실패:', err);
    } finally {
      setLoading(false);
    }
  };

  if (loading) return <div className="channel-loading">채널 목록 로딩 중...</div>;

  return (
    <div className="channel-selector">
      <h3 className="channel-selector-title">🎯 질문할 채널 선택</h3>
      <div className="channel-grid">
        {channels.map(channel => (
          <div 
            key={channel.name} 
            className={`channel-card ${selectedChannel === channel.name ? 'selected' : ''}`}
            onClick={() => onChannelSelect(channel.name)}
          >
            <div className="channel-name">{channel.name}</div>
            <div className="channel-stats">{channel.video_count}개 영상</div>
            {channel.description && (
              <div className="channel-description">{channel.description}</div>
            )}
            {channel.last_updated && (
              <div className="channel-updated">최근 업데이트: {channel.last_updated}</div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};
```

#### 3.2 AI 답변 컴포넌트 개선
```typescript
// app/src/components/AIAnswer.tsx
interface VideoSource {
  video_id: string;
  title: string;
  timestamp?: number;
  relevance_score: number;
  excerpt: string;
}

interface AIResponse {
  answer: string;
  sources: VideoSource[];
  channel_used: string;
  response_time: number;
}

const AIAnswerComponent: React.FC<{ response: AIResponse }> = ({ response }) => {
  const openVideoAtTimestamp = (videoId: string, timestamp?: number) => {
    const url = `https://youtube.com/watch?v=${videoId}${timestamp ? `&t=${timestamp}s` : ''}`;
    window.open(url, '_blank');
  };

  const formatTimestamp = (seconds?: number) => {
    if (!seconds) return '';
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
  };

  return (
    <div className="ai-response">
      <div className="response-header">
        <span className="channel-badge">📺 {response.channel_used}</span>
        <span className="response-time">⏱️ {response.response_time.toFixed(1)}초</span>
      </div>
      
      <div className="answer-content">
        <ReactMarkdown>{response.answer}</ReactMarkdown>
      </div>
      
      {response.sources.length > 0 && (
        <div className="sources-section">
          <h4 className="sources-title">📚 참고 영상</h4>
          <div className="sources-list">
            {response.sources.map((source, i) => (
              <div 
                key={i} 
                className="source-item"
                onClick={() => openVideoAtTimestamp(source.video_id, source.timestamp)}
              >
                <div className="source-main">
                  <span className="source-title">{source.title}</span>
                  <span className="source-relevance">{(source.relevance_score * 100).toFixed(1)}% 관련</span>
                </div>
                <div className="source-details">
                  {source.timestamp && (
                    <span className="source-timestamp">🕐 {formatTimestamp(source.timestamp)}</span>
                  )}
                  <span className="source-excerpt">{source.excerpt.slice(0, 100)}...</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
```

### 4. 프롬프트 관리 시스템

#### 4.1 프롬프트 편집 UI (새 탭 추가)
```typescript
// app/src/components/PromptManager.tsx
const PromptManagerTab: React.FC = () => {
  const [selectedChannel, setSelectedChannel] = useState<string>('');
  const [currentPrompt, setCurrentPrompt] = useState<any>(null);
  const [promptVersions, setPromptVersions] = useState<any[]>([]);
  const [isEditing, setIsEditing] = useState(false);

  const loadChannelPrompt = async (channelName: string) => {
    try {
      const prompt = await invoke<any>('get_channel_prompt', { channelName });
      const versions = await invoke<any[]>('get_prompt_versions', { channelName });
      setCurrentPrompt(prompt);
      setPromptVersions(versions);
      setSelectedChannel(channelName);
    } catch (err) {
      console.error('프롬프트 로드 실패:', err);
    }
  };

  const savePrompt = async () => {
    if (!selectedChannel || !currentPrompt) return;
    
    try {
      const newVersion = await invoke<number>('save_channel_prompt', {
        channelName: selectedChannel,
        promptData: currentPrompt
      });
      alert(`새 버전 v${newVersion}이 저장되었습니다.`);
      loadChannelPrompt(selectedChannel); // 새로고침
    } catch (err) {
      alert(`저장 실패: ${err}`);
    }
  };

  return (
    <div className="prompt-management">
      <div className="prompt-header">
        <h2 className="tab-title">📝 프롬프트 관리</h2>
        <ChannelSelector onChannelSelect={loadChannelPrompt} selectedChannel={selectedChannel} />
      </div>

      {currentPrompt && (
        <div className="prompt-editor-container">
          <div className="prompt-editor">
            <h3>✏️ 프롬프트 편집</h3>
            
            <div className="form-group">
              <label>페르소나:</label>
              <input
                type="text"
                value={currentPrompt.persona || ''}
                onChange={(e) => setCurrentPrompt({...currentPrompt, persona: e.target.value})}
                placeholder="예: 10년차 부동산 투자 전문가"
              />
            </div>

            <div className="form-group">
              <label>톤 & 스타일:</label>
              <input
                type="text"
                value={currentPrompt.tone || ''}
                onChange={(e) => setCurrentPrompt({...currentPrompt, tone: e.target.value})}
                placeholder="예: 친근하지만 전문적인 스타일"
              />
            </div>

            <div className="form-group">
              <label>시스템 프롬프트:</label>
              <textarea
                rows={8}
                value={currentPrompt.system_prompt || ''}
                onChange={(e) => setCurrentPrompt({...currentPrompt, system_prompt: e.target.value})}
                placeholder="AI의 역할과 행동 방식을 정의하세요..."
              />
            </div>

            <div className="form-group">
              <label>답변 규칙:</label>
              <textarea
                rows={4}
                value={currentPrompt.rules?.join('\n') || ''}
                onChange={(e) => setCurrentPrompt({
                  ...currentPrompt, 
                  rules: e.target.value.split('\n').filter(r => r.trim())
                })}
                placeholder="각 줄에 하나씩 규칙을 입력하세요..."
              />
            </div>

            <div className="prompt-actions">
              <button onClick={savePrompt} className="save-button">
                💾 새 버전 저장
              </button>
              <button onClick={() => setIsEditing(!isEditing)} className="edit-button">
                {isEditing ? '📖 미리보기' : '✏️ 편집 모드'}
              </button>
            </div>
          </div>

          <div className="prompt-versions">
            <h3>📚 버전 히스토리</h3>
            <div className="versions-list">
              {promptVersions.map(version => (
                <div key={version.version} className="version-item">
                  <div className="version-header">
                    <span className="version-number">v{version.version}</span>
                    <span className="version-date">{new Date(version.created_at).toLocaleDateString()}</span>
                  </div>
                  <div className="version-preview">
                    {version.persona.slice(0, 50)}...
                  </div>
                  <button 
                    onClick={() => setCurrentPrompt(version)}
                    className="restore-button"
                  >
                    🔄 이 버전으로 복원
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
```

### 5. 자동 프롬프트 생성 CLI 도구

#### 5.1 CLI 명령어 추가 (`vault/90_indices/auto_prompt.py`)
```python
#!/usr/bin/env python3
"""
채널별 자동 프롬프트 생성 CLI 도구
"""
import sys
from pathlib import Path
from prompt_manager import PromptManager

def main():
    if len(sys.argv) < 2:
        print("🤖 Y-Data House 자동 프롬프트 생성기")
        print("\n📋 사용법:")
        print("  python auto_prompt.py list                    # 분석 가능한 채널 목록")
        print("  python auto_prompt.py analyze <채널명>        # 특정 채널 분석")
        print("  python auto_prompt.py generate <채널명>       # 특정 채널 프롬프트 생성")
        print("  python auto_prompt.py batch                   # 모든 채널 프롬프트 생성")
        return
    
    command = sys.argv[1]
    prompt_manager = PromptManager()
    
    if command == "list":
        # 분석 가능한 채널 목록
        channels = prompt_manager.list_available_channels_for_analysis()
        if channels:
            print(f"📺 분석 가능한 채널 ({len(channels)}개):")
            for i, channel in enumerate(channels, 1):
                print(f"  {i}. {channel}")
        else:
            print("분석 가능한 채널이 없습니다. 먼저 벡터 임베딩을 생성하세요.")
    
    elif command == "analyze":
        if len(sys.argv) < 3:
            print("❌ 채널명이 필요합니다.")
            print("사용법: python auto_prompt.py analyze <채널명>")
            return
        
        channel_name = sys.argv[2]
        analysis = prompt_manager.get_channel_analysis(channel_name)
        
        if analysis:
            print(f"📊 {channel_name} 채널 분석 결과:")
            print(f"  📹 총 영상 수: {analysis['total_videos']}")
            print(f"  🔑 주요 키워드: {', '.join(list(analysis['keywords'].keys())[:10])}")
            print(f"  🎭 주요 톤: {analysis['tone_analysis']['primary_tone']}")
            print(f"  📈 분석 깊이: {analysis['content_patterns']['analysis_depth']}")
            print(f"  💼 투자 용어 빈도: {analysis['content_patterns']['investment_terms']}")
            print(f"  📍 지역 언급 빈도: {analysis['content_patterns']['location_mentions']}")
        else:
            print(f"❌ {channel_name} 채널을 찾을 수 없습니다.")
    
    elif command == "generate":
        if len(sys.argv) < 3:
            print("❌ 채널명이 필요합니다.")
            print("사용법: python auto_prompt.py generate <채널명>")
            return
        
        channel_name = sys.argv[2]
        version = prompt_manager.auto_generate_channel_prompt(channel_name)
        
        if version > 0:
            print(f"✅ {channel_name} 채널 자동 프롬프트 v{version} 생성 완료!")
        else:
            print(f"❌ {channel_name} 채널 프롬프트 생성 실패")
    
    elif command == "batch":
        # 모든 채널 일괄 생성
        results = prompt_manager.batch_generate_prompts()
        
        success_count = len([v for v in results.values() if v > 0])
        total_count = len(results)
        
        print(f"\n🎉 일괄 생성 완료: {success_count}/{total_count} 성공")
        
        if success_count < total_count:
            failed_channels = [ch for ch, v in results.items() if v == 0]
            print(f"❌ 실패한 채널: {', '.join(failed_channels)}")
    
    else:
        print(f"❌ 알 수 없는 명령어: {command}")
        print("사용 가능한 명령어: list, analyze, generate, batch")

if __name__ == "__main__":
    main()
```

### 6. Rust 백엔드 API 확장

#### 6.1 새로운 Tauri 명령어 추가 (`app/src-tauri/src/main.rs`)
```rust
// 채널별 AI 질문 (채널 선택 포함)
#[command]
async fn ask_ai_with_channel(query: String, channel_name: String) -> Result<String, String> {
    let project_root = get_project_root();
    let rag_script = project_root.join("vault").join("90_indices").join("rag.py");
    
    if !rag_script.exists() {
        return Err("RAG 스크립트를 찾을 수 없습니다".to_string());
    }
    
    let venv_python = project_root.join("venv").join("bin").join("python");
    let output = Command::new(&venv_python)
        .args(&[rag_script.to_str().unwrap(), &query, &channel_name])
        .current_dir(&project_root)
        .env("PYTHONUNBUFFERED", "1")
        .output()
        .map_err(|e| e.to_string())?;
    
    if output.status.success() {
        Ok(String::from_utf8_lossy(&output.stdout).to_string())
    } else {
        let stderr = String::from_utf8_lossy(&output.stderr);
        Err(format!("AI 질문 실패: {}", stderr))
    }
}

// AI용 채널 목록 조회
#[command]
async fn get_available_channels_for_ai() -> Result<Vec<ChannelInfo>, String> {
    let project_root = get_project_root();
    let chroma_path = project_root.join("vault").join("90_indices").join("chroma");
    
    if !chroma_path.exists() {
        return Ok(vec![]);
    }
    
    // Python 스크립트로 채널 목록 조회
    let rag_script = project_root.join("vault").join("90_indices").join("rag.py");
    let venv_python = project_root.join("venv").join("bin").join("python");
    
    let output = Command::new(&venv_python)
        .args(&[rag_script.to_str().unwrap(), "channels"])
        .current_dir(&project_root)
        .output()
        .map_err(|e| e.to_string())?;
    
    if output.status.success() {
        let stdout = String::from_utf8_lossy(&output.stdout);
        // 파싱 로직 구현 필요
        Ok(parse_channel_list(&stdout))
    } else {
        Err("채널 목록 조회 실패".to_string())
    }
}

// 채널별 프롬프트 조회
#[command]
async fn get_channel_prompt(channel_name: String) -> Result<String, String> {
    let project_root = get_project_root();
    let prompts_dir = project_root.join("vault").join("90_indices").join("prompts");
    let channel_dir = prompts_dir.join(&channel_name);
    
    if !channel_dir.exists() {
        return Ok("{}".to_string()); // 기본 프롬프트 반환
    }
    
    // 활성 버전 확인
    let active_file = channel_dir.join("active.txt");
    let version = if active_file.exists() {
        std::fs::read_to_string(&active_file)
            .map_err(|e| e.to_string())?
            .trim()
            .parse::<u32>()
            .unwrap_or(1)
    } else {
        1
    };
    
    // 프롬프트 파일 읽기
    let prompt_file = channel_dir.join(format!("prompt_v{}.json", version));
    if prompt_file.exists() {
        std::fs::read_to_string(&prompt_file).map_err(|e| e.to_string())
    } else {
        Ok("{}".to_string())
    }
}

// 채널별 자동 프롬프트 생성
#[command]
async fn auto_generate_channel_prompt(channel_name: String) -> Result<u32, String> {
    let project_root = get_project_root();
    let auto_prompt_script = project_root.join("vault").join("90_indices").join("auto_prompt.py");
    
    if !auto_prompt_script.exists() {
        return Err("자동 프롬프트 생성 스크립트를 찾을 수 없습니다".to_string());
    }
    
    let venv_python = project_root.join("venv").join("bin").join("python");
    let output = Command::new(&venv_python)
        .args(&[auto_prompt_script.to_str().unwrap(), "generate", &channel_name])
        .current_dir(&project_root)
        .output()
        .map_err(|e| e.to_string())?;
    
    if output.status.success() {
        let stdout = String::from_utf8_lossy(&output.stdout);
        // 버전 번호 추출 (예: "v3 생성 완료" -> 3)
        if let Some(version_match) = stdout.find("v") {
            if let Some(space_pos) = stdout[version_match..].find(" ") {
                let version_str = &stdout[version_match + 1..version_match + space_pos];
                if let Ok(version) = version_str.parse::<u32>() {
                    return Ok(version);
                }
            }
        }
        Ok(1) // 기본값
    } else {
        let stderr = String::from_utf8_lossy(&output.stderr);
        Err(format!("자동 프롬프트 생성 실패: {}", stderr))
    }
}

// 채널 분석 결과 조회
#[command]
async fn get_channel_analysis(channel_name: String) -> Result<String, String> {
    let project_root = get_project_root();
    let auto_prompt_script = project_root.join("vault").join("90_indices").join("auto_prompt.py");
    
    let venv_python = project_root.join("venv").join("bin").join("python");
    let output = Command::new(&venv_python)
        .args(&[auto_prompt_script.to_str().unwrap(), "analyze", &channel_name])
        .current_dir(&project_root)
        .output()
        .map_err(|e| e.to_string())?;
    
    if output.status.success() {
        Ok(String::from_utf8_lossy(&output.stdout).to_string())
    } else {
        let stderr = String::from_utf8_lossy(&output.stderr);
        Err(format!("채널 분석 실패: {}", stderr))
    }
}

// 모든 채널 자동 프롬프트 일괄 생성
#[command]
async fn batch_generate_prompts() -> Result<String, String> {
    let project_root = get_project_root();
    let auto_prompt_script = project_root.join("vault").join("90_indices").join("auto_prompt.py");
    
    let venv_python = project_root.join("venv").join("bin").join("python");
    let output = Command::new(&venv_python)
        .args(&[auto_prompt_script.to_str().unwrap(), "batch"])
        .current_dir(&project_root)
        .output()
        .map_err(|e| e.to_string())?;
    
    if output.status.success() {
        Ok(String::from_utf8_lossy(&output.stdout).to_string())
    } else {
        let stderr = String::from_utf8_lossy(&output.stderr);
        Err(format!("일괄 프롬프트 생성 실패: {}", stderr))
    }
}

// 채널별 프롬프트 저장
#[command]
async fn save_channel_prompt(channel_name: String, prompt_data: String) -> Result<u32, String> {
    let project_root = get_project_root();
    let prompts_dir = project_root.join("vault").join("90_indices").join("prompts");
    let channel_dir = prompts_dir.join(&channel_name);
    
    // 디렉토리 생성
    std::fs::create_dir_all(&channel_dir).map_err(|e| e.to_string())?;
    
    // 기존 버전 확인
    let existing_versions: Vec<u32> = std::fs::read_dir(&channel_dir)
        .map_err(|e| e.to_string())?
        .filter_map(|entry| {
            let entry = entry.ok()?;
            let filename = entry.file_name().to_string_lossy().to_string();
            if filename.starts_with("prompt_v") && filename.ends_with(".json") {
                let version_str = filename.strip_prefix("prompt_v")?.strip_suffix(".json")?;
                version_str.parse().ok()
            } else {
                None
            }
        })
        .collect();
    
    let new_version = existing_versions.iter().max().unwrap_or(&0) + 1;
    
    // 새 프롬프트 파일 저장
    let prompt_file = channel_dir.join(format!("prompt_v{}.json", new_version));
    std::fs::write(&prompt_file, &prompt_data).map_err(|e| e.to_string())?;
    
    // 활성 버전 업데이트
    let active_file = channel_dir.join("active.txt");
    std::fs::write(&active_file, new_version.to_string()).map_err(|e| e.to_string())?;
    
    Ok(new_version)
}
```

## 🏗️ 구현 로드맵

### Phase 1: 기반 시스템 구축 (1주)
1. **채널별 벡터 분석 시스템**
   - `vault/90_indices/channel_analyzer.py` 구현
   - 벡터 데이터에서 키워드, 톤, 패턴 자동 추출
   - 채널 특성 기반 페르소나 자동 생성

2. **파일 기반 프롬프트 시스템**
   - `vault/90_indices/prompt_manager.py` 생성
   - 채널별 프롬프트 CRUD 기능
   - 자동 프롬프트 생성 기능
   - 버전 관리 시스템

3. **자동 프롬프트 생성 CLI**
   - `vault/90_indices/auto_prompt.py` 구현
   - 채널 분석 및 프롬프트 자동 생성
   - 일괄 처리 기능

4. **채널 선택 UI 개발**
   - React 컴포넌트 추가
   - Tauri 백엔드 API 확장

### Phase 2: 고도화 RAG 구현 (1-2주)
1. **Multi-Stage Retrieval**
   - 채널 특화 HyDE 구현
   - Query Decomposition 구현
   - LLM Re-ranking 강화

2. **프롬프트 시스템 통합**
   - 채널별 맞춤 답변 생성
   - 동적 프롬프트 로딩

### Phase 3: 인터랙티브 UI (1주)
1. **클릭형 영상 링크**
   - YouTube 타임스탬프 링크
   - 미리보기 카드
   - 관련도 점수 표시

2. **프롬프트 관리 UI**
   - 편집기 구현
   - 버전 히스토리 표시

## 🎯 성공 기준

### ✅ 기능적 요구사항
1. **채널별 맞춤 답변**: 각 채널의 특성을 반영한 전문적 답변 제공
2. **인터랙티브 소스**: 클릭으로 YouTube 원본 영상 즉시 접근
3. **프롬프트 관리**: 실시간 편집, 버전 관리 가능
4. **성능**: 질문 → 답변 5초 이내

### 📊 품질 지표
1. **정확도**: 채널별 특성이 반영된 전문적 답변
2. **속도**: 평균 응답 시간 3초 이하
3. **사용성**: 채널 전환 및 질문 입력 원클릭
4. **유지보수성**: 새 채널 추가 및 프롬프트 편집 용이

## 🔧 기술 스택

### 백엔드 확장
- **파일 시스템**: JSON 기반 프롬프트 관리
- **Python**: RAG 파이프라인 고도화
- **Rust/Tauri**: API 확장 및 파일 관리

### 프론트엔드 개선
- **React**: 새로운 컴포넌트 및 상태 관리
- **TypeScript**: 타입 안전성 강화
- **CSS**: 인터랙티브 UI 디자인

### AI/ML
- **DeepSeek**: Chain-of-Thought 및 채널별 맞춤 프롬프트
- **ChromaDB**: 벡터 검색 최적화
- **프롬프트 엔지니어링**: 채널별 특성 반영

---

**개발 우선순위**: 
1. 채널별 벡터 분석 시스템 구현
2. 자동 프롬프트 생성 기능 개발
3. 채널 선택 UI 구현
4. 파일 기반 프롬프트 관리 시스템
5. 채널별 맞춤 답변 생성
6. 클릭형 영상 링크 기능
7. 프롬프트 편집 UI

## 🚀 사용 시나리오

### 1. 자동 프롬프트 생성
```bash
# 1. 벡터 임베딩 생성 (기존)
make embed

# 2. 모든 채널 자동 프롬프트 생성
python vault/90_indices/auto_prompt.py batch

# 3. 특정 채널 분석
python vault/90_indices/auto_prompt.py analyze takaki_takehana

# 4. 특정 채널 프롬프트 생성
python vault/90_indices/auto_prompt.py generate takaki_takehana
```

### 2. **완전 자동화된** AI 질문 워크플로우
1. **채널 선택** → `takaki_takehana` 선택
2. **자동 로드** → 벡터 분석으로 생성된 전문가 프롬프트 자동 적용
3. **질문 입력** → "도쿄 원룸 투자 수익률은?"
4. **전문가 답변** → "10년차 일본 부동산 투자 전문가" 페르소나로 답변
5. **소스 확인** → YouTube 영상 원클릭 접근

#### 🔍 **자동 생성된 프롬프트 예시**
```
당신은 takaki_takehana 채널을 대표하는 일본 부동산 투자 전문 AI입니다.

이 채널의 특징:
- 주요 키워드: 부동산, 투자, 도쿄, 수익률, 임대
- 콘텐츠 스타일: 실용적이고 경험 중심적인 접근
- 분석 깊이: deep (구체적 수치와 데이터 중시)

답변 규칙:
- 구체적인 수치와 데이터를 포함하여 답변
- 실제 경험과 사례를 중심으로 설명
- 답변 구조: 🚀 핵심 요약 → 📊 데이터 분석 → 📚 근거/출처 → 📝 실행 단계
```

### 3. 프롬프트 관리
1. **자동 생성** → 벡터 데이터 분석으로 초기 프롬프트 생성
2. **수동 편집** → 웹 UI에서 프롬프트 세부 조정
3. **버전 관리** → 변경 이력 추적 및 롤백 가능
4. **성능 모니터링** → 답변 품질에 따른 프롬프트 개선
