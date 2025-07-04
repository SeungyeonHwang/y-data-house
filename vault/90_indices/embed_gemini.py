#!/usr/bin/env python3
"""
Gemini를 활용한 Vault 영상 자막 임베딩 시스템
기존 OpenAI 기반 시스템과 완전히 분리된 독립적인 벡터 검색 시스템

실행 경로: vault/10_videos → vault/90_indices/chroma_gemini
각 영상은 독립된 문서로 저장되며, 통합 검색 지원
"""

import sys
import os
from pathlib import Path
import yaml
import chromadb
from chromadb.config import Settings as ChromaSettings
import re
import hashlib
# import google.generativeai as genai  # 로컬 gemini 사용으로 주석 처리
from dotenv import load_dotenv
import time
from typing import List, Dict, Optional, Tuple
import logging

# 환경변수 로드
load_dotenv()

# Vault 경로 설정
VAULT_ROOT = Path(__file__).parent.parent
VIDEOS_PATH = VAULT_ROOT / "10_videos"
CHROMA_GEMINI_PATH = VAULT_ROOT / "90_indices" / "chroma_gemini"

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def setup_gemini_api() -> bool:
    """로컬 gemini 대신 OpenAI 임베딩 사용"""
    try:
        # 로컬 gemini는 임베딩을 지원하지 않으므로 OpenAI 사용
        from openai import OpenAI
        client = OpenAI()
        # 간단한 테스트로 연결 확인
        client.embeddings.create(
            model="text-embedding-3-small", 
            input="test"
        )
        logger.info("✅ OpenAI 임베딩 API 연결 확인")
        return True
    except Exception as e:
        logger.error(f"❌ OpenAI API 설정 실패: {e}")
        return False
    
    try:
        genai.configure(api_key=api_key)
        logger.info("✅ Gemini API 설정 완료")
        return True
    except Exception as e:
        logger.error(f"❌ Gemini API 설정 실패: {e}")
        return False

def get_gemini_embedding(text: str, model: str = "models/text-embedding-004") -> Optional[List[float]]:
    """Gemini를 사용하여 텍스트 임베딩 생성"""
    try:
        # 텍스트 길이 제한 (Gemini API 제한 고려)
        if len(text) > 50000:  # 약 50K 문자 제한
            text = text[:50000]
        
        result = genai.embed_content(
            model=model,
            content=text,
            task_type="retrieval_document"  # 문서 검색용 임베딩
        )
        
        return result['embedding']
        
    except Exception as e:
        logger.error(f"임베딩 생성 실패: {e}")
        # API 제한이나 오류 시 잠시 대기
        time.sleep(1)
        return None

def create_text_chunks(text: str, chunk_size: int = 3000, overlap: int = 300) -> List[str]:
    """긴 텍스트를 겹치는 청크로 분할"""
    chunks = []
    start = 0
    
    while start < len(text):
        end = start + chunk_size
        
        # 마지막 청크가 아니면 문장 경계에서 자르기
        if end < len(text):
            # 마지막 마침표나 줄바꿈을 찾아서 자연스럽게 분할
            last_period = text.rfind('.', start, end)
            last_newline = text.rfind('\n', start, end)
            
            cut_point = max(last_period, last_newline)
            if cut_point > start:
                end = cut_point + 1
        
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        
        # 다음 시작점 설정 (겹침 고려)
        start = end - overlap if end < len(text) else end
    
    return chunks

def sanitize_collection_name(name: str) -> str:
    """ChromaDB 컬렉션 이름 생성 (Gemini 전용)"""
    # 원본 이름의 해시값 생성
    hash_suffix = hashlib.sha1(name.encode('utf-8')).hexdigest()[:8]
    
    # 영문자만 추출해서 접두사로 사용
    ascii_prefix = re.sub(r'[^a-zA-Z0-9]', '', name)[:10]
    
    if not ascii_prefix:
        ascii_prefix = 'gemini'
    
    if ascii_prefix and ascii_prefix[0].isdigit():
        ascii_prefix = 'gemini' + ascii_prefix
    
    # Gemini 전용 컬렉션임을 명시
    collection_name = f"gemini_{ascii_prefix}_{hash_suffix}"
    
    # 길이 제한
    collection_name = collection_name[:50]
    
    # 유효성 검증
    if not re.match(r'^[a-zA-Z0-9][a-zA-Z0-9._-]*[a-zA-Z0-9]$', collection_name):
        collection_name = f"gemini_{hash_suffix}"
    
    return collection_name

def process_video_documents(chroma_client, target_channels: Optional[List[str]] = None):
    """영상별 문서 처리 및 임베딩 생성 - 채널별 격리 방식"""
    logger.info(f"🔍 영상 검색: {VIDEOS_PATH}")
    logger.info(f"💾 Gemini Chroma 저장: {CHROMA_GEMINI_PATH}")
    
    if target_channels:
        logger.info(f"🎯 선택된 채널만 처리: {target_channels}")
    else:
        logger.info("🎯 모든 채널 처리 (Gemini 채널별 격리 모드)")
    
    # 채널별 처리 통계
    channel_stats = {}
    total_processed = 0
    total_skipped = 0
    total_error = 0
    
    # 채널별로 그룹화하여 처리
    for channel_dir in VIDEOS_PATH.iterdir():
        if not channel_dir.is_dir():
            continue
            
        channel_name = channel_dir.name
        
        # 특정 채널만 처리하는 경우 필터링
        if target_channels and channel_name not in target_channels:
            logger.info(f"⏭️  스킵: {channel_name} (선택되지 않음)")
            continue
            
        # 채널별 Gemini 컬렉션 생성 (DeepSeek 방식과 동일한 격리)
        collection_name = f"gemini_channel_{sanitize_collection_name(channel_name)}"
        
        logger.info(f"\n📺 채널 처리: {channel_name}")
        logger.info(f"📦 Gemini 컬렉션: {collection_name}")
        
        # 채널별 컬렉션 생성 (독립적)
        channel_collection = chroma_client.get_or_create_collection(
            name=collection_name,
            metadata={
                "description": f"{channel_name} 영상 Gemini 임베딩 (채널별 격리)",
                "channel_name": channel_name,
                "model": "gemini-text-embedding-004",
                "isolated": True
            }
        )
        
        # 기존 임베딩된 video_id 목록 가져오기
        try:
            existing_data = channel_collection.get()
            existing_ids = set(existing_data['ids']) if existing_data['ids'] else set()
            logger.info(f"  📊 기존 임베딩: {len(existing_ids)}개")
        except Exception:
            existing_ids = set()
            logger.info(f"  📊 기존 임베딩: 0개 (새로운 컬렉션)")
        
        channel_processed = 0
        channel_skipped = 0
        channel_error = 0
        
        # 해당 채널의 모든 captions.md 파일 처리
        for captions_file in channel_dir.rglob("captions.md"):
            try:
                with open(captions_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # YAML frontmatter 파싱
                if content.startswith('---'):
                    parts = content.split('---', 2)
                    if len(parts) >= 3:
                        metadata = yaml.safe_load(parts[1])
                        transcript = parts[2].strip()
                        
                        video_id = str(metadata.get("video_id", f"unknown_{channel_processed}"))
                        
                        # 중복 체크: 이미 임베딩된 경우 스킵
                        if video_id in existing_ids:
                            channel_skipped += 1
                            logger.debug(f"  ⏭️  스킵됨: {metadata.get('title', 'Unknown')} (이미 임베딩됨)")
                            continue
                        
                        # 긴 텍스트인 경우 청크로 분할
                        if len(transcript) > 3000:
                            chunks = create_text_chunks(transcript)
                            logger.info(f"  📝 {metadata.get('title', 'Unknown')} - {len(chunks)}개 청크로 분할")
                        else:
                            chunks = [transcript]
                        
                        # 각 청크에 대해 임베딩 생성
                        for chunk_idx, chunk in enumerate(chunks):
                            try:
                                # Gemini 임베딩 생성
                                embedding = get_gemini_embedding(chunk)
                                if embedding is None:
                                    logger.warning(f"  ⚠️  임베딩 생성 실패: 청크 {chunk_idx}")
                                    continue
                                
                                # 메타데이터 준비
                                chunk_metadata = {
                                    "title": str(metadata.get("title", "")),
                                    "channel": str(metadata.get("channel", channel_name)),
                                    "video_id": str(metadata.get("video_id", "")),
                                    "upload": str(metadata.get("upload", "")),
                                    "duration": str(metadata.get("duration", "")),
                                    "source_url": str(metadata.get("source_url", "")),
                                    "file_path": str(captions_file.relative_to(VAULT_ROOT)),
                                    "video_year": str(metadata.get("upload", ""))[:4] if metadata.get("upload") else "unknown",
                                    "chunk_index": chunk_idx,
                                    "total_chunks": len(chunks),
                                    "chunk_preview": chunk[:200] + "..." if len(chunk) > 200 else chunk,
                                    "embedding_model": "gemini-text-embedding-004",
                                    "unified_search": True
                                }
                                
                                # 청크별 고유 ID 생성
                                chunk_id = f"{video_id}_chunk_{chunk_idx}" if len(chunks) > 1 else video_id
                                
                                # 채널별 컬렉션에 저장
                                channel_collection.add(
                                    documents=[chunk],
                                    metadatas=[chunk_metadata],
                                    ids=[chunk_id],
                                    embeddings=[embedding]
                                )
                                
                                logger.debug(f"    ✅ 청크 {chunk_idx + 1}/{len(chunks)} 임베딩 완료")
                                
                                # API 제한 고려 잠시 대기
                                time.sleep(0.1)
                                
                            except Exception as e:
                                logger.error(f"    ❌ 청크 {chunk_idx} 처리 실패: {e}")
                                channel_error += 1
                                continue
                        
                        channel_processed += 1
                        logger.info(f"  ✅ 처리 완료: {metadata.get('title', 'Unknown')}")
                        
            except Exception as e:
                logger.error(f"  ❌ 파일 처리 오류: {captions_file} - {e}")
                channel_error += 1
                continue
        
        # 채널별 통계 저장
        channel_stats[channel_name] = {
            "processed": channel_processed,
            "skipped": channel_skipped,
            "error": channel_error,
            "collection_name": collection_name
        }
        
        total_processed += channel_processed
        total_skipped += channel_skipped
        total_error += channel_error
        
        logger.info(f"  📊 {channel_name}: {channel_processed}개 새로 임베딩, {channel_skipped}개 스킵됨, {channel_error}개 오류")
    
    # 최종 결과 출력
    logger.info(f"\n🎉 Gemini 임베딩 완료 (채널별 격리 모드):")
    logger.info(f"  📈 총 처리: {total_processed}개 새로 임베딩")
    logger.info(f"  ⏭️  총 스킵: {total_skipped}개")
    logger.info(f"  ❌ 총 오류: {total_error}개")
    logger.info(f"  📦 생성된 컬렉션: {len(channel_stats)}개 (채널별 격리)")
    
    logger.info(f"\n📋 채널별 상세:")
    for channel_name, stats in channel_stats.items():
        logger.info(f"  📺 {channel_name}: {stats['processed']}개 처리 → {stats['collection_name']}")

def search_with_gemini(query: str, n_results: int = 10) -> List[Dict]:
    """Gemini 임베딩을 사용한 벡터 검색"""
    if not setup_gemini_api():
        return []
    
    try:
        # ChromaDB 클라이언트 초기화
        client = chromadb.PersistentClient(
            path=str(CHROMA_GEMINI_PATH),
            settings=ChromaSettings(anonymized_telemetry=False)
        )
        
        # 통합 검색 컬렉션 가져오기
        collection = client.get_collection("gemini_unified_search")
        
        # 쿼리 임베딩 생성
        query_embedding = get_gemini_embedding(query, model="models/text-embedding-004")
        if query_embedding is None:
            logger.error("❌ 쿼리 임베딩 생성 실패")
            return []
        
        # 검색 실행
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            include=["documents", "metadatas", "distances"]
        )
        
        # 결과 포맷팅
        formatted_results = []
        if results["documents"][0]:
            for i, (doc, metadata, distance) in enumerate(zip(
                results['documents'][0],
                results['metadatas'][0],
                results['distances'][0]
            )):
                formatted_results.append({
                    'rank': i + 1,
                    'title': metadata.get('title', 'Unknown'),
                    'channel': metadata.get('channel', 'Unknown'),
                    'content_snippet': doc[:300] + "..." if len(doc) > 300 else doc,
                    'distance': distance,
                    'similarity': 1 - distance,
                    'video_id': metadata.get('video_id', ''),
                    'source_url': metadata.get('source_url', ''),
                    'upload': metadata.get('upload', ''),
                    'file_path': metadata.get('file_path', ''),
                    'chunk_info': f"{metadata.get('chunk_index', 0) + 1}/{metadata.get('total_chunks', 1)}" if metadata.get('total_chunks', 1) > 1 else "전체"
                })
        
        return formatted_results
        
    except Exception as e:
        logger.error(f"❌ Gemini 검색 실패: {e}")
        return []

def list_gemini_collections():
    """Gemini 컬렉션 목록 확인 (채널별 격리 방식)"""
    try:
        client = chromadb.PersistentClient(path=str(CHROMA_GEMINI_PATH))
        collections = client.list_collections()
        
        gemini_collections = [c for c in collections if c.name.startswith("gemini_channel_")]
        
        logger.info(f"🔍 Gemini ChromaDB 컬렉션 목록 (채널별 격리):")
        for collection in gemini_collections:
            try:
                data = collection.get()
                count = len(data['ids']) if data['ids'] else 0
                logger.info(f"  - {collection.name}: {count}개 문서")
                
                # 메타데이터 샘플 출력
                if count > 0 and data['metadatas']:
                    sample_metadata = data['metadatas'][0]
                    channel = sample_metadata.get('channel', 'N/A')
                    model = sample_metadata.get('embedding_model', 'N/A')
                    isolated = sample_metadata.get('isolated', False)
                    status = "채널별 격리" if isolated else "일반"
                    logger.info(f"    채널: {channel}, 모델: {model} ({status})")
            except Exception as e:
                logger.error(f"  - {collection.name}: 오류 - {e}")
                
    except Exception as e:
        logger.error(f"❌ 컬렉션 목록 조회 실패: {e}")

def main(target_channels: Optional[List[str]] = None):
    """메인 실행 함수"""
    if not setup_gemini_api():
        sys.exit(1)
    
    try:
        # ChromaDB 클라이언트 초기화
        client = chromadb.PersistentClient(
            path=str(CHROMA_GEMINI_PATH),
            settings=ChromaSettings(anonymized_telemetry=False)
        )
        
        logger.info("✅ Gemini ChromaDB 클라이언트 초기화 완료")
        
        # 영상 문서 처리
        process_video_documents(client, target_channels)
        
    except Exception as e:
        logger.error(f"❌ Gemini 임베딩 처리 실패: {e}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "list":
            list_gemini_collections()
        elif command == "search":
            if len(sys.argv) < 3:
                print("사용법: python embed_gemini.py search <검색어>")
                print("예시: python embed_gemini.py search '도쿄 부동산 투자 전략'")
                sys.exit(1)
            
            query = " ".join(sys.argv[2:])
            results = search_with_gemini(query)
            
            if results:
                print(f"\n🔍 Gemini 검색 결과: '{query}'")
                print(f"📊 {len(results)}개 결과 발견")
                print("=" * 80)
                
                for result in results:
                    print(f"{result['rank']}. {result['title']}")
                    print(f"   📺 채널: {result['channel']}")
                    print(f"   📅 업로드: {result['upload']}")
                    print(f"   🔗 청크: {result['chunk_info']}")
                    print(f"   📊 유사도: {result['similarity']:.3f}")
                    print(f"   📝 내용: {result['content_snippet']}")
                    print(f"   🔗 링크: {result['source_url']}")
                    print("-" * 80)
            else:
                print("검색 결과가 없습니다.")
                
        elif command == "channels":
            # 특정 채널들만 처리
            target_channels = sys.argv[2:] if len(sys.argv) > 2 else None
            if not target_channels:
                print("사용법: python embed_gemini.py channels <채널명1> [채널명2] ...")
                print("예시: python embed_gemini.py channels 도쿄부동산 takaki_takehana")
                sys.exit(1)
            main(target_channels)
        else:
            main()
    else:
        main()