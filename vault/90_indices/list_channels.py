#!/usr/bin/env python3
"""
채널 목록 조회 스크립트
Tauri 앱에서 사용할 채널 정보를 JSON 형태로 반환
"""

import json
import sys
from pathlib import Path
import chromadb
from datetime import datetime

# 프로젝트 루트 설정
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root / "src"))

CHROMA_PATH = project_root / "vault" / "90_indices" / "chroma"

def get_available_channels():
    """사용 가능한 채널 목록 조회"""
    if not CHROMA_PATH.exists():
        return []
    
    try:
        client = chromadb.PersistentClient(path=str(CHROMA_PATH))
        collections = client.list_collections()
        
        channels = []
        for collection in collections:
            try:
                # 컬렉션 정보 가져오기
                coll = client.get_collection(collection.name)
                count = coll.count()
                
                # 메타데이터에서 추가 정보 가져오기
                metadata = collection.metadata or {}
                
                channel_info = {
                    "name": collection.name,
                    "video_count": count,
                    "description": metadata.get("description", f"{collection.name} 채널의 영상 컬렉션"),
                    "last_updated": metadata.get("last_updated", datetime.now().isoformat())
                }
                
                channels.append(channel_info)
                
            except Exception as e:
                print(f"Warning: 채널 {collection.name} 정보 로드 실패: {e}", file=sys.stderr)
                continue
        
        return channels
        
    except Exception as e:
        print(f"Error: Chroma DB 접근 실패: {e}", file=sys.stderr)
        return []

def main():
    """메인 함수"""
    try:
        channels = get_available_channels()
        print(json.dumps(channels, ensure_ascii=False, indent=2))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main() 