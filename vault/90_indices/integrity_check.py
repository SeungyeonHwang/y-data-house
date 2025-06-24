#!/usr/bin/env python3
"""
Y-Data-House 채널별 격리 정합성 검사 스크립트
- ChromaDB 컬렉션과 실제 파일 구조 비교
- 채널별 격리 상태 확인
- 벡터 데이터 무결성 검증
"""

import sys
from pathlib import Path
import yaml
import chromadb
from chromadb.config import Settings as ChromaSettings
import re
import hashlib
from collections import defaultdict

# Vault 경로 설정
VAULT_ROOT = Path(__file__).parent.parent
VIDEOS_PATH = VAULT_ROOT / "10_videos"
CHROMA_PATH = VAULT_ROOT / "90_indices" / "chroma"

def sanitize_collection_name(name: str) -> str:
    """ChromaDB 컬렉션 이름 생성 (해시 기반 고유 식별자)"""
    hash_suffix = hashlib.sha1(name.encode('utf-8')).hexdigest()[:8]
    ascii_prefix = re.sub(r'[^a-zA-Z0-9]', '', name)[:10]
    
    if not ascii_prefix:
        ascii_prefix = 'ch'
    
    if ascii_prefix and ascii_prefix[0].isdigit():
        ascii_prefix = 'ch' + ascii_prefix
    
    collection_name = f"{ascii_prefix}_{hash_suffix}"
    collection_name = collection_name[:50]
    
    if not re.match(r'^[a-zA-Z0-9][a-zA-Z0-9._-]*[a-zA-Z0-9]$', collection_name):
        collection_name = f"ch_{hash_suffix}"
    
    return collection_name

def check_file_structure():
    """vault/10_videos 디렉토리 구조 확인"""
    print("📁 파일 구조 검사:")
    print(f"  🔍 검사 경로: {VIDEOS_PATH}")
    
    if not VIDEOS_PATH.exists():
        print(f"  ❌ 비디오 경로가 존재하지 않습니다: {VIDEOS_PATH}")
        return {}
    
    channel_stats = {}
    total_videos = 0
    
    for channel_dir in VIDEOS_PATH.iterdir():
        if not channel_dir.is_dir():
            continue
            
        channel_name = channel_dir.name
        print(f"\n  📺 채널: {channel_name}")
        
        # captions.md 파일 카운트
        captions_files = list(channel_dir.rglob("captions.md"))
        video_count = len(captions_files)
        total_videos += video_count
        
        # 실제 비디오 파일 확인
        video_files = list(channel_dir.rglob("*.mp4"))
        
        channel_stats[channel_name] = {
            "captions_count": video_count,
            "video_files": len(video_files),
            "captions_files": captions_files
        }
        
        print(f"    📄 자막 파일: {video_count}개")
        print(f"    🎥 비디오 파일: {len(video_files)}개")
        
        # 파일 구조 무결성 확인
        missing_videos = video_count - len(video_files)
        if missing_videos > 0:
            print(f"    ⚠️  누락된 비디오: {missing_videos}개")
    
    print(f"\n  📊 전체 통계: {len(channel_stats)}개 채널, {total_videos}개 비디오")
    return channel_stats

def check_chroma_collections():
    """ChromaDB 컬렉션 상태 확인"""
    print(f"\n🗄️  ChromaDB 컬렉션 검사:")
    print(f"  🔍 ChromaDB 경로: {CHROMA_PATH}")
    
    if not CHROMA_PATH.exists():
        print(f"  ❌ ChromaDB 경로가 존재하지 않습니다: {CHROMA_PATH}")
        return {}
    
    try:
        client = chromadb.PersistentClient(
            path=str(CHROMA_PATH),
            settings=ChromaSettings(anonymized_telemetry=False)
        )
        
        collections = client.list_collections()
        print(f"  📦 총 컬렉션 수: {len(collections)}개")
        
        collection_stats = {}
        total_embedded = 0
        
        for collection in collections:
            try:
                data = collection.get()
                doc_count = len(data['ids']) if data['ids'] else 0
                total_embedded += doc_count
                
                # 컬렉션 메타데이터에서 채널명 추출
                channel_name = "Unknown"
                if data['metadatas'] and len(data['metadatas']) > 0:
                    first_meta = data['metadatas'][0]
                    channel_name = first_meta.get('channel', 'Unknown')
                    isolated = first_meta.get('isolated_channel', False)
                
                collection_stats[collection.name] = {
                    "channel_name": channel_name,
                    "document_count": doc_count,
                    "collection_uuid": collection.id,
                    "isolated": isolated
                }
                
                print(f"\n  📚 컬렉션: {collection.name}")
                print(f"    📺 채널: {channel_name}")
                print(f"    📄 문서 수: {doc_count}개")
                print(f"    🆔 UUID: {collection.id}")
                print(f"    🔐 격리 모드: {'✅' if isolated else '❌'}")
                
                # ChromaDB 전체 크기 확인 (개별 UUID 폴더는 내부 구현이라 체크 안함)
                chroma_db_size = CHROMA_PATH / "chroma.sqlite3"
                if chroma_db_size.exists():
                    db_size = chroma_db_size.stat().st_size
                    print(f"    💾 DB 크기: {db_size / (1024*1024):.1f}MB")
                
            except Exception as e:
                print(f"  ❌ 컬렉션 {collection.name} 오류: {e}")
                
        print(f"\n  📊 전체 임베딩: {total_embedded}개 문서")
        return collection_stats
        
    except Exception as e:
        print(f"  ❌ ChromaDB 연결 실패: {e}")
        return {}

def cross_check_integrity(file_stats, collection_stats):
    """파일 구조와 ChromaDB 간 정합성 교차 검증"""
    print(f"\n🔍 채널별 격리 정합성 교차 검증:")
    
    issues = []
    channel_mapping = {}
    
    # 1. 채널명 → 컬렉션명 매핑 생성
    for channel_name in file_stats.keys():
        expected_collection = f"channel_{sanitize_collection_name(channel_name)}"
        channel_mapping[channel_name] = expected_collection
    
    print(f"  📋 채널 → 컬렉션 매핑:")
    for channel, collection in channel_mapping.items():
        print(f"    📺 {channel} → 📦 {collection}")
    
    # 2. 각 채널별 정합성 확인
    for channel_name, file_info in file_stats.items():
        expected_collection = channel_mapping[channel_name]
        
        print(f"\n  🔍 {channel_name} 채널 검증:")
        print(f"    📁 파일: {file_info['captions_count']}개 자막")
        
        # 해당 컬렉션이 존재하는지 확인
        if expected_collection in collection_stats:
            collection_info = collection_stats[expected_collection]
            embedded_count = collection_info['document_count']
            
            print(f"    📦 컬렉션: {embedded_count}개 임베딩")
            print(f"    🔐 격리: {'✅' if collection_info['isolated'] else '❌'}")
            
            # 개수 비교
            if file_info['captions_count'] == embedded_count:
                print(f"    ✅ 정합성: 완전 일치")
            elif embedded_count == 0:
                print(f"    ⚠️  정합성: 임베딩 없음 (처리 필요)")
            elif file_info['captions_count'] > embedded_count:
                missing = file_info['captions_count'] - embedded_count
                print(f"    ⚠️  정합성: {missing}개 임베딩 누락")
                issues.append(f"{channel_name}: {missing}개 임베딩 누락")
            else:
                extra = embedded_count - file_info['captions_count']
                print(f"    ⚠️  정합성: {extra}개 불필요한 임베딩")
                issues.append(f"{channel_name}: {extra}개 불필요한 임베딩")
                
        else:
            print(f"    ❌ 컬렉션: 누락됨")
            issues.append(f"{channel_name}: 컬렉션 누락")
    
    # 3. 불필요한 컬렉션 확인
    expected_collections = set(channel_mapping.values())
    actual_collections = set(collection_stats.keys())
    
    orphan_collections = actual_collections - expected_collections
    if orphan_collections:
        print(f"\n  ⚠️  불필요한 컬렉션:")
        for orphan in orphan_collections:
            print(f"    📦 {orphan}")
            issues.append(f"불필요한 컬렉션: {orphan}")
    
    return issues

def check_vector_isolation():
    """벡터 격리 상태 확인"""
    print(f"\n🔐 벡터 격리 검증:")
    
    if not CHROMA_PATH.exists():
        print("  ❌ ChromaDB가 초기화되지 않음")
        return
    
    try:
        client = chromadb.PersistentClient(
            path=str(CHROMA_PATH),
            settings=ChromaSettings(anonymized_telemetry=False)
        )
        collections = client.list_collections()
        
        # 컬렉션 간 데이터 섞임 확인
        channel_documents = defaultdict(set)
        
        for collection in collections:
            data = collection.get()
            if data['metadatas']:
                for meta in data['metadatas']:
                    channel = meta.get('channel', 'Unknown')
                    video_id = meta.get('video_id', 'Unknown')
                    channel_documents[channel].add(video_id)
        
        print(f"  📊 채널별 문서 분포:")
        for channel, docs in channel_documents.items():
            print(f"    📺 {channel}: {len(docs)}개 고유 문서")
        
        # 중복 video_id 확인 (같은 비디오가 여러 채널에 있으면 안됨)
        all_video_ids = []
        for docs in channel_documents.values():
            all_video_ids.extend(docs)
        
        duplicates = len(all_video_ids) - len(set(all_video_ids))
        if duplicates > 0:
            print(f"    ⚠️  중복 video_id: {duplicates}개")
        else:
            print(f"    ✅ 중복 없음: 모든 video_id 고유")
            
    except Exception as e:
        print(f"  ❌ 격리 검증 실패: {e}")

def main():
    """메인 정합성 검사 실행"""
    print("🔍 Y-Data-House 채널별 격리 정합성 검사")
    print("=" * 60)
    
    # 1. 파일 구조 검사
    file_stats = check_file_structure()
    
    # 2. ChromaDB 컬렉션 검사  
    collection_stats = check_chroma_collections()
    
    # 3. 교차 검증
    issues = cross_check_integrity(file_stats, collection_stats)
    
    # 4. 벡터 격리 검증
    check_vector_isolation()
    
    # 5. 최종 결과
    print(f"\n" + "=" * 60)
    print("📋 정합성 검사 결과:")
    
    if not issues:
        print("  ✅ 모든 검사 통과!")
        print("  🔐 채널별 격리가 올바르게 유지되고 있습니다.")
    else:
        print(f"  ⚠️  {len(issues)}개 문제 발견:")
        for issue in issues:
            print(f"    - {issue}")
    
    print(f"\n🎯 권장 사항:")
    print(f"  1. 누락된 임베딩이 있다면 '채널별 벡터 생성' 실행")
    print(f"  2. 불필요한 컬렉션은 수동으로 정리 필요")
    print(f"  3. 정기적인 정합성 검사 권장")

if __name__ == "__main__":
    main() 