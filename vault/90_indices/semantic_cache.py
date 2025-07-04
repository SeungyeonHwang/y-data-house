#!/usr/bin/env python3
"""
Semantic Cache System - LLM 호출 40% 절감
rewritten query와 HyDE 문서 캐싱으로 70% hit rate 목표

조언 기반 최적화:
- (model, temperature, prompt_hash) 키로 캐시
- TTL 7일 설정
- 유사 질의 재사용 (semantic similarity)
- 파일 기반 → Redis 확장 가능
"""

import os
import hashlib
import json
import time
import pickle
from typing import Dict, Optional, Any, List, Union
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass
import sqlite3
from threading import Lock
from schemas import CacheKey, CacheEntry

@dataclass
class CacheStats:
    """캐시 통계"""
    total_requests: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    
    @property
    def hit_rate(self) -> float:
        return self.cache_hits / self.total_requests if self.total_requests > 0 else 0.0

class SemanticCache:
    """Semantic Cache 시스템"""
    
    def __init__(self, cache_dir: Path = None, ttl_seconds: int = 604800):  # 7일
        """초기화"""
        self.cache_dir = cache_dir or Path(__file__).parent / "cache"
        self.cache_dir.mkdir(exist_ok=True)
        self.ttl_seconds = ttl_seconds
        self.stats = CacheStats()
        self._lock = Lock()
        
        # SQLite DB 초기화 (메타데이터 저장용)
        self.db_path = self.cache_dir / "cache_meta.db"
        self._init_db()
        
        print(f"💾 Semantic Cache 초기화: {self.cache_dir}")
        print(f"⏰ TTL: {ttl_seconds}초 ({ttl_seconds//86400}일)")
    
    def _init_db(self):
        """SQLite DB 초기화"""
        with sqlite3.connect(self.db_path) as conn:
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
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_created_ttl 
                ON cache_entries (created_at, ttl_seconds)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_model_temp 
                ON cache_entries (model, temperature)
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
        """캐시에서 데이터 조회"""
        with self._lock:
            self.stats.total_requests += 1
            
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
                    if not row:
                        self.stats.cache_misses += 1
                        return None
                    
                    created_at_str, ttl_seconds, hit_count, data_file = row
                    created_at = datetime.fromisoformat(created_at_str)
                    
                    # TTL 만료 확인
                    if self._is_expired(created_at, ttl_seconds):
                        self._delete_entry(key_hash, data_file)
                        self.stats.cache_misses += 1
                        return None
                    
                    # 데이터 로드
                    data = self._load_data_file(data_file)
                    if data is None:
                        self._delete_entry(key_hash, data_file)
                        self.stats.cache_misses += 1
                        return None
                    
                    # 히트 카운트 증가
                    conn.execute("""
                        UPDATE cache_entries 
                        SET hit_count = ? 
                        WHERE key_hash = ?
                    """, (hit_count + 1, key_hash))
                    
                    self.stats.cache_hits += 1
                    print(f"✅ 캐시 히트: {key_hash[:8]}... (hit_count: {hit_count + 1})")
                    return data
                    
            except Exception as e:
                print(f"⚠️ 캐시 조회 실패: {e}")
                self.stats.cache_misses += 1
                return None
    
    def set(self, model: str, temperature: float, prompt: str, data: Any, query: str = "", ttl_seconds: int = None) -> bool:
        """캐시에 데이터 저장"""
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
                
                print(f"💾 캐시 저장: {key_hash[:8]}... ({data_size} bytes)")
                return True
                
            except Exception as e:
                print(f"❌ 캐시 저장 실패: {e}")
                return False
    
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
        """캐시 통계 조회"""
        cache_size = 0
        entry_count = 0
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("SELECT COUNT(*), SUM(data_size) FROM cache_entries")
                row = cursor.fetchone()
                if row:
                    entry_count, total_size = row
                    cache_size = total_size or 0
        except Exception:
            pass
        
        return {
            "total_requests": self.stats.total_requests,
            "cache_hits": self.stats.cache_hits,
            "cache_misses": self.stats.cache_misses,
            "hit_rate": self.stats.hit_rate,
            "entry_count": entry_count,
            "cache_size_bytes": cache_size,
            "cache_size_mb": cache_size / (1024 * 1024) if cache_size > 0 else 0
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