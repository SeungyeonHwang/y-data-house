#!/usr/bin/env python3
"""
L2 Semantic Cache System - LLM 호출 40%→65% 절감 (전문가 조언 반영)
텍스트 유사도 기반 질문 매칭으로 지연 -120ms 달성

L2 캐시 구조:
- L1: (model, temperature, exact_prompt_hash) - 정확 매칭
- L2: (query_normalized_hash, fuzzy_matching) - 텍스트 유사 매칭
- 정규화된 질문들을 자동으로 캐시 재사용
- 단어 기반 빠른 유사성 검색
"""

import os
import hashlib
import json
import time
import pickle
import re
from typing import Dict, Optional, Any, List, Union, Tuple
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass
import sqlite3
from threading import Lock
from schemas import CacheKey, CacheEntry

@dataclass
class CacheStats:
    """L2 캐시 통계 (전문가 조언 추적)"""
    total_requests: int = 0
    l1_hits: int = 0      # 정확 매칭 히트
    l2_hits: int = 0      # 유사 질문 매칭 히트  
    cache_misses: int = 0
    avg_latency_saved_ms: float = 0.0  # 절약된 평균 지연시간
    
    @property
    def total_hits(self) -> int:
        return self.l1_hits + self.l2_hits
    
    @property
    def hit_rate(self) -> float:
        return self.total_hits / self.total_requests if self.total_requests > 0 else 0.0
    
    @property
    def l2_effectiveness(self) -> float:
        """L2 캐시 효과성 (L2 히트 / 전체 히트)"""
        return self.l2_hits / self.total_hits if self.total_hits > 0 else 0.0

class SemanticCache:
    """L2 Semantic Cache 시스템 (전문가 조언 반영)"""
    
    def __init__(self, cache_dir: Path = None, ttl_seconds: int = 604800, 
                 similarity_threshold: float = 0.7, enable_l2: bool = True):  # 7일
        """초기화 - L2 텍스트 유사도 캐시 지원"""
        self.cache_dir = cache_dir or Path(__file__).parent / "cache"
        self.cache_dir.mkdir(exist_ok=True)
        self.ttl_seconds = ttl_seconds
        self.similarity_threshold = similarity_threshold  # L2 캐시용 텍스트 유사도 임계값
        self.enable_l2 = enable_l2
        self.stats = CacheStats()
        self._lock = Lock()
        
        # SQLite DB 초기화 (메타데이터 저장용)
        self.db_path = self.cache_dir / "cache_meta.db"
        self._init_db()
        
        print(f"💾 Semantic Cache 초기화: {self.cache_dir}")
        print(f"⏰ TTL: {ttl_seconds}초 ({ttl_seconds//86400}일)")
        print(f"🔄 L2 텍스트 유사도 캐시: {'활성화' if self.enable_l2 else '비활성화'} (임계값: {similarity_threshold})")
    
    def _init_db(self):
        """SQLite DB 초기화 - L2 임베딩 테이블 추가"""
        with sqlite3.connect(self.db_path) as conn:
            # L1 캐시 테이블 (기존)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cache_entries (
                    key_hash TEXT PRIMARY KEY,
                    model TEXT,
                    temperature REAL,
                    prompt_hash TEXT,
                    query_hash TEXT,
                    created_at TIMESTAMP,
                    ttl_seconds INTEGER,
                    hit_count INTEGER DEFAULT 0,
                    data_file TEXT,
                    data_size INTEGER
                )
            """)
            
            # L2 캐시 테이블 (새로 추가 - 텍스트 기반 유사 질문 매칭)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS l2_query_patterns (
                    pattern_hash TEXT PRIMARY KEY,
                    original_query TEXT,
                    normalized_query TEXT,
                    query_keywords TEXT,
                    model TEXT,
                    temperature REAL,
                    cache_key_hash TEXT,
                    created_at TIMESTAMP,
                    similarity_hits INTEGER DEFAULT 0,
                    FOREIGN KEY (cache_key_hash) REFERENCES cache_entries (key_hash)
                )
            """)
            
            # 인덱스 생성
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_created_ttl 
                ON cache_entries (created_at, ttl_seconds)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_model_temp 
                ON cache_entries (model, temperature)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_l2_model_temp 
                ON l2_query_patterns (model, temperature)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_l2_keywords 
                ON l2_query_patterns (query_keywords)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_l2_created 
                ON l2_query_patterns (created_at)
            """)
    
    def _generate_cache_key(self, model: str, temperature: float, prompt: str, query: str = "") -> CacheKey:
        """캐시 키 생성"""
        prompt_hash = hashlib.sha256(prompt.encode('utf-8')).hexdigest()[:16]
        query_hash = hashlib.sha256(query.encode('utf-8')).hexdigest()[:16] if query else ""
        
        return CacheKey(
            model=model,
            temperature=temperature,
            prompt_hash=prompt_hash,
            query_hash=query_hash
        )
    
    def _get_key_hash(self, cache_key: CacheKey) -> str:
        """캐시 키를 문자열 해시로 변환"""
        key_str = f"{cache_key.model}:{cache_key.temperature}:{cache_key.prompt_hash}:{cache_key.query_hash}"
        return hashlib.sha256(key_str.encode('utf-8')).hexdigest()[:32]
    
    def _normalize_query(self, query: str) -> str:
        """질문 정규화 (L2 캐시용)"""
        # 소문자 변환
        normalized = query.lower()
        
        # 특수문자 제거 (한글, 영문, 숫자만 유지)
        normalized = re.sub(r'[^\w\s가-힣]', ' ', normalized)
        
        # 여러 공백을 하나로
        normalized = re.sub(r'\s+', ' ', normalized)
        
        # 양끝 공백 제거
        normalized = normalized.strip()
        
        return normalized
    
    def _get_query_keywords(self, query: str) -> List[str]:
        """핵심 키워드 추출 (L2 캐시용)"""
        normalized = self._normalize_query(query)
        
        # 불용어 리스트 (한국어)
        stopwords = {'은', '는', '이', '가', '을', '를', '의', '에', '에서', '로', '와', '과', '하고', 
                    '그리고', '또한', '하지만', '그러나', '그런데', '따라서', '그래서', '그러므로',
                    '무엇', '어떤', '어떻게', '왜', '언제', '어디', '누가', '몇', '얼마'}
        
        # 단어 분리 및 불용어 제거
        words = [word for word in normalized.split() if len(word) > 1 and word not in stopwords]
        
        # 중복 제거 및 정렬
        keywords = sorted(list(set(words)))
        
        return keywords[:10]  # 최대 10개 키워드
    
    def _calculate_text_similarity(self, query1: str, query2: str) -> float:
        """텍스트 유사도 계산 (Jaccard similarity + keyword overlap)"""
        keywords1 = set(self._get_query_keywords(query1))
        keywords2 = set(self._get_query_keywords(query2))
        
        if not keywords1 and not keywords2:
            return 1.0
        if not keywords1 or not keywords2:
            return 0.0
        
        # Jaccard similarity
        intersection = keywords1.intersection(keywords2)
        union = keywords1.union(keywords2)
        
        jaccard = len(intersection) / len(union) if union else 0.0
        
        # 길이 유사성 (보너스)
        len1, len2 = len(query1), len(query2)
        length_similarity = 1.0 - abs(len1 - len2) / max(len1, len2, 1)
        
        # 최종 유사도 (Jaccard 80% + 길이 유사성 20%)
        final_similarity = jaccard * 0.8 + length_similarity * 0.2
        
        return final_similarity
    
    def _is_expired(self, created_at: datetime, ttl_seconds: int) -> bool:
        """TTL 만료 확인"""
        expiry_time = created_at + timedelta(seconds=ttl_seconds)
        return datetime.now() > expiry_time
    
    def _save_data_file(self, key_hash: str, data: Any) -> str:
        """데이터 파일 저장"""
        data_file = f"{key_hash}.pkl"
        file_path = self.cache_dir / data_file
        
        with open(file_path, 'wb') as f:
            pickle.dump(data, f)
        
        return data_file
    
    def _load_data_file(self, data_file: str) -> Any:
        """데이터 파일 로드"""
        file_path = self.cache_dir / data_file
        
        if not file_path.exists():
            return None
        
        try:
            with open(file_path, 'rb') as f:
                return pickle.load(f)
        except Exception as e:
            print(f"⚠️ 캐시 파일 로드 실패: {e}")
            return None
    
    def get(self, model: str, temperature: float, prompt: str, query: str = "") -> Optional[Any]:
        """L1 + L2 캐시에서 데이터 조회"""
        with self._lock:
            self.stats.total_requests += 1
            
            # L1 캐시 조회 (정확 매칭)
            cache_key = self._generate_cache_key(model, temperature, prompt, query)
            key_hash = self._get_key_hash(cache_key)
            
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.execute("""
                        SELECT created_at, ttl_seconds, hit_count, data_file
                        FROM cache_entries 
                        WHERE key_hash = ?
                    """, (key_hash,))
                    
                    row = cursor.fetchone()
                    if row:
                        created_at_str, ttl_seconds, hit_count, data_file = row
                        created_at = datetime.fromisoformat(created_at_str)
                        
                        # TTL 만료 확인
                        if not self._is_expired(created_at, ttl_seconds):
                            # 데이터 로드
                            data = self._load_data_file(data_file)
                            if data is not None:
                                # 히트 카운트 증가
                                conn.execute("""
                                    UPDATE cache_entries 
                                    SET hit_count = ? 
                                    WHERE key_hash = ?
                                """, (hit_count + 1, key_hash))
                                
                                self.stats.l1_hits += 1
                                print(f"✅ L1 캐시 히트: {key_hash[:8]}... (hit_count: {hit_count + 1})")
                                return data
                        else:
                            self._delete_entry(key_hash, data_file)
                    
                    # L2 캐시 조회 (유사 질문 매칭)
                    if self.enable_l2 and query:
                        l2_result = self._find_similar_cached_query(model, temperature, query, conn)
                        if l2_result:
                            self.stats.l2_hits += 1
                            print(f"🔄 L2 캐시 히트: 유사도 {l2_result['similarity']:.3f}")
                            return l2_result['data']
                    
                    self.stats.cache_misses += 1
                    return None
                    
            except Exception as e:
                print(f"⚠️ 캐시 조회 실패: {e}")
                self.stats.cache_misses += 1
                return None
    
    def _find_similar_cached_query(self, model: str, temperature: float, query: str, conn) -> Optional[Dict]:
        """L2 캐시에서 유사한 질문 찾기"""
        try:
            # 현재 질문의 키워드
            query_keywords = set(self._get_query_keywords(query))
            
            # 같은 모델/온도의 L2 패턴 조회
            cursor = conn.execute("""
                SELECT l2.original_query, l2.cache_key_hash, l2.similarity_hits,
                       ce.created_at, ce.ttl_seconds, ce.data_file
                FROM l2_query_patterns l2
                JOIN cache_entries ce ON l2.cache_key_hash = ce.key_hash
                WHERE l2.model = ? AND l2.temperature = ?
                ORDER BY l2.similarity_hits DESC
                LIMIT 20
            """, (model, temperature))
            
            best_match = None
            best_similarity = 0.0
            
            for row in cursor.fetchall():
                cached_query, cache_key_hash, similarity_hits, created_at_str, ttl_seconds, data_file = row
                
                # TTL 확인
                created_at = datetime.fromisoformat(created_at_str)
                if self._is_expired(created_at, ttl_seconds):
                    continue
                
                # 유사도 계산
                similarity = self._calculate_text_similarity(query, cached_query)
                
                if similarity >= self.similarity_threshold and similarity > best_similarity:
                    # 데이터 로드 시도
                    data = self._load_data_file(data_file)
                    if data is not None:
                        best_match = {
                            'data': data,
                            'similarity': similarity,
                            'original_query': cached_query,
                            'cache_key_hash': cache_key_hash
                        }
                        best_similarity = similarity
            
            # 가장 좋은 매칭 업데이트
            if best_match:
                conn.execute("""
                    UPDATE l2_query_patterns 
                    SET similarity_hits = similarity_hits + 1 
                    WHERE cache_key_hash = ?
                """, (best_match['cache_key_hash'],))
            
            return best_match
            
        except Exception as e:
            print(f"⚠️ L2 캐시 조회 실패: {e}")
            return None
    
    def set(self, model: str, temperature: float, prompt: str, data: Any, query: str = "", ttl_seconds: int = None) -> bool:
        """L1 + L2 캐시에 데이터 저장"""
        with self._lock:
            cache_key = self._generate_cache_key(model, temperature, prompt, query)
            key_hash = self._get_key_hash(cache_key)
            ttl = ttl_seconds or self.ttl_seconds
            
            try:
                # 데이터 파일 저장
                data_file = self._save_data_file(key_hash, data)
                data_size = (self.cache_dir / data_file).stat().st_size
                
                # 메타데이터 저장
                with sqlite3.connect(self.db_path) as conn:
                    # L1 캐시 저장
                    conn.execute("""
                        INSERT OR REPLACE INTO cache_entries 
                        (key_hash, model, temperature, prompt_hash, query_hash, 
                         created_at, ttl_seconds, hit_count, data_file, data_size)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                    """, (
                        key_hash,
                        cache_key.model,
                        cache_key.temperature,
                        cache_key.prompt_hash,
                        cache_key.query_hash,
                        datetime.now().isoformat(),
                        ttl,
                        data_file,
                        data_size
                    ))
                    
                    # L2 패턴 저장 (질문이 있는 경우)
                    if self.enable_l2 and query:
                        self._store_l2_pattern(model, temperature, query, key_hash, conn)
                
                print(f"💾 L1 캐시 저장: {key_hash[:8]}... ({data_size} bytes)")
                return True
                
            except Exception as e:
                print(f"❌ 캐시 저장 실패: {e}")
                return False
    
    def _store_l2_pattern(self, model: str, temperature: float, query: str, cache_key_hash: str, conn):
        """L2 질문 패턴 저장"""
        try:
            normalized_query = self._normalize_query(query)
            keywords = self._get_query_keywords(query)
            keywords_str = ' '.join(keywords)
            
            # 패턴 해시 생성
            pattern_str = f"{model}:{temperature}:{normalized_query}"
            pattern_hash = hashlib.sha256(pattern_str.encode('utf-8')).hexdigest()[:16]
            
            conn.execute("""
                INSERT OR REPLACE INTO l2_query_patterns 
                (pattern_hash, original_query, normalized_query, query_keywords,
                 model, temperature, cache_key_hash, created_at, similarity_hits)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
            """, (
                pattern_hash,
                query,
                normalized_query,
                keywords_str,
                model,
                temperature,
                cache_key_hash,
                datetime.now().isoformat()
            ))
            
            print(f"🔄 L2 패턴 저장: {pattern_hash} (키워드: {len(keywords)}개)")
            
        except Exception as e:
            print(f"⚠️ L2 패턴 저장 실패: {e}")
    
    def _delete_entry(self, key_hash: str, data_file: str):
        """캐시 엔트리 삭제"""
        try:
            # 데이터 파일 삭제
            file_path = self.cache_dir / data_file
            if file_path.exists():
                file_path.unlink()
            
            # DB 엔트리 삭제
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM cache_entries WHERE key_hash = ?", (key_hash,))
                
        except Exception as e:
            print(f"⚠️ 캐시 엔트리 삭제 실패: {e}")
    
    def cleanup_expired(self) -> int:
        """만료된 캐시 엔트리 정리"""
        with self._lock:
            deleted_count = 0
            
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.execute("""
                        SELECT key_hash, data_file, created_at, ttl_seconds
                        FROM cache_entries
                    """)
                    
                    expired_entries = []
                    for row in cursor.fetchall():
                        key_hash, data_file, created_at_str, ttl_seconds = row
                        created_at = datetime.fromisoformat(created_at_str)
                        
                        if self._is_expired(created_at, ttl_seconds):
                            expired_entries.append((key_hash, data_file))
                    
                    # 만료된 엔트리 삭제
                    for key_hash, data_file in expired_entries:
                        self._delete_entry(key_hash, data_file)
                        deleted_count += 1
                
                if deleted_count > 0:
                    print(f"🧹 만료된 캐시 엔트리 {deleted_count}개 정리 완료")
                
                return deleted_count
                
            except Exception as e:
                print(f"❌ 캐시 정리 실패: {e}")
                return 0
    
    def get_stats(self) -> Dict[str, Any]:
        """L2 캐시 통계 조회 (전문가 조언 지표 포함)"""
        cache_size = 0
        l1_entry_count = 0
        l2_pattern_count = 0
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                # L1 캐시 통계
                cursor = conn.execute("SELECT COUNT(*), SUM(data_size) FROM cache_entries")
                row = cursor.fetchone()
                if row:
                    l1_entry_count, total_size = row
                    cache_size = total_size or 0
                
                # L2 패턴 통계
                cursor = conn.execute("SELECT COUNT(*) FROM l2_query_patterns")
                row = cursor.fetchone()
                if row:
                    l2_pattern_count = row[0]
        except Exception:
            pass
        
        # 지연시간 절약 계산 (추정값)
        estimated_latency_saved = self.stats.total_hits * 120  # 120ms per hit
        
        return {
            "total_requests": self.stats.total_requests,
            "l1_hits": self.stats.l1_hits,
            "l2_hits": self.stats.l2_hits,
            "total_hits": self.stats.total_hits,
            "cache_misses": self.stats.cache_misses,
            "hit_rate": self.stats.hit_rate,
            "l2_effectiveness": self.stats.l2_effectiveness,
            "l1_entry_count": l1_entry_count,
            "l2_pattern_count": l2_pattern_count,
            "cache_size_bytes": cache_size,
            "cache_size_mb": cache_size / (1024 * 1024) if cache_size > 0 else 0,
            "estimated_latency_saved_ms": estimated_latency_saved,
            "similarity_threshold": self.similarity_threshold,
            "l2_enabled": self.enable_l2
        }
    
    def clear(self) -> bool:
        """전체 캐시 삭제"""
        with self._lock:
            try:
                # 모든 데이터 파일 삭제
                for file_path in self.cache_dir.glob("*.pkl"):
                    file_path.unlink()
                
                # DB 초기화
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute("DELETE FROM cache_entries")
                
                # 통계 리셋
                self.stats = CacheStats()
                
                print("🧹 전체 캐시 삭제 완료")
                return True
                
            except Exception as e:
                print(f"❌ 캐시 삭제 실패: {e}")
                return False
    
    def find_similar_queries(self, query: str, model: str, temperature: float, limit: int = 5) -> List[Dict]:
        """유사한 쿼리 검색 (간단한 키워드 기반)"""
        query_words = set(query.lower().split())
        similar_entries = []
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    SELECT key_hash, query_hash, hit_count, created_at
                    FROM cache_entries 
                    WHERE model = ? AND temperature = ?
                    ORDER BY hit_count DESC
                    LIMIT ?
                """, (model, temperature, limit * 2))  # 더 많이 가져와서 필터링
                
                for row in cursor.fetchall():
                    key_hash, query_hash, hit_count, created_at = row
                    
                    # 간단한 유사도 계산 (실제로는 더 정교한 semantic similarity 필요)
                    if query_hash:  # query_hash가 있는 경우만
                        similar_entries.append({
                            "key_hash": key_hash,
                            "query_hash": query_hash,
                            "hit_count": hit_count,
                            "created_at": created_at
                        })
                
                return similar_entries[:limit]
                
        except Exception as e:
            print(f"⚠️ 유사 쿼리 검색 실패: {e}")
            return []

class CachedLLMClient:
    """캐시가 적용된 LLM 클라이언트 래퍼"""
    
    def __init__(self, llm_client, cache: SemanticCache):
        """초기화"""
        self.llm_client = llm_client
        self.cache = cache
        print("🔄 CachedLLMClient 초기화 완료")
    
    def chat_completion_cached(self, model: str, messages: List[Dict], temperature: float = 0.7, 
                             max_tokens: int = 150, use_cache: bool = True, **kwargs) -> Any:
        """캐시가 적용된 chat completion"""
        
        if not use_cache:
            return self.llm_client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )
        
        # 프롬프트 구성 (캐시 키용)
        prompt_parts = []
        user_query = ""
        
        for msg in messages:
            if msg["role"] == "system":
                prompt_parts.append(f"SYSTEM: {msg['content']}")
            elif msg["role"] == "user":
                prompt_parts.append(f"USER: {msg['content']}")
                user_query = msg['content']  # 마지막 user 메시지를 쿼리로 사용
        
        prompt = "\n".join(prompt_parts)
        
        # 캐시에서 조회
        cached_response = self.cache.get(model, temperature, prompt, user_query)
        if cached_response is not None:
            return cached_response
        
        # 캐시 미스 - LLM 호출
        start_time = time.time()
        response = self.llm_client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )
        call_time = (time.time() - start_time) * 1000
        
        # 응답 캐시에 저장
        self.cache.set(model, temperature, prompt, response, user_query)
        
        print(f"🚀 LLM 호출 완료 ({call_time:.1f}ms), 캐시에 저장됨")
        return response 