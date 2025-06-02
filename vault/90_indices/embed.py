#!/usr/bin/env python3
"""
Vault 영상 자막을 Chroma DB에 임베딩하는 스크립트
실행 경로: vault/10_videos → vault/90_indices/chroma
"""

import sys
from pathlib import Path
import yaml
import chromadb
from chromadb.config import Settings as ChromaSettings

# Vault 경로 설정
VAULT_ROOT = Path(__file__).parent.parent
VIDEOS_PATH = VAULT_ROOT / "10_videos"
CHROMA_PATH = VAULT_ROOT / "90_indices" / "chroma"

def main():
    """메인 임베딩 실행 함수"""
    print(f"🔍 영상 검색: {VIDEOS_PATH}")
    print(f"💾 Chroma 저장: {CHROMA_PATH}")
    
    # Chroma 클라이언트 초기화
    client = chromadb.PersistentClient(
        path=str(CHROMA_PATH),
        settings=ChromaSettings(anonymized_telemetry=False)
    )
    
    collection = client.get_or_create_collection(
        name="video_transcripts",
        metadata={"description": "YouTube 영상 자막 임베딩"}
    )
    
    # 기존 임베딩된 video_id 목록 가져오기
    try:
        existing_data = collection.get()
        existing_ids = set(existing_data['ids']) if existing_data['ids'] else set()
        print(f"📊 기존 임베딩: {len(existing_ids)}개")
    except Exception:
        existing_ids = set()
        print("📊 기존 임베딩: 0개 (새로운 컬렉션)")
    
    processed_count = 0
    skipped_count = 0
    
    # 모든 captions.md 파일 처리
    for captions_file in VIDEOS_PATH.rglob("captions.md"):
        try:
            with open(captions_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # YAML frontmatter 파싱
            if content.startswith('---'):
                parts = content.split('---', 2)
                if len(parts) >= 3:
                    metadata = yaml.safe_load(parts[1])
                    transcript = parts[2].strip()
                    
                    video_id = str(metadata.get("video_id", f"video_{processed_count}"))
                    
                    # 중복 체크: 이미 임베딩된 경우 스킵
                    if video_id in existing_ids:
                        skipped_count += 1
                        print(f"⏭️  스킵됨: {metadata.get('title', 'Unknown')} (이미 임베딩됨)")
                        continue
                    
                    # Chroma에 추가 (모든 메타데이터를 문자열로 변환)
                    collection.add(
                        documents=[transcript],
                        metadatas=[{
                            "title": str(metadata.get("title", "")),
                            "channel": str(metadata.get("channel", "")),
                            "video_id": str(metadata.get("video_id", "")),
                            "upload": str(metadata.get("upload", "")),
                            "duration": str(metadata.get("duration", "")),
                            "excerpt": str(metadata.get("excerpt", "")),
                            "file_path": str(captions_file.relative_to(VAULT_ROOT))
                        }],
                        ids=[video_id]
                    )
                    
                    processed_count += 1
                    print(f"✅ 처리됨: {metadata.get('title', 'Unknown')}")
                    
        except Exception as e:
            print(f"❌ 오류: {captions_file} - {e}")
            continue
    
    print(f"\n🎉 완료: {processed_count}개 새로 임베딩, {skipped_count}개 스킵됨")

def search_example(query: str, n_results: int = 5):
    """검색 예시 함수"""
    client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    collection = client.get_collection("video_transcripts")
    
    results = collection.query(
        query_texts=[query],
        n_results=n_results
    )
    
    print(f"\n🔍 검색: '{query}'")
    for i, (doc, metadata) in enumerate(zip(results['documents'][0], results['metadatas'][0])):
        print(f"{i+1}. {metadata['title']} ({metadata['channel']})")
        print(f"   {metadata['excerpt'][:100]}...")
        print()

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "search":
        query = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "도쿄 부동산"
        search_example(query)
    else:
        main()
