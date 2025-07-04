#!/usr/bin/env python3
"""
Gemini 검색 세션 관리 시스템
- 검색 기록 자동 저장
- 대화 세션 관리 
- 영상 링크 클릭 가능
- 세션별 북마크 기능
"""

import os
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
import logging

# 경로 설정
VAULT_ROOT = Path(__file__).parent.parent
SESSIONS_PATH = VAULT_ROOT / "90_indices" / "search_sessions"

logger = logging.getLogger(__name__)

class SearchSessionManager:
    """검색 세션 관리 클래스"""
    
    def __init__(self):
        self.sessions_dir = SESSIONS_PATH
        self.sessions_dir.mkdir(exist_ok=True)
        
        # 현재 활성 세션
        self.current_session_id = None
        self.current_session_data = None
    
    def create_new_session(self, title: Optional[str] = None) -> str:
        """새로운 검색 세션 생성"""
        session_id = str(uuid.uuid4())[:8]
        timestamp = datetime.now()
        
        if not title:
            title = f"검색 세션 {timestamp.strftime('%m/%d %H:%M')}"
        
        session_data = {
            "session_id": session_id,
            "title": title,
            "created_at": timestamp.isoformat(),
            "updated_at": timestamp.isoformat(),
            "searches": [],
            "bookmarks": [],
            "total_searches": 0,
            "favorite": False
        }
        
        self.current_session_id = session_id
        self.current_session_data = session_data
        self._save_session(session_data)
        
        logger.info(f"🆕 새 검색 세션 생성: {title} ({session_id})")
        return session_id
    
    def load_session(self, session_id: str) -> Dict[str, Any]:
        """기존 세션 로드"""
        session_file = self.sessions_dir / f"{session_id}.json"
        
        if not session_file.exists():
            raise FileNotFoundError(f"세션을 찾을 수 없습니다: {session_id}")
        
        try:
            with open(session_file, 'r', encoding='utf-8') as f:
                session_data = json.load(f)
            
            self.current_session_id = session_id
            self.current_session_data = session_data
            
            logger.info(f"📂 세션 로드: {session_data['title']} ({session_id})")
            return session_data
            
        except Exception as e:
            logger.error(f"세션 로드 실패: {e}")
            raise
    
    def save_search(self, query: str, results: List[Dict[str, Any]], 
                   channel_filter: Optional[str] = None,
                   year_filter: Optional[str] = None) -> Dict[str, Any]:
        """검색 결과를 현재 세션에 저장"""
        
        if not self.current_session_id:
            self.create_new_session()
        
        search_entry = {
            "search_id": str(uuid.uuid4())[:8],
            "timestamp": datetime.now().isoformat(),
            "query": query,
            "channel_filter": channel_filter,
            "year_filter": year_filter,
            "results_count": len(results),
            "results": []
        }
        
        # 검색 결과 처리 (클릭 가능한 링크와 함께 저장)
        for i, result in enumerate(results):
            processed_result = {
                "rank": result.get('rank', i + 1),
                "title": result.get('title', 'Unknown'),
                "channel": result.get('channel', 'Unknown'),
                "upload": result.get('upload', ''),
                "similarity": result.get('similarity', 0.0),
                "content_snippet": result.get('content_snippet', ''),
                "video_id": result.get('video_id', ''),
                "source_url": result.get('source_url', ''),
                "file_path": result.get('file_path', ''),
                "chunk_info": result.get('chunk_info', ''),
                # 로컬 파일 경로 추가
                "local_video_path": self._get_local_video_path(result.get('file_path', '')),
                "local_transcript_path": result.get('file_path', ''),
                "clickable_youtube_url": result.get('source_url', ''),
                "clickable_local_video": self._get_clickable_local_path(result.get('file_path', ''))
            }
            search_entry["results"].append(processed_result)
        
        # 세션에 검색 기록 추가
        self.current_session_data["searches"].append(search_entry)
        self.current_session_data["total_searches"] += 1
        self.current_session_data["updated_at"] = datetime.now().isoformat()
        
        # 세션 저장
        self._save_session(self.current_session_data)
        
        logger.info(f"💾 검색 저장: '{query}' → {len(results)}개 결과")
        return search_entry
    
    def add_bookmark(self, search_id: str, result_rank: int, note: Optional[str] = None):
        """검색 결과를 북마크에 추가"""
        if not self.current_session_data:
            return False
        
        # 해당 검색 찾기
        search_entry = None
        for search in self.current_session_data["searches"]:
            if search["search_id"] == search_id:
                search_entry = search
                break
        
        if not search_entry:
            return False
        
        # 해당 결과 찾기
        result = None
        for r in search_entry["results"]:
            if r["rank"] == result_rank:
                result = r
                break
        
        if not result:
            return False
        
        # 북마크 추가
        bookmark = {
            "bookmark_id": str(uuid.uuid4())[:8],
            "created_at": datetime.now().isoformat(),
            "search_id": search_id,
            "query": search_entry["query"],
            "result": result,
            "note": note or ""
        }
        
        self.current_session_data["bookmarks"].append(bookmark)
        self.current_session_data["updated_at"] = datetime.now().isoformat()
        
        self._save_session(self.current_session_data)
        
        logger.info(f"⭐ 북마크 추가: {result['title']}")
        return True
    
    def get_all_sessions(self) -> List[Dict[str, Any]]:
        """모든 세션 목록 반환"""
        sessions = []
        
        for session_file in self.sessions_dir.glob("*.json"):
            try:
                with open(session_file, 'r', encoding='utf-8') as f:
                    session_data = json.load(f)
                
                # 세션 요약 정보만 추출
                session_summary = {
                    "session_id": session_data["session_id"],
                    "title": session_data["title"],
                    "created_at": session_data["created_at"],
                    "updated_at": session_data["updated_at"],
                    "total_searches": session_data["total_searches"],
                    "total_bookmarks": len(session_data.get("bookmarks", [])),
                    "favorite": session_data.get("favorite", False)
                }
                sessions.append(session_summary)
                
            except Exception as e:
                logger.warning(f"세션 파일 읽기 실패: {session_file} - {e}")
                continue
        
        # 최근 수정순 정렬
        sessions.sort(key=lambda x: x["updated_at"], reverse=True)
        return sessions
    
    def delete_session(self, session_id: str) -> bool:
        """세션 삭제"""
        session_file = self.sessions_dir / f"{session_id}.json"
        
        if not session_file.exists():
            return False
        
        try:
            # 현재 활성 세션이면 클리어
            if self.current_session_id == session_id:
                self.current_session_id = None
                self.current_session_data = None
            
            session_file.unlink()
            logger.info(f"🗑️ 세션 삭제: {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"세션 삭제 실패: {e}")
            return False
    
    def export_session_html(self, session_id: str) -> str:
        """세션을 HTML 형태로 익스포트 (클릭 가능한 링크 포함)"""
        session = self.load_session(session_id)
        
        html_content = f"""
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{session['title']} - 검색 세션</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 20px; line-height: 1.6; }}
        .header {{ background: #f5f5f5; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}
        .search {{ background: white; border: 1px solid #ddd; border-radius: 8px; margin: 20px 0; padding: 20px; }}
        .result {{ background: #fafafa; border-left: 4px solid #007AFF; margin: 10px 0; padding: 15px; }}
        .similarity {{ color: #007AFF; font-weight: bold; }}
        .channel {{ color: #666; font-size: 0.9em; }}
        .snippet {{ color: #333; margin: 10px 0; font-style: italic; }}
        .links {{ margin-top: 10px; }}
        .links a {{ margin-right: 15px; text-decoration: none; color: #007AFF; }}
        .links a:hover {{ text-decoration: underline; }}
        .bookmark {{ background: #fff3cd; border-color: #ffc107; }}
        .timestamp {{ color: #666; font-size: 0.9em; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🔍 {session['title']}</h1>
        <p>세션 ID: {session['session_id']}</p>
        <p>생성일: {session['created_at'][:19].replace('T', ' ')}</p>
        <p>총 검색: {session['total_searches']}회, 북마크: {len(session.get('bookmarks', []))}개</p>
    </div>
"""
        
        # 북마크된 항목들
        if session.get('bookmarks'):
            html_content += "<h2>⭐ 북마크</h2>\n"
            for bookmark in session['bookmarks']:
                result = bookmark['result']
                html_content += f"""
    <div class="result bookmark">
        <h4>{result['title']}</h4>
        <p class="channel">📺 {result['channel']} | 유사도: <span class="similarity">{result['similarity']:.3f}</span></p>
        <p class="snippet">{result['content_snippet']}</p>
        <div class="links">
            <a href="{result['clickable_youtube_url']}" target="_blank">🌐 YouTube에서 보기</a>
            <a href="file://{result['clickable_local_video']}" target="_blank">📹 로컬 영상 열기</a>
            <a href="file://{result['local_transcript_path']}" target="_blank">📄 자막 보기</a>
        </div>
        {f'<p><strong>노트:</strong> {bookmark["note"]}</p>' if bookmark.get('note') else ''}
        <p class="timestamp">북마크 추가: {bookmark['created_at'][:19].replace('T', ' ')}</p>
    </div>
"""
        
        # 검색 기록들
        html_content += "<h2>🔍 검색 기록</h2>\n"
        for search in session['searches']:
            query_info = f"'{search['query']}'"
            if search.get('channel_filter'):
                query_info += f" (채널: {search['channel_filter']})"
            if search.get('year_filter'):
                query_info += f" (연도: {search['year_filter']})"
            
            html_content += f"""
    <div class="search">
        <h3>{query_info}</h3>
        <p class="timestamp">{search['timestamp'][:19].replace('T', ' ')} | {search['results_count']}개 결과</p>
"""
            
            for result in search['results']:
                html_content += f"""
        <div class="result">
            <h4>{result['rank']}. {result['title']}</h4>
            <p class="channel">📺 {result['channel']} | 유사도: <span class="similarity">{result['similarity']:.3f}</span> | {result['chunk_info']}</p>
            <p class="snippet">{result['content_snippet']}</p>
            <div class="links">
                <a href="{result['clickable_youtube_url']}" target="_blank">🌐 YouTube에서 보기</a>
                <a href="file://{result['clickable_local_video']}" target="_blank">📹 로컬 영상 열기</a>
                <a href="file://{result['local_transcript_path']}" target="_blank">📄 자막 보기</a>
            </div>
        </div>
"""
            html_content += "    </div>\n"
        
        html_content += """
</body>
</html>
"""
        
        # HTML 파일 저장
        html_file = self.sessions_dir / f"{session_id}_export.html"
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        logger.info(f"📤 세션 HTML 익스포트: {html_file}")
        return str(html_file)
    
    def _save_session(self, session_data: Dict[str, Any]):
        """세션 데이터 저장"""
        session_file = self.sessions_dir / f"{session_data['session_id']}.json"
        
        try:
            with open(session_file, 'w', encoding='utf-8') as f:
                json.dump(session_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"세션 저장 실패: {e}")
            raise
    
    def _get_local_video_path(self, file_path: str) -> str:
        """자막 파일 경로에서 비디오 파일 경로 추출"""
        if not file_path:
            return ""
        
        try:
            # captions.md -> video.mp4로 변경
            transcript_path = Path(file_path)
            video_path = transcript_path.parent / "video.mp4"
            
            if video_path.exists():
                return str(video_path)
            else:
                return ""
        except Exception:
            return ""
    
    def _get_clickable_local_path(self, file_path: str) -> str:
        """클릭 가능한 로컬 파일 경로 생성"""
        local_video = self._get_local_video_path(file_path)
        if local_video:
            # 절대 경로로 변환
            abs_path = Path(local_video).resolve()
            return str(abs_path)
        return ""

# 편의 함수들
def create_session(title: Optional[str] = None) -> str:
    """새 세션 생성"""
    manager = SearchSessionManager()
    return manager.create_new_session(title)

def save_search_to_session(query: str, results: List[Dict[str, Any]], 
                          channel_filter: Optional[str] = None,
                          year_filter: Optional[str] = None,
                          session_id: Optional[str] = None) -> Dict[str, Any]:
    """검색을 세션에 저장"""
    manager = SearchSessionManager()
    
    if session_id:
        manager.load_session(session_id)
    elif not manager.current_session_id:
        manager.create_new_session()
    
    return manager.save_search(query, results, channel_filter, year_filter)

def list_all_sessions() -> List[Dict[str, Any]]:
    """모든 세션 목록"""
    manager = SearchSessionManager()
    return manager.get_all_sessions()

def delete_session(session_id: str) -> bool:
    """세션 삭제"""
    manager = SearchSessionManager()
    return manager.delete_session(session_id)

def export_session_html(session_id: str) -> str:
    """세션을 HTML로 익스포트"""
    manager = SearchSessionManager()
    return manager.export_session_html(session_id)