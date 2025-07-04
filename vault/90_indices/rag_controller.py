#!/usr/bin/env python3
"""
RAG Controller - Search-First & Prompt-Light 통합 제어
파이프라인 통합 + 조건부 실행 + 캐싱 + 성능 최적화

조언 기반 아키텍처:
- 검색 품질을 '하드'하게 올리고, 프롬프트는 '심플+검증'으로 유지
- LLM 호출·비용을 캐싱과 조건부 파이프라인으로 절감
- 800ms → < 500ms 목표
"""

import os
import time
import uuid
from typing import Optional, Dict, Any, List
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

from schemas import (
    SearchQuery, SearchConfig, SearchResult,
    AnswerRequest, AnswerResponse, AnswerConfig, 
    RAGResponse, QueryType, AnswerStyle
)
from search_pipeline import SearchPipeline
from answer_pipeline import AnswerPipeline
from semantic_cache import SemanticCache, CachedLLMClient

# 환경변수 로드
load_dotenv()

class RAGController:
    """Search-First & Prompt-Light RAG 시스템 통합 컨트롤러"""
    
    def __init__(self, chroma_path: Path, model: str = "deepseek-chat", enable_cache: bool = True):
        """초기화"""
        self.model = model
        self.chroma_path = chroma_path
        
        print(f"🚀 RAG Controller 초기화 시작 (모델: {model})")
        
        # 캐시 시스템 초기화
        self.cache = None
        self.cached_client = None
        
        if enable_cache:
            try:
                cache_dir = chroma_path.parent / "cache"
                self.cache = SemanticCache(cache_dir)
                
                # DeepSeek 클라이언트
                api_key = os.getenv('DEEPSEEK_API_KEY')
                if api_key:
                    raw_client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com/v1")
                    self.cached_client = CachedLLMClient(raw_client, self.cache)
                    print("✅ 캐시 시스템 활성화")
                else:
                    print("⚠️ DEEPSEEK_API_KEY 없음, 캐시 비활성화")
            except Exception as e:
                print(f"⚠️ 캐시 시스템 초기화 실패: {e}")
        
        # 검색 파이프라인 초기화
        try:
            self.search_pipeline = SearchPipeline(chroma_path, model)
            print("✅ Search Pipeline 로드됨")
        except Exception as e:
            raise ValueError(f"❌ Search Pipeline 초기화 실패: {e}")
        
        # 답변 파이프라인 초기화  
        try:
            prompts_dir = chroma_path.parent / "prompts"
            self.answer_pipeline = AnswerPipeline(model, prompts_dir)
            print("✅ Answer Pipeline 로드됨")
        except Exception as e:
            raise ValueError(f"❌ Answer Pipeline 초기화 실패: {e}")
        
        # 기본 설정 (매우 관대하게)
        self.default_search_config = SearchConfig(
            max_results=15,  # 10 → 15로 증가
            enable_hyde=True,
            enable_rewrite=True,
            enable_rerank=True,
            rerank_threshold=0.2,  # 0.3 → 0.2로 낮춤
            similarity_threshold=0.05  # 0.15 → 0.05로 대폭 낮춤 (매우 관대)
        )
        
        self.default_answer_config = AnswerConfig(
            style=AnswerStyle.BULLET_POINTS,  # 기본 스타일 명시적 설정
            enable_self_refine=True,
            enable_react=False,  # 기본적으로 비활성화, 필요시에만
            max_tokens=1200,  # 800 → 1200으로 증가 (JSON 응답 고려)
            temperature=0.7
        )
        
        print("🎯 RAG Controller 초기화 완료")
    
    def _optimize_search_config(self, query: str, query_type: QueryType) -> SearchConfig:
        """쿼리 타입에 따른 검색 설정 최적화 (관대한 검색)"""
        config = SearchConfig(**self.default_search_config.dict())
        
        # 단순한 쿼리는 경량화하지만 충분한 문서 확보
        if query_type == QueryType.SIMPLE:
            config.enable_rerank = False  # Re-rank 생략
            config.max_results = 12       # 8 → 12로 증가
            config.similarity_threshold = 0.03  # 0.1 → 0.03으로 매우 관대하게
            print("🔧 단순 쿼리: 관대한 경량 검색 모드")
            
        # 복잡한 쿼리는 전체 파이프라인 활용
        elif query_type == QueryType.COMPLEX:
            config.enable_rerank = True
            config.max_results = 15       # 10 → 15로 증가
            config.rerank_threshold = 0.15  # 0.25 → 0.15로 낮춤
            config.similarity_threshold = 0.08  # 0.2 → 0.08로 낮춤
            print("🔧 복잡 쿼리: 관대한 고품질 검색 모드")
            
        # 사실 확인 쿼리는 정확도 우선이지만 여전히 관대하게
        elif query_type == QueryType.FACTUAL:
            config.enable_rerank = True
            config.max_results = 12       # 8 → 12로 증가
            config.similarity_threshold = 0.15  # 0.25 → 0.15로 낮춤
            print("🔧 사실 확인: 관대한 정확도 우선 모드")
            
        # 분석적 쿼리는 가장 폭넓은 검색
        elif query_type == QueryType.ANALYTICAL:
            config.enable_rerank = True
            config.max_results = 20       # 12 → 20으로 대폭 증가
            config.similarity_threshold = 0.02  # 0.12 → 0.02로 매우 관대하게
            print("🔧 분석적 쿼리: 최대한 관대한 폭넓은 검색 모드")
        
        return config
    
    def _optimize_answer_config(self, query: str, search_result: SearchResult) -> AnswerConfig:
        """검색 결과에 따른 답변 설정 최적화"""
        config = AnswerConfig(**self.default_answer_config.dict())
        
        # 검색 결과가 우수하면 Self-Refine 생략
        if search_result.documents:
            avg_similarity = sum(doc.similarity for doc in search_result.documents) / len(search_result.documents)
            
            if avg_similarity > 0.7:
                config.enable_self_refine = False
                print("🔧 고품질 검색 결과: Self-Refine 생략")
            
            # 검색 결과가 부족하면 ReAct 활성화
            if len(search_result.documents) < 3 or avg_similarity < 0.4:
                config.enable_react = True
                print("🔧 검색 결과 부족: ReAct 활성화")
        
        return config
    
    def _should_use_fast_mode(self, query: str) -> bool:
        """빠른 모드 사용 여부 결정 (성능 우선, 기준 완화)"""
        # 매우 짧은 질문만 빠른 모드 (20자 → 10자로 변경)
        if len(query) < 10:
            return True
        
        # 명확히 간단한 패턴만 빠른 모드
        fast_patterns = [
            r'^\s*(뭐|무엇|정의|설명|의미)\s*\??\s*$',  # 단일 단어 질문
            r'^\s*(언제|어디|누구|몇)\s+.*\??\s*$',     # 간단한 의문사 질문
            r'^\s*(간단히|빠르게|요약)\s+.*$'           # 명시적 요약 요청
        ]
        
        import re
        for pattern in fast_patterns:
            if re.search(pattern, query):
                return True
        
        return False
    
    def query(self, query: str, channel_name: str, 
              search_config: Optional[SearchConfig] = None,
              answer_config: Optional[AnswerConfig] = None,
              fast_mode: bool = False) -> RAGResponse:
        """메인 RAG 쿼리 처리"""
        start_time = time.time()
        query_id = str(uuid.uuid4())[:8]
        
        print(f"🔍 RAG Query 시작: {query_id} - '{query}' in {channel_name}")
        
        # 빠른 모드 자동 판단
        if not fast_mode:
            fast_mode = self._should_use_fast_mode(query)
        
        if fast_mode:
            print("⚡ 빠른 모드 활성화")
        
        try:
            # 1. 검색 쿼리 구성
            search_query = SearchQuery(
                query_id=query_id,
                original_query=query,
                channel_name=channel_name
            )
            
            # 2. 검색 설정 최적화
            if search_config is None:
                search_config = self._optimize_search_config(query, search_query.query_type)
            
            # 빠른 모드에서도 관대한 결과 확보
            if fast_mode:
                search_config.enable_rerank = False
                search_config.enable_rewrite = False
                search_config.max_results = 12    # 8 → 12로 증가
                search_config.similarity_threshold = 0.03  # 매우 관대하게
            
            # 3. 검색 실행
            search_start = time.time()
            search_result = self.search_pipeline.search(search_query, search_config)
            search_time = (time.time() - search_start) * 1000
            
            # 4. 스마트 fallback 처리
            if not search_result.documents:
                # 채널별 대표 정보 검색 시도
                fallback_result = self._get_channel_fallback_info(channel_name, query)
                
                if fallback_result:
                    print(f"🔄 Fallback 정보 제공: {len(fallback_result.documents)}개 문서")
                    search_result = fallback_result
                else:
                    return RAGResponse(
                        query_id=query_id,
                        channel_name=channel_name,
                        original_query=query,
                        answer=self._generate_smart_fallback_answer(channel_name, query),
                        confidence=0.3,
                        total_time_ms=(time.time() - start_time) * 1000,
                        search_time_ms=search_time,
                        answer_time_ms=0,
                        documents_found=0,
                        sources_used=[]
                    )
            
            # 5. 답변 설정 최적화
            if answer_config is None:
                answer_config = self._optimize_answer_config(query, search_result)
            
            # 빠른 모드에서는 답변 단순화
            if fast_mode:
                answer_config.enable_self_refine = False
                answer_config.enable_react = False
                answer_config.max_tokens = 800  # 400 → 800으로 증가
            
            # 6. 답변 생성 요청 구성
            answer_request = AnswerRequest(
                query_id=query_id,
                original_query=query,
                search_result=search_result,
                config=answer_config
            )
            
            # 7. 답변 생성 실행
            answer_start = time.time()
            answer_response = self.answer_pipeline.generate_answer(answer_request)
            answer_time = (time.time() - answer_start) * 1000
            
            total_time = (time.time() - start_time) * 1000
            
            # 8. 최종 응답 구성
            rag_response = RAGResponse(
                query_id=query_id,
                channel_name=channel_name,
                original_query=query,
                answer=answer_response.answer,
                confidence=answer_response.confidence,
                total_time_ms=total_time,
                search_time_ms=search_time,
                answer_time_ms=answer_time,
                documents_found=len(search_result.documents),
                sources_used=answer_response.sources_used,
                search_quality={
                    "hyde_used": search_result.hyde_used,
                    "rewrite_used": search_result.rewrite_used,
                    "rerank_used": search_result.rerank_used,
                    "avg_similarity": sum(doc.similarity for doc in search_result.documents) / len(search_result.documents) if search_result.documents else 0.0
                },
                debug_info={
                    "query_type": search_query.query_type.value,
                    "fast_mode": fast_mode,
                    "self_refined": answer_response.self_refined,
                    "react_steps": answer_response.react_steps,
                    "token_usage": answer_response.token_usage,
                    "cache_used": self.cache is not None
                }
            )
            
            # 성능 목표 체크
            if total_time > 500:
                print(f"⚠️ 성능 목표 초과: {total_time:.1f}ms > 500ms")
            else:
                print(f"✅ 성능 목표 달성: {total_time:.1f}ms < 500ms")
            
            print(f"🎯 RAG Query 완료: {query_id} ({total_time:.1f}ms)")
            return rag_response
            
        except Exception as e:
            total_time = (time.time() - start_time) * 1000
            print(f"❌ RAG Query 실패: {query_id} - {e}")
            
            return RAGResponse(
                query_id=query_id,
                channel_name=channel_name,
                original_query=query,
                answer=f"죄송합니다. 처리 중 오류가 발생했습니다: {e}",
                confidence=0.0,
                total_time_ms=total_time,
                search_time_ms=0,
                answer_time_ms=0,
                documents_found=0,
                sources_used=[],
                debug_info={"error": str(e)}
            )
    
    def get_available_channels(self) -> List[Dict[str, Any]]:
        """사용 가능한 채널 목록 반환"""
        return self.search_pipeline.chroma_client.list_collections()
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """캐시 통계 조회"""
        if self.cache:
            return self.cache.get_stats()
        return {"cache_enabled": False}
    
    def cleanup_cache(self) -> int:
        """만료된 캐시 정리"""
        if self.cache:
            return self.cache.cleanup_expired()
        return 0
    
    def clear_cache(self) -> bool:
        """전체 캐시 삭제"""
        if self.cache:
            return self.cache.clear()
        return False
    
    def health_check(self) -> Dict[str, Any]:
        """시스템 상태 체크"""
        health_status = {
            "status": "healthy",
            "components": {
                "search_pipeline": True,
                "answer_pipeline": True,
                "cache": self.cache is not None,
                "chroma_db": False
            },
            "performance": {
                "last_query_time": None,
                "cache_hit_rate": 0.0
            }
        }
        
        # ChromaDB 연결 체크
        try:
            collections = self.search_pipeline.chroma_client.list_collections()
            health_status["components"]["chroma_db"] = True
            health_status["chroma_collections"] = len(collections)
        except Exception:
            health_status["components"]["chroma_db"] = False
            health_status["status"] = "degraded"
        
        # 캐시 상태 체크
        if self.cache:
            cache_stats = self.cache.get_stats()
            health_status["performance"]["cache_hit_rate"] = cache_stats["hit_rate"]
        
        return health_status 
    
    def _get_channel_fallback_info(self, channel_name: str, query: str) -> Optional[SearchResult]:
        """채널별 대표 정보 검색 (관련성 낮은 질문에 대한 fallback)"""
        try:
            # 채널별 주요 키워드로 검색
            channel_keywords = {
                "일본 부동산 투자": ["부동산", "투자", "도쿄", "수익률", "아파트", "임대"],
                "竹花貴騎 (Takaki Takehana)": ["마케팅", "비즈니스", "브랜딩", "전략", "성장"],
                "竹花貴騎_Takaki_Takehana": ["마케팅", "비즈니스", "브랜딩", "전략", "성장"]
            }
            
            keywords = channel_keywords.get(channel_name, ["정보", "가이드", "팁"])
            
            # 가장 관련성 높은 키워드로 검색
            for keyword in keywords:
                fallback_query = SearchQuery(
                    query_id=str(uuid.uuid4())[:8],
                    original_query=keyword,
                    channel_name=channel_name
                )
                
                fallback_config = SearchConfig(
                    max_results=5,  # 전문가 조언: 4-5개가 choice overload 방지
                    enable_hyde=False,
                    enable_rewrite=False, 
                    enable_rerank=False,
                    similarity_threshold=0.1  # 매우 관대하게
                )
                
                result = self.search_pipeline.search(fallback_query, fallback_config)
                if result.documents:
                    print(f"🎯 Fallback 키워드 '{keyword}'로 {len(result.documents)}개 문서 발견")
                    return result
            
            return None
            
        except Exception as e:
            print(f"⚠️ Fallback 검색 실패: {e}")
            return None
    
    def _generate_smart_fallback_answer(self, channel_name: str, query: str) -> str:
        """스마트 fallback 답변 생성"""
        channel_info = {
            "일본 부동산 투자": {
                "focus": "일본 부동산 투자 전략과 시장 분석",
                "topics": ["도쿄 아파트 투자", "임대 수익률", "대출 활용", "시장 동향", "투자 지역 선정"],
                "suggestion": "도쿄 부동산 투자나 임대 수익률에 대해 질문해보세요"
            },
            "竹花貴騎 (Takaki Takehana)": {
                "focus": "마케팅 전략과 비즈니스 성장",
                "topics": ["디지털 마케팅", "브랜드 전략", "사업 확장", "고객 확보", "온라인 비즈니스"],
                "suggestion": "마케팅 전략이나 비즈니스 성장에 대해 질문해보세요"
            },
            "竹花貴騎_Takaki_Takehana": {
                "focus": "마케팅 전략과 비즈니스 성장", 
                "topics": ["디지털 마케팅", "브랜드 전략", "사업 확장", "고객 확보", "온라인 비즈니스"],
                "suggestion": "마케팅 전략이나 비즈니스 성장에 대해 질문해보세요"
            }
        }
        
        info = channel_info.get(channel_name, {
            "focus": "다양한 주제",
            "topics": ["정보", "가이드", "팁"],
            "suggestion": "채널의 주요 주제에 대해 질문해보세요"
        })
        
        return f"""## 🤖 {channel_name} 채널 안내
        
**현재 질문**: "{query}"

죄송합니다. 직접적으로 관련된 정보를 찾지 못했습니다. 

## 🎯 이 채널의 주요 주제
**전문 분야**: {info['focus']}

**다루는 주제들**:
{chr(10).join(f'• {topic}' for topic in info['topics'])}

## 💡 추천 질문
{info['suggestion']}

더 구체적인 질문을 해주시면 관련된 영상 내용을 바탕으로 상세한 답변을 드릴 수 있습니다.""" 