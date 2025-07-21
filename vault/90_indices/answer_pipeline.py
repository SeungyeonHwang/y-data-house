#!/usr/bin/env python3
"""
Prompt-Light 답변 파이프라인
경량 프롬프트 + Self-Refine (1회) + ReAct + JSON Schema

조언 기반 최적화:
- 채널별 1-2줄 프롬프트만 사용
- Self-Refine 1회로 제한해 토큰 폭증 방지  
- JSON Schema 강제로 파서 오류 감소
- ReAct는 추가 검색 필요시에만
"""

import os
import time
import json
from typing import List, Dict, Optional, Any
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
from schemas import (
    AnswerRequest, AnswerResponse, AnswerConfig, ChannelPrompt,
    SearchResult, AnswerStyle
)
from prompt_manager import PromptManager

# 환경변수 로드
load_dotenv()

class AnswerPipeline:
    """Prompt-Light 답변 생성 파이프라인"""
    
    def __init__(self, model: str = "deepseek-chat", prompts_dir: Path = None):
        """초기화"""
        self.model = model
        
        # DeepSeek 클라이언트 초기화
        try:
            api_key = os.getenv('DEEPSEEK_API_KEY')
            if not api_key:
                raise ValueError("DEEPSEEK_API_KEY 환경변수가 필요합니다")
                
            self.client = OpenAI(
                api_key=api_key,
                base_url="https://api.deepseek.com/v1"
            )
            print(f"✅ DeepSeek API 클라이언트 초기화 완료 (모델: {model})")
        except Exception as e:
            raise ValueError(f"❌ DeepSeek API 초기화 실패: {e}")
        
        # 프롬프트 매니저 초기화 (채널별 경량 프롬프트용)
        try:
            self.prompt_manager = PromptManager(prompts_dir) if prompts_dir else None
            if self.prompt_manager:
                print(f"✅ PromptManager 로드됨")
        except Exception as e:
            print(f"⚠️ PromptManager 초기화 실패: {e}")
            self.prompt_manager = None
        
        # 기본 JSON 스키마 템플릿
        self.default_schema = {
            "answer": "string - 메인 답변 내용",
            "key_points": ["string array - 핵심 포인트들"],
            "sources": ["string array - 사용된 영상 ID들"],
            "confidence": "number - 답변 신뢰도 (0-1)",
            "summary": "string - 한 줄 요약"
        }
        
        # 적응형 Temperature용 질문 분류 패턴
        self.factual_patterns = [
            r'\b(언제|몇|얼마|어디|누가|무엇|어느|몇개|몇명)\b',  # 5W1H 질문
            r'\b(가격|비용|요금|수치|통계|날짜|시간|주소|위치)\b',  # 구체적 수치/위치
            r'\b(정의|의미|뜻|개념|용어)\b',                      # 정의 관련
            r'\b(사실|확인|맞나|진짜|정말)\b',                    # 사실 확인
        ]
        
        self.analytical_patterns = [
            r'\b(왜|이유|원인|배경|근거|까닭)\b',                 # 인과관계
            r'\b(어떻게|방법|방식|과정|절차|단계)\b',              # 방법/절차
            r'\b(비교|차이|장단점|vs|대비|어떤.*좋)\b',           # 비교분석
            r'\b(전략|계획|방향|방침|정책)\b',                    # 전략적 사고
            r'\b(평가|분석|검토|고려|판단)\b',                    # 분석적 사고
            r'\b(미래|전망|예측|예상|앞으로)\b',                  # 예측/전망
            r'\b(추천|권장|제안|추천.*방법)\b',                   # 추천/제안
        ]
        
        print("💬 Answer Pipeline 초기화 완료 (적응형 Temperature 지원)")
    
    def _classify_question_type(self, query: str) -> str:
        """질문 유형 분류 - 사실형 vs 분석형 (전문가 조언 기반)"""
        import re
        
        query_lower = query.lower()
        
        # 사실형 패턴 점수 계산
        factual_score = 0
        for pattern in self.factual_patterns:
            if re.search(pattern, query_lower):
                factual_score += 1
        
        # 분석형 패턴 점수 계산
        analytical_score = 0
        for pattern in self.analytical_patterns:
            if re.search(pattern, query_lower):
                analytical_score += 1
        
        # 길이 기반 추가 점수 (짧은 질문 = 사실형 경향)
        if len(query) <= 20:
            factual_score += 0.5
        elif len(query) >= 50:
            analytical_score += 0.5
        
        # 질문 복잡도 (복수 질문 = 분석형)
        if query.count('?') > 1 or query.count('？') > 1:
            analytical_score += 1
        
        # 결과 판정
        if factual_score > analytical_score:
            return "factual"
        elif analytical_score > factual_score:
            return "analytical"
        else:
            # 동점인 경우 질문 길이와 구조로 판단
            if len(query) <= 30 and ('무엇' in query or '언제' in query or '어디' in query):
                return "factual"
            else:
                return "analytical"
    
    def _get_adaptive_temperature(self, query: str, config: AnswerConfig) -> float:
        """적응형 Temperature 계산 (전문가 조언: 사실형 0.4, 분석형 0.65)"""
        if not config.enable_adaptive_temperature:
            return config.temperature
        
        question_type = self._classify_question_type(query)
        
        if question_type == "factual":
            temperature = config.factual_temperature
            print(f"🎯 사실형 질문 감지 → Temperature: {temperature}")
        else:
            temperature = config.analytical_temperature
            print(f"🧠 분석형 질문 감지 → Temperature: {temperature}")
        
        return temperature
    
    def _load_channel_prompt(self, channel_name: str) -> ChannelPrompt:
        """채널별 경량 프롬프트 로드"""
        if self.prompt_manager:
            try:
                prompt_data = self.prompt_manager.get_channel_prompt(channel_name)
                
                # 경량화: 핵심 정보만 추출
                return ChannelPrompt(
                    channel_name=channel_name,
                    persona=prompt_data.get('persona', f'{channel_name} 채널 전문가')[:100],  # 1-2줄로 제한
                    tone=prompt_data.get('tone', '친근하고 전문적인 스타일')[:50],
                    expertise_keywords=prompt_data.get('expertise_keywords', [])[:5],  # 상위 5개만
                    system_prompt=prompt_data.get('system_prompt', 
                        f'당신은 {channel_name} 채널의 정보를 바탕으로 정확한 답변을 제공하는 AI입니다.')[:200]  # 간결하게
                )
            except Exception as e:
                print(f"⚠️ 채널 프롬프트 로드 실패: {e}")
        
        # 기본 경량 프롬프트
        return ChannelPrompt(
            channel_name=channel_name,
            persona=f'{channel_name} 채널 전문 분석가',
            tone='친근하고 도움이 되는 스타일',
            expertise_keywords=[],
            system_prompt=f'당신은 {channel_name} 채널의 영상 내용을 바탕으로 정확하고 유용한 답변을 제공하는 AI 어시스턴트입니다.'
        )
    
    def _build_context(self, search_result: SearchResult, max_context_length: int = 2000) -> str:
        """검색 결과로부터 컨텍스트 구성 (영상 연관성 정보 강화)"""
        if not search_result.documents:
            return "검색된 문서가 없습니다."
        
        context_parts = []
        for i, doc in enumerate(search_result.documents[:6]):  # 전문가 조언: top-6 chunk × 최대 800 tok가 LLM-window 최적
            # 영상 메타데이터 추출 (안전하게)
            metadata = doc.metadata if hasattr(doc, 'metadata') and doc.metadata else {}
            upload_date = metadata.get('upload_date', '날짜 미상')
            duration = metadata.get('duration', '시간 미상')
            chunk_index = metadata.get('chunk_index', 'N/A')
            
            # 영상 연관성 정보 강화
            context_part = f"""
📺 **영상 {i+1}** [{doc.video_id}]
📝 **제목**: {doc.title}
📅 **업로드**: {upload_date}
⏱️ **영상 길이**: {duration}
🔍 **연관성 점수**: {doc.similarity:.3f} (매우 높음: 0.8+, 높음: 0.6+, 보통: 0.4+)
📍 **청크 위치**: {chunk_index}번째 구간
📖 **관련 내용**: {doc.content[:400]}...
🎯 **이 영상의 가치**: {'핵심 답변 제공' if doc.similarity > 0.7 else '보조 정보 제공' if doc.similarity > 0.5 else '참고 자료'}
---"""
            context_parts.append(context_part)
        
        context = "\n".join(context_parts)
        
        if len(context) > max_context_length:
            context = context[:max_context_length] + "\n...(내용 생략)"
        
        return context
    
    def _get_json_schema_instruction(self, config: AnswerConfig) -> str:
        """JSON 스키마 지시사항 생성 (명확하고 강제적)"""
        
        # 스타일별 예시 (도움이 되는 답변 중심)
        if config.style == AnswerStyle.BULLET_POINTS:
            format_example = """
{
  "answer": "## 🎯 핵심 답변\\n\\n• **영상 기반 정보**: 구체적인 설명 내용 [video_id_1]\\n• **추가 전문 지식**: 영상에서 다루지 않았지만 관련된 유용한 정보\\n• **실전 조언**: 종합적인 가이드 및 주의사항 [video_id_2]\\n\\n## 📚 정보 출처 구분\\n- 🎬 영상 정보: [video_id] 표시\\n- 🧠 전문 지식: 일반적으로 알려진 정보",
  "key_points": [
    "영상에서 확인된 핵심 포인트",
    "추가로 알아두면 좋은 관련 정보", 
    "실용적인 조언 및 주의사항"
  ],
  "video_connections": [
    {
      "video_id": "20231201_investment_guide",
      "title": "부동산 투자 가이드",
      "relevance_score": 0.92,
      "connection_reason": "질문의 핵심 주제인 투자 전략을 직접적으로 다루고 있음",
      "key_content": "도쿄 아파트 투자 수익률 분석 및 실전 팁",
      "usage_in_answer": "첫 번째 포인트의 근거 자료로 활용"
    }
  ],
  "additional_insights": "영상에서 직접 다루지 않았지만 질문 해결에 도움되는 보완 정보들",
  "sources": [
    {"video_id": "20231201_investment_guide", "relevance": "투자 전략 설명"},
    {"video_id": "20231215_market_analysis", "relevance": "시장 분석 내용"}
  ],
  "confidence": 0.85,
  "summary": "영상 정보와 전문 지식을 종합한 완전한 답변"
}"""
        elif config.style == AnswerStyle.DETAILED_EXPLANATION:
            format_example = """
{
  "answer": "## 📋 상세 분석\\n\\n**영상 기반 분석**: 자세한 설명... [video_id_1]\\n\\n**보완 정보**: 영상에서 다루지 않은 관련 전문 지식\\n\\n**종합 결론**: 완전한 분석 결과 [video_id_2]",
  "key_points": ["영상 확인 요점", "추가 전문 지식", "실용적 결론"],
  "video_connections": [
    {
      "video_id": "actual_video_id",
      "title": "실제 영상 제목",
      "relevance_score": 0.88,
      "connection_reason": "상세 분석의 근거가 되는 핵심 내용 포함",
      "key_content": "영상에서 다룬 구체적 내용",
      "usage_in_answer": "상세 분석 섹션의 주요 근거로 활용"
    }
  ],
  "additional_insights": "영상에 없지만 분석에 필요한 보완 정보",
  "sources": [{"video_id": "actual_video_id", "relevance": "관련성 설명"}],
  "confidence": 0.80,
  "summary": "영상과 전문지식을 종합한 완전한 분석"
}"""
        else:  # SUMMARY
            format_example = """
{
  "answer": "## 📝 요약\\n\\n🎬 **영상 요약**: 핵심 내용 정리... [video_id_1]\\n🧠 **추가 정보**: 보완적인 전문 지식\\n💡 **결론**: 종합적인 요약",
  "key_points": ["영상 핵심 요점", "보완 정보", "최종 결론"],
  "video_connections": [
    {
      "video_id": "actual_video_id",
      "title": "실제 영상 제목",
      "relevance_score": 0.85,
      "connection_reason": "요약의 핵심 근거가 되는 내용",
      "key_content": "영상의 주요 포인트",
      "usage_in_answer": "요약 내용의 직접적 근거"
    }
  ],
  "additional_insights": "영상 외 유용한 관련 정보",
  "sources": [{"video_id": "actual_video_id", "relevance": "관련성"}],
  "confidence": 0.75,
  "summary": "완전하고 유용한 요약"
}"""
        
        return f"""
## ⚠️ 응답 형식 (JSON 필수)

**반드시 다음 JSON 형식으로만 응답하세요:**

```json
{format_example.strip()}
```

## 📋 필수 요구사항:

1. **JSON 형식 필수**: 다른 텍스트 없이 오직 JSON만 출력
2. **실제 video_id 사용**: [video_id_1] 형태로 실제 영상 ID 표시
3. **video_connections 배열**: 각 영상과 질문의 연관성을 상세히 설명
4. **additional_insights 필드**: 영상에 없지만 유용한 보완 정보 제공
5. **sources 배열**: 각 출처의 video_id와 relevance 명시
6. **confidence**: 0.0~1.0 사이의 정확한 수치
7. **한글 사용**: 모든 내용은 한글로 작성

## 🎯 도움이 되는 답변 작성 방법:
- **영상 우선**: 가능한 한 영상 내용을 주요 근거로 활용
- **적극적 보완**: 영상에 없는 내용도 질문 해결에 도움된다면 적극 포함
- **출처 구분**: 영상 정보(🎬)와 일반 전문지식(🧠)을 명확히 구분
- **완전한 답변**: 질문자가 만족할 수 있는 완전하고 유용한 정보 제공
- **실용성 중심**: 이론보다는 실제 도움이 되는 구체적 정보 우선
- **관련성 확장**: 질문과 간접적으로라도 관련된 유용한 정보 포함
"""
    
    def _extract_json_from_response(self, response_text: str) -> Dict[str, Any]:
        """LLM 응답에서 JSON 추출 (강화된 파싱)"""
        try:
            # JSON 코드블록 찾기
            import re
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', response_text, re.DOTALL)
            
            if json_match:
                json_str = json_match.group(1)
            else:
                # 코드블록 없으면 직접 JSON 찾기
                json_match = re.search(r'(\{.*\})', response_text, re.DOTALL)
                if json_match:
                    json_str = json_match.group(1)
                else:
                    raise ValueError("JSON 형식을 찾을 수 없습니다")
            
            # JSON 파싱 시도
            try:
                parsed_json = json.loads(json_str)
            except json.JSONDecodeError as e:
                print(f"⚠️ JSON 파싱 실패: {e}")
                # 불완전한 JSON 복구 시도
                parsed_json = self._repair_incomplete_json(json_str, response_text)
            
            # 필수 필드 검증 및 타입 안전성 보장
            required_fields = ['answer', 'confidence', 'sources']
            for field in required_fields:
                if field not in parsed_json:
                    if field == 'answer':
                        parsed_json[field] = response_text[:500] + "..." if len(response_text) > 500 else response_text
                    elif field == 'confidence':
                        parsed_json[field] = 0.5
                    elif field == 'sources':
                        parsed_json[field] = []
            
            # 타입 안전성 확보
            if not isinstance(parsed_json.get('answer'), str):
                parsed_json['answer'] = str(parsed_json.get('answer', ''))
            
            if not isinstance(parsed_json.get('confidence'), (int, float)):
                try:
                    parsed_json['confidence'] = float(parsed_json.get('confidence', 0.5))
                except (ValueError, TypeError):
                    parsed_json['confidence'] = 0.5
            
            if not isinstance(parsed_json.get('sources'), list):
                parsed_json['sources'] = []
            
            return parsed_json
            
        except Exception as e:
            print(f"⚠️ JSON 파싱 실패: {e}")
            # 안전한 fallback 응답
            clean_text = response_text.replace('\n', ' ').strip()
            return {
                "answer": clean_text[:1000] + "..." if len(clean_text) > 1000 else clean_text,
                "key_points": [],
                "sources": [],
                "confidence": 0.3,
                "summary": "JSON 파싱 실패로 인한 기본 응답"
            }
    
    def _repair_incomplete_json(self, json_str: str, full_response: str) -> Dict[str, Any]:
        """불완전한 JSON 복구 시도"""
        try:
            # 기본 구조 추출
            result = {}
            
            # answer 필드 추출
            answer_match = re.search(r'"answer":\s*"([^"]*(?:\\.[^"]*)*)"', json_str, re.DOTALL)
            if answer_match:
                result['answer'] = answer_match.group(1).replace('\\"', '"').replace('\\n', '\n')
            else:
                # answer 필드가 없으면 전체 응답에서 추출
                result['answer'] = full_response[:800]
            
            # key_points 추출
            key_points_match = re.search(r'"key_points":\s*\[(.*?)\]', json_str, re.DOTALL)
            if key_points_match:
                points_str = key_points_match.group(1)
                # 개별 포인트 추출
                points = re.findall(r'"([^"]*(?:\\.[^"]*)*)"', points_str)
                result['key_points'] = [p.replace('\\"', '"') for p in points]
            else:
                result['key_points'] = []
            
            # sources 추출 (간단한 형태)
            sources_match = re.search(r'"sources":\s*\[(.*?)\]', json_str, re.DOTALL)
            if sources_match:
                result['sources'] = []
                # video_id 패턴 찾기
                video_ids = re.findall(r'"video_id":\s*"([^"]*)"', sources_match.group(1))
                for vid in video_ids:
                    result['sources'].append({"video_id": vid, "relevance": "복구된 정보"})
            else:
                result['sources'] = []
            
            # confidence 추출
            conf_match = re.search(r'"confidence":\s*([0-9.]+)', json_str)
            if conf_match:
                try:
                    result['confidence'] = float(conf_match.group(1))
                except:
                    result['confidence'] = 0.5
            else:
                result['confidence'] = 0.5
            
            print(f"🔧 JSON 복구 성공: {len(result)} 필드")
            return result
            
        except Exception as e:
            print(f"⚠️ JSON 복구 실패: {e}")
            return {
                "answer": full_response[:800],
                "key_points": [],
                "sources": [],
                "confidence": 0.3,
                "summary": "JSON 복구 실패"
            }
    
    def _should_use_react(self, query: str, search_result: SearchResult) -> bool:
        """ReAct 패턴 사용 여부 결정"""
        # 검색 결과가 부족하거나 신뢰도가 낮을 때만
        if len(search_result.documents) < 2:
            return True
        
        avg_similarity = sum(doc.similarity for doc in search_result.documents) / len(search_result.documents)
        if avg_similarity < 0.4:
            return True
        
        # 복잡한 쿼리 패턴 (최신 정보, 비교, 예측 등)
        react_patterns = [
            r'\b(최신|최근|현재|지금|오늘)\b',
            r'\b(비교|차이|vs|대비)\b', 
            r'\b(예측|전망|미래|계획)\b',
            r'\b(추천|제안|조언)\b'
        ]
        
        import re
        for pattern in react_patterns:
            if re.search(pattern, query.lower()):
                return True
        
        return False
    
    def _apply_react_pattern(self, query: str, initial_context: str, channel_name: str) -> str:
        """ReAct 패턴 적용 (추가 정보 필요시)"""
        try:
            react_prompt = f"""당신은 {channel_name} 채널 전문가입니다. 현재 정보로 질문에 완전히 답할 수 있는지 판단하세요.

## 현재 질문
{query}

## 현재 가진 정보
{initial_context[:500]}...

## 판단 과정 (ReAct)
Thought: 현재 정보로 질문에 충분히 답할 수 있는가?
Action: [SUFFICIENT] 또는 [NEED_MORE_INFO: 필요한 정보 유형]
Observation: 정보 충족도 평가
Final Answer: 다음 단계 결정

간단히 판단 결과만 응답하세요: "SUFFICIENT" 또는 "NEED_MORE_INFO: ..."
"""
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": f"당신은 {channel_name} 채널 전문 정보 평가자입니다."},
                    {"role": "user", "content": react_prompt}
                ],
                max_tokens=100,
                temperature=0.3
            )
            
            result = response.choices[0].message.content.strip()
            print(f"🔧 ReAct 판단: {result}")
            
            if "NEED_MORE_INFO" in result:
                return f"현재 정보로는 부족합니다. {result}"
            else:
                return "현재 정보로 충분합니다."
                
        except Exception as e:
            print(f"⚠️ ReAct 패턴 실패: {e}")
            return "현재 정보로 충분합니다."
    
    def _generate_initial_answer(self, request: AnswerRequest) -> str:
        """초기 답변 생성 (적응형 Temperature 적용)"""
        # 채널별 경량 프롬프트 로드
        channel_prompt = request.channel_prompt or self._load_channel_prompt(request.search_result.channel_name)
        
        # 컨텍스트 구성 (비디오 ID 포함)
        context = self._build_context(request.search_result)
        
        # 검색된 비디오 ID 목록 생성
        video_ids = [doc.video_id for doc in request.search_result.documents]
        video_list = ", ".join(video_ids) if video_ids else "없음"
        
        # JSON 스키마 지시사항
        json_instruction = self._get_json_schema_instruction(request.config)
        
        # 적응형 Temperature 계산 (전문가 조언 반영)
        adaptive_temp = self._get_adaptive_temperature(request.original_query, request.config)
        
        # 도움이 되는 답변 중심 시스템 프롬프트
        system_message = f"{channel_prompt.system_prompt} {channel_prompt.tone}으로 답변하되, 영상에 없는 내용이라도 질문 해결에 도움이 된다면 적극적으로 포함하여 완전하고 유용한 답변을 제공하세요."
        
        user_prompt = f"""## 검색된 컨텍스트 ({request.search_result.channel_name} 채널)
{context}

## 사용 가능한 비디오 ID 목록
{video_list}

## 사용자 질문
{request.original_query}

## 🎯 도움이 되는 답변 제공 지시사항
- **영상 우선 활용**: {request.search_result.channel_name} 채널의 영상 내용을 주요 근거로 활용
- **영상별 연관성 명시**: 각 영상이 질문과 어떻게 연결되는지 구체적으로 설명
- **보완 정보 제공**: 영상에서 직접 다루지 않지만 질문과 관련된 유용한 정보도 포함
- **video_connections 포함**: 영상과 질문의 연관성 점수와 구체적 근거 포함
- **적극적 답변**: 영상 정보 + 채널 특성 + 일반적 전문 지식을 종합하여 최대한 도움되는 답변 제공
- **정보 구분**: 영상 기반 정보와 추가 전문 지식을 명확히 구분하여 표시
- **스타일**: {request.config.style.value} 형식으로 작성
- **출처 표시**: [video_id] 형태로 영상 ID 명시적 표시

{json_instruction}

**핵심**: 사용자에게 최대한 도움이 되는 답변을 제공하세요. 
영상 내용을 주요 근거로 하되, 질문 해결에 필요한 추가 정보도 적극적으로 포함하여 완전한 답변을 만드세요.
정보의 출처(영상 vs 일반 지식)는 명확히 구분하여 표시하세요."""
        
        try:
            start_time = time.time()
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=request.config.max_tokens,
                temperature=adaptive_temp  # 적응형 Temperature 적용
            )
            
            generation_time = (time.time() - start_time) * 1000
            initial_answer = response.choices[0].message.content.strip()
            
            print(f"📝 초기 답변 생성 완료 ({generation_time:.1f}ms, temp={adaptive_temp})")
            return initial_answer
            
        except Exception as e:
            print(f"❌ 초기 답변 생성 실패: {e}")
            return json.dumps({
                "answer": f"답변 생성 중 오류가 발생했습니다: {e}",
                "key_points": [],
                "sources": [],
                "confidence": 0.0,
                "summary": "오류 발생"
            }, ensure_ascii=False)
    
    def _apply_self_refine(self, initial_answer: str, query: str, channel_name: str) -> str:
        """Self-Refine 1회 적용 (토큰 폭증 방지)"""
        try:
            # 초기 답변에서 JSON 추출
            initial_json = self._extract_json_from_response(initial_answer)
            
            if initial_json.get('confidence', 0) > 0.8:
                print("🎯 초기 답변 신뢰도 높음, Self-Refine 생략")
                return initial_answer
            
            refine_prompt = f"""당신은 {channel_name} 채널 전문 답변 품질 검토자입니다.

## 원본 질문
{query}

## 초기 답변 (JSON)
{json.dumps(initial_json, ensure_ascii=False, indent=2)}

## 개선 지시사항
1. 답변의 정확성과 완성도를 검토
2. 누락된 중요 정보가 있는지 확인  
3. 출처 표시가 적절한지 점검
4. 신뢰도를 재평가

개선된 답변을 동일한 JSON 형식으로 작성하세요. 20% 이상 품질 개선을 목표로 하되, 기존 답변이 이미 우수하다면 유지하세요."""

            start_time = time.time()
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": f"당신은 {channel_name} 채널 전문 답변 검토자입니다."},
                    {"role": "user", "content": refine_prompt}
                ],
                max_tokens=800,
                temperature=0.5
            )
            
            refine_time = (time.time() - start_time) * 1000
            refined_answer = response.choices[0].message.content.strip()
            
            print(f"✨ Self-Refine 완료 ({refine_time:.1f}ms)")
            return refined_answer
            
        except Exception as e:
            print(f"⚠️ Self-Refine 실패: {e}")
            return initial_answer
    
    def generate_answer(self, request: AnswerRequest) -> AnswerResponse:
        """메인 답변 생성 파이프라인"""
        start_time = time.time()
        
        print(f"💬 답변 생성 시작: {request.query_id}")
        
        # 0. ReAct 패턴 적용 여부 판단
        react_steps = []
        if request.config.enable_react:
            context_preview = self._build_context(request.search_result, 500)
            if self._should_use_react(request.original_query, request.search_result):
                react_result = self._apply_react_pattern(request.original_query, context_preview, request.search_result.channel_name)
                react_steps.append(react_result)
        
        # 1. 초기 답변 생성
        initial_answer = self._generate_initial_answer(request)
        
        # 2. Self-Refine 적용 (1회 제한)
        final_answer = initial_answer
        self_refined = False
        
        if request.config.enable_self_refine:
            refined_answer = self._apply_self_refine(initial_answer, request.original_query, request.search_result.channel_name)
            if refined_answer != initial_answer:
                final_answer = refined_answer
                self_refined = True
        
        # 3. JSON 파싱 및 검증
        answer_json = self._extract_json_from_response(final_answer)
        
        # 4. 사용된 소스 추출 (안전하게)
        sources_used = []
        try:
            for doc in request.search_result.documents:
                # 안전한 필드 값 검사
                for field in ['answer', 'key_points']:
                    field_value = answer_json.get(field, '')
                    
                    # 다양한 타입을 안전하게 문자열로 변환
                    if isinstance(field_value, list):
                        field_str = ' '.join(str(item) for item in field_value)
                    elif isinstance(field_value, str):
                        field_str = field_value
                    else:
                        field_str = str(field_value) if field_value else ''
                    
                    if doc.video_id in field_str:
                        sources_used.append(doc.video_id)
                        break  # 이미 찾았으므로 다음 문서로
        except Exception as e:
            print(f"⚠️ 소스 추출 오류: {e}")
        
        # 소스가 비어있으면 검색된 영상들 포함 (전문가 조언: 4-5개 최적)
        if not sources_used:
            sources_used = [doc.video_id for doc in request.search_result.documents[:5]]  # Choice Overload 방지
        
        generation_time = (time.time() - start_time) * 1000
        
        # 토큰 사용량 추정 (안전한 계산)
        try:
            # 원본 쿼리 토큰 수 계산
            query_tokens = len(request.original_query.split()) * 1.3 if isinstance(request.original_query, str) else 10
            
            # 답변 토큰 수 계산 (안전하게)
            answer_text = answer_json.get('answer', '')
            if isinstance(answer_text, list):
                # 리스트인 경우 문자열로 변환
                answer_text = ' '.join(str(item) for item in answer_text)
            elif not isinstance(answer_text, str):
                # 문자열이 아닌 경우 문자열로 변환
                answer_text = str(answer_text)
            
            completion_tokens = len(answer_text.split()) * 1.3 if answer_text else 5
            
            token_usage = {
                "prompt_tokens": int(query_tokens),
                "completion_tokens": int(completion_tokens),
                "total_tokens": int(query_tokens + completion_tokens)
            }
        except Exception as e:
            print(f"⚠️ 토큰 계산 오류: {e}, 기본값 사용")
            token_usage = {
                "prompt_tokens": 50,
                "completion_tokens": 100,
                "total_tokens": 150
            }
        
        print(f"✅ 답변 생성 완료 ({generation_time:.1f}ms)")
        
        return AnswerResponse(
            query_id=request.query_id,
            answer=answer_json.get('answer', '답변 생성 실패'),
            confidence=float(answer_json.get('confidence', 0.5)),
            sources_used=sources_used,
            generation_time_ms=generation_time,
            self_refined=self_refined,
            react_steps=react_steps,
            token_usage=token_usage
        ) 