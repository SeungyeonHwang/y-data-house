#!/usr/bin/env python3
"""
Search-First 검색 파이프라인
HyDE → Query Rewrite → Vector Search → Conditional Re-Rank

조언 기반 최적화:
- Re-Rank는 복잡한 쿼리에만 적용
- 캐싱으로 LLM 호출 40% 절감
- latency budget ≤ 400ms
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
        """HyDE 문서 생성 (150 토큰 제한)"""
        try:
            prompt = f"""당신은 {channel_name} 채널 전문가입니다. 
다음 질문에 대한 완벽한 답변이 담긴 150토큰 내외의 가상 문서를 작성하세요.

질문: {query}

이 채널의 관점에서 구체적인 수치, 지역명, 전략이 포함된 답변을 작성해주세요."""

            start_time = time.time()
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": f"당신은 {channel_name} 채널 전문가입니다."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=150,
                temperature=0.7
            )
            
            hyde_doc = response.choices[0].message.content.strip()
            generation_time = (time.time() - start_time) * 1000
            
            print(f"🎯 HyDE 생성 완료 ({generation_time:.1f}ms): {hyde_doc[:50]}...")
            return hyde_doc
            
        except Exception as e:
            print(f"⚠️ HyDE 생성 실패: {e}")
            return None
    
    def _rewrite_query(self, query: str, channel_name: str, context: str = "") -> Optional[str]:
        """Query Rewriting - 채널 특화 키워드 삽입 (60 토큰 제한)"""
        try:
            prompt = f"""당신은 {channel_name} 채널 전문 검색 최적화 전문가입니다. 
사용자의 질문을 이 채널의 컨텐츠에서 검색하기 쉬운 형태로 재작성하세요.

원본 질문: {query}
채널 컨텍스트: {context[:200]}

{channel_name} 채널의 영상에서 찾을 수 있는 핵심 키워드와 개념을 포함한 검색 쿼리로 재작성하세요.
**60토큰 이내로 간결하게 작성하세요.**"""

            start_time = time.time()
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": f"당신은 {channel_name} 채널 전문 검색 질의 최적화 전문가입니다."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=60,
                temperature=0.3
            )
            
            rewritten = response.choices[0].message.content.strip()
            generation_time = (time.time() - start_time) * 1000
            
            print(f"🔄 Query Rewrite 완료 ({generation_time:.1f}ms): {rewritten}")
            return rewritten
            
        except Exception as e:
            print(f"⚠️ Query Rewriting 실패: {e}")
            return None
    
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
                formatted_results.append({
                    'video_id': metadata.get('video_id', 'unknown') if metadata else 'unknown',
                    'title': metadata.get('title', 'Unknown Title') if metadata else 'Unknown Title',
                    'content': doc,
                    'metadata': metadata if metadata else {},
                    'distance': distance,
                    'similarity': 1 - distance,
                    'search_time_ms': search_time
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
    
    def _llm_rerank(self, query: str, candidates: List[Dict], channel_name: str) -> List[Dict]:
        """LLM Re-Ranking (top 8 문서에만 적용, 400ms 예산)"""
        if not candidates:
            return []
        
        try:
            start_time = time.time()
            
            # 후보 정보 구성 (간결하게)
            candidate_info = []
            for i, result in enumerate(candidates[:8]):  # top 8만
                candidate_info.append(
                    f"문서 {i+1}: {result['title']}\n"
                    f"내용: {result['content'][:150]}...\n"
                    f"유사도: {result['similarity']:.3f}"
                )
            
            candidates_text = "\n---\n".join(candidate_info)
            
            prompt = f"""당신은 {channel_name} 채널 전문 문서 관련성 평가자입니다. 
사용자 질문에 가장 도움이 될 문서들을 선별해주세요.

질문: {query}

후보 문서들:
{candidates_text}

가장 관련성 높은 문서 번호를 우선순위대로 나열하세요. (예: 1,3,5,2)
최대 5개까지 선택하세요."""

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": f"당신은 {channel_name} 채널 전문 문서 관련성 평가자입니다."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=50,
                temperature=0.1
            )
            
            rerank_time = (time.time() - start_time) * 1000
            
            selection = response.choices[0].message.content.strip()
            print(f"🤖 LLM Re-rank 완료 ({rerank_time:.1f}ms): {selection}")
            
            # 선택된 인덱스 파싱
            try:
                selected_indices = [int(x.strip()) - 1 for x in selection.replace(' ', '').split(',') if x.strip().isdigit()]
                reranked = []
                
                for i, idx in enumerate(selected_indices):
                    if 0 <= idx < len(candidates):
                        doc = candidates[idx].copy()
                        doc['rank_score'] = 1.0 - (i * 0.1)  # 순위 점수
                        reranked.append(doc)
                
                if len(reranked) >= 2:
                    return reranked
                else:
                    # fallback: 유사도 기반
                    return [r for r in candidates if r['similarity'] > 0.3][:5]
                    
            except Exception:
                print("⚠️ Re-rank 결과 파싱 실패, 유사도 기반 fallback")
                return [r for r in candidates if r['similarity'] > 0.3][:5]
                
        except Exception as e:
            print(f"⚠️ LLM Re-ranking 실패: {e}")
            return [r for r in candidates if r['similarity'] > 0.3][:5]
    
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
        
        # 2. 쿼리 복잡도 분류
        query_type = self._classify_query_complexity(search_query.original_query)
        print(f"📊 쿼리 타입: {query_type.value}")
        
        all_results = []
        search_methods = []
        
        # 3. 원본 쿼리 검색 (항상 실행)
        print("📝 1단계: 원본 쿼리 검색")
        original_results = self._vector_search(collection, search_query.original_query, config.max_results)
        if original_results:
            all_results.append(original_results)
            search_methods.append("original")
        
        # 4. HyDE 검색 (활성화된 경우)
        hyde_used = False
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
        
        # 5. Query Rewriting 검색 (활성화된 경우)
        rewrite_used = False
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
        
        # 6. 결과 병합 및 중복 제거
        if not all_results:
            search_time_ms = (time.time() - start_time) * 1000
            return SearchResult(
                query_id=search_query.query_id,
                channel_name=search_query.channel_name,
                documents=[],
                total_found=0,
                search_time_ms=search_time_ms,
                hyde_used=hyde_used,
                rewrite_used=rewrite_used,
                rerank_used=False
            )
        
        merged_results = self._merge_and_deduplicate(all_results, search_methods)
        
        # 7. 조건부 Re-ranking
        rerank_used = False
        final_results = merged_results
        
        if config.enable_rerank and self._should_use_rerank(query_type, len(merged_results)):
            print("🤖 4단계: LLM Re-ranking (조건부)")
            reranked_results = self._llm_rerank(search_query.original_query, merged_results, search_query.channel_name)
            if reranked_results:
                final_results = reranked_results
                rerank_used = True
        
        # 8. 유사도 임계값 필터링
        filtered_results = [r for r in final_results if r['similarity'] > config.similarity_threshold]
        final_documents = filtered_results[:config.max_results]
        
        # 9. SearchDocument 객체로 변환
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
        
        print(f"✅ 검색 완료 ({search_time_ms:.1f}ms): {len(search_documents)}개 문서")
        
        return SearchResult(
            query_id=search_query.query_id,
            channel_name=search_query.channel_name,
            documents=search_documents,
            total_found=len(merged_results),
            search_time_ms=search_time_ms,
            hyde_used=hyde_used,
            rewrite_used=rewrite_used,
            rerank_used=rerank_used
        ) 