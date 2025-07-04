#!/usr/bin/env python3
"""
비디오 상세 정보 조회 스크립트
특정 비디오의 제목, 자막, 메타데이터를 JSON 형태로 반환
"""

import json
import sys
from pathlib import Path
import chromadb
from datetime import datetime
import re

# 프로젝트 루트 설정
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root / "src"))

CHROMA_PATH = project_root / "vault" / "90_indices" / "chroma"
VAULT_PATH = project_root / "vault" / "10_videos"

def get_video_info_from_chroma(video_id: str, channel_name: str):
    """Chroma DB에서 비디오 정보 조회"""
    try:
        client = chromadb.PersistentClient(path=str(CHROMA_PATH))
        collection = client.get_collection(channel_name)
        
        # video_id가 포함된 문서 검색
        results = collection.get(
            where={"video_id": video_id},
            include=["documents", "metadatas"]
        )
        
        if results["documents"]:
            # 첫 번째 결과 사용
            metadata = results["metadatas"][0] if results["metadatas"] else {}
            document = results["documents"][0] if results["documents"] else ""
            
            return {
                "video_id": video_id,
                "title": metadata.get("title", f"영상 {video_id}"),
                "transcript": document,
                "duration": metadata.get("duration"),
                "upload_date": metadata.get("upload_date"),
                "description": metadata.get("description")
            }
    
    except Exception as e:
        print(f"Warning: Chroma DB에서 비디오 정보 조회 실패: {e}", file=sys.stderr)
    
    return None

def get_video_info_from_vault(video_id: str, channel_name: str):
    """Vault 파일에서 비디오 정보 조회"""
    try:
        channel_dir = VAULT_PATH / channel_name
        if not channel_dir.exists():
            return None
        
        # 비디오 ID를 포함하는 디렉토리 찾기
        for year_dir in channel_dir.iterdir():
            if not year_dir.is_dir():
                continue
                
            for video_dir in year_dir.iterdir():
                if not video_dir.is_dir():
                    continue
                
                # 디렉토리명에서 비디오 ID 확인
                if video_id in video_dir.name:
                    # captions.md 파일에서 정보 추출
                    captions_file = video_dir / "captions.md"
                    if captions_file.exists():
                        content = captions_file.read_text(encoding='utf-8')
                        
                        # YAML frontmatter 파싱
                        if content.startswith('---'):
                            parts = content.split('---', 2)
                            if len(parts) >= 3:
                                yaml_content = parts[1]
                                transcript_content = parts[2].strip()
                                
                                # 간단한 YAML 파싱
                                title_match = re.search(r'^title:\s*"?([^"]+)"?$', yaml_content, re.MULTILINE)
                                upload_match = re.search(r'^upload:\s*(\d{4}-\d{2}-\d{2})$', yaml_content, re.MULTILINE)
                                
                                return {
                                    "video_id": video_id,
                                    "title": title_match.group(1) if title_match else f"영상 {video_id}",
                                    "transcript": transcript_content[:1000] + "..." if len(transcript_content) > 1000 else transcript_content,
                                    "duration": None,
                                    "upload_date": upload_match.group(1) if upload_match else None,
                                    "description": None
                                }
                        else:
                            # Frontmatter가 없는 경우 전체 내용을 자막으로 사용
                            return {
                                "video_id": video_id,
                                "title": f"영상 {video_id}",
                                "transcript": content[:1000] + "..." if len(content) > 1000 else content,
                                "duration": None,
                                "upload_date": None,
                                "description": None
                            }
    
    except Exception as e:
        print(f"Warning: Vault에서 비디오 정보 조회 실패: {e}", file=sys.stderr)
    
    return None

def get_video_details(video_id: str, channel_name: str):
    """비디오 상세 정보 조회 (Chroma DB 우선, 실패 시 Vault)"""
    
    # 1. Chroma DB에서 조회 시도
    info = get_video_info_from_chroma(video_id, channel_name)
    if info:
        print(f"✅ Chroma DB에서 비디오 정보 조회 성공: {video_id}", file=sys.stderr)
        return info
    
    # 2. Vault에서 조회 시도  
    info = get_video_info_from_vault(video_id, channel_name)
    if info:
        print(f"✅ Vault에서 비디오 정보 조회 성공: {video_id}", file=sys.stderr)
        return info
    
    # 3. 기본값 반환
    print(f"⚠️ 비디오 정보를 찾을 수 없음, 기본값 반환: {video_id}", file=sys.stderr)
    return {
        "video_id": video_id,
        "title": f"영상 {video_id}",
        "transcript": "자막 정보를 불러올 수 없습니다.",
        "duration": None,
        "upload_date": None,
        "description": None
    }

def main():
    """메인 함수"""
    if len(sys.argv) != 3:
        print("Usage: python get_video_info.py <video_id> <channel_name>", file=sys.stderr)
        sys.exit(1)
    
    video_id = sys.argv[1]
    channel_name = sys.argv[2]
    
    try:
        video_info = get_video_details(video_id, channel_name)
        print(json.dumps(video_info, ensure_ascii=False, indent=2))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        # 에러 시에도 기본 정보 반환
        fallback_info = {
            "video_id": video_id,
            "title": f"영상 {video_id}",
            "transcript": "자막 정보를 불러올 수 없습니다.",
            "duration": None,
            "upload_date": None,
            "description": None
        }
        print(json.dumps(fallback_info, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main() 