#!/usr/bin/env python3
"""
Y-Data-House RAG 시스템 I/O 스키마 정의
Search-First & Prompt-Light 아키텍처용 JSON 스키마
"""

from typing import List, Dict, Optional, Union, Any
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum

# =============================================================================
# 검색 파이프라인 스키마 (search_pipeline.py)
# =============================================================================

class QueryType(str, Enum):
    """쿼리 타입 분류"""
    SIMPLE = "simple"           # 단순 검색
    COMPLEX = "complex"         # 복잡한 추론 필요
    FACTUAL = "factual"         # 사실 확인
    ANALYTICAL = "analytical"   # 분석적 질문

class SearchDocument(BaseModel):
    """검색된 문서 정보"""
    video_id: str = Field(..., description="YouTube 비디오 ID")
    title: str = Field(..., description="영상 제목")
    content: str = Field(..., description="문서 내용")
    similarity: float = Field(..., ge=0.0, le=1.0, description="유사도 점수")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="추가 메타데이터")
    search_method: str = Field(..., description="검색 방법 (original, hyde, rewritten)")
    rank_score: Optional[float] = Field(None, description="Re-rank 점수")

class SearchQuery(BaseModel):
    """검색 쿼리 정보"""
    query_id: str = Field(..., description="고유 쿼리 ID")
    original_query: str = Field(..., description="원본 사용자 질문")
    channel_name: str = Field(..., description="대상 채널명")
    query_type: QueryType = Field(default=QueryType.SIMPLE, description="쿼리 복잡도")
    timestamp: datetime = Field(default_factory=datetime.now, description="쿼리 시각")
    
    # 검색 최적화 필드
    hyde_document: Optional[str] = Field(None, description="HyDE 생성 문서")
    rewritten_query: Optional[str] = Field(None, description="재작성된 쿼리")
    expansion_terms: List[str] = Field(default_factory=list, description="확장 키워드")

class SearchConfig(BaseModel):
    """검색 설정 - 전문가 조언 반영 버전"""
    max_results: int = Field(default=12, description="벡터 검색 최대 결과 수 (12→top-6 re-rank)")
    similarity_threshold: float = Field(default=0.20, description="1차 필터 유사도 임계값 (하이-리콜)")
    precision_threshold: float = Field(default=0.30, description="2차 필터 정밀도 임계값 (고-정밀)")
    enable_hyde: bool = Field(default=True, description="HyDE 활성화")
    enable_rewrite: bool = Field(default=True, description="Query Rewriting 활성화")
    enable_rerank: bool = Field(default=True, description="Re-ranking 활성화")
    enable_rag_fusion: bool = Field(default=True, description="RAG-Fusion 다중 쿼리 활성화")
    rag_fusion_queries: int = Field(default=4, description="RAG-Fusion 생성 쿼리 수 (3-5개 최적)")
    rerank_threshold: float = Field(default=0.3, description="Re-rank 활성화 임계값")
    rerank_top_k: int = Field(default=6, description="Re-ranking 대상 문서 수 (6개 최적)")

class SearchResult(BaseModel):
    """검색 결과 - RAG-Fusion 지원"""
    query_id: str = Field(..., description="쿼리 ID")
    channel_name: str = Field(..., description="채널명")
    documents: List[SearchDocument] = Field(..., description="검색된 문서들")
    total_found: int = Field(..., description="총 발견된 문서 수")
    search_time_ms: float = Field(..., description="검색 소요 시간(ms)")
    
    # 검색 단계별 정보 - 전문가 조언 반영
    hyde_used: bool = Field(default=False, description="HyDE 사용 여부")
    fusion_used: bool = Field(default=False, description="RAG-Fusion 다중 쿼리 사용 여부")
    rewrite_used: bool = Field(default=False, description="Query Rewrite 사용 여부")
    rerank_used: bool = Field(default=False, description="Re-ranking 사용 여부")
    cache_hit: bool = Field(default=False, description="캐시 히트 여부")

# =============================================================================
# 답변 파이프라인 스키마 (answer_pipeline.py)
# =============================================================================

class AnswerStyle(str, Enum):
    """답변 스타일"""
    BULLET_POINTS = "bullet_points"     # 불릿 포인트
    STRUCTURED = "structured"           # 구조화된 답변
    CONVERSATIONAL = "conversational"   # 대화형
    ANALYTICAL = "analytical"           # 분석형

class AnswerConfig(BaseModel):
    """답변 생성 설정 - 전문가 조언 반영"""
    style: AnswerStyle = Field(default=AnswerStyle.BULLET_POINTS, description="답변 스타일")
    max_bullets: int = Field(default=5, description="최대 불릿 수")
    include_sources: bool = Field(default=True, description="출처 포함 여부")
    enable_self_refine: bool = Field(default=True, description="Self-Refine 활성화")
    enable_react: bool = Field(default=False, description="ReAct 패턴 활성화")
    max_tokens: int = Field(default=650, description="최대 토큰 수 (600-750 최적)")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="기본 생성 온도")
    enable_adaptive_temperature: bool = Field(default=True, description="적응형 Temperature 활성화")
    factual_temperature: float = Field(default=0.4, description="사실형 질문 온도")
    analytical_temperature: float = Field(default=0.65, description="분석형 질문 온도")

class ChannelPrompt(BaseModel):
    """채널별 프롬프트 정보 (경량화)"""
    channel_name: str = Field(..., description="채널명")
    persona: str = Field(..., description="AI 페르소나 (1-2줄)")
    tone: str = Field(..., description="답변 톤")
    expertise_keywords: List[str] = Field(default_factory=list, description="전문 키워드")
    system_prompt: str = Field(..., description="시스템 프롬프트 (간결)")

class AnswerRequest(BaseModel):
    """답변 생성 요청"""
    query_id: str = Field(..., description="쿼리 ID")
    original_query: str = Field(..., description="원본 질문")
    search_result: SearchResult = Field(..., description="검색 결과")
    config: AnswerConfig = Field(default_factory=AnswerConfig, description="답변 설정")
    channel_prompt: Optional[ChannelPrompt] = Field(None, description="채널별 프롬프트")

class AnswerResponse(BaseModel):
    """답변 결과"""
    query_id: str = Field(..., description="쿼리 ID")
    answer: str = Field(..., description="생성된 답변")
    confidence: float = Field(..., ge=0.0, le=1.0, description="답변 신뢰도")
    sources_used: List[str] = Field(..., description="사용된 영상 ID들")
    generation_time_ms: float = Field(..., description="생성 소요 시간(ms)")
    
    # 답변 생성 과정 정보
    self_refined: bool = Field(default=False, description="Self-Refine 적용 여부")
    react_steps: List[str] = Field(default_factory=list, description="ReAct 단계들")
    token_usage: Dict[str, int] = Field(default_factory=dict, description="토큰 사용량")

# =============================================================================
# 캐시 스키마 (semantic_cache.py)
# =============================================================================

class CacheKey(BaseModel):
    """캐시 키 구조"""
    model: str = Field(..., description="사용된 모델명")
    temperature: float = Field(..., description="생성 온도")
    prompt_hash: str = Field(..., description="프롬프트 해시")
    query_hash: str = Field(..., description="쿼리 해시")

class CacheEntry(BaseModel):
    """캐시 엔트리"""
    key: CacheKey = Field(..., description="캐시 키")
    data: Union[SearchResult, AnswerResponse, str] = Field(..., description="캐시된 데이터")
    created_at: datetime = Field(default_factory=datetime.now, description="생성 시각")
    ttl_seconds: int = Field(default=604800, description="TTL (7일)")  # 7 * 24 * 60 * 60
    hit_count: int = Field(default=0, description="히트 횟수")

# =============================================================================
# 통합 RAG 응답 스키마
# =============================================================================

class RAGResponse(BaseModel):
    """최종 RAG 시스템 응답"""
    query_id: str = Field(..., description="쿼리 ID")
    channel_name: str = Field(..., description="채널명")
    original_query: str = Field(..., description="원본 질문")
    answer: str = Field(..., description="최종 답변")
    confidence: float = Field(..., ge=0.0, le=1.0, description="답변 신뢰도")
    
    # 성능 메트릭
    total_time_ms: float = Field(..., description="총 처리 시간(ms)")
    search_time_ms: float = Field(..., description="검색 시간(ms)")
    answer_time_ms: float = Field(..., description="답변 생성 시간(ms)")
    
    # 품질 메트릭
    documents_found: int = Field(..., description="발견된 문서 수")
    sources_used: List[str] = Field(..., description="사용된 소스들")
    search_quality: Dict[str, Any] = Field(default_factory=dict, description="검색 품질 정보")
    
    # 디버깅 정보 (개발용)
    debug_info: Dict[str, Any] = Field(default_factory=dict, description="디버깅 정보")

# =============================================================================
# 메트릭 및 모니터링 스키마
# =============================================================================

class SearchMetrics(BaseModel):
    """검색 성능 메트릭"""
    recall_at_5: float = Field(..., description="Recall@5")
    mrr: float = Field(..., description="Mean Reciprocal Rank")
    avg_search_time_ms: float = Field(..., description="평균 검색 시간")
    cache_hit_rate: float = Field(..., description="캐시 히트율")

class AnswerMetrics(BaseModel):
    """답변 품질 메트릭"""
    avg_confidence: float = Field(..., description="평균 신뢰도")
    avg_answer_length: int = Field(..., description="평균 답변 길이")
    self_refine_improvement: float = Field(..., description="Self-Refine 개선율")
    token_efficiency: float = Field(..., description="토큰 효율성")

class SystemMetrics(BaseModel):
    """시스템 전체 메트릭"""
    timestamp: datetime = Field(default_factory=datetime.now, description="측정 시각")
    search_metrics: SearchMetrics = Field(..., description="검색 메트릭")
    answer_metrics: AnswerMetrics = Field(..., description="답변 메트릭")
    total_queries: int = Field(..., description="총 쿼리 수")
    avg_total_time_ms: float = Field(..., description="평균 전체 처리 시간") 