#!/usr/bin/env python3
"""
Gemini 기반 고급 벡터 검색 시스템
통합 검색, 채널별 필터링, 의미론적 검색 등 다양한 검색 기능 제공

기능:
1. 통합 검색: 모든 채널에서 검색
2. 채널별 필터링: 특정 채널에서만 검색  
3. 시간 필터링: 특정 기간 영상만 검색
4. 유사도 기반 정렬: 관련성 높은 순으로 정렬
5. 상세 결과 표시: 컨텍스트와 함께 표시
"""

import sys
import os
from pathlib import Path
import chromadb
from chromadb.config import Settings as ChromaSettings
from local_gemini import LocalGeminiClient
from dotenv import load_dotenv
import argparse
import json
from typing import List, Dict, Optional, Any
import logging
from datetime import datetime
import re
from session_manager import SearchSessionManager, save_search_to_session

# 환경변수 로드
load_dotenv()

# 경로 설정
VAULT_ROOT = Path(__file__).parent.parent
CHROMA_GEMINI_PATH = VAULT_ROOT / "90_indices" / "chroma_gemini"

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class GeminiSearchEngine:
    """Gemini 기반 벡터 검색 엔진"""
    
    def __init__(self):
        self.client = None
        self.collection = None
        self._setup_api()
        self._setup_database()
    
    def _setup_api(self):
        """로컬 Gemini 설정"""
        # 로컬 gemini 사용으로 API 키 불필요
        logger.info("✅ 로컬 Gemini 설정 완료")
    
    def _setup_database(self):
        """ChromaDB 데이터베이스 설정"""
        try:
            self.client = chromadb.PersistentClient(
                path=str(CHROMA_GEMINI_PATH),
                settings=ChromaSettings(anonymized_telemetry=False)
            )
            
            logger.info("✅ Gemini 검색 데이터베이스 연결 완료 (채널별 격리 모드)")
            
        except Exception as e:
            raise ValueError(f"❌ 검색 데이터베이스 연결 실패: {e}\n'python vault/90_indices/embed_gemini.py'를 먼저 실행하세요.")
    
    def _get_query_embedding(self, query: str) -> List[float]:
        """쿼리를 임베딩으로 변환 (로컬 gemini는 임베딩 미지원, OpenAI 사용)"""
        try:
            # 로컬 gemini는 임베딩 지원하지 않으므로 OpenAI 사용
            from openai import OpenAI
            client = OpenAI()
            result = client.embeddings.create(
                model="text-embedding-3-small",
                input=query
            )
            return result.data[0].embedding
        except Exception as e:
            logger.error(f"쿼리 임베딩 생성 실패: {e}")
            return None
    
    def get_collection_by_channel(self, channel_name: str):
        """채널명으로 Gemini 컬렉션 가져오기 (DeepSeek 방식과 동일)"""
        from embed_gemini import sanitize_collection_name
        collection_name = f"gemini_channel_{sanitize_collection_name(channel_name)}"
        try:
            return self.client.get_collection(collection_name)
        except Exception:
            return None
    
    def search(self, 
               query: str, 
               n_results: int = 10,
               channel_filter: Optional[str] = None,
               year_filter: Optional[str] = None,
               min_similarity: float = 0.0,
               save_to_session: bool = True,
               session_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """채널별 격리 검색 실행"""
        
        logger.info(f"🔍 Gemini 검색 시작: '{query}'")
        if channel_filter:
            logger.info(f"📺 채널 필터: {channel_filter}")
        if year_filter:
            logger.info(f"📅 연도 필터: {year_filter}")
        
        # 쿼리 임베딩 생성
        query_embedding = self._get_query_embedding(query)
        if query_embedding is None:
            return []
        
        all_results = []
        
        if channel_filter:
            # 특정 채널에서만 검색
            collection = self.get_collection_by_channel(channel_filter)
            if not collection:
                logger.error(f"❌ 채널 '{channel_filter}' 컬렉션을 찾을 수 없습니다.")
                return []
            
            results = self._search_in_collection(collection, query_embedding, n_results * 2)
            all_results.extend(results)
            
        else:
            # 모든 채널에서 검색 (채널별 격리 유지)
            collections = self.client.list_collections()
            gemini_collections = [c for c in collections if c.name.startswith("gemini_channel_")]
            
            if not gemini_collections:
                logger.info("❌ 검색 가능한 Gemini 컬렉션이 없습니다.")
                return []
            
            logger.info(f"🔍 {len(gemini_collections)}개 채널에서 검색 중...")
            
            for collection in gemini_collections:
                try:
                    results = self._search_in_collection(collection, query_embedding, n_results)
                    all_results.extend(results)
                except Exception as e:
                    logger.warning(f"⚠️ {collection.name} 검색 실패: {e}")
                    continue
        
        if not all_results:
            logger.info("❌ 검색 결과가 없습니다.")
            return []
        
        # 유사도 기반 정렬 및 필터링
        filtered_results = []
        for result in all_results:
            # 유사도 필터
            if result['similarity'] < min_similarity:
                continue
            
            # 연도 필터 (채널 필터는 이미 위에서 처리됨)
            if year_filter and year_filter not in result.get('video_year', ''):
                continue
            
            # 쿼리 기반 스니펫 생성
            result['content_snippet'] = self._create_content_snippet(result['content'], query)
            filtered_results.append(result)
        
        # 유사도 기준 정렬 및 중복 제거
        unique_results = {}
        for result in filtered_results:
            video_id = result['video_id']
            if video_id not in unique_results or result['similarity'] > unique_results[video_id]['similarity']:
                unique_results[video_id] = result
        
        final_results = sorted(unique_results.values(), key=lambda x: x['similarity'], reverse=True)
        
        # 순위 재정렬
        for i, result in enumerate(final_results[:n_results], 1):
            result['rank'] = i
        
        logger.info(f"📊 Gemini 검색 완료: {len(all_results)} → {len(final_results[:n_results])}")
        
        # 세션에 검색 결과 저장 (옵션)
        if save_to_session and final_results[:n_results]:
            try:
                search_entry = save_search_to_session(
                    query=query,
                    results=final_results[:n_results],
                    channel_filter=channel_filter,
                    year_filter=year_filter,
                    session_id=session_id
                )
                logger.info(f"💾 검색 결과 세션 저장 완료: {search_entry['search_id']}")
            except Exception as e:
                logger.warning(f"⚠️ 세션 저장 실패: {e}")
        
        return final_results[:n_results]
    
    def _search_in_collection(self, collection, query_embedding: List[float], n_results: int) -> List[Dict[str, Any]]:
        """단일 컬렉션에서 검색 실행"""
        try:
            search_results = collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results,
                include=["documents", "metadatas", "distances"]
            )
            
            if not search_results["documents"][0]:
                return []
            
            results = []
            for doc, metadata, distance in zip(
                search_results['documents'][0],
                search_results['metadatas'][0],
                search_results['distances'][0]
            ):
                similarity = 1 - distance
                
                result = {
                    'title': metadata.get('title', 'Unknown'),
                    'channel': metadata.get('channel', 'Unknown'),
                    'upload': metadata.get('upload', ''),
                    'video_year': metadata.get('video_year', ''),
                    'video_id': metadata.get('video_id', ''),
                    'source_url': metadata.get('source_url', ''),
                    'file_path': metadata.get('file_path', ''),
                    'content': doc,
                    'similarity': similarity,
                    'distance': distance,
                    'chunk_info': self._get_chunk_info(metadata),
                    'metadata': metadata
                }
                
                results.append(result)
            
            return results
            
        except Exception as e:
            logger.error(f"컬렉션 검색 실패: {e}")
            return []
    
    def _create_content_snippet(self, content: str, query: str, snippet_length: int = 400) -> str:
        """검색어 주변 컨텍스트를 포함한 스니펫 생성"""
        content_lower = content.lower()
        query_lower = query.lower()
        
        # 검색어가 포함된 위치 찾기
        query_terms = query_lower.split()
        best_position = 0
        max_matches = 0
        
        # 윈도우를 슬라이딩하면서 가장 많은 검색어가 포함된 위치 찾기
        window_size = snippet_length // 2
        for i in range(0, len(content) - window_size, 50):
            window = content_lower[i:i + window_size]
            matches = sum(1 for term in query_terms if term in window)
            if matches > max_matches:
                max_matches = matches
                best_position = i
        
        # 스니펫 생성
        start = max(0, best_position - snippet_length // 4)
        end = min(len(content), start + snippet_length)
        snippet = content[start:end]
        
        # 앞뒤 말줄임표 추가
        if start > 0:
            snippet = "..." + snippet
        if end < len(content):
            snippet = snippet + "..."
        
        return snippet.strip()
    
    def _get_chunk_info(self, metadata: Dict) -> str:
        """청크 정보 포맷팅"""
        chunk_index = metadata.get('chunk_index', 0)
        total_chunks = metadata.get('total_chunks', 1)
        
        if total_chunks > 1:
            return f"청크 {chunk_index + 1}/{total_chunks}"
        else:
            return "전체"
    
    def get_available_channels(self) -> List[str]:
        """사용 가능한 채널 목록 반환 (채널별 격리 방식)"""
        try:
            collections = self.client.list_collections()
            channels = []
            
            for collection in collections:
                if collection.name.startswith("gemini_channel_"):
                    try:
                        data = collection.get()
                        if data['metadatas'] and len(data['metadatas']) > 0:
                            channel_name = data['metadatas'][0].get('channel', 'Unknown')
                            video_count = len(data['ids']) if data['ids'] else 0
                            
                            channels.append({
                                'name': channel_name,
                                'collection_name': collection.name,
                                'video_count': video_count
                            })
                    except Exception:
                        continue
            
            return sorted([ch['name'] for ch in channels])
        except Exception as e:
            logger.error(f"채널 목록 조회 실패: {e}")
            return []
    
    def get_available_years(self) -> List[str]:
        """사용 가능한 연도 목록 반환 (모든 채널에서)"""
        try:
            collections = self.client.list_collections()
            years = set()
            
            for collection in collections:
                if collection.name.startswith("gemini_channel_"):
                    try:
                        data = collection.get()
                        for metadata in data['metadatas']:
                            year = metadata.get('video_year', '')
                            if year and year != 'unknown':
                                years.add(year)
                    except Exception:
                        continue
            
            return sorted(list(years), reverse=True)
        except Exception as e:
            logger.error(f"연도 목록 조회 실패: {e}")
            return []
    
    def get_database_stats(self) -> Dict[str, Any]:
        """데이터베이스 통계 정보 (채널별 격리 방식)"""
        try:
            collections = self.client.list_collections()
            gemini_collections = [c for c in collections if c.name.startswith("gemini_channel_")]
            
            total_documents = 0
            total_channels = len(gemini_collections)
            channel_stats = {}
            year_stats = {}
            unique_videos = set()
            
            for collection in gemini_collections:
                try:
                    data = collection.get()
                    if not data['metadatas']:
                        continue
                    
                    channel_name = data['metadatas'][0].get('channel', 'Unknown')
                    channel_docs = len(data['ids'])
                    total_documents += channel_docs
                    channel_stats[channel_name] = channel_docs
                    
                    # 연도별 통계 및 고유 비디오 수집
                    for metadata in data['metadatas']:
                        year = metadata.get('video_year', 'unknown')
                        year_stats[year] = year_stats.get(year, 0) + 1
                        
                        video_id = metadata.get('video_id', '')
                        if video_id:
                            unique_videos.add(video_id)
                            
                except Exception as e:
                    logger.warning(f"컬렉션 {collection.name} 통계 조회 실패: {e}")
                    continue
            
            return {
                'total_documents': total_documents,
                'unique_videos': len(unique_videos),
                'channels': total_channels,
                'channel_distribution': dict(sorted(channel_stats.items(), key=lambda x: x[1], reverse=True)),
                'year_distribution': dict(sorted(year_stats.items(), key=lambda x: x[0], reverse=True)),
                'embedding_model': 'gemini-text-embedding-004',
                'isolation_mode': True
            }
        except Exception as e:
            logger.error(f"통계 조회 실패: {e}")
            return {}

def print_search_results(results: List[Dict], show_content: bool = False, format_type: str = "detailed"):
    """검색 결과를 포맷팅하여 출력"""
    if not results:
        print("🔍 검색 결과가 없습니다.")
        return
    
    print(f"\n🔍 검색 결과: {len(results)}개 발견")
    print("=" * 100)
    
    for result in results:
        if format_type == "simple":
            print(f"{result['rank']}. {result['title']} ({result['channel']}) - 유사도: {result['similarity']:.3f}")
        
        elif format_type == "detailed":
            print(f"\n{result['rank']}. 📺 {result['title']}")
            print(f"   🏠 채널: {result['channel']}")
            print(f"   📅 업로드: {result['upload']} ({result['video_year']})")
            print(f"   📊 유사도: {result['similarity']:.3f}")
            print(f"   🔗 청크: {result['chunk_info']}")
            print(f"   📝 스니펫: {result['content_snippet']}")
            print(f"   🌐 링크: {result['source_url']}")
            
            if show_content:
                print(f"   📄 전체 내용:")
                content_lines = result['content'].split('\n')
                for line in content_lines[:5]:  # 처음 5줄만 표시
                    print(f"      {line}")
                if len(content_lines) > 5:
                    print(f"      ... ({len(content_lines) - 5}줄 더)")
            
            print("-" * 80)
        
        elif format_type == "json":
            # JSON 형태로 출력 (API나 자동화에 유용)
            print(json.dumps(result, ensure_ascii=False, indent=2))

def main():
    """메인 실행 함수"""
    parser = argparse.ArgumentParser(description="Gemini 기반 벡터 검색 시스템")
    
    # 서브커맨드 설정
    subparsers = parser.add_subparsers(dest='command', help='사용 가능한 명령어')
    
    # 검색 명령어
    search_parser = subparsers.add_parser('search', help='벡터 검색 실행')
    search_parser.add_argument('query', help='검색어')
    search_parser.add_argument('-n', '--num-results', type=int, default=10, help='결과 개수 (기본: 10)')
    search_parser.add_argument('-c', '--channel', help='특정 채널에서만 검색')
    search_parser.add_argument('-y', '--year', help='특정 연도 영상만 검색')
    search_parser.add_argument('-s', '--min-similarity', type=float, default=0.0, help='최소 유사도 (0.0-1.0)')
    search_parser.add_argument('--show-content', action='store_true', help='전체 내용 표시')
    search_parser.add_argument('--format', choices=['simple', 'detailed', 'json'], default='detailed', help='출력 형식')
    
    # 채널 목록 명령어
    subparsers.add_parser('channels', help='사용 가능한 채널 목록 표시')
    
    # 연도 목록 명령어
    subparsers.add_parser('years', help='사용 가능한 연도 목록 표시')
    
    # 통계 명령어
    subparsers.add_parser('stats', help='데이터베이스 통계 표시')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    try:
        # 검색 엔진 초기화
        search_engine = GeminiSearchEngine()
        
        if args.command == 'search':
            # 검색 실행
            results = search_engine.search(
                query=args.query,
                n_results=args.num_results,
                channel_filter=args.channel,
                year_filter=args.year,
                min_similarity=args.min_similarity,
                save_to_session=True  # 자동 세션 저장 활성화
            )
            
            # 결과 출력
            print_search_results(results, args.show_content, args.format)
            
        elif args.command == 'channels':
            # 채널 목록 표시
            channels = search_engine.get_available_channels()
            print(f"\n📺 사용 가능한 채널 ({len(channels)}개):")
            for i, channel in enumerate(channels, 1):
                print(f"  {i}. {channel}")
            
        elif args.command == 'years':
            # 연도 목록 표시
            years = search_engine.get_available_years()
            print(f"\n📅 사용 가능한 연도 ({len(years)}개):")
            for year in years:
                print(f"  - {year}")
            
        elif args.command == 'stats':
            # 통계 정보 표시
            stats = search_engine.get_database_stats()
            print(f"\n📊 Gemini 검색 데이터베이스 통계:")
            print(f"  📄 총 문서 수: {stats.get('total_documents', 0):,}개")
            print(f"  🎬 고유 비디오 수: {stats.get('unique_videos', 0):,}개")
            print(f"  📺 채널 수: {stats.get('channels', 0)}개")
            print(f"  🤖 임베딩 모델: {stats.get('embedding_model', 'N/A')}")
            
            # 채널별 분포
            channel_dist = stats.get('channel_distribution', {})
            if channel_dist:
                print(f"\n📺 채널별 문서 분포 (상위 10개):")
                for i, (channel, count) in enumerate(list(channel_dist.items())[:10], 1):
                    print(f"  {i}. {channel}: {count:,}개")
            
            # 연도별 분포
            year_dist = stats.get('year_distribution', {})
            if year_dist:
                print(f"\n📅 연도별 문서 분포:")
                for year, count in year_dist.items():
                    if year != 'unknown':
                        print(f"  {year}: {count:,}개")
            
    except Exception as e:
        logger.error(f"❌ 검색 엔진 오류: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()