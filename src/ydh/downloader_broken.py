"""
yt-dlp wrapper with download archive functionality.
"""

import logging
import sys
import time
import os
from pathlib import Path
from typing import Dict, List, Optional, Any, Set
import re

import yt_dlp
from tqdm import tqdm

from .config import settings

logger = logging.getLogger(__name__)


class WarningCapturer:
    """yt-dlp 경고 메시지를 필터링하는 클래스."""
    
    def __init__(self):
        self.original_stderr = sys.stderr
        self.suppressed_msgs = ["nsig extraction failed", "Some formats may be missing"]
    
    def __enter__(self):
        sys.stderr = self
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.stderr = self.original_stderr
    
    def write(self, data):
        # 특정 경고 메시지를 필터링
        if not any(msg in data for msg in self.suppressed_msgs):
            self.original_stderr.write(data)
    
    def flush(self):
        self.original_stderr.flush()


class VideoDownloader:
    """YouTube 비디오 다운로드 클래스."""
    
    def __init__(self):
        """VideoDownloader 초기화."""
        self._setup_logger()
    
    def _setup_logger(self) -> None:
        """yt-dlp 로거 설정."""
        class YtDlpLogger:
            def debug(self, msg):
                # 🔥 DEBUG: 모든 디버그 메시지 출력
                logger.info(f"[yt-dlp DEBUG] {msg}")
            
            def warning(self, msg):
                # 🔥 DEBUG: 모든 경고 메시지 출력
                logger.warning(f"[yt-dlp WARNING] {msg}")
            
            def error(self, msg):
                logger.error(f"[yt-dlp ERROR] {msg}")
                
            def info(self, msg):
                # 🔥 DEBUG: 정보 메시지도 추가
                logger.info(f"[yt-dlp INFO] {msg}")
        
        self.yt_dlp_logger = YtDlpLogger()
    
    def get_channel_videos(self, channel_url: str, chunk_size: int = 100) -> List[Dict[str, Any]]:
        """
        채널 URL에서 영상 목록을 청크 단위로 가져옵니다.
        
        Args:
            channel_url: YouTube 채널 URL
            chunk_size: 청크당 영상 수 (기본: 100개)
            
        Returns:
            List[Dict[str, Any]]: 영상 정보 목록
        """
        logger.info("채널 영상 목록 수집 중 (청크 단위 처리)...")
        
        all_videos = []
        chunk_num = 1
        max_chunks = 10  # 최대 10청크 (1000개 영상)
        
        while chunk_num <= max_chunks:
            start_idx = (chunk_num - 1) * chunk_size + 1
            end_idx = chunk_num * chunk_size
            
            logger.info(f"📦 청크 {chunk_num}: 영상 {start_idx}-{end_idx} 처리 중...")
            
            # 🔥 청크별 yt-dlp 옵션
            chunk_opts = {
                'quiet': True,  # 청크 처리시 출력 줄이기
                'verbose': False,
                'extract_flat': True,
                'ignoreerrors': True,
                'no_warnings': True,
                'skip_download': True,
                'logger': self.yt_dlp_logger,
                'http_headers': {
                    'User-Agent': settings.user_agent,
                },
                # 🛡️ 봇 감지 회피: 브라우저 쿠키 사용
                'cookiesfrombrowser': (settings.browser, None, None, None) if settings.use_browser_cookies else None,
                # 🔥 환경변수에서 rate limiting 설정
                'socket_timeout': int(os.getenv('YDH_YTDLP_SOCKET_TIMEOUT', '15')),
                'retries': int(os.getenv('YDH_YTDLP_RETRIES', '2')),
                'sleep_interval': int(os.getenv('YDH_YTDLP_SLEEP_INTERVAL', '2')),
                'max_sleep_interval': int(os.getenv('YDH_YTDLP_MAX_SLEEP_INTERVAL', '5')),
                'sleep_interval_requests': int(os.getenv('YDH_YTDLP_SLEEP_REQUESTS', '20')),
                # 🔥 청크 범위 설정
                'playliststart': start_idx,
                'playlistend': end_idx,
            }
            
            chunk_videos = self._get_chunk_videos(channel_url, chunk_opts, chunk_num)
            
            if not chunk_videos:
                logger.info(f"📦 청크 {chunk_num}: 영상이 없습니다. 수집 완료")
                break
            
            all_videos.extend(chunk_videos)
            logger.info(f"📦 청크 {chunk_num}: {len(chunk_videos)}개 영상 수집 완료")
            
            # 마지막 청크가 꽉 차지 않으면 끝
            if len(chunk_videos) < chunk_size:
                logger.info(f"📦 마지막 청크 감지. 총 {len(all_videos)}개 영상 수집 완료")
                break
                
            chunk_num += 1
            
            # 청크 간 지연
            import time
            time.sleep(2)
        
        logger.info(f"✅ 전체 수집 완료: {len(all_videos)}개 영상")
        return all_videos

    def _get_chunk_videos(self, channel_url: str, opts: dict, chunk_num: int) -> List[Dict[str, Any]]:
        """
        단일 청크의 영상 목록을 가져옵니다.
        """
        # 🔥 FIXED: 채널 URL을 videos 탭으로 변경
        videos_url = channel_url  # 기본적으로는 원본 URL 사용
        if '@' in channel_url and not channel_url.endswith('/videos'):
            videos_url = f"{channel_url}/videos"
        elif ('/c/' in channel_url or '/channel/' in channel_url) and not channel_url.endswith('/videos'):
            videos_url = f"{channel_url}/videos"
        
        try:
            logger.info(f"🌐 청크 {chunk_num} 수집 중... URL: {videos_url}")
            with yt_dlp.YoutubeDL(opts) as ydl:
                result = ydl.extract_info(videos_url, download=False)
                
            if not result or 'entries' not in result:
                logger.warning(f"청크 {chunk_num}: entries가 없습니다. 원본 URL로 재시도...")
                # 🔥 FIXED: videos URL이 실패하면 원본 URL로 재시도
                fallback_url = channel_url if videos_url != channel_url else channel_url.replace('/videos', '')
                with yt_dlp.YoutubeDL(opts) as ydl:
                    result = ydl.extract_info(fallback_url, download=False)
                if not result or 'entries' not in result:
                    logger.error(f"청크 {chunk_num}: 채널 정보를 가져오지 못했습니다.")
                    return []
            
            # 유효한 영상만 필터링
            videos = [v for v in result['entries'] if v and v.get('id')]
            logger.info(f"✅ 청크 {chunk_num}: {len(videos)}개 영상 발견")
            return videos
            
        except Exception as e:
            logger.error(f"❌ 청크 {chunk_num} 처리 중 오류: {e}")
            return []
    
    def get_video_count_estimate(self, channel_url: str) -> int:
        """
        채널의 대략적인 영상 수를 빠르게 확인합니다.
        """
        # 첫 번째 청크만 가져와서 총 영상 수 추정
        try:
            opts = {
                'quiet': True,
                'extract_flat': True,
                'ignoreerrors': True,
                'no_warnings': True,
                'skip_download': True,
                'playliststart': 1,
                'playlistend': 1,  # 첫 번째 영상만
            }
            
            with yt_dlp.YoutubeDL(opts) as ydl:
                result = ydl.extract_info(channel_url, download=False)
                
            if result and 'playlist_count' in result:
                return result['playlist_count']
            return 0
            
        except Exception as e:
            logger.error(f"영상 수 추정 실패: {e}")
            return 0

    def get_video_info(self, video_url: str) -> Optional[Dict[str, Any]]:
                
                if not result or 'entries' not in result:
                    logger.warning("entries가 없습니다. 원본 URL로 재시도...")
                    # 🔥 FIXED: videos URL이 실패하면 원본 URL로 재시도
                    fallback_url = channel_url if videos_url != channel_url else channel_url.replace('/videos', '')
                    logger.debug(f"폴백 URL: {fallback_url}")
                    result = ydl.extract_info(fallback_url, download=False)
                    if not result or 'entries' not in result:
                        logger.error("채널 정보를 가져오지 못했습니다.")
                        return []
                
                # 전체 영상 수 확인
                total_count = result.get('playlist_count', 0) or len([e for e in result['entries'] if e])
                logger.info(f"채널 전체 영상 수: {total_count}개")
                
                # 🔥 NEW: 2단계 - 100개 이상이면 페이징 처리
                if total_count <= 100:
                    # 100개 이하면 한 번에 처리
                    videos = self._extract_valid_videos(result['entries'])
                else:
                    # 100개 이상이면 구간별로 나눠서 처리
                    logger.info(f"대용량 채널 감지: {total_count}개 영상을 100개씩 나눠서 처리")
                    videos = self._fetch_videos_in_chunks(videos_url, total_count, base_opts)
                
                logger.info(f"총 {len(videos)}개 영상을 발견했습니다.")
                
                # 🔥 NEW: 디버깅을 위해 처음 5개 비디오 ID 로그
                if settings.detailed_debug and videos:
                    sample_ids = [v.get('id', 'NO_ID') for v in videos[:5]]
                    logger.debug(f"샘플 비디오 IDs: {sample_ids}")
                
                return videos
                
        except Exception as e:
            logger.error(f"채널 정보 수집 중 오류 발생: {e}")
            # 🔥 NEW: 3단계 - 폴백: 풀 메타데이터 추출 후 필터링
            return self._fallback_full_extraction(channel_url)
    
    def _extract_valid_videos(self, entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        유효한 비디오만 필터링합니다.
        
        Args:
            entries: yt-dlp에서 반환된 entries
            
        Returns:
            List[Dict[str, Any]]: 유효한 비디오 목록
        """
        videos = []
        for entry in entries:
            if entry and entry.get('id'):
                video_id = entry.get('id', '')
                # 채널 ID (UC로 시작하고 22-24자리)가 아닌 실제 비디오 ID만 포함
                if not (video_id.startswith('UC') and len(video_id) >= 22):
                    # 정상적인 비디오 ID는 보통 11자리
                    if len(video_id) == 11:
                        videos.append(entry)
                    else:
                        logger.debug(f"이상한 ID 제외: {video_id}")
        return videos
    
    def _fetch_videos_in_chunks(self, videos_url: str, total_count: int, base_opts: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        대용량 채널의 영상을 100개씩 나눠서 가져옵니다.
        
        Args:
            videos_url: 채널 비디오 URL
            total_count: 전체 영상 수
            base_opts: 기본 yt-dlp 옵션
            
        Returns:
            List[Dict[str, Any]]: 전체 비디오 목록
        """
        all_videos = []
        chunk_size = 100
        
        for start in range(1, total_count + 1, chunk_size):
            end = min(start + chunk_size - 1, total_count)
            playlist_items = f"{start}-{end}"
            
            logger.info(f"영상 {start}-{end} 처리 중... ({len(all_videos)}/{total_count})")
            
            chunk_opts = {
                **base_opts,
                'playlist_items': playlist_items
            }
            
            try:
                with yt_dlp.YoutubeDL(chunk_opts) as ydl:
                    result = ydl.extract_info(videos_url, download=False)
                    
                    if result and 'entries' in result:
                        chunk_videos = self._extract_valid_videos(result['entries'])
                        all_videos.extend(chunk_videos)
                        
                        if settings.detailed_debug:
                            logger.debug(f"청크 {start}-{end}: {len(chunk_videos)}개 영상 추가")
                    
                    # 서버 부하 방지
                    time.sleep(0.5)
                    
            except Exception as e:
                logger.warning(f"청크 {start}-{end} 처리 실패: {e}")
                continue
        
        return all_videos
    
    def _fallback_full_extraction(self, channel_url: str) -> List[Dict[str, Any]]:
        """
        플랫 추출 실패 시 풀 메타데이터 추출 후 필터링하는 폴백 방법.
        
        Args:
            channel_url: 채널 URL
            
        Returns:
            List[Dict[str, Any]]: 비디오 목록
        """
        logger.warning("플랫 추출 실패. 풀 메타데이터 추출로 폴백...")
        
        fallback_opts = {
            'quiet': True,
            'extract_flat': False,  # 풀 메타데이터 추출
            'ignoreerrors': True,
            'no_warnings': True,
            'skip_download': True,
            'logger': self.yt_dlp_logger,
            'http_headers': {
                'User-Agent': settings.user_agent,
            },
            'cookiesfrombrowser': (settings.browser, None, None, None) if settings.use_browser_cookies else None,
            'playlist_end': 200,  # 최대 200개로 제한
        }
        
        try:
            with yt_dlp.YoutubeDL(fallback_opts) as ydl:
                result = ydl.extract_info(channel_url, download=False)
                
                if result and 'entries' in result:
                    # 필수 필드만 추출해서 경량화
                    videos = []
                    for entry in result['entries']:
                        if entry and entry.get('id'):
                            videos.append({
                                'id': entry['id'],
                                'title': entry.get('title', '제목 없음'),
                                'url': entry.get('webpage_url', f"https://www.youtube.com/watch?v={entry['id']}"),
                                'upload_date': entry.get('upload_date', ''),
                                'duration': entry.get('duration', 0),
                            })
                    
                    logger.info(f"폴백으로 {len(videos)}개 영상 추출 완료")
                    return videos
                    
        except Exception as e:
            logger.error(f"폴백 추출도 실패: {e}")
        
        return []
    
    def get_video_info(self, video_url: str) -> Optional[Dict[str, Any]]:
        """
        비디오 정보를 가져옵니다.
        
        Args:
            video_url: YouTube 비디오 URL
            
        Returns:
            Optional[Dict[str, Any]]: 비디오 정보
        """
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'logger': self.yt_dlp_logger,
            'http_headers': {
                'User-Agent': settings.user_agent,
            },
            # 🛡️ 봇 감지 회피: 브라우저 쿠키 사용
            'cookiesfrombrowser': (settings.browser, None, None, None) if settings.use_browser_cookies else None,
            # 🔥 환경변수에서 rate limiting 및 타임아웃 설정 읽기
            'socket_timeout': int(os.getenv('YDH_YTDLP_SOCKET_TIMEOUT', '30')),
            'retries': int(os.getenv('YDH_YTDLP_RETRIES', '2')),
            'sleep_interval': int(os.getenv('YDH_YTDLP_SLEEP_INTERVAL', '1')),
            'max_sleep_interval': int(os.getenv('YDH_YTDLP_MAX_SLEEP_INTERVAL', '3')),
            'sleep_interval_requests': int(os.getenv('YDH_YTDLP_SLEEP_REQUESTS', '10')),
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(video_url, download=False)
        except Exception as e:
            logger.error(f"비디오 정보 추출 실패: {e}")
            return None
    
    def sanitize_filename(self, name: str) -> str:
        """
        파일/폴더 이름에 사용할 수 없는 문자를 '_'로 대체합니다.
        
        Args:
            name: 원본 이름
            
        Returns:
            str: 정리된 이름
        """
        return re.sub(r'[\\/*?:"<>|]', "_", name)
    
    def create_video_folder(self, video_info: Dict[str, Any]) -> Path:
        """
        각 영상별 폴더를 생성합니다.
        
        Args:
            video_info: 비디오 정보
            
        Returns:
            Path: 생성된 폴더 경로
        """
        title = video_info.get('title', '제목 없음')
        upload_date = video_info.get('upload_date', '')
        
        # 제목에서 폴더명에 적합하지 않은 문자 제거
        safe_title = self.sanitize_filename(title)
        
        # 제목이 너무 길면 잘라서 사용
        if len(safe_title) > 50:
            safe_title = safe_title[:50]
        
        # 폴더명 형식: YYYYMMDD_Title
        folder_name = f"{upload_date}_{safe_title}"
        folder_path = settings.download_path / folder_name
        
        # 폴더가 없으면 생성
        folder_path.mkdir(parents=True, exist_ok=True)
        
        return folder_path
    
    def download_video(self, video_info: Dict[str, Any], output_folder: Path, channel_name: str = "") -> bool:
        """
        개별 비디오를 다운로드합니다.
        
        Args:
            video_info: 비디오 정보
            output_folder: 출력 폴더
            channel_name: 채널 이름 (다운로드 아카이브용)
            
        Returns:
            bool: 다운로드 성공 여부
        """
        video_id = video_info.get('id', '')
        title = video_info.get('title', '제목 없음')
        
        if not video_id:
            logger.error("비디오 ID가 없습니다.")
            return False
        
        # 품질 선택
        format_selector = 'bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[height<=1080]/best'
        if settings.max_quality:
            if settings.max_quality == "best" or settings.max_quality == "high":
                format_selector = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best'
            elif settings.max_quality == "4k" or settings.max_quality == "2160p":
                format_selector = 'bestvideo[ext=mp4][height<=2160]+bestaudio[ext=m4a]/best[height<=2160]/best'
            elif settings.max_quality == "1440p" or settings.max_quality == "2k":
                format_selector = 'bestvideo[ext=mp4][height<=1440]+bestaudio[ext=m4a]/best[height<=1440]/best'
            elif settings.max_quality == "1080p":
                format_selector = 'bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[height<=1080]/best'
            elif settings.max_quality == "720p" or settings.max_quality == "medium":
                format_selector = 'bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/best[height<=720]/best'
            elif settings.max_quality == "480p" or settings.max_quality == "low":
                format_selector = 'bestvideo[ext=mp4][height<=480]+bestaudio[ext=m4a]/best[height<=480]/best'
            elif settings.max_quality == "360p":
                format_selector = 'bestvideo[ext=mp4][height<=360]+bestaudio[ext=m4a]/best[height<=360]/best'
            elif settings.max_quality == "audio-only":
                format_selector = 'bestaudio[ext=m4a]/bestaudio'
        
        # yt-dlp 옵션 설정
        ydl_opts = {
            'outtmpl': str(output_folder / f'{title}.%(ext)s'),
            'format': format_selector,
            'merge_output_format': 'mp4',
            'logger': self.yt_dlp_logger,
            'ignoreerrors': True,
            'quiet': True,
            'no_warnings': True,
            'verbose': False,
            'http_headers': {
                'User-Agent': settings.user_agent,
            },
            # 🔥 환경변수에서 rate limiting 및 타임아웃 설정 읽기
            'socket_timeout': int(os.getenv('YDH_YTDLP_SOCKET_TIMEOUT', '30')),
            'retries': int(os.getenv('YDH_YTDLP_RETRIES', '3')),
            'fragment_retries': 3,
            'sleep_interval': int(os.getenv('YDH_YTDLP_SLEEP_INTERVAL', '1')),
            'max_sleep_interval': int(os.getenv('YDH_YTDLP_MAX_SLEEP_INTERVAL', '3')),
            'sleep_interval_requests': int(os.getenv('YDH_YTDLP_SLEEP_REQUESTS', '10')),
            # 🛡️ 봇 감지 회피: 브라우저 쿠키 사용
            'cookiesfrombrowser': (settings.browser, None, None, None) if settings.use_browser_cookies else None,
            # 자막 다운로드 옵션
            'writesubtitles': True,
            'writeautomaticsub': True,
            'subtitleslangs': settings.subtitle_languages,
            'subtitlesformat': 'vtt',
            'embedsubtitles': False,
            'noembedsubtitles': True,
            'embedthumbnails': False,
            'nopostoverwrites': True,
            'postprocessor_args': {
                'ffmpeg': ['-c', 'copy', '-sn'],
            },
        }
        
        try:
            video_url = f"https://www.youtube.com/watch?v={video_id}"
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                error_code = ydl.download([video_url])
                
                if error_code == 0:
                    logger.info(f"다운로드 완료: {title}")
                    
                    # 🔥 NEW: 비디오 메타데이터를 JSON 파일로 저장
                    self._save_video_metadata(video_info, output_folder)
                    
                    # 🔥 FIXED: 다운로드 성공 후에만 아카이브에 기록
                    self._add_to_archive(video_id, channel_name)
                    
                    return True
                else:
                    logger.error(f"다운로드 실패: {title}")
                    return False
                    
        except Exception as e:
            logger.error(f"다운로드 중 오류 발생: {e}")
            return False
    
    def _save_video_metadata(self, video_info: Dict[str, Any], output_folder: Path) -> None:
        """
        비디오 메타데이터를 JSON 파일로 저장합니다.
        
        Args:
            video_info: 비디오 정보
            output_folder: 출력 폴더
        """
        try:
            import json
            
            # 필요한 메타데이터만 추출
            metadata = {
                'id': video_info.get('id', ''),
                'title': video_info.get('title', ''),
                'upload_date': video_info.get('upload_date', ''),
                'uploader': video_info.get('uploader', ''),
                'duration': video_info.get('duration', 0),
                'view_count': video_info.get('view_count', 0),
                'description': video_info.get('description', ''),
                'webpage_url': video_info.get('webpage_url', ''),
                'channel_url': video_info.get('channel_url', ''),
                'channel_id': video_info.get('channel_id', ''),
                'tags': video_info.get('tags', []),
                'categories': video_info.get('categories', []),
                'thumbnail': video_info.get('thumbnail', ''),
                'uploader_id': video_info.get('uploader_id', ''),
            }
            
            # 메타데이터 파일 저장
            metadata_file = output_folder / 'metadata.json'
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)
            
            logger.debug(f"메타데이터 저장 완료: {metadata_file}")
            
        except Exception as e:
            logger.warning(f"메타데이터 저장 실패: {e}")
    
    def get_downloaded_archive_path(self, channel_name: str) -> Path:
        """
        채널별 downloaded 아카이브 파일 경로를 반환합니다.
        
        Args:
            channel_name: 채널 이름
            
        Returns:
            Path: 채널별 downloaded.txt 경로
        """
        safe_channel_name = re.sub(r'[\\/*?:"<>|]', "_", channel_name)
        return settings.download_path / f"{safe_channel_name}_downloaded.txt"
    
    def _load_downloaded_archive(self, channel_name: str) -> Set[str]:
        """
        다운로드 아카이브 파일에서 이미 다운로드된 영상 ID 목록을 로드합니다.
        실제 파일이 존재하는 경우만 "다운로드 완료"로 처리합니다.
        
        Args:
            channel_name: 채널 이름
            
        Returns:
            Set[str]: 다운로드된 영상 ID 목록
        """
        archive_path = self.get_downloaded_archive_path(channel_name)
        downloaded_ids = set()
        invalid_ids = []
        
        if archive_path.exists():
            try:
                with open(archive_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and line.startswith('youtube '):
                            video_id = line.split(' ', 1)[1]
                            
                            # 🔥 FIXED: 실제 파일 존재 여부 체크
                            if self._video_file_exists(video_id):
                                downloaded_ids.add(video_id)
                            else:
                                invalid_ids.append(video_id)
                                
                logger.debug(f"아카이브에서 {len(downloaded_ids)}개 영상 ID 로드완료")
                
                # 🔥 FIXED: 실제 파일이 없는 ID들은 아카이브에서 제거
                if invalid_ids:
                    logger.info(f"실제 파일이 없는 {len(invalid_ids)}개 영상을 아카이브에서 제거")
                    self._clean_archive(archive_path, invalid_ids)
                    
            except Exception as e:
                logger.warning(f"아카이브 파일 읽기 실패: {e}")
        
        return downloaded_ids
    
    def _video_file_exists(self, video_id: str) -> bool:
        """
        비디오 파일이 downloads 폴더나 vault에 존재하는지 확인합니다.
        
        Args:
            video_id: 비디오 ID
            
        Returns:
            bool: 파일 존재 여부
        """
        # downloads 폴더에서 찾기
        for folder in settings.download_path.iterdir():
            if folder.is_dir():
                # metadata.json에서 비디오 ID 확인
                metadata_file = folder / 'metadata.json'
                if metadata_file.exists():
                    try:
                        import json
                        with open(metadata_file, 'r', encoding='utf-8') as f:
                            metadata = json.load(f)
                            if metadata.get('id') == video_id:
                                # 실제 비디오 파일이 있는지 확인
                                video_files = list(folder.glob('*.mp4'))
                                if video_files:
                                    return True
                    except Exception:
                        pass
        
        # vault 폴더에서 찾기 (이미 처리된 영상)
        vault_path = settings.vault_root / "10_videos"
        if vault_path.exists():
            for channel_folder in vault_path.iterdir():
                if channel_folder.is_dir():
                    for year_folder in channel_folder.iterdir():
                        if year_folder.is_dir():
                            for video_folder in year_folder.iterdir():
                                if video_folder.is_dir():
                                    # captions.md에서 video_id 확인
                                    md_file = video_folder / 'captions.md'
                                    if md_file.exists():
                                        try:
                                            with open(md_file, 'r', encoding='utf-8') as f:
                                                content = f.read()
                                                if f"video_id: {video_id}" in content:
                                                    return True
                                        except Exception:
                                            pass
        
        return False
    
    def _clean_archive(self, archive_path: Path, invalid_ids: List[str]) -> None:
        """
        아카이브에서 유효하지 않은 ID들을 제거합니다.
        
        Args:
            archive_path: 아카이브 파일 경로
            invalid_ids: 제거할 ID 목록
        """
        try:
            # 기존 내용 읽기
            valid_lines = []
            with open(archive_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and line.startswith('youtube '):
                        video_id = line.split(' ', 1)[1]
                        if video_id not in invalid_ids:
                            valid_lines.append(line)
            
            # 유효한 라인들만 다시 쓰기
            with open(archive_path, 'w', encoding='utf-8') as f:
                for line in valid_lines:
                    f.write(f"{line}\n")
                    
        except Exception as e:
            logger.warning(f"아카이브 정리 실패: {e}")
    
    def download_channel_videos(self, channel_url: str, channel_name: str = "") -> Dict[str, int]:
        """
        채널의 모든 새 영상을 다운로드합니다 (최신 영상부터).
        
        Args:
            channel_url: 채널 URL
            channel_name: 채널 이름 (통계용)
            
        Returns:
            Dict[str, int]: 다운로드 통계
        """
        # 다운로드 경로 생성
        settings.download_path.mkdir(parents=True, exist_ok=True)
        
        # 채널에서 영상 목록 가져오기
        videos = self.get_channel_videos(channel_url)
        
        if not videos:
            logger.warning("다운로드할 영상이 없습니다.")
            return {"total": 0, "downloaded": 0, "skipped": 0, "failed": 0}
        
        logger.info(f"채널에서 총 {len(videos)}개 영상을 발견했습니다.")
        
        # 🚀 이미 다운로드된 영상 ID 목록 로드
        downloaded_ids = self._load_downloaded_archive(channel_name)
        logger.info(f"이미 다운로드된 영상: {len(downloaded_ids)}개")
        
        # 🔥 사전 필터링: 이미 다운로드된 영상 제외
        new_videos = [v for v in videos if v.get('id') not in downloaded_ids]
        skipped_count = len(videos) - len(new_videos)
        
        if not new_videos:
            logger.info("모든 영상이 이미 다운로드되었습니다.")
            return {"total": len(videos), "downloaded": 0, "skipped": skipped_count, "failed": 0}
        
        logger.info(f"새로운 영상: {len(new_videos)}개 (기존 {skipped_count}개 건너뛰기)")
        
        # 다운로드 수 제한 적용
        if settings.max_downloads_per_run > 0:
            original_count = len(new_videos)
            new_videos = new_videos[:settings.max_downloads_per_run]
            if original_count > len(new_videos):
                logger.info(f"다운로드 수 제한: {original_count}개 중 {len(new_videos)}개만 다운로드 (최신 순)")
        
        logger.info(f"실제 다운로드 대상: {len(new_videos)}개")
        videos = new_videos  # 필터링된 목록으로 교체
        
        # 다운로드 진행 상황 추적
        stats = {"total": len(videos), "downloaded": 0, "skipped": skipped_count, "failed": 0}
        
        # 프로그레스 바 초기화
        pbar = tqdm(
            total=len(videos), 
            desc="다운로드 진행률", 
            unit="개", 
            ncols=80, 
            leave=False, 
            bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt}'
        )
        
        try:
            with WarningCapturer():
                for idx, video in enumerate(videos):
                    video_id = video.get('id')
                    if not video_id:
                        pbar.update(1)
                        stats["failed"] += 1
                        continue
                    
                    try:
                        # 비디오 상세 정보 가져오기
                        video_url = f"https://www.youtube.com/watch?v={video_id}"
                        video_info = self.get_video_info(video_url)
                        
                        if not video_info:
                            stats["failed"] += 1
                            pbar.update(1)
                            continue
                        
                        # 영상별 폴더 생성
                        folder_path = self.create_video_folder(video_info)
                        
                        # 비디오 다운로드
                        if self.download_video(video_info, folder_path, channel_name):
                            stats["downloaded"] += 1
                            
                            if settings.detailed_debug:
                                logger.info(f"저장 위치: {folder_path}")
                        else:
                            stats["failed"] += 1
                        
                        # 서버 부하 방지를 위한 지연
                        time.sleep(0.5)
                        
                    except Exception as e:
                        logger.error(f"영상 처리 중 예외 발생: {e}")
                        stats["failed"] += 1
                    
                    pbar.update(1)
            
            pbar.close()
            
            logger.info("-" * 50)
            logger.info(f"다운로드 완료: {stats['downloaded']}개 성공")
            logger.info(f"건너뛴 영상: {stats['skipped']}개")
            logger.info(f"실패한 영상: {stats['failed']}개")
            logger.info(f"다운로드 위치: {settings.download_path.absolute()}")
            
            return stats
            
        except Exception as e:
            pbar.close()
            logger.error(f"다운로드 중 오류 발생: {e}")
            return stats
    
    def retry_failed_downloads(self, channel_name: str = "") -> Dict[str, int]:
        """
        실패한 다운로드를 재시도합니다.
        
        Args:
            channel_name: 채널 이름
            
        Returns:
            Dict[str, int]: 재시도 통계
        """
        retry_candidates = []
        
        if not retry_candidates:
            logger.info("재시도할 영상이 없습니다.")
            return {"total": 0, "downloaded": 0, "failed": 0}
        
        logger.info(f"재시도할 영상: {len(retry_candidates)}개")
        
        stats = {"total": len(retry_candidates), "downloaded": 0, "failed": 0}
        
        for video_id in retry_candidates:
            try:
                video_url = f"https://www.youtube.com/watch?v={video_id}"
                video_info = self.get_video_info(video_url)
                
                if video_info:
                    folder_path = self.create_video_folder(video_info)
                    
                    if self.download_video(video_info, folder_path, channel_name):
                        stats["downloaded"] += 1
                        logger.info(f"재시도 성공: {video_info.get('title', '')}")
                    else:
                        stats["failed"] += 1
                else:
                    stats["failed"] += 1
                    
            except Exception as e:
                logger.error(f"재시도 중 오류: {e}")
                stats["failed"] += 1
        
        logger.info(f"재시도 완료: {stats['downloaded']}개 성공, {stats['failed']}개 실패")
        return stats
    
    def cleanup_incomplete_downloads(self) -> int:
        """
        불완전한 다운로드 파일들을 정리합니다.
        
        Returns:
            int: 정리된 파일 수
        """
        cleaned_count = 0
        
        # .part 파일들 정리
        for part_file in settings.download_path.rglob("*.part"):
            try:
                part_file.unlink()
                cleaned_count += 1
                logger.debug(f"불완전한 파일 삭제: {part_file}")
            except Exception as e:
                logger.warning(f"파일 삭제 실패: {e}")
        
        # .tmp 파일들 정리
        for tmp_file in settings.download_path.rglob("*.tmp"):
            try:
                tmp_file.unlink()
                cleaned_count += 1
                logger.debug(f"임시 파일 삭제: {tmp_file}")
            except Exception as e:
                logger.warning(f"파일 삭제 실패: {e}")
        
        if cleaned_count > 0:
            logger.info(f"불완전한 다운로드 파일 {cleaned_count}개 정리 완료")
        
        return cleaned_count

    def _add_to_archive(self, video_id: str, channel_name: str) -> None:
        """
        다운로드된 영상을 아카이브에 추가합니다.
        
        Args:
            video_id: 비디오 ID
            channel_name: 채널 이름
        """
        archive_path = self.get_downloaded_archive_path(channel_name)
        with open(archive_path, 'a', encoding='utf-8') as f:
            f.write(f"youtube {video_id}\n")
        logger.debug(f"아카이브에 영상 추가: {video_id}") 