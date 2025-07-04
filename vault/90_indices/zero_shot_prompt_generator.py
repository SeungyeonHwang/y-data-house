#!/usr/bin/env python3
"""
제로샷 프롬프트 자동 생성 시스템 - Y-Data-House
AI가 채널 정보를 분석해서 최적화된 프롬프트를 자동 생성
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
import re
from dotenv import load_dotenv
from openai import OpenAI
import chromadb
from chromadb.config import Settings as ChromaSettings

# 환경변수 로드
load_dotenv()

class ZeroShotPromptGenerator:
    """제로샷 방식 프롬프트 자동 생성기"""
    
    def __init__(self, chroma_path: Path = None, model: str = "gpt-4"):
        """초기화"""
        self.chroma_path = chroma_path or Path(__file__).parent / "chroma"
        self.model = model
        
        # OpenAI 클라이언트 초기화 (DeepSeek 호환)
        api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        
        if not api_key:
            raise ValueError("❌ DEEPSEEK_API_KEY 또는 OPENAI_API_KEY 환경변수가 필요합니다")
        
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url if "deepseek" in model else None
        )
        
        # ChromaDB 클라이언트 초기화
        try:
            self.chroma_client = chromadb.PersistentClient(
                path=str(self.chroma_path),
                settings=ChromaSettings(anonymized_telemetry=False)
            )
            print(f"✅ ChromaDB 연결됨: {self.chroma_path}")
        except Exception as e:
            raise ValueError(f"❌ ChromaDB 로드 실패: {e}")
        
        print(f"🤖 제로샷 프롬프트 생성기 초기화 완료 (모델: {model})")
    
    def _find_collection_by_channel_name(self, channel_name: str):
        """채널명으로 실제 컬렉션 찾기 (channel_analyzer와 동일한 로직)"""
        try:
            collections = self.chroma_client.list_collections()
            
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
    
    def get_channel_summary(self, channel_name: str) -> Dict:
        """채널의 요약 정보 추출"""
        try:
            # 올바른 컬렉션 찾기 (channel_analyzer와 동일한 로직 사용)
            target_collection = self._find_collection_by_channel_name(channel_name)
            
            if not target_collection:
                print(f"❌ {channel_name} 채널의 컬렉션을 찾을 수 없습니다")
                return {}
            
            # 전체 문서 조회
            results = target_collection.get()
            documents = results['documents']
            metadatas = results['metadatas'] if results['metadatas'] else []
            
            if not documents:
                print(f"❌ {channel_name} 채널에 문서가 없습니다")
                return {}
            
            # 채널 요약 정보 구성
            summary = {
                'channel_name': channel_name,
                'total_documents': len(documents),
                'sample_documents': documents[:5],  # 첫 5개 문서 샘플
                'video_titles': [],
                'content_keywords': self._extract_keywords_simple(documents),
                'content_length_stats': self._analyze_content_length(documents),
                'metadata_insights': self._analyze_metadata_simple(metadatas)
            }
            
            # 비디오 제목 추출
            for metadata in metadatas[:10]:  # 첫 10개만
                if isinstance(metadata, dict) and 'title' in metadata:
                    summary['video_titles'].append(metadata['title'])
            
            return summary
            
        except Exception as e:
            print(f"❌ 채널 요약 추출 실패: {e}")
            return {}
    
    def _extract_keywords_simple(self, documents: List[str]) -> List[str]:
        """간단한 키워드 추출"""
        all_text = ' '.join(documents)
        
        # 한글/영어/숫자만 유지
        cleaned = re.sub(r'[^\w가-힣\s]', ' ', all_text)
        words = cleaned.split()
        
        # 단어 빈도 계산 (길이 2 이상)
        word_count = {}
        for word in words:
            if len(word) >= 2:
                word_count[word] = word_count.get(word, 0) + 1
        
        # 상위 20개 키워드 반환
        sorted_words = sorted(word_count.items(), key=lambda x: x[1], reverse=True)
        return [word for word, count in sorted_words[:20]]
    
    def _analyze_content_length(self, documents: List[str]) -> Dict:
        """콘텐츠 길이 분석"""
        lengths = [len(doc) for doc in documents]
        return {
            'avg_length': sum(lengths) / len(lengths) if lengths else 0,
            'max_length': max(lengths) if lengths else 0,
            'min_length': min(lengths) if lengths else 0
        }
    
    def _analyze_metadata_simple(self, metadatas: List[Dict]) -> Dict:
        """메타데이터 간단 분석"""
        insights = {
            'video_count': len(metadatas),
            'has_timestamps': False,
            'has_descriptions': False
        }
        
        for metadata in metadatas:
            if isinstance(metadata, dict):
                if 'timestamp' in metadata or 'upload_date' in metadata:
                    insights['has_timestamps'] = True
                if 'description' in metadata:
                    insights['has_descriptions'] = True
        
        return insights
    
    def generate_prompt_with_ai(self, channel_summary: Dict) -> Dict:
        """AI를 활용한 제로샷 프롬프트 생성"""
        if not channel_summary:
            return self._get_fallback_prompt()
        
        # 메타 프롬프트 구성
        meta_prompt = self._build_meta_prompt(channel_summary)
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system", 
                        "content": "당신은 YouTube 채널별 맞춤 AI 프롬프트 설계 전문가입니다. 주어진 채널 정보를 분석하여 최적화된 프롬프트를 JSON 형태로 생성해주세요."
                    },
                    {
                        "role": "user", 
                        "content": meta_prompt
                    }
                ],
                max_tokens=1500,
                temperature=0.3  # 일관성을 위해 낮은 온도
            )
            
            # JSON 파싱
            ai_response = response.choices[0].message.content.strip()
            prompt_data = self._parse_ai_response(ai_response, channel_summary)
            
            return prompt_data
            
        except Exception as e:
            print(f"❌ AI 프롬프트 생성 실패: {e}")
            return self._get_fallback_prompt(channel_summary.get('channel_name', 'unknown'))
    
    def _build_meta_prompt(self, channel_summary: Dict) -> str:
        """Prompt-Light 메타 프롬프트 생성 (Search-First 아키텍처 반영)"""
        channel_name = channel_summary.get('channel_name', 'Unknown')
        total_docs = channel_summary.get('total_documents', 0)
        keywords = ', '.join(channel_summary.get('content_keywords', [])[:8])  # 8개로 제한
        video_titles = channel_summary.get('video_titles', [])[:3]  # 3개로 제한
        
        # 간단한 콘텐츠 미리보기 (1개만)
        content_preview = ""
        if channel_summary.get('sample_documents'):
            sample = channel_summary['sample_documents'][0]
            preview = sample[:200] + "..." if len(sample) > 200 else sample
            content_preview = f"대표 콘텐츠: {preview}"
        
        meta_prompt = f"""
Y-Data-House RAG v7.0 "Search-First & Prompt-Light" 아키텍처용 경량 프롬프트를 생성해주세요.

## 📊 채널 정보
- 채널: {channel_name}
- 문서: {total_docs}개
- 키워드: {keywords}
- 대표 영상: {', '.join(video_titles)}
{content_preview}

## 🎯 새로운 아키텍처 철학
"Search-First & Prompt-Light" - 검색 품질을 '하드'하게 올리고, 프롬프트는 '심플+검증'으로 유지
✅ 4단계 검색 파이프라인이 이미 고품질 검색 수행
✅ 프롬프트는 경량화하여 토큰 효율성 극대화
✅ 간단한 지침으로 빠른 응답 (<500ms 목표)

## 📝 경량 프롬프트 요구사항
아래 JSON 형식으로 **간단하고 핵심적인** 프롬프트만 생성:

```json
{{
  "persona": "채널 전문가 (1-2줄, 100자 이내)",
  "tone": "답변 스타일 (1줄, 50자 이내)", 
  "system_prompt": "AI 역할 간단 설명 (150자 이내)",
  "expertise_keywords": ["핵심 키워드 5개 이하"],
  "target_audience": "주요 사용자층 (50자 이내)"
}}
```

## ⚡ 중요 제약사항
1. **극도로 간결**: persona(100자), tone(50자), system_prompt(150자) 제한
2. **검색 의존**: "채널 영상을 바탕으로" 정도로만 언급 (검색은 이미 고도화됨)
3. **복잡한 규칙 금지**: 기존의 복잡한 output_format, self_refine 설정 불필요
4. **키워드 중심**: expertise_keywords 5개 이하로 핵심만
5. **실용성 우선**: 사용자가 바로 이해할 수 있는 단순한 설명

## 예시 (참고용)
```json
{{
  "persona": "일본 부동산 투자 전문 컨설턴트",
  "tone": "친근하고 데이터 기반", 
  "system_prompt": "채널 영상을 바탕으로 일본 부동산 투자에 대한 실용적 조언을 제공합니다.",
  "expertise_keywords": ["도쿄 아파트", "투자 수익률", "지역 분석", "구매 전략"],
  "target_audience": "일본 부동산 투자 관심자"
}}
```

**{channel_name} 채널에 최적화된 경량 프롬프트 JSON을 생성해주세요:**
"""
        
        return meta_prompt.strip()
    
    def _parse_ai_response(self, ai_response: str, channel_summary: Dict) -> Dict:
        """AI 응답 파싱 및 검증 (Prompt-Light 버전)"""
        try:
            # JSON 부분만 추출
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', ai_response, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                # JSON 코드블록이 없으면 전체에서 JSON 찾기
                json_match = re.search(r'(\{.*\})', ai_response, re.DOTALL)
                if json_match:
                    json_str = json_match.group(1)
                else:
                    raise ValueError("JSON 형식을 찾을 수 없습니다")
            
            # JSON 파싱
            prompt_data = json.loads(json_str)
            
            # 경량 프롬프트 필드 길이 제한 적용
            if 'persona' in prompt_data:
                prompt_data['persona'] = prompt_data['persona'][:100]  # 100자 제한
            if 'tone' in prompt_data:
                prompt_data['tone'] = prompt_data['tone'][:50]       # 50자 제한
            if 'system_prompt' in prompt_data:
                prompt_data['system_prompt'] = prompt_data['system_prompt'][:200]  # 150자 → 200자 여유
            if 'target_audience' in prompt_data:
                prompt_data['target_audience'] = prompt_data['target_audience'][:50]  # 50자 제한
            if 'expertise_keywords' in prompt_data and isinstance(prompt_data['expertise_keywords'], list):
                prompt_data['expertise_keywords'] = prompt_data['expertise_keywords'][:5]  # 5개 제한
            
            # 기본 메타데이터 추가 (Prompt-Light 메타데이터)
            prompt_data.update({
                "version": 1,
                "channel_name": channel_summary.get('channel_name', 'unknown'),
                "created_at": datetime.now().isoformat(),
                "auto_generated": True,
                "generation_method": "prompt_light_ai",  # 새로운 방식임을 명시
                "model_used": self.model,
                "source_documents": channel_summary.get('total_documents', 0),
                "architecture": "search_first_prompt_light"  # 아키텍처 버전 명시
            })
            
            # 필수 경량 필드 검증 및 기본값 설정
            light_required_fields = {
                'persona': f'{channel_summary.get("channel_name", "unknown")} 채널 전문가',
                'tone': '친근하고 전문적인 스타일',
                'system_prompt': f'채널 영상을 바탕으로 {channel_summary.get("channel_name", "정보")}에 대한 답변을 제공합니다.',
                'expertise_keywords': [],
                'target_audience': '관심 있는 일반 사용자'
            }
            
            for field, default_value in light_required_fields.items():
                if field not in prompt_data:
                    print(f"⚠️ 필수 필드 누락: {field}, 기본값 설정")
                    prompt_data[field] = default_value
            
            # 기존 복잡한 필드들 제거 (새 아키텍처에서 불필요)
            deprecated_fields = [
                'rules', 'output_format', 'tooling', 'self_refine', 
                'response_schema', 'quality_metrics', 'unique_value'
            ]
            for field in deprecated_fields:
                if field in prompt_data:
                    del prompt_data[field]
            
            print(f"✅ Prompt-Light 프롬프트 생성 완료")
            print(f"   페르소나: {prompt_data['persona'][:50]}...")
            print(f"   키워드: {len(prompt_data.get('expertise_keywords', []))}개")
            
            return prompt_data
            
        except Exception as e:
            print(f"❌ AI 응답 파싱 실패: {e}")
            print(f"원본 응답: {ai_response[:300]}...")
            return self._get_fallback_prompt(channel_summary.get('channel_name', 'unknown'))
    
    def _get_default_field_value(self, field: str) -> str:
        """누락된 필드의 기본값 반환 (Prompt-Light 버전)"""
        defaults = {
            'persona': 'YouTube 채널 전문 분석가',
            'tone': '친근하고 전문적인 스타일',
            'system_prompt': '채널 영상을 바탕으로 정확하고 유용한 답변을 제공합니다.',
            'target_audience': '관심 있는 일반 사용자'
        }
        return defaults.get(field, '')
    
    def _get_fallback_prompt(self, channel_name: str = "unknown") -> Dict:
        """AI 생성 실패 시 경량 폴백 프롬프트"""
        return {
            "version": 1,
            "channel_name": channel_name,
            "created_at": datetime.now().isoformat(),
            "auto_generated": True,
            "generation_method": "prompt_light_fallback",
            "architecture": "search_first_prompt_light",
            "persona": f"{channel_name} 채널 전문 분석가",
            "tone": "친근하고 전문적인 스타일",
            "system_prompt": f"채널 영상을 바탕으로 {channel_name}에 대한 실용적 조언을 제공합니다.",
            "expertise_keywords": [],
            "target_audience": f"{channel_name} 관심자"
        }
    
    def generate_channel_prompt(self, channel_name: str) -> Dict:
        """채널별 제로샷 프롬프트 생성 (메인 함수)"""
        print(f"🔍 {channel_name} 채널 정보 수집 중...")
        
        # 1. 채널 요약 정보 수집
        channel_summary = self.get_channel_summary(channel_name)
        if not channel_summary:
            print(f"❌ {channel_name} 채널 정보를 찾을 수 없습니다")
            return {}
        
        print(f"📊 채널 분석 완료: {channel_summary['total_documents']}개 문서")
        print(f"🔑 주요 키워드: {', '.join(channel_summary['content_keywords'][:5])}")
        
        # 2. AI로 프롬프트 생성
        print(f"🤖 AI 프롬프트 생성 중... (모델: {self.model})")
        prompt_data = self.generate_prompt_with_ai(channel_summary)
        
        if prompt_data:
            print(f"✅ {channel_name} 제로샷 프롬프트 생성 완료!")
            print(f"📝 페르소나: {prompt_data.get('persona', 'N/A')}")
            print(f"🎯 전문분야: {', '.join(prompt_data.get('expertise_keywords', [])[:3])}")
            return prompt_data
        else:
            print(f"❌ {channel_name} 프롬프트 생성 실패")
            return {}


def main():
    """테스트 실행"""
    try:
        # 제로샷 생성기 초기화
        generator = ZeroShotPromptGenerator(model="deepseek-chat")
        
        # 사용 가능한 채널 확인
        collections = generator.chroma_client.list_collections()
        if not collections:
            print("❌ 분석 가능한 채널이 없습니다")
            print("💡 먼저 'python embed.py'로 벡터 임베딩을 생성하세요")
            return
        
        channel_names = [c.name for c in collections]
        print(f"📺 사용 가능한 채널 ({len(channel_names)}개):")
        for i, name in enumerate(channel_names, 1):
            print(f"  {i}. {name}")
        
        # 첫 번째 채널로 테스트
        if channel_names:
            test_channel = channel_names[0]
            print(f"\n🧪 {test_channel} 제로샷 프롬프트 생성 테스트...")
            
            prompt_data = generator.generate_channel_prompt(test_channel)
            
            if prompt_data:
                print(f"\n📋 생성된 프롬프트 미리보기:")
                print(f"  페르소나: {prompt_data.get('persona', 'N/A')}")
                print(f"  톤: {prompt_data.get('tone', 'N/A')}")
                print(f"  시스템 프롬프트: {prompt_data.get('system_prompt', 'N/A')[:100]}...")
                print(f"  규칙 수: {len(prompt_data.get('rules', []))}")
                print(f"  생성 방법: {prompt_data.get('generation_method', 'N/A')}")
            
    except Exception as e:
        print(f"❌ 오류: {e}")


if __name__ == "__main__":
    main() 