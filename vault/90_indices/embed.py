#!/usr/bin/env python3
"""
Vault 영상 자막을 Chroma DB에 임베딩하는 스크립트 (채널별 완전 격리)
실행 경로: vault/10_videos → vault/90_indices/chroma
각 채널은 독립된 컬렉션으로 완전히 분리됨
"""

import sys
from pathlib import Path
import yaml
import chromadb
from chromadb.config import Settings as ChromaSettings
import re
import hashlib

# Vault 경로 설정
VAULT_ROOT = Path(__file__).parent.parent
VIDEOS_PATH = VAULT_ROOT / "10_videos"
CHROMA_PATH = VAULT_ROOT / "90_indices" / "chroma"

def sanitize_collection_name(name: str) -> str:
    """ChromaDB 컬렉션 이름 생성 (해시 기반 고유 식별자)"""
    # 원본 이름의 해시값 생성 (SHA1의 처음 8자리)
    hash_suffix = hashlib.sha1(name.encode('utf-8')).hexdigest()[:8]
    
    # 영문자만 추출해서 접두사로 사용 (최대 10자)
    ascii_prefix = re.sub(r'[^a-zA-Z0-9]', '', name)[:10]
    
    # 접두사가 없으면 'ch'로 시작
    if not ascii_prefix:
        ascii_prefix = 'ch'
    
    # 접두사가 숫자로 시작하면 앞에 'ch' 추가
    if ascii_prefix and ascii_prefix[0].isdigit():
        ascii_prefix = 'ch' + ascii_prefix
    
    # 최종 컬렉션명: 접두사_해시값 형태
    collection_name = f"{ascii_prefix}_{hash_suffix}"
    
    # ChromaDB 규칙 준수 확인 및 길이 제한
    collection_name = collection_name[:50]
    
    # 유효성 최종 검증
    if not re.match(r'^[a-zA-Z0-9][a-zA-Z0-9._-]*[a-zA-Z0-9]$', collection_name):
        # 안전한 폴백: ch_ + 해시값
        collection_name = f"ch_{hash_suffix}"
    
    return collection_name

def main(target_channels=None):
    """메인 임베딩 실행 함수 - 채널별 격리 컬렉션 생성"""
    print(f"🔍 영상 검색: {VIDEOS_PATH}")
    print(f"💾 Chroma 저장: {CHROMA_PATH}")
    
    if target_channels:
        print(f"🎯 선택된 채널만 처리: {target_channels}")
    else:
        print("🎯 모든 채널 처리 (채널별 완전 격리 모드)")
    
    # Chroma 클라이언트 초기화
    client = chromadb.PersistentClient(
        path=str(CHROMA_PATH),
        settings=ChromaSettings(anonymized_telemetry=False)
    )
    
    # 채널별 처리 통계
    channel_stats = {}
    total_processed = 0
    total_skipped = 0
    
    # 채널별로 그룹화하여 처리
    for channel_dir in VIDEOS_PATH.iterdir():
        if not channel_dir.is_dir():
            continue
            
        channel_name = channel_dir.name
        
        # 특정 채널만 처리하는 경우 필터링
        if target_channels and channel_name not in target_channels:
            print(f"⏭️  스킵: {channel_name} (선택되지 않음)")
            continue
        collection_name = f"channel_{sanitize_collection_name(channel_name)}"
        
        print(f"\n📺 채널 처리: {channel_name}")
        print(f"📦 컬렉션: {collection_name}")
        sys.stdout.flush()  # 실시간 출력을 위한 flush
        
        # 채널별 컬렉션 생성 (독립적)
        channel_collection = client.get_or_create_collection(
            name=collection_name,
            metadata={
                "description": f"{channel_name} 영상 자막 임베딩 (격리됨)",
                "channel_name": channel_name,
                "isolated": True
            }
        )
        
        # 기존 임베딩된 video_id 목록 가져오기
        try:
            existing_data = channel_collection.get()
            existing_ids = set(existing_data['ids']) if existing_data['ids'] else set()
            print(f"  📊 기존 임베딩: {len(existing_ids)}개")
        except Exception:
            existing_ids = set()
            print(f"  📊 기존 임베딩: 0개 (새로운 컬렉션)")
        
        channel_processed = 0
        channel_skipped = 0
        
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
                        
                        video_id = str(metadata.get("video_id", f"video_{total_processed}"))
                        
                        # 중복 체크: 이미 임베딩된 경우 스킵
                        if video_id in existing_ids:
                            channel_skipped += 1
                            print(f"  ⏭️  스킵됨: {metadata.get('title', 'Unknown')} (이미 임베딩됨)")
                            sys.stdout.flush()
                            continue
                        
                        # 메타데이터 정리 및 확장
                        enhanced_metadata = {
                            "title": str(metadata.get("title", "")),
                            "channel": str(metadata.get("channel", channel_name)),
                            "channel_normalized": sanitize_collection_name(channel_name),
                            "video_id": str(metadata.get("video_id", "")),
                            "upload": str(metadata.get("upload", "")),
                            "duration": str(metadata.get("duration", "")),
                            "excerpt": str(metadata.get("excerpt", ""))[:500],  # 길이 제한
                            "source_url": str(metadata.get("source_url", "")),
                            "file_path": str(captions_file.relative_to(VAULT_ROOT)),
                            "video_year": str(metadata.get("upload", ""))[:4] if metadata.get("upload") else "unknown",
                            "isolated_channel": True  # 격리 모드 표시
                        }
                        
                        # 채널별 컬렉션에만 추가 (통합 컬렉션 없음)
                        channel_collection.add(
                            documents=[transcript],
                            metadatas=[enhanced_metadata],
                            ids=[video_id]
                        )
                        
                        channel_processed += 1
                        print(f"  ✅ 처리됨: {metadata.get('title', 'Unknown')}")
                        sys.stdout.flush()
                        
            except Exception as e:
                print(f"  ❌ 오류: {captions_file} - {e}")
                continue
        
        # 채널별 통계 저장
        channel_stats[channel_name] = {
            "processed": channel_processed,
            "skipped": channel_skipped,
            "collection_name": collection_name
        }
        
        total_processed += channel_processed
        total_skipped += channel_skipped
        
        print(f"  📊 {channel_name}: {channel_processed}개 새로 임베딩, {channel_skipped}개 스킵됨")
        sys.stdout.flush()
    
    # 최종 결과 출력
    print(f"\n🎉 전체 완료 (채널별 격리 모드):")
    print(f"  📈 총 처리: {total_processed}개 새로 임베딩")
    print(f"  ⏭️  총 스킵: {total_skipped}개")
    print(f"  📦 생성된 컬렉션: {len(channel_stats)}개 (채널별 격리)")
    
    print(f"\n📋 채널별 상세:")
    for channel_name, stats in channel_stats.items():
        print(f"  📺 {channel_name}: {stats['processed']}개 처리 → {stats['collection_name']}")

def list_collections():
    """생성된 컬렉션 목록 확인"""
    client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    collections = client.list_collections()
    
    print(f"📦 ChromaDB 컬렉션 목록 (채널별 격리):")
    for collection in collections:
        try:
            data = collection.get()
            count = len(data['ids']) if data['ids'] else 0
            print(f"  - {collection.name}: {count}개 문서")
            
            # 메타데이터 샘플 출력
            if count > 0 and data['metadatas']:
                sample_metadata = data['metadatas'][0]
                channel = sample_metadata.get('channel', 'N/A')
                isolated = sample_metadata.get('isolated_channel', False)
                status = "격리됨" if isolated else "일반"
                print(f"    채널: {channel} ({status})")
        except Exception as e:
            print(f"  - {collection.name}: 오류 - {e}")

def search_example(query: str, channel_name: str, n_results: int = 5):
    """채널별 검색 예시 (통합 검색 제거)"""
    if not channel_name:
        print("❌ 채널명이 필요합니다. 채널별 격리 모드에서는 통합 검색이 불가능합니다.")
        print("사용법: python embed.py search <채널명> <검색어>")
        return
    
    client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    
    # 특정 채널에서만 검색
    collection_name = f"channel_{sanitize_collection_name(channel_name)}"
    try:
        collection = client.get_collection(collection_name)
        print(f"🔍 채널별 검색: '{query}' in {channel_name}")
    except Exception:
        print(f"❌ 채널 '{channel_name}' 컬렉션을 찾을 수 없습니다.")
        available_channels = []
        for coll in client.list_collections():
            if coll.name.startswith("channel_"):
                try:
                    data = coll.get()
                    if data['metadatas'] and len(data['metadatas']) > 0:
                        ch_name = data['metadatas'][0].get('channel', 'Unknown')
                        available_channels.append(ch_name)
                except:
                    continue
        
        if available_channels:
            print(f"사용 가능한 채널: {', '.join(available_channels)}")
        return
    
    results = collection.query(
        query_texts=[query],
        n_results=n_results
    )
    
    if not results['documents'][0]:
        print("검색 결과가 없습니다.")
        return
    
    print(f"📊 {len(results['documents'][0])}개 결과 발견:")
    for i, (doc, metadata) in enumerate(zip(results['documents'][0], results['metadatas'][0])):
        print(f"{i+1}. {metadata['title']}")
        print(f"   년도: {metadata.get('video_year', 'N/A')}")
        print(f"   {metadata.get('excerpt', doc[:100])}...")
        print()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "list":
            list_collections()
        elif command == "search":
            if len(sys.argv) < 4:
                print("사용법: python embed.py search <채널명> <검색어>")
                print("예시: python embed.py search takaki_takehana 도쿄투자")
                sys.exit(1)
            channel_name = sys.argv[2]
            query = " ".join(sys.argv[3:])
            search_example(query, channel_name)
        elif command == "channels":
            # 특정 채널들만 처리: python embed.py channels channel1 channel2 ...
            target_channels = sys.argv[2:] if len(sys.argv) > 2 else None
            if not target_channels:
                print("사용법: python embed.py channels <채널명1> [채널명2] ...")
                print("예시: python embed.py channels 도쿄부동산")
                sys.exit(1)
            main(target_channels)
        else:
            main()
    else:
        main()
