#!/usr/bin/env python3
"""
Search-First 검색 파이프라인
HyDE → Query Rewrite → Vector Search → Conditional Re-Rank

조언 기반 최적화:
- Re-Rank는 복잡한 쿼리에만 적용
- 캐싱으로 LLM 호출 40% 절감
- latency budget ≤ 500ms (통일된 목표)
"""

import os
import time
import hashlib
import re
from typing import List, Dict, Optional, Tuple
from pathlib import Path
from dotenv import load_dotenv
import chromadb
from chromadb.config import Settings as ChromaSettings
from openai import OpenAI
from schemas import (
    SearchQuery, SearchConfig, SearchResult, SearchDocument, 
    QueryType, CacheKey
)

# 환경변수 로드
load_dotenv()

class SearchPipeline:
    """Search-First 검색 파이프라인"""
    
    def __init__(self, chroma_path: Path, model: str = "deepseek-chat"):
        """초기화"""
        self.model = model
        self.chroma_path = chroma_path
        
        # DeepSeek 클라이언트 초기화 (HyDE, Query Rewrite용)
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
        
        # ChromaDB 클라이언트 초기화
        try:
            self.chroma_client = chromadb.PersistentClient(
                path=str(chroma_path),
                settings=ChromaSettings(anonymized_telemetry=False)
            )
            print(f"✅ ChromaDB 연결됨: {chroma_path}")
        except Exception as e:
            raise ValueError(f"❌ ChromaDB 로드 실패: {e}")
        
        # 쿼리 복잡도 분류 패턴
        self.complex_patterns = [
            r'\b(비교|분석|평가|어떤.*좋|차이|장단점)\b',  # 비교/분석
            r'\b(왜|이유|원인|근거|배경)\b',              # 인과관계
            r'\b(전략|방법|방식|과정|단계)\b',             # 절차/전략
            r'\b(미래|전망|예측|계획)\b',                 # 예측/계획
            r'\b(최적|최고|가장.*|제일.*)\b',            # 최적화
        ]
        
        print("🔍 Search Pipeline 초기화 완료")
    
    def _get_relevance_category(self, similarity: float) -> str:
        """유사도 점수를 기반으로 연관성 카테고리 분류"""
        if similarity >= 0.8:
            return "매우 높음"
        elif similarity >= 0.6:
            return "높음"
        elif similarity >= 0.4:
            return "보통"
        elif similarity >= 0.2:
            return "낮음"
        else:
            return "매우 낮음"
    
    def _classify_query_complexity(self, query: str) -> QueryType:
        """쿼리 복잡도 자동 분류"""
        query = query.lower()
        
        # 복잡한 패턴 검사
        complex_score = 0
        for pattern in self.complex_patterns:
            if re.search(pattern, query):
                complex_score += 1
        
        # 길이 기준 추가
        if len(query) > 50:
            complex_score += 1
        
        # 질문 수 기준
        question_count = query.count('?') + query.count('？')
        if question_count > 1:
            complex_score += 1
        
        # 복잡도 분류
        if complex_score >= 2:
            return QueryType.COMPLEX
        elif '언제' in query or '얼마' in query or '몇' in query:
            return QueryType.FACTUAL
        elif complex_score == 1:
            return QueryType.ANALYTICAL
        else:
            return QueryType.SIMPLE
    
    def _select_pipeline_mode(self, query_type: QueryType, query: str) -> str:
        """조건부 파이프라인 모드 선택 (전문가 조언 반영)"""
        
        # 1. 경량 파이프라인: 간단한 FAQ, 사실형 질문
        if query_type in [QueryType.SIMPLE, QueryType.FACTUAL]:
            # 단순한 키워드 검색이나 사실 확인
            if len(query) <= 30 and ('무엇' in query or '언제' in query or '얼마' in query):
                return "lightweight"
        
        # 2. 종합 파이프라인: 복잡한 분석, 비교, 전략 질문
        if query_type == QueryType.COMPLEX:
            return "comprehensive"
        
        # 복잡한 키워드가 포함된 경우 종합 파이프라인
        complex_keywords = ['비교', '차이점', '장단점', '분석', '평가', '추천', '전략', 
                           '방법', '과정', '절차', '이유', '원인', '배경', '영향', 
                           '미래', '전망', '예측', '고려사항', 'vs']
        
        if any(keyword in query for keyword in complex_keywords):
            return "comprehensive"
        
        # 다중 질문이나 긴 질문
        if len(query) > 60 or query.count('?') > 1 or query.count('？') > 1:
            return "comprehensive"
        
        # 3. 표준 파이프라인: 나머지 (분석형, 중간 복잡도)
        return "standard"
    
    def _get_channel_collection(self, channel_name: str):
        """채널명으로 컬렉션 가져오기"""
        try:
            collections = self.chroma_client.list_collections()
            
            for collection in collections:
                if collection.name.startswith("channel_"):
                    try:
                        sample = collection.get(limit=1, include=['metadatas'])
                        if sample['metadatas'] and sample['metadatas'][0]:
                            metadata_channel = sample['metadatas'][0].get('channel', '')
                            if metadata_channel == channel_name:
                                return collection
                    except:
                        continue
            
            return None
        except Exception as e:
            print(f"❌ 컬렉션 검색 실패: {e}")
            return None
    
    def _generate_hyde_document(self, query: str, channel_name: str) -> Optional[str]:
        """HyDE 문서 생성 (100 토큰으로 단축)"""
        try:
            prompt = f"""당신은 {channel_name} 채널 전문가입니다. 
다음 질문에 대한 완벽한 답변이 담긴 100토큰 내외의 가상 문서를 작성하세요.

질문: {query}

이 채널의 관점에서 구체적인 수치, 지역명, 전략이 포함된 답변을 작성해주세요."""

            start_time = time.time()
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": f"당신은 {channel_name} 채널 전문가입니다."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=100,  # 150 → 100으로 단축
                temperature=0.7
            )
            
            hyde_doc = response.choices[0].message.content.strip()
            generation_time = (time.time() - start_time) * 1000
            
            print(f"🎯 HyDE 생성 완료 ({generation_time:.1f}ms, 100tok): {hyde_doc[:50]}...")
            return hyde_doc
            
        except Exception as e:
            print(f"⚠️ HyDE 생성 실패: {e}")
            return None
    
    def _rewrite_query(self, query: str, channel_name: str, context: str = "") -> Optional[str]:
        """Query Rewriting - 채널 특화 키워드 삽입 (40 토큰으로 단축)"""
        try:
            prompt = f"""당신은 {channel_name} 채널 전문 검색 최적화 전문가입니다. 
사용자의 질문을 이 채널의 컨텐츠에서 검색하기 쉬운 형태로 재작성하세요.

원본 질문: {query}
채널 컨텍스트: {context[:150]}

{channel_name} 채널의 영상에서 찾을 수 있는 핵심 키워드와 개념을 포함한 검색 쿼리로 재작성하세요.
**40토큰 이내로 간결하게 작성하세요.**"""

            start_time = time.time()
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": f"당신은 {channel_name} 채널 전문 검색 질의 최적화 전문가입니다."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=40,  # 60 → 40으로 단축
                temperature=0.3
            )
            
            rewritten = response.choices[0].message.content.strip()
            generation_time = (time.time() - start_time) * 1000
            
            print(f"🔄 Query Rewrite 완료 ({generation_time:.1f}ms, 40tok): {rewritten}")
            return rewritten
            
        except Exception as e:
            print(f"⚠️ Query Rewriting 실패: {e}")
            return None

    def _generate_fusion_queries(self, query: str, channel_name: str, num_queries: int = 4) -> List[str]:
        """RAG-Fusion용 다중 변형 쿼리 생성 (3-5개)"""
        try:
            prompt = f"""당신은 {channel_name} 채널 전문 검색 전략가입니다.
주어진 질문의 다양한 측면을 탐색하기 위해 {num_queries}개의 서로 다른 변형 질문을 생성하세요.

원본 질문: {query}

**생성 규칙:**
1. 같은 의도를 다른 관점에서 표현
2. 구체적인 키워드와 추상적인 개념 혼합
3. 질문 길이와 스타일 다양화
4. {channel_name} 채널 특성 반영

{num_queries}개의 변형 질문을 한 줄씩 번호 없이 작성하세요:"""

            start_time = time.time()
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": f"당신은 {channel_name} 채널 전문 다각도 질문 생성 전문가입니다."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=150,  # 200 → 150으로 단축
                temperature=0.8  # 창의성을 위해 높은 temperature
            )
            
            result = response.choices[0].message.content.strip()
            generation_time = (time.time() - start_time) * 1000
            
            # 변형 쿼리들 파싱
            fusion_queries = []
            for line in result.split('\n'):
                line = line.strip()
                if line and not line.startswith(('1.', '2.', '3.', '4.', '5.')):
                    # 번호 제거 후 정리
                    clean_line = re.sub(r'^\d+[\.\)]\s*', '', line).strip()
                    if clean_line and clean_line != query:  # 원본과 다른 경우만
                        fusion_queries.append(clean_line)
            
            # 중복 제거 및 개수 조정
            unique_queries = []
            for q in fusion_queries:
                if q not in unique_queries and len(unique_queries) < num_queries:
                    unique_queries.append(q)
            
            print(f"🎯 RAG-Fusion 쿼리 생성 완료 ({generation_time:.1f}ms): {len(unique_queries)}개")
            for i, fq in enumerate(unique_queries, 1):
                print(f"  {i}. {fq}")
                
            return unique_queries
            
        except Exception as e:
            print(f"⚠️ RAG-Fusion 쿼리 생성 실패: {e}")
            return []
    
    def _reciprocal_rank_fusion(self, query_results: List[List[Dict]], k: int = 60) -> List[Dict]:
        """Reciprocal Rank Fusion (RRF)으로 다중 검색 결과 병합"""
        video_scores = {}
        
        for query_idx, results in enumerate(query_results):
            for rank, doc in enumerate(results):
                video_id = doc['video_id']
                
                # RRF 점수 계산: 1 / (k + rank)
                rrf_score = 1.0 / (k + rank + 1)
                
                if video_id not in video_scores:
                    video_scores[video_id] = {
                        'doc': doc,
                        'rrf_score': 0.0,
                        'appearances': 0,
                        'best_rank': rank + 1,
                        'query_sources': []
                    }
                
                video_scores[video_id]['rrf_score'] += rrf_score
                video_scores[video_id]['appearances'] += 1
                video_scores[video_id]['best_rank'] = min(video_scores[video_id]['best_rank'], rank + 1)
                video_scores[video_id]['query_sources'].append(query_idx)
        
        # RRF 점수로 정렬
        sorted_results = sorted(
            video_scores.values(), 
            key=lambda x: x['rrf_score'], 
            reverse=True
        )
        
        # 결과 포맷팅
        fusion_results = []
        for item in sorted_results:
            doc = item['doc'].copy()
            doc['rrf_score'] = item['rrf_score']
            doc['fusion_appearances'] = item['appearances']
            doc['best_rank'] = item['best_rank']
            doc['search_method'] = 'rag_fusion'
            fusion_results.append(doc)
        
        print(f"🔗 RRF 병합 완료: {len(fusion_results)}개 문서, 평균 출현: {sum(item['appearances'] for item in sorted_results) / len(sorted_results):.1f}회")
        
        return fusion_results
    
    def _vector_search(self, collection, query_text: str, n_results: int = 8) -> List[Dict]:
        """벡터 검색 실행"""
        try:
            start_time = time.time()
            results = collection.query(
                query_texts=[query_text],
                n_results=n_results,
                include=["distances", "metadatas", "documents"]
            )
            search_time = (time.time() - start_time) * 1000
            
            if not results["documents"][0]:
                return []
            
            formatted_results = []
            for i, (doc, metadata, distance) in enumerate(zip(
                results['documents'][0],
                results['metadatas'][0], 
                results['distances'][0]
            )):
                # 영상 메타데이터 강화
                safe_metadata = metadata if metadata else {}
                formatted_results.append({
                    'video_id': safe_metadata.get('video_id', 'unknown'),
                    'title': safe_metadata.get('title', 'Unknown Title'),
                    'content': doc,
                    'metadata': {
                        'upload_date': safe_metadata.get('upload_date', '날짜 미상'),
                        'duration': safe_metadata.get('duration', '시간 미상'),
                        'chunk_index': safe_metadata.get('chunk_index', 0),
                        'chunk_start_time': safe_metadata.get('chunk_start_time', '00:00'),
                        'channel': safe_metadata.get('channel', 'Unknown Channel'),
                        'view_count': safe_metadata.get('view_count', 'N/A'),
                        'description': safe_metadata.get('description', '')[:100] + '...' if safe_metadata.get('description') else 'N/A'
                    },
                    'distance': distance,
                    'similarity': 1 - distance,
                    'search_time_ms': search_time,
                    'relevance_category': self._get_relevance_category(1 - distance)
                })
            
            print(f"📊 벡터 검색 완료 ({search_time:.1f}ms): {len(formatted_results)}개 문서")
            return formatted_results
            
        except Exception as e:
            print(f"❌ 벡터 검색 실패: {e}")
            return []
    
    def _should_use_rerank(self, query_type: QueryType, results_count: int) -> bool:
        """Re-rank 사용 여부 결정 (조건부 실행)"""
        # 복잡한 쿼리이고 충분한 결과가 있을 때만
        return (
            query_type in [QueryType.COMPLEX, QueryType.ANALYTICAL] and 
            results_count >= 5
        )
    
    def _cross_encoder_rerank(self, query: str, candidates: List[Dict], channel_name: str) -> List[Dict]:
        """Cross-Encoder 정밀 Re-Ranking (전문가 조언: precision +12pt 향상)"""
        if not candidates:
            return []
        
        try:
            start_time = time.time()
            
            # 각 후보에 대해 개별 정밀 점수 계산
            scored_candidates = []
            
            for i, candidate in enumerate(candidates[:6]):  # top-6로 제한 (전문가 조언)
                title = candidate.get('title', 'Unknown')
                content = candidate.get('content', '')[:300]  # 더 많은 컨텍스트
                similarity = candidate.get('similarity', 0.0)
                
                # 영상 메타데이터 추출
                upload_date = candidate.get('metadata', {}).get('upload_date', '날짜 미상')
                duration = candidate.get('metadata', {}).get('duration', '시간 미상')
                chunk_time = candidate.get('metadata', {}).get('chunk_start_time', '00:00')
                
                # Cross-Encoder 스타일 정밀 점수 요청 (영상 정보 포함)
                scoring_prompt = f"""질문과 영상 내용의 연관성을 정밀 평가하세요.

## 사용자 질문
"{query}"

## 영상 정보
📺 **제목**: {title}
📅 **업로드**: {upload_date}
⏱️ **길이**: {duration}
📍 **구간**: {chunk_time}부터 시작하는 내용
🔍 **벡터 유사도**: {similarity:.3f}

## 영상 내용
{content}

**영상 연관성 평가 기준:**
1. 질문의 핵심 의도와 영상 내용의 직접적 일치도
2. 영상에서 제공하는 구체적 답변의 완성도
3. {channel_name} 채널 특성과 영상 맥락의 적합성
4. 영상 정보의 신뢰성과 질문 해결 능력
5. 다른 영상과의 차별화된 가치

영상과 질문의 연관성 점수를 0.0~1.0 사이로 평가하세요 (예: 0.85)"""

                try:
                    response = self.client.chat.completions.create(
                        model=self.model,
                        messages=[
                            {"role": "system", "content": f"정밀한 영상-질문 연관성 평가자입니다. {channel_name} 채널의 영상 데이터베이스에서 질문과 가장 관련 높은 영상을 찾아 객관적으로 평가하세요."},
                            {"role": "user", "content": scoring_prompt}
                        ],
                        max_tokens=8,
                        temperature=0.1  # 일관성 우선
                    )
                    
                    # 점수 추출 및 검증
                    score_text = response.choices[0].message.content.strip()
                    try:
                        cross_score = float(score_text)
                        cross_score = max(0.0, min(1.0, cross_score))  # 범위 제한
                    except ValueError:
                        cross_score = similarity  # fallback
                    
                except Exception as e:
                    print(f"⚠️ Cross-Encoder 점수 계산 실패 ({i+1}번): {e}")
                    cross_score = similarity
                
                # 하이브리드 점수: Cross-Encoder(75%) + Vector(25%)
                final_score = cross_score * 0.75 + similarity * 0.25
                
                candidate_scored = candidate.copy()
                candidate_scored['cross_encoder_score'] = cross_score
                candidate_scored['final_rerank_score'] = final_score
                candidate_scored['rank_score'] = final_score
                
                scored_candidates.append(candidate_scored)
                print(f"  📊 문서 {i+1}: vec={similarity:.3f} → cross={cross_score:.3f} → final={final_score:.3f}")
            
            # 최종 점수로 정렬
            reranked = sorted(scored_candidates, key=lambda x: x['final_rerank_score'], reverse=True)
            
            rerank_time = (time.time() - start_time) * 1000
            print(f"🎯 Cross-Encoder Re-rank 완료 ({rerank_time:.1f}ms): top-{len(reranked)}개 정밀 재평가")
            
            return reranked
                
        except Exception as e:
            print(f"⚠️ Cross-Encoder Re-ranking 실패: {e}")
            # fallback: 벡터 유사도 기반 정렬
            return sorted(candidates, key=lambda x: x['similarity'], reverse=True)[:6]
    
    def _merge_and_deduplicate(self, all_results: List[List[Dict]], search_methods: List[str]) -> List[Dict]:
        """검색 결과 병합 및 중복 제거"""
        seen_videos = {}
        
        for results, method in zip(all_results, search_methods):
            for result in results:
                video_id = result['video_id']
                result['search_method'] = method
                
                # 더 높은 유사도의 결과 유지
                if video_id not in seen_videos or result['similarity'] > seen_videos[video_id]['similarity']:
                    seen_videos[video_id] = result
        
        # 유사도순 정렬
        merged_results = sorted(seen_videos.values(), key=lambda x: x['similarity'], reverse=True)
        
        print(f"🔗 결과 병합 완료: {len(merged_results)}개 고유 문서")
        return merged_results
    
    def search(self, search_query: SearchQuery, config: SearchConfig) -> SearchResult:
        """메인 검색 파이프라인 실행"""
        start_time = time.time()
        
        print(f"🔍 검색 시작: '{search_query.original_query}' in {search_query.channel_name}")
        
        # 1. 채널 컬렉션 가져오기
        collection = self._get_channel_collection(search_query.channel_name)
        if not collection:
            return SearchResult(
                query_id=search_query.query_id,
                channel_name=search_query.channel_name,
                documents=[],
                total_found=0,
                search_time_ms=0,
                hyde_used=False,
                rewrite_used=False,
                rerank_used=False
            )
        
        # 2. 쿼리 복잡도 분류 및 조건부 파이프라인 결정
        query_type = self._classify_query_complexity(search_query.original_query)
        pipeline_mode = self._select_pipeline_mode(query_type, search_query.original_query)
        print(f"📊 쿼리 타입: {query_type.value} → 파이프라인: {pipeline_mode}")
        
        all_results = []
        search_methods = []
        
        # 3. 원본 쿼리 검색 (모든 파이프라인에서 실행)
        print("📝 1단계: 원본 쿼리 검색")
        original_results = self._vector_search(collection, search_query.original_query, config.max_results)
        if original_results:
            all_results.append(original_results)
            search_methods.append("original")
        
        # 4. 조건부 고급 검색 기법 적용
        hyde_used = False
        fusion_used = False
        rewrite_used = False
        
        if pipeline_mode == "lightweight":
            # 경량 파이프라인: 간단한 FAQ, 사실형 질문
            print("⚡ 경량 파이프라인: 벡터 검색만 수행")
            
        elif pipeline_mode == "standard":
            # 표준 파이프라인: HyDE + Query Rewriting
            print("🔄 표준 파이프라인: HyDE + 쿼리 재작성")
            
            # HyDE 검색
            if config.enable_hyde:
                print("🎯 2단계: HyDE 검색")
                hyde_doc = self._generate_hyde_document(search_query.original_query, search_query.channel_name)
                if hyde_doc:
                    search_query.hyde_document = hyde_doc
                    hyde_results = self._vector_search(collection, hyde_doc, config.max_results)
                    if hyde_results:
                        all_results.append(hyde_results)
                        search_methods.append("hyde")
                        hyde_used = True
            
            # Query Rewriting
            if config.enable_rewrite and all_results:
                print("🔄 3단계: Query Rewriting 검색")
                context = all_results[0][0]['content'] if all_results[0] else ""
                rewritten_query = self._rewrite_query(search_query.original_query, search_query.channel_name, context)
                if rewritten_query and rewritten_query != search_query.original_query:
                    search_query.rewritten_query = rewritten_query
                    rewrite_results = self._vector_search(collection, rewritten_query, config.max_results)
                    if rewrite_results:
                        all_results.append(rewrite_results)
                        search_methods.append("rewritten")
                        rewrite_used = True
                        
        elif pipeline_mode == "comprehensive":
            # 종합 파이프라인: 모든 기법 활용
            print("🚀 종합 파이프라인: 전체 스택 활용")
            
            # HyDE 검색
            if config.enable_hyde:
                print("🎯 2단계: HyDE 검색")
                hyde_doc = self._generate_hyde_document(search_query.original_query, search_query.channel_name)
                if hyde_doc:
                    search_query.hyde_document = hyde_doc
                    hyde_results = self._vector_search(collection, hyde_doc, config.max_results)
                    if hyde_results:
                        all_results.append(hyde_results)
                        search_methods.append("hyde")
                        hyde_used = True
            
            # RAG-Fusion 검색 (복잡한 질문에만)
            if config.enable_rag_fusion:
                print(f"🎯 3단계: RAG-Fusion 다중 쿼리 검색 ({config.rag_fusion_queries}개)")
                fusion_queries = self._generate_fusion_queries(
                    search_query.original_query, 
                    search_query.channel_name, 
                    config.rag_fusion_queries
                )
                
                if fusion_queries:
                    fusion_results_list = []
                    for i, fq in enumerate(fusion_queries):
                        print(f"  검색 중: {fq[:50]}...")
                        fq_results = self._vector_search(collection, fq, config.max_results)
                        if fq_results:
                            fusion_results_list.append(fq_results)
                    
                    if fusion_results_list:
                        # RRF로 병합
                        rrf_results = self._reciprocal_rank_fusion(fusion_results_list)
                        if rrf_results:
                            all_results.append(rrf_results)
                            search_methods.append("rag_fusion")
                            fusion_used = True
            
            # Query Rewriting
            if config.enable_rewrite and all_results:
                print("🔄 4단계: Query Rewriting 검색")
                context = all_results[0][0]['content'] if all_results[0] else ""
                rewritten_query = self._rewrite_query(search_query.original_query, search_query.channel_name, context)
                if rewritten_query and rewritten_query != search_query.original_query:
                    search_query.rewritten_query = rewritten_query
                    rewrite_results = self._vector_search(collection, rewritten_query, config.max_results)
                    if rewrite_results:
                        all_results.append(rewrite_results)
                        search_methods.append("rewritten")
                        rewrite_used = True
        
        # 7. 결과 병합 및 중복 제거
        if not all_results:
            search_time_ms = (time.time() - start_time) * 1000
            return SearchResult(
                query_id=search_query.query_id,
                channel_name=search_query.channel_name,
                documents=[],
                total_found=0,
                search_time_ms=search_time_ms,
                hyde_used=hyde_used,
                fusion_used=fusion_used,
                rewrite_used=rewrite_used,
                rerank_used=False
            )
        
        merged_results = self._merge_and_deduplicate(all_results, search_methods)
        
        # 8. 2층 유사도 필터링 - 전문가 조언 반영
        # 1차 필터: recall 최적화 (낮은 threshold)
        first_filter = [r for r in merged_results if r['similarity'] > config.similarity_threshold]
        print(f"🔍 1차 필터 (recall={config.similarity_threshold}): {len(merged_results)} → {len(first_filter)}개")
        
        # 9. 조건부 Cross-Encoder Re-ranking (전문가 조언 반영)
        rerank_used = False
        final_results = first_filter
        
        if config.enable_rerank and self._should_use_rerank(query_type, len(first_filter)):
            print(f"🎯 5단계: Cross-Encoder Re-ranking (top-{config.rerank_top_k})")
            # Re-ranking용 후보: 12개에서 top-6 선별 (전문가 조언: precision +12pt)
            rerank_candidates = first_filter[:12]  # 더 많은 후보에서 선별
            reranked_results = self._cross_encoder_rerank(search_query.original_query, rerank_candidates, search_query.channel_name)
            if reranked_results:
                final_results = reranked_results[:config.rerank_top_k]  # top-k로 제한
                rerank_used = True
        
        # 10. 2차 필터링: 정밀도 최적화 (높은 threshold) - Re-rank 후 적용
        if rerank_used:
            # Re-rank된 결과는 이미 품질이 검증되었으므로 precision_threshold 적용 안 함
            precision_filtered = final_results
        else:
            # Re-rank 없는 경우만 precision threshold 적용
            precision_filtered = [r for r in final_results if r['similarity'] > config.precision_threshold]
            print(f"🎯 2차 필터 (precision={config.precision_threshold}): {len(final_results)} → {len(precision_filtered)}개")
            final_results = precision_filtered
        
        # 11. 최종 결과 개수 제한 (전문가 조언: top-6 최적)
        display_limit = min(6, config.rerank_top_k if rerank_used else config.max_results)
        final_documents = final_results[:display_limit]
        
        # 12. SearchDocument 객체로 변환
        search_documents = []
        for doc in final_documents:
            search_documents.append(SearchDocument(
                video_id=doc['video_id'],
                title=doc['title'],
                content=doc['content'],
                similarity=doc['similarity'],
                metadata=doc['metadata'],
                search_method=doc['search_method'],
                rank_score=doc.get('rank_score')
            ))
        
        search_time_ms = (time.time() - start_time) * 1000
        
        # 결과 요약 출력
        used_methods = []
        if hyde_used: used_methods.append("HyDE")
        if fusion_used: used_methods.append("RAG-Fusion")
        if rewrite_used: used_methods.append("Rewrite")
        if rerank_used: used_methods.append("Re-rank")
        
        methods_str = " + ".join(used_methods) if used_methods else "기본"
        print(f"✅ 검색 완료 ({search_time_ms:.1f}ms): {len(search_documents)}개 문서 [{methods_str}]")
        
        return SearchResult(
            query_id=search_query.query_id,
            channel_name=search_query.channel_name,
            documents=search_documents,
            total_found=len(merged_results),
            search_time_ms=search_time_ms,
            hyde_used=hyde_used,
            fusion_used=fusion_used,
            rewrite_used=rewrite_used,
            rerank_used=rerank_used
        ) 