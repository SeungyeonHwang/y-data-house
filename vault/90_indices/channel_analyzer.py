#!/usr/bin/env python3
"""
채널별 벡터 데이터 분석 시스템 - Y-Data-House 자동 프롬프트 생성
"""

import os
import re
from pathlib import Path
from collections import Counter
from typing import Dict, List, Tuple, Optional
import chromadb
from chromadb.config import Settings as ChromaSettings
from datetime import datetime
import json


class ChannelAnalyzer:
    """벡터 데이터를 분석하여 채널 특성을 자동으로 추출하는 클래스"""
    
    def __init__(self, chroma_path: Path = None):
        """초기화"""
        self.chroma_path = chroma_path or Path(__file__).parent / "chroma"
        
        if not self.chroma_path.exists():
            raise ValueError(f"❌ ChromaDB 경로가 존재하지 않습니다: {self.chroma_path}")
        
        try:
            self.client = chromadb.PersistentClient(
                path=str(self.chroma_path),
                settings=ChromaSettings(anonymized_telemetry=False)
            )
            print(f"✅ ChromaDB 연결됨: {self.chroma_path}")
        except Exception as e:
            raise ValueError(f"❌ ChromaDB 연결 실패: {e}")
    
    def sanitize_collection_name(self, name: str) -> str:
        """ChromaDB 컬렉션 이름 정리"""
        sanitized = re.sub(r'[^\w가-힣]', '_', name)
        sanitized = re.sub(r'_+', '_', sanitized).strip('_')
        return sanitized[:50] if sanitized else "unknown_channel"
    
    def _find_collection_by_channel_name(self, channel_name: str):
        """채널명으로 실제 컬렉션 찾기"""
        try:
            collections = self.client.list_collections()
            
            for collection in collections:
                if collection.name.startswith("channel_"):
                    # 컬렉션에서 샘플 데이터 가져와서 채널명 확인
                    try:
                        sample = collection.get(limit=1, include=['metadatas'])
                        if sample['metadatas'] and sample['metadatas'][0]:
                            metadata_channel = sample['metadatas'][0].get('channel', '')
                            if metadata_channel == channel_name:
                                return collection
                    except:
                        continue
            
            print(f"📋 사용 가능한 컬렉션들:")
            for collection in collections:
                if collection.name.startswith("channel_"):
                    try:
                        sample = collection.get(limit=1, include=['metadatas'])
                        if sample['metadatas'] and sample['metadatas'][0]:
                            metadata_channel = sample['metadatas'][0].get('channel', '알 수 없음')
                            print(f"  - {collection.name} → {metadata_channel}")
                    except:
                        print(f"  - {collection.name} → 메타데이터 확인 불가")
            
            return None
        except Exception as e:
            print(f"❌ 컬렉션 검색 실패: {e}")
            return None
    
    def list_available_channels_for_analysis(self) -> List[str]:
        """분석 가능한 채널 목록 반환"""
        try:
            collections = self.client.list_collections()
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
    
    def analyze_channel_content(self, channel_name: str) -> Dict:
        """채널 벡터 데이터 분석하여 특성 추출"""
        # 실제 컬렉션명을 찾기 위해 모든 컬렉션을 확인
        collection = self._find_collection_by_channel_name(channel_name)
        if not collection:
            print(f"❌ '{channel_name}' 채널의 컬렉션을 찾을 수 없습니다.")
            return {}
        
        try:
            data = collection.get(include=['documents', 'metadatas'])
            
            if not data['documents']:
                print(f"⚠️ {channel_name} 채널에 데이터가 없습니다.")
                return {}
            
            print(f"📊 {channel_name} 채널 분석 시작: {len(data['documents'])}개 문서")
            
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
                'total_videos': len(set(m.get('video_id', '') for m in data['metadatas'] if m)),
                'total_documents': len(data['documents']),
                'analysis_timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            print(f"⚠️ 채널 분석 실패: {e}")
            return {}
    
    def _extract_keywords(self, documents: List[str]) -> Dict[str, int]:
        """문서에서 주요 키워드 추출"""
        all_text = ' '.join(documents)
        
        # 한글 키워드 추출 (2-8글자)
        korean_keywords = re.findall(r'[가-힣]{2,8}', all_text)
        
        # 영문 키워드 추출 (3-15글자)
        english_keywords = re.findall(r'[A-Za-z]{3,15}', all_text.lower())
        
        # 숫자 패턴 추출 (수치 + 단위)
        number_patterns = re.findall(r'\d+[년월일%억만원평달층분]', all_text)
        
        # 특수 키워드 패턴
        special_patterns = re.findall(r'[가-힣]+(?:투자|부동산|수익|전략|분석|매매|임대)', all_text)
        
        # 빈도 계산
        all_keywords = korean_keywords + english_keywords + number_patterns + special_patterns
        keyword_counts = Counter(all_keywords)
        
        # 불용어 제거
        stopwords = {
            '이것', '그것', '저것', '여기', '거기', '저기', '이거', '그거', '저거',
            '때문', '경우', '정도', '시간', '사람', '생각', '말씀', '이야기',
            'this', 'that', 'have', 'been', 'will', 'with', 'from', 'they'
        }
        
        filtered_keywords = {k: v for k, v in keyword_counts.items() 
                           if k not in stopwords and v >= 2}
        
        # 상위 30개 키워드 반환
        return dict(Counter(filtered_keywords).most_common(30))
    
    def _analyze_content_patterns(self, documents: List[str]) -> Dict:
        """콘텐츠 패턴 분석"""
        patterns = {
            'investment_terms': 0,
            'location_mentions': 0,
            'numerical_data': 0,
            'experience_sharing': 0,
            'analysis_depth': 'medium',
            'real_estate_focus': 0,
            'practical_tips': 0
        }
        
        # 패턴 분석을 위한 키워드 그룹
        investment_terms = ['투자', '수익률', '매매', '임대', '자산', '포트폴리오', '펀드', '배당']
        locations = ['도쿄', '오사카', '교토', '요코하마', '시부야', '신주쿠', '하라주쿠', '롯폰기']
        experience_words = ['경험', '실제로', '직접', '해보니', '느낀점', '후기', '체험', '실전']
        real_estate_words = ['부동산', '아파트', '원룸', '오피스텔', '상가', '토지', '건물']
        practical_words = ['방법', '팁', '노하우', '전략', '비법', '요령', '기법']
        
        for doc in documents:
            # 투자 관련 용어
            patterns['investment_terms'] += sum(doc.count(term) for term in investment_terms)
            
            # 지역 언급
            patterns['location_mentions'] += sum(doc.count(loc) for loc in locations)
            
            # 수치 데이터
            patterns['numerical_data'] += len(re.findall(r'\d+[%억만원평년달]', doc))
            
            # 경험 공유 표현
            patterns['experience_sharing'] += sum(doc.count(word) for word in experience_words)
            
            # 부동산 집중도
            patterns['real_estate_focus'] += sum(doc.count(word) for word in real_estate_words)
            
            # 실용적 팁
            patterns['practical_tips'] += sum(doc.count(word) for word in practical_words)
        
        # 분석 깊이 판단
        total_docs = len(documents)
        if patterns['numerical_data'] > total_docs * 5 and patterns['investment_terms'] > total_docs * 3:
            patterns['analysis_depth'] = 'deep'
        elif patterns['numerical_data'] < total_docs * 1:
            patterns['analysis_depth'] = 'light'
        
        return patterns
    
    def _analyze_metadata(self, metadatas: List[Dict]) -> Dict:
        """메타데이터 분석"""
        insights = {
            'avg_duration': 0,
            'upload_frequency': 'unknown',
            'popular_topics': [],
            'recent_trends': [],
            'video_types': {}
        }
        
        if not metadatas or not any(metadatas):
            return insights
        
        # 비디오 길이 평균
        durations = []
        for m in metadatas:
            if m and m.get('duration'):
                try:
                    # "MM:SS" 형식을 초로 변환
                    duration_str = str(m['duration'])
                    if ':' in duration_str:
                        parts = duration_str.split(':')
                        if len(parts) == 2:
                            minutes, seconds = int(parts[0]), int(parts[1])
                            durations.append(minutes * 60 + seconds)
                except:
                    continue
        
        if durations:
            insights['avg_duration'] = sum(durations) / len(durations)
        
        # 인기 토픽
        all_topics = []
        for m in metadatas:
            if m and m.get('topic'):
                if isinstance(m['topic'], list):
                    all_topics.extend(m['topic'])
                else:
                    all_topics.append(str(m['topic']))
        
        if all_topics:
            topic_counts = Counter(all_topics)
            insights['popular_topics'] = [topic for topic, _ in topic_counts.most_common(5)]
        
        # 비디오 유형 분석
        titles = [m.get('title', '') for m in metadatas if m and m.get('title')]
        type_keywords = {
            '분석': ['분석', '리뷰', '평가'],
            '팁': ['팁', '방법', '노하우', '비법'],
            '경험담': ['후기', '경험', '체험', '실전'],
            '뉴스': ['속보', '뉴스', '정보', '업데이트']
        }
        
        for title in titles:
            for vid_type, keywords in type_keywords.items():
                if any(keyword in title for keyword in keywords):
                    insights['video_types'][vid_type] = insights['video_types'].get(vid_type, 0) + 1
        
        return insights
    
    def _analyze_tone(self, documents: List[str]) -> Dict:
        """톤 & 스타일 분석"""
        tone_indicators = {
            'formal': ['습니다', '됩니다', '있습니다', '것입니다', '드립니다'],
            'casual': ['해요', '이에요', '거예요', '네요', '어요'],
            'expert': ['분석', '데이터', '지표', '전문적', '연구', '조사'],
            'practical': ['실제', '직접', '경험', '팁', '방법', '노하우'],
            'enthusiastic': ['정말', '너무', '대박', '완전', '진짜', '최고']
        }
        
        tone_scores = {tone: 0 for tone in tone_indicators.keys()}
        total_words = 0
        
        for doc in documents:
            total_words += len(doc.split())
            for tone, indicators in tone_indicators.items():
                tone_scores[tone] += sum(doc.count(indicator) for indicator in indicators)
        
        # 상대적 점수 계산 (1000단어 기준)
        if total_words > 0:
            normalized_scores = {tone: (score * 1000) / total_words 
                               for tone, score in tone_scores.items()}
        else:
            normalized_scores = tone_scores
        
        # 주요 톤 결정
        primary_tone = max(normalized_scores, key=normalized_scores.get)
        
        return {
            'primary_tone': primary_tone,
            'tone_scores': tone_scores,
            'normalized_scores': normalized_scores,
            'style_description': self._generate_style_description(primary_tone, normalized_scores)
        }
    
    def _generate_style_description(self, primary_tone: str, tone_scores: Dict) -> str:
        """스타일 설명 생성"""
        style_map = {
            'formal': '정중하고 전문적인 어투',
            'casual': '친근하고 편안한 대화체',
            'expert': '분석적이고 데이터 중심적인 스타일',
            'practical': '실용적이고 경험 중심적인 접근',
            'enthusiastic': '활기차고 열정적인 표현'
        }
        
        primary_desc = style_map.get(primary_tone, '균형잡힌 스타일')
        
        # 보조 톤 식별
        secondary_tones = sorted(tone_scores.items(), key=lambda x: x[1], reverse=True)[1:3]
        secondary_elements = []
        
        for tone, score in secondary_tones:
            if score > 0.3:  # 임계값 이상인 경우에만
                if tone == 'expert':
                    secondary_elements.append('전문성')
                elif tone == 'practical':
                    secondary_elements.append('실용성')
                elif tone == 'enthusiastic':
                    secondary_elements.append('열정')
        
        if secondary_elements:
            return f"{primary_desc}이며 {', '.join(secondary_elements)}도 강조하는 스타일"
        else:
            return primary_desc
    
    def generate_auto_prompt(self, channel_analysis: Dict) -> Dict:
        """채널 분석 결과를 바탕으로 자동 프롬프트 생성"""
        if not channel_analysis:
            return self._get_default_prompt()
        
        channel_name = channel_analysis['channel_name']
        keywords = list(channel_analysis.get('keywords', {}).keys())[:10]
        patterns = channel_analysis.get('content_patterns', {})
        tone_analysis = channel_analysis.get('tone_analysis', {})
        metadata = channel_analysis.get('metadata_insights', {})
        
        # 페르소나 생성
        persona = self._generate_persona(patterns, tone_analysis, keywords)
        
        # 전문 분야 결정
        expertise = self._determine_expertise(keywords, patterns)
        
        # 시스템 프롬프트 생성
        system_prompt = f"""당신은 {channel_name} 채널을 대표하는 {expertise} 전문 AI 어시스턴트입니다.

이 채널의 특징:
- 주요 키워드: {', '.join(keywords[:5])}
- 콘텐츠 스타일: {tone_analysis.get('style_description', '전문적')}
- 분석 깊이: {patterns.get('analysis_depth', 'medium')}
- 총 영상 수: {channel_analysis.get('total_videos', 0)}개

당신의 역할은 이 채널의 영상 내용만을 바탕으로 사용자에게 정확하고 실용적인 조언을 제공하는 것입니다."""

        # 답변 규칙 생성
        rules = self._generate_rules(patterns, tone_analysis)
        
        # 출력 형식 결정
        output_format = self._determine_output_format(patterns, tone_analysis)
        
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
                "total_documents": channel_analysis.get('total_documents', 0),
                "analysis_timestamp": channel_analysis.get('analysis_timestamp'),
                "content_patterns": patterns,
                "tone_scores": tone_analysis.get('normalized_scores', {})
            }
        }
    
    def _generate_persona(self, patterns: Dict, tone_analysis: Dict, keywords: List[str]) -> str:
        """패턴 분석을 바탕으로 페르소나 생성"""
        base_persona = "전문 컨텐츠 분석가"
        
        # 부동산/투자 전문성 판단
        if patterns.get('investment_terms', 0) > 30 or any('투자' in k for k in keywords[:5]):
            if patterns.get('real_estate_focus', 0) > 20:
                base_persona = "부동산 투자 전문가"
            else:
                base_persona = "투자 전문가"
        
        # 경험 중심성 추가
        if patterns.get('experience_sharing', 0) > 20:
            base_persona += "이며 실전 경험이 풍부한 컨설턴트"
        
        # 분석 깊이 추가
        if patterns.get('analysis_depth') == 'deep':
            base_persona += "이며 데이터 기반 분석을 중시하는 전문가"
        
        # 실용성 추가
        if patterns.get('practical_tips', 0) > 15:
            base_persona += "이며 실용적인 조언을 제공하는 멘토"
        
        return base_persona
    
    def _determine_expertise(self, keywords: List[str], patterns: Dict) -> str:
        """키워드와 패턴을 바탕으로 전문 분야 결정"""
        # 키워드 기반 분야 판단
        real_estate_keywords = ['부동산', '투자', '매매', '임대', '원룸', '아파트']
        finance_keywords = ['펀드', '주식', '자산', '수익률', '배당']
        travel_keywords = ['여행', '맛집', '문화', '관광']
        
        if any(keyword in keywords for keyword in real_estate_keywords):
            return "부동산 투자"
        elif any(keyword in keywords for keyword in finance_keywords):
            return "자산 관리"
        elif any(keyword in keywords for keyword in travel_keywords):
            return "라이프스타일"
        else:
            # 패턴 기반 판단
            if patterns.get('real_estate_focus', 0) > 10:
                return "부동산"
            elif patterns.get('investment_terms', 0) > 20:
                return "투자"
            else:
                return "종합 정보"
    
    def _generate_rules(self, patterns: Dict, tone_analysis: Dict) -> List[str]:
        """패턴에 따른 답변 규칙 생성"""
        rules = [
            "반드시 이 채널의 정보만 활용하여 답변",
            "모르는 내용은 추측 금지, '정보 부족' 명시"
        ]
        
        # 수치 데이터 중심성
        if patterns.get('numerical_data', 0) > 50:
            rules.append("구체적인 수치와 데이터를 포함하여 답변")
        
        # 경험 공유 중심성
        if patterns.get('experience_sharing', 0) > 15:
            rules.append("실제 경험과 사례를 중심으로 설명")
        
        # 실용적 접근
        if tone_analysis.get('primary_tone') == 'practical' or patterns.get('practical_tips', 0) > 10:
            rules.append("실행 가능한 구체적 단계 제시")
        
        # 전문성 중시
        if tone_analysis.get('primary_tone') == 'expert':
            rules.append("전문 용어 사용 시 설명 포함")
        
        # 기본 답변 구조
        rules.append("답변 구조: 핵심 요약 → 근거 → 실행 단계")
        
        return rules
    
    def _determine_output_format(self, patterns: Dict, tone_analysis: Dict) -> Dict:
        """패턴에 따른 출력 형식 결정"""
        if patterns.get('analysis_depth') == 'deep':
            return {
                "structure": "🚀 핵심 요약 → 📊 데이터 분석 → 📚 근거/출처 → 📝 실행 단계 → 💡 한줄 요약",
                "max_bullets": 7,
                "include_video_links": True,
                "data_emphasis": True
            }
        elif patterns.get('experience_sharing', 0) > 20:
            return {
                "structure": "🚀 핵심 요약 → 💼 실제 경험 → 📚 근거/출처 → 📝 실행 가이드 → 💡 한줄 요약",
                "max_bullets": 5,
                "include_video_links": True,
                "experience_emphasis": True
            }
        else:
            return {
                "structure": "🚀 핵심 요약 → 📚 근거/출처 → 📝 실행 단계 → 💡 한줄 요약",
                "max_bullets": 5,
                "include_video_links": True,
                "balanced_approach": True
            }
    
    def _get_default_prompt(self) -> Dict:
        """기본 프롬프트 반환"""
        return {
            "version": 1,
            "channel_name": "default",
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


def main():
    """테스트 실행"""
    try:
        analyzer = ChannelAnalyzer()
        
        # 사용 가능한 채널 목록
        channels = analyzer.list_available_channels_for_analysis()
        print(f"📺 분석 가능한 채널: {channels}")
        
        if channels:
            # 첫 번째 채널 분석 테스트
            channel = channels[0]
            print(f"\n🔍 {channel} 채널 분석 테스트...")
            
            analysis = analyzer.analyze_channel_content(channel)
            if analysis:
                print(f"✅ 분석 완료:")
                print(f"  키워드: {list(analysis['keywords'].keys())[:5]}")
                print(f"  주요 톤: {analysis['tone_analysis']['primary_tone']}")
                print(f"  분석 깊이: {analysis['content_patterns']['analysis_depth']}")
                
                # 자동 프롬프트 생성 테스트
                auto_prompt = analyzer.generate_auto_prompt(analysis)
                print(f"  페르소나: {auto_prompt['persona']}")
            
    except Exception as e:
        print(f"❌ 오류: {e}")


if __name__ == "__main__":
    main()