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
        
        print("💬 Answer Pipeline 초기화 완료")
    
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
        """검색 결과를 컨텍스트로 구성 (토큰 효율성 고려)"""
        context_parts = []
        current_length = 0
        
        for i, doc in enumerate(search_result.documents):
            # 영상 정보 헤더 (간결)
            header = f"[영상 {i+1}] {doc.title}"
            
            # 내용 요약 (토큰 절약)
            content_preview = doc.content[:400] + "..." if len(doc.content) > 400 else doc.content
            
            part = f"{header}\n{content_preview}"
            part_length = len(part)
            
            if current_length + part_length > max_context_length:
                break
                
            context_parts.append(part)
            current_length += part_length
        
        return "\n\n".join(context_parts)
    
    def _get_json_schema_instruction(self, config: AnswerConfig) -> str:
        """JSON 스키마 지시사항 생성"""
        schema_fields = []
        
        if config.style == AnswerStyle.BULLET_POINTS:
            schema_fields = [
                f"answer: 최대 {config.max_bullets}개 bullet point로 구성된 메인 답변",
                "key_points: 핵심 포인트 배열 (3-5개)",
                "sources: 사용된 영상 ID 배열",
                f"confidence: 답변 신뢰도 (0.0-1.0)",
                "summary: 한 줄 핵심 요약"
            ]
        elif config.style == AnswerStyle.STRUCTURED:
            schema_fields = [
                "answer: 구조화된 답변 (헤딩과 섹션 포함)",
                "key_points: 각 섹션별 핵심 포인트",
                "sources: 사용된 영상 ID 배열", 
                "confidence: 답변 신뢰도 (0.0-1.0)",
                "summary: 전체 내용 요약"
            ]
        else:
            schema_fields = [
                "answer: 자연스러운 대화형 답변",
                "key_points: 핵심 내용 요약",
                "sources: 사용된 영상 ID 배열",
                "confidence: 답변 신뢰도 (0.0-1.0)", 
                "summary: 한 줄 요약"
            ]
        
        return f"""

## 📝 출력 형식 (JSON)
반드시 다음 JSON 형식으로 응답하세요:
```json
{{
  {chr(10).join([f'  "{field.split(":")[0]}": {field.split(":", 1)[1].strip()}' for field in schema_fields])}
}}
```

JSON 외의 다른 텍스트는 출력하지 마세요."""
    
    def _extract_json_from_response(self, response_text: str) -> Dict[str, Any]:
        """LLM 응답에서 JSON 추출"""
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
            
            # JSON 파싱
            parsed_json = json.loads(json_str)
            
            # 필수 필드 검증
            required_fields = ['answer', 'confidence', 'sources']
            for field in required_fields:
                if field not in parsed_json:
                    raise ValueError(f"필수 필드 누락: {field}")
            
            return parsed_json
            
        except Exception as e:
            print(f"⚠️ JSON 파싱 실패: {e}")
            # Fallback: 기본 구조로 응답
            return {
                "answer": response_text,
                "key_points": [],
                "sources": [],
                "confidence": 0.5,
                "summary": "JSON 파싱 실패로 인한 기본 응답"
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
        """초기 답변 생성"""
        # 채널별 경량 프롬프트 로드
        channel_prompt = request.channel_prompt or self._load_channel_prompt(request.search_result.channel_name)
        
        # 컨텍스트 구성
        context = self._build_context(request.search_result)
        
        # JSON 스키마 지시사항
        json_instruction = self._get_json_schema_instruction(request.config)
        
        # 경량 프롬프트 구성
        system_message = f"{channel_prompt.system_prompt} {channel_prompt.tone}으로 답변하세요."
        
        user_prompt = f"""## 검색된 컨텍스트 ({request.search_result.channel_name} 채널)
{context}

## 사용자 질문
{request.original_query}

## 답변 요구사항
- {request.search_result.channel_name} 채널의 정보만 활용
- {request.config.style.value} 스타일로 작성
- 출처를 명확히 표시 ([영상 1], [영상 2] 등)
- 모르는 내용은 추측하지 말고 "정보 부족" 명시

{json_instruction}"""
        
        try:
            start_time = time.time()
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=request.config.max_tokens,
                temperature=request.config.temperature
            )
            
            generation_time = (time.time() - start_time) * 1000
            initial_answer = response.choices[0].message.content.strip()
            
            print(f"📝 초기 답변 생성 완료 ({generation_time:.1f}ms)")
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
        
        # 4. 사용된 소스 추출
        sources_used = []
        for doc in request.search_result.documents:
            if any(doc.video_id in str(answer_json.get(field, '')) for field in ['answer', 'key_points']):
                sources_used.append(doc.video_id)
        
        # 소스가 비어있으면 검색된 영상들 포함
        if not sources_used:
            sources_used = [doc.video_id for doc in request.search_result.documents[:3]]
        
        generation_time = (time.time() - start_time) * 1000
        
        # 토큰 사용량 추정 (간단한 계산)
        token_usage = {
            "prompt_tokens": len(request.original_query.split()) * 1.3,  # 근사치
            "completion_tokens": len(answer_json.get('answer', '').split()) * 1.3,
            "total_tokens": 0
        }
        token_usage["total_tokens"] = token_usage["prompt_tokens"] + token_usage["completion_tokens"]
        
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