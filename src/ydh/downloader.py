"""
yt-dlp wrapper with download archive functionality.
"""

import logging
import sys
import time
import os
import warnings
from pathlib import Path
from typing import Dict, List, Optional, Any, Set
import re
import signal
import json
import threading

import yt_dlp
from tqdm import tqdm

from .config import settings
from .converter import CaptionConverter

# multiprocessing 경고 억제
warnings.filterwarnings("ignore", category=UserWarning, module="multiprocessing.resource_tracker")

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
                if settings.detailed_debug:
                    logger.debug(f"[yt-dlp] {msg}")
            
            def warning(self, msg):
                # 불필요한 경고 무시
                if not any(x in msg for x in ["nsig extraction failed", "Some formats may be missing", 
                                            "Requested format is not available", "SABR streaming", 
                                            "Some web client https formats have been skipped"]):
                    logger.warning(f"[yt-dlp] {msg}")
            
            def error(self, msg):
                logger.error(f"[yt-dlp] {msg}")
        
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
                # 🔥 환경변수에서 rate limiting 설정 (더 짧은 타임아웃)
                'socket_timeout': int(os.getenv('YDH_YTDLP_SOCKET_TIMEOUT', '8')),  # 8초로 단축
                'retries': int(os.getenv('YDH_YTDLP_RETRIES', '1')),  # 1회로 단축
                'sleep_interval': int(os.getenv('YDH_YTDLP_SLEEP_INTERVAL', '1')),
                'max_sleep_interval': int(os.getenv('YDH_YTDLP_MAX_SLEEP_INTERVAL', '3')),
                'sleep_interval_requests': int(os.getenv('YDH_YTDLP_SLEEP_REQUESTS', '10')),
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
            time.sleep(2)
        
        logger.info(f"✅ 전체 수집 완료: {len(all_videos)}개 영상")
        return all_videos
    
    def check_for_new_videos_fast(self, channel_url: str, channel_name: str, check_count: int = 20) -> Dict[str, Any]:
        """
        🚀 OPTIMIZED: 채널에 신규 영상이 있는지 빠르게 확인합니다.
        
        Args:
            channel_url: YouTube 채널 URL
            channel_name: 채널 이름 (아카이브 파일용)
            check_count: 확인할 최신 영상 수 (기본: 20개)
            
        Returns:
            Dict[str, Any]: {
                'has_new_videos': bool,
                'new_video_count': int,
                'latest_videos': List[Dict],
                'total_checked': int
            }
        """
        logger.info(f"🔍 신규 영상 빠른 확인 중... (최신 {check_count}개 영상 체크)")
        start_time = time.time()
        
        # 기존 다운로드 아카이브 로드
        downloaded_ids = self._load_downloaded_archive(channel_name)
        logger.info(f"📋 기존 다운로드: {len(downloaded_ids)}개 영상")
        
        # downloads 폴더의 진행중인 영상 확인
        downloading_ids = self._check_downloads_folder(channel_name)
        
        # 전체 제외할 영상 ID 목록 (아카이브 + 진행중)
        all_excluded_ids = downloaded_ids | downloading_ids
        
        # 최신 영상만 빠르게 가져오기
        latest_videos = self._get_latest_videos_only(channel_url, check_count)
        
        if not latest_videos:
            logger.warning("⚠️ 최신 영상 목록을 가져올 수 없습니다")
            return {
                'has_new_videos': False,
                'new_video_count': 0,
                'latest_videos': [],
                'total_checked': 0
            }
        
        # 신규 영상 필터링 (아카이브 + 진행중 영상 모두 제외)
        new_videos = [v for v in latest_videos if v.get('id') not in all_excluded_ids]
        
        elapsed = time.time() - start_time
        logger.info(f"⚡ 빠른 확인 완료: {len(latest_videos)}개 확인, {len(new_videos)}개 신규 ({elapsed:.1f}초)")
        
        return {
            'has_new_videos': len(new_videos) > 0,
            'new_video_count': len(new_videos),
            'latest_videos': new_videos,
            'total_checked': len(latest_videos)
        }
    
    def _get_latest_videos_only(self, channel_url: str, count: int = 20) -> List[Dict[str, Any]]:
        """
        채널의 최신 영상만 빠르게 가져옵니다.
        
        Args:
            channel_url: YouTube 채널 URL
            count: 가져올 최신 영상 수
            
        Returns:
            List[Dict[str, Any]]: 최신 영상 목록
        """
        # 🔥 최적화된 yt-dlp 옵션 (최소한의 데이터만)
        opts = {
            'quiet': True,
            'verbose': False,
            'extract_flat': True,
            'ignoreerrors': True,
            'no_warnings': True,
            'skip_download': True,
            'logger': self.yt_dlp_logger,
            'http_headers': {
                'User-Agent': settings.user_agent,
            },
            # 🛡️ 봇 감지 회피
            'cookiesfrombrowser': (settings.browser, None, None, None) if settings.use_browser_cookies else None,
            # 🔥 타임아웃 60초로 증가
            'socket_timeout': 60,  # 60초로 증가
            'retries': int(os.getenv('YDH_YTDLP_RETRIES', '1')),  # 1회만
            'sleep_interval': int(os.getenv('YDH_YTDLP_SLEEP_INTERVAL', '0')),  # 지연 최소화
            'max_sleep_interval': int(os.getenv('YDH_YTDLP_MAX_SLEEP_INTERVAL', '1')),
            'sleep_interval_requests': int(os.getenv('YDH_YTDLP_SLEEP_REQUESTS', '5')),
            # 🔥 핵심: 최신 영상만 가져오기
            'playliststart': 1,
            'playlistend': count,
            # 🔥 인증 체크 스킵 강화
            'extractor_args': {
                'youtube': {
                    'skip': ['webpage'],
                    'player_client': ['android'],
                },
                'youtubetab': {
                    'skip': ['webpage', 'authcheck'],  # authcheck 스킵
                    'approximate_date': False,  # 정확한 날짜 스킵
                }
            }
        }
        
        try:
            # URL 전처리
            import urllib.parse
            decoded_url = urllib.parse.unquote(channel_url)
            videos_url = decoded_url
            
            if '@' in decoded_url and not decoded_url.endswith('/videos'):
                videos_url = f"{decoded_url}/videos"
            elif ('/c/' in decoded_url or '/channel/' in decoded_url) and not decoded_url.endswith('/videos'):
                videos_url = f"{decoded_url}/videos"
            
            logger.info(f"🌐 최신 영상 수집 중... URL: {videos_url}")
            
            with yt_dlp.YoutubeDL(opts) as ydl:
                result = ydl.extract_info(videos_url, download=False)
                
            if not result or 'entries' not in result:
                # Fallback: videos URL 실패시 원본 URL 시도
                logger.warning("videos URL 실패, 원본 URL로 재시도...")
                fallback_url = channel_url if videos_url != channel_url else channel_url.replace('/videos', '')
                with yt_dlp.YoutubeDL(opts) as ydl:
                    result = ydl.extract_info(fallback_url, download=False)
                    
                if not result or 'entries' not in result:
                    logger.error("❌ 채널 정보를 가져올 수 없습니다")
                    return []
            
            # 유효한 영상만 필터링
            videos = [v for v in result['entries'] if v and v.get('id')]
            logger.info(f"✅ 최신 {len(videos)}개 영상 수집 완료")
            return videos
            
        except Exception as e:
            logger.error(f"❌ 최신 영상 수집 실패: {e}")
            return []

    def _extract_channel_id(self, channel_url: str) -> Optional[str]:
        """
        채널 URL에서 채널 ID를 추출합니다.
        
        Args:
            channel_url: YouTube 채널 URL
            
        Returns:
            Optional[str]: 추출된 채널 ID (UC...) 또는 None
        """
        try:
            # URL 디코딩
            import urllib.parse
            decoded_url = urllib.parse.unquote(channel_url)
            
            # 1. /channel/UC... 형태
            if '/channel/' in decoded_url:
                channel_id = decoded_url.split('/channel/')[-1].split('/')[0]
                if channel_id.startswith('UC') and len(channel_id) == 24:
                    return channel_id
            
            # 2. @handle 형태 - yt-dlp로 채널 ID 추출
            if '@' in decoded_url:
                return self._get_channel_id_from_handle(decoded_url)
            
            # 3. /c/ 또는 /user/ 형태 - yt-dlp로 채널 ID 추출
            if '/c/' in decoded_url or '/user/' in decoded_url:
                return self._get_channel_id_from_handle(decoded_url)
                
            return None
            
        except Exception as e:
            logger.warning(f"채널 ID 추출 실패: {e}")
            return None

    def _get_channel_id_from_handle(self, channel_url: str) -> Optional[str]:
        """
        핸들/사용자명으로부터 채널 ID를 추출합니다.
        """
        try:
            opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': True,
                'skip_download': True,
                'socket_timeout': 60,  # 60초로 증가
                'retries': 1,
                'extractor_args': {
                    'youtube': {
                        'skip': ['webpage'],
                        'player_client': ['android'],
                    },
                    'youtubetab': {
                        'skip': ['webpage', 'authcheck'],
                    }
                }
            }
            
            logger.info(f"🔍 채널 ID 추출 중: {channel_url}")
            start_time = time.time()
            last_progress_time = start_time
            
            def progress_monitor():
                """5초마다 진행상황 로그 출력"""
                nonlocal last_progress_time
                while True:
                    time.sleep(5)
                    current_time = time.time()
                    if current_time - last_progress_time > 4:  # 4초 이상 지났으면
                        elapsed = current_time - start_time
                        logger.info(f"📊 채널 ID 추출 진행 중... ({elapsed:.1f}초 경과)")
                        last_progress_time = current_time
                    else:
                        break  # 메인 작업이 완료됨
            
            # 백그라운드에서 진행상황 모니터링 시작
            monitor_thread = threading.Thread(target=progress_monitor, daemon=True)
            monitor_thread.start()
            
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    result = ydl.extract_info(channel_url, download=False)
                
                # 작업 완료 - 진행상황 모니터링 중단
                last_progress_time = time.time()
                
                # result가 None이거나 dict가 아니면 즉시 반환
                if not result or not isinstance(result, dict):
                    return None
                
                # 1. 직접 ID 확인
                if 'id' in result and result['id']:
                    channel_id = result['id']
                    if isinstance(channel_id, str) and channel_id.startswith('UC') and len(channel_id) == 24:
                        logger.info(f"✅ 채널 ID 추출 성공: {channel_id}")
                        return channel_id
                        
                # 2. uploader_id 확인
                if 'uploader_id' in result and result['uploader_id']:
                    uploader_id = result['uploader_id']
                    if isinstance(uploader_id, str) and uploader_id.startswith('UC') and len(uploader_id) == 24:
                        logger.info(f"✅ 채널 ID 추출 성공 (uploader_id): {uploader_id}")
                        return uploader_id
                
                # 3. entries에서 찾기 (매우 안전하게)
                if 'entries' in result:
                    entries = result['entries']
                    # entries가 리스트인지 확인
                    if isinstance(entries, (list, tuple)):
                        for entry in entries:
                            # entry가 dict이고 channel_id가 있는지 확인
                            if (isinstance(entry, dict) and 
                                'channel_id' in entry and 
                                entry['channel_id']):
                                
                                channel_id = entry['channel_id']
                                if (isinstance(channel_id, str) and 
                                    channel_id.startswith('UC') and 
                                    len(channel_id) == 24):
                                    logger.info(f"✅ 채널 ID 추출 성공 (entries): {channel_id}")
                                    return channel_id
                
                return None
                
            except Exception as e:
                # 작업 완료 (에러) - 진행상황 모니터링 중단
                last_progress_time = time.time()
                raise e
                
        except Exception as e:
            logger.warning(f"핸들에서 채널 ID 추출 실패: {e}")
            return None

    def _convert_to_uploads_playlist(self, channel_id: str) -> str:
        """
        채널 ID (UC...)를 Uploads 재생목록 ID (UU...)로 변환합니다.
        
        Args:
            channel_id: 채널 ID (UC로 시작)
            
        Returns:
            str: Uploads 재생목록 URL
        """
        if not channel_id.startswith('UC') or len(channel_id) != 24:
            raise ValueError(f"잘못된 채널 ID 형식: {channel_id}")
        
        # UC를 UU로 변환
        uploads_playlist_id = 'UU' + channel_id[2:]
        uploads_url = f"https://www.youtube.com/playlist?list={uploads_playlist_id}"
        
        logger.info(f"🔄 Uploads 재생목록 변환: {channel_id} → {uploads_playlist_id}")
        return uploads_url

    def _get_chunk_videos(self, channel_url: str, opts: dict, chunk_num: int) -> List[Dict[str, Any]]:
        """
        특정 청크의 영상을 가져옵니다.
        Uploads 재생목록 방식만 사용합니다.
        """
        try:
            # 채널 ID 추출
            channel_id = self._extract_channel_id(channel_url)
            
            if not channel_id:
                logger.warning(f"채널 ID 추출 실패: {channel_url}")
                return []
            
            # Uploads 재생목록 URL 생성
            uploads_url = self._convert_to_uploads_playlist(channel_id)
            logger.info(f"🌐 청크 {chunk_num} 수집 중... Uploads URL: {uploads_url}")
            
            # 옵션 설정 (타임아웃 제거)
            enhanced_opts = {
                **opts,
                'extract_flat': 'in_playlist',
                'playlist_items': f"{(chunk_num-1)*100 + 1}-{chunk_num*100}",
                'extractor_retries': 1,
                'skip_unavailable_fragments': True,
                'socket_timeout': 60,  # yt-dlp 내부 소켓 타임아웃만 유지 (60초)
                'retries': 1,
                'extractor_args': {
                    'youtube': {
                        'skip': ['webpage'],
                        'player_client': ['android'],
                    },
                    'youtubetab': {
                        'skip': ['webpage', 'authcheck'],
                        'limit': 200,
                    }
                }
            }
            
            logger.info(f"⚡ 타임아웃 제거됨, 필요한 만큼 대기")
            
            start_time = time.time()
            last_progress_time = start_time
            
            # 진행상황 모니터링을 위한 스레드 시작
            def progress_monitor():
                """5초마다 진행상황 로그 출력"""
                nonlocal last_progress_time
                while True:
                    time.sleep(5)
                    current_time = time.time()
                    if current_time - last_progress_time > 4:  # 4초 이상 지났으면
                        elapsed = current_time - start_time
                        logger.info(f"📊 청크 {chunk_num} 진행 중... ({elapsed:.1f}초 경과)")
                        last_progress_time = current_time
                    else:
                        break  # 메인 작업이 완료됨
            
            # 백그라운드에서 진행상황 모니터링 시작
            monitor_thread = threading.Thread(target=progress_monitor, daemon=True)
            monitor_thread.start()
            
            try:
                # 직접 실행 (ThreadPoolExecutor 타임아웃 제거)
                with yt_dlp.YoutubeDL(enhanced_opts) as ydl:
                    result = ydl.extract_info(uploads_url, download=False)
                
                # 작업 완료 - 진행상황 모니터링 중단
                last_progress_time = time.time()
                
                elapsed = time.time() - start_time
                logger.info(f"⚡ 추출 완료 시간: {elapsed:.1f}초")
                
                if result and 'entries' in result:
                    videos = [v for v in result['entries'] if v and v.get('id')]
                    logger.info(f"✅ 청크 {chunk_num}: {len(videos)}개 영상 발견")
                    return videos
                else:
                    logger.warning(f"청크 {chunk_num}: entries 없음")
                    return []
                    
            except Exception as e:
                # 작업 완료 (에러) - 진행상황 모니터링 중단
                last_progress_time = time.time()
                raise e
                
        except Exception as e:
            logger.error(f"❌ 청크 {chunk_num} 처리 중 오류: {e}")
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
    
    # 나머지 메서드들은 기존과 동일하게 유지
    def sanitize_filename(self, name: str) -> str:
        """파일/폴더 이름에 사용할 수 없는 문자를 '_'로 대체합니다."""
        return re.sub(r'[\\/*?:"<>|]', "_", name)
    
    def create_video_folder(self, video_info: Dict[str, Any]) -> Path:
        """각 영상별 폴더를 생성합니다."""
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
        """개별 비디오를 다운로드합니다."""
        video_id = video_info.get('id', '')
        title = video_info.get('title', '제목 없음')
        
        if not video_id:
            logger.error("비디오 ID가 없습니다.")
            return False
        
        # 품질 선택
        format_selector = 'bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[height<=1080]/best'
        if settings.max_quality:
            if settings.max_quality == "480p" or settings.max_quality == "low":
                format_selector = 'bestvideo[ext=mp4][height<=480]+bestaudio[ext=m4a]/best[height<=480]/best'
        
        # yt-dlp 옵션 설정
        ydl_opts = {
            'outtmpl': str(output_folder / f'{title}.%(ext)s'),
            'format': format_selector,
            'merge_output_format': 'mp4',
            'logger': self.yt_dlp_logger,
            'ignoreerrors': True,
            'quiet': True,
            'no_warnings': True,
            'http_headers': {
                'User-Agent': settings.user_agent,
            },
            # 🔥 환경변수에서 rate limiting 설정
            'socket_timeout': int(os.getenv('YDH_YTDLP_SOCKET_TIMEOUT', '30')),
            'retries': int(os.getenv('YDH_YTDLP_RETRIES', '3')),
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
        }
        
        try:
            video_url = f"https://www.youtube.com/watch?v={video_id}"
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                error_code = ydl.download([video_url])
                
                if error_code == 0:
                    logger.info(f"다운로드 완료: {title}")
                    self._save_video_metadata(video_info, output_folder)
                    self._add_to_archive(video_id, channel_name)
                    return True
                else:
                    logger.error(f"다운로드 실패: {title}")
                    return False
                    
        except Exception as e:
            logger.error(f"다운로드 중 오류 발생: {e}")
            return False
    
    def _save_video_metadata(self, video_info: Dict[str, Any], output_folder: Path) -> None:
        """비디오 메타데이터를 JSON 파일로 저장합니다."""
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
            }
            
            # 메타데이터 파일 저장
            metadata_file = output_folder / 'metadata.json'
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)
            
        except Exception as e:
            logger.warning(f"메타데이터 저장 실패: {e}")
    
    def get_downloaded_archive_path(self, channel_name: str) -> Path:
        """채널별 downloaded 아카이브 파일 경로를 반환합니다."""
        safe_channel_name = re.sub(r'[\\/*?:"<>|]', "_", channel_name)
        return settings.download_path / f"{safe_channel_name}_downloaded.txt"
    
    def _load_downloaded_archive(self, channel_name: str) -> Set[str]:
        """다운로드 아카이브 파일에서 이미 다운로드된 영상 ID 목록을 로드합니다."""
        archive_path = self.get_downloaded_archive_path(channel_name)
        downloaded_ids = set()
        
        if archive_path.exists():
            try:
                with open(archive_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and line.startswith('youtube '):
                            video_id = line.split(' ', 1)[1]
                            downloaded_ids.add(video_id)
                            
                logger.debug(f"아카이브에서 {len(downloaded_ids)}개 영상 ID 로드완료")
                    
            except Exception as e:
                logger.warning(f"아카이브 파일 읽기 실패: {e}")
        
        return downloaded_ids
    
    def _check_downloads_folder(self, channel_name: str) -> Set[str]:
        """
        downloads 폴더에서 이미 다운로드 진행중인 영상 ID들을 확인합니다.
        
        Args:
            channel_name: 채널 이름
            
        Returns:
            Set[str]: downloads 폴더에 있는 영상 ID 목록
        """
        downloading_ids = set()
        
        try:
            # downloads 폴더 확인
            if not settings.download_path.exists():
                return downloading_ids
            
            # downloads 폴더의 모든 하위 폴더 확인
            for item in settings.download_path.iterdir():
                if item.is_dir():
                    try:
                        # 폴더 이름에서 video ID 추출 시도
                        folder_name = item.name
                        
                        # 1. metadata.json 파일에서 video ID 확인
                        metadata_file = item / 'metadata.json'
                        if metadata_file.exists():
                            try:
                                import json
                                with open(metadata_file, 'r', encoding='utf-8') as f:
                                    metadata = json.load(f)
                                    video_id = metadata.get('id')
                                    if video_id:
                                        downloading_ids.add(video_id)
                                        continue
                            except Exception:
                                pass
                        
                        # 2. 폴더 이름에서 YouTube ID 패턴 찾기 (11자리 영숫자)
                        import re
                        id_pattern = r'[a-zA-Z0-9_-]{11}'
                        matches = re.findall(id_pattern, folder_name)
                        for match in matches:
                            # YouTube video ID는 보통 특정 패턴을 가지므로 더 엄격하게 체크
                            if len(match) == 11 and not match.isdigit():
                                downloading_ids.add(match)
                                break
                        
                        # 3. 폴더 내 비디오 파일에서 ID 추출
                        for video_file in item.glob("*.mp4"):
                            video_name = video_file.stem
                            matches = re.findall(id_pattern, video_name)
                            for match in matches:
                                if len(match) == 11 and not match.isdigit():
                                    downloading_ids.add(match)
                                    break
                    except Exception as e:
                        logger.debug(f"폴더 처리 중 오류 (무시): {item} - {e}")
                        continue
            
            if downloading_ids:
                logger.info(f"📁 downloads 폴더에서 {len(downloading_ids)}개 진행중 영상 발견")
                logger.debug(f"진행중 영상 ID들: {list(downloading_ids)[:5]}...")  # 처음 5개만 로그
            
        except Exception as e:
            logger.warning(f"downloads 폴더 확인 중 오류: {e}")
        
        return downloading_ids

    def download_channel_videos(self, channel_url: str, channel_name: str = "", full_scan: bool = False) -> Dict[str, int]:
        """
        🚀 2-STAGE OPTIMIZED: 채널의 새 영상을 2단계 방식으로 다운로드합니다.
        
        Args:
            channel_url: YouTube 채널 URL
            channel_name: 채널 이름
            full_scan: True면 전체 무결성 검사 모드, False면 빠른 확인 모드 (기본값)
        
        Returns:
            Dict[str, int]: 다운로드 통계
            
        두 가지 모드:
        - 빠른 확인 모드 (기본): 최신 영상만 확인하여 신규 영상 다운로드
        - 전체 검사 모드 (--full-scan): 모든 영상과 아카이브 비교하여 누락 영상 복구
        """
        # 다운로드 경로 생성
        settings.download_path.mkdir(parents=True, exist_ok=True)
        
        # 모드별 로깅
        mode_text = "전체 무결성 검사" if full_scan else "빠른 확인"
        logger.info(f"🚀 {mode_text} 모드 시작: {channel_url}")
        total_start_time = time.time()
        
        if full_scan:
            # 전체 무결성 검사 모드
            return self._full_integrity_scan_and_download(channel_url, channel_name, total_start_time)
        else:
            # 빠른 확인 모드 (기본)
            return self._fast_check_and_download(channel_url, channel_name, total_start_time)
    
    def _fast_check_and_download(self, channel_url: str, channel_name: str, start_time: float) -> Dict[str, int]:
        """빠른 확인 모드: 최신 영상만 확인하여 신규 영상 다운로드"""
        logger.info("⚡ 1단계: 빠른 신규 영상 확인")
        
        # 빠른 신규 영상 확인
        fast_check = self.check_for_new_videos_fast(channel_url, channel_name)
        
        if not fast_check['has_new_videos']:
            logger.info("✅ 신규 영상이 없습니다. 다운로드를 건너뜁니다.")
            elapsed = time.time() - start_time
            logger.info(f"⚡ 총 소요시간: {elapsed:.1f}초")
            return {
                "total": fast_check['total_checked'], 
                "downloaded": 0, 
                "skipped": fast_check['total_checked'], 
                "failed": 0
            }
        
        logger.info(f"🎯 신규 영상 감지: {fast_check['new_video_count']}개")
        
        # 신규 영상이 있는 경우, 추가 수집 여부 결정
        if fast_check['new_video_count'] >= 15:  # 최신 20개 중 15개 이상이 신규면 더 수집
            logger.info("📚 신규 영상이 많아 전체 스캔을 수행합니다...")
            videos = self.get_channel_videos(channel_url)
            
            # 기존 다운로드 아카이브와 비교
            downloaded_ids = self._load_downloaded_archive(channel_name)
            # downloads 폴더에 있는 진행중인 영상들도 제외
            downloading_ids = self._check_downloads_folder(channel_name)
            all_excluded_ids = downloaded_ids | downloading_ids
            
            new_videos = [v for v in videos if v.get('id') not in all_excluded_ids]
            skipped_count = len(videos) - len(new_videos)
            
        else:
            # 최신 영상만으로 충분 (fast_check에서 이미 downloads 폴더 체크됨)
            logger.info("📋 최신 영상만으로 다운로드를 진행합니다...")
            new_videos = fast_check['latest_videos']
            skipped_count = fast_check['total_checked'] - len(new_videos)
        
        # 실제 다운로드 진행
        return self._execute_download(new_videos, skipped_count, start_time, "빠른 확인", channel_name)
    
    def _full_integrity_scan_and_download(self, channel_url: str, channel_name: str, start_time: float) -> Dict[str, int]:
        """전체 무결성 검사 모드: 모든 영상과 아카이브를 비교하여 누락 영상 복구"""
        logger.info("🔍 전체 무결성 검사 모드")
        logger.warning("⏰ 이 작업은 몇 분이 소요될 수 있습니다...")
        
        # 1단계: 전체 영상 목록 수집
        logger.info("📚 1단계: 채널의 전체 영상 목록 수집 중...")
        all_videos = self.get_channel_videos(channel_url)
        
        if not all_videos:
            logger.warning("채널에서 영상을 찾을 수 없습니다.")
            elapsed = time.time() - start_time
            logger.info(f"⚡ 총 소요시간: {elapsed:.1f}초")
            return {"total": 0, "downloaded": 0, "skipped": 0, "failed": 0}
        
        logger.info(f"📊 채널 전체 영상: {len(all_videos)}개")
        
        # 2단계: 로컬 아카이브와 비교
        logger.info("📋 2단계: 로컬 아카이브와 비교 중...")
        downloaded_ids = self._load_downloaded_archive(channel_name)
        logger.info(f"📥 이미 다운로드된 영상: {len(downloaded_ids)}개")
        
        # 3단계: downloads 폴더의 진행중인 영상 확인
        logger.info("📁 3단계: downloads 폴더의 진행중 영상 확인 중...")
        downloading_ids = self._check_downloads_folder(channel_name)
        
        # 4단계: 누락된 영상 식별 (아카이브 + 진행중 영상 모두 제외)
        all_excluded_ids = downloaded_ids | downloading_ids
        missing_videos = [v for v in all_videos if v.get('id') not in all_excluded_ids]
        skipped_count = len(all_videos) - len(missing_videos)
        
        if downloading_ids:
            logger.info(f"🔄 downloads 폴더의 {len(downloading_ids)}개 진행중 영상 건너뜀")
        
        if not missing_videos:
            logger.info("✅ 누락된 영상이 없습니다. 모든 영상이 완전히 다운로드되어 있습니다.")
            elapsed = time.time() - start_time
            logger.info(f"⚡ 총 소요시간: {elapsed:.1f}초")
            return {
                "total": len(all_videos), 
                "downloaded": 0, 
                "skipped": skipped_count, 
                "failed": 0
            }
        
        logger.info(f"🔍 누락된 영상 발견: {len(missing_videos)}개")
        logger.info("📥 누락된 영상들을 다운로드합니다...")
        
        # 4단계: 누락된 영상들 다운로드
        return self._execute_download(missing_videos, skipped_count, start_time, "무결성 검사", channel_name)
    
    def _execute_download(self, videos_to_download: List[Dict[str, Any]], skipped_count: int, start_time: float, mode_name: str, channel_name: str = "") -> Dict[str, int]:
        """실제 비디오 다운로드 실행"""
        if not videos_to_download:
            logger.info("다운로드할 영상이 없습니다.")
            elapsed = time.time() - start_time
            logger.info(f"⚡ 총 소요시간: {elapsed:.1f}초")
            return {"total": 0, "downloaded": 0, "skipped": skipped_count, "failed": 0}
        
        logger.info(f"📥 다운로드 대상: {len(videos_to_download)}개 영상")
        
        # 다운로드 수 제한 적용 (빠른 확인 모드에서만)
        if mode_name == "빠른 확인" and settings.max_downloads_per_run > 0:
            original_count = len(videos_to_download)
            videos_to_download = videos_to_download[:settings.max_downloads_per_run]
            if original_count > len(videos_to_download):
                logger.info(f"다운로드 수 제한: {original_count}개 중 {len(videos_to_download)}개만 다운로드 (최신 순)")
        
        # 다운로드 통계 초기화
        stats = {"total": len(videos_to_download), "downloaded": 0, "skipped": skipped_count, "failed": 0}
        
        # 간단한 진행률 표시 - multiprocessing 이슈 방지
        total_videos = len(videos_to_download)
        logger.info(f"📥 {mode_name} 다운로드 시작: {total_videos}개 영상")
        
        try:
            with WarningCapturer():
                for idx, video in enumerate(videos_to_download):
                    current_progress = idx + 1
                    progress_percent = (current_progress / total_videos) * 100
                    
                    video_id = video.get('id')
                    if not video_id:
                        logger.warning(f"[{current_progress}/{total_videos}] ({progress_percent:.1f}%) 비디오 ID 없음")
                        stats["failed"] += 1
                        continue
                    
                    try:
                        # 비디오 상세 정보 가져오기
                        video_url = f"https://www.youtube.com/watch?v={video_id}"
                        video_info = self.get_video_info(video_url)
                        
                        if not video_info:
                            logger.warning(f"[{current_progress}/{total_videos}] ({progress_percent:.1f}%) 비디오 정보 없음: {video_id}")
                            stats["failed"] += 1
                            continue
                        
                        video_title = video_info.get('title', '제목 없음')
                        logger.info(f"[{current_progress}/{total_videos}] ({progress_percent:.1f}%) 다운로드 중: {video_title}")
                        
                        # 영상별 폴더 생성
                        folder_path = self.create_video_folder(video_info)
                        
                        # 비디오 다운로드 - 전달받은 채널 이름 사용, fallback으로 영상 정보에서 추출
                        final_channel_name = channel_name or video_info.get('uploader', '') or video_info.get('channel', '')
                        if self.download_video(video_info, folder_path, final_channel_name):
                            stats["downloaded"] += 1
                            logger.info(f"✅ [{current_progress}/{total_videos}] 다운로드 완료: {video_title}")
                        else:
                            stats["failed"] += 1
                            logger.error(f"❌ [{current_progress}/{total_videos}] 다운로드 실패: {video_title}")
                        
                        # 서버 부하 방지를 위한 지연
                        time.sleep(0.5)
                        
                    except Exception as e:
                        logger.error(f"❌ [{current_progress}/{total_videos}] 영상 처리 중 예외 발생: {e}")
                        stats["failed"] += 1
            
            # 결과 요약
            elapsed = time.time() - start_time
            logger.info("-" * 50)
            logger.info(f"✅ {mode_name} 모드 완료!")
            logger.info(f"📥 다운로드 성공: {stats['downloaded']}개")
            logger.info(f"⏭️ 건너뛴 영상: {stats['skipped']}개") 
            logger.info(f"❌ 실패한 영상: {stats['failed']}개")
            logger.info(f"⚡ 총 소요시간: {elapsed:.1f}초")
            logger.info(f"📂 다운로드 위치: {settings.download_path.absolute()}")
            
            return stats
            
        except Exception as e:
            logger.error(f"다운로드 중 오류 발생: {e}")
            elapsed = time.time() - start_time
            logger.info(f"⚡ 총 소요시간: {elapsed:.1f}초")
            return stats
            
        finally:
            # 진행률 표시 완료
            logger.info(f"📊 {mode_name} 모드 진행률 표시 완료")
    
    def _add_to_archive(self, video_id: str, channel_name: str) -> None:
        """다운로드된 영상을 아카이브에 추가합니다."""
        archive_path = self.get_downloaded_archive_path(channel_name)
        with open(archive_path, 'a', encoding='utf-8') as f:
            f.write(f"youtube {video_id}\n")
        logger.debug(f"아카이브에 영상 추가: {video_id}")
    
    def retry_failed_downloads(self, channel_name: str = "") -> Dict[str, int]:
        """실패한 다운로드를 재시도합니다."""
        return {"total": 0, "downloaded": 0, "failed": 0}
    
    def cleanup_incomplete_downloads(self) -> int:
        """불완전한 다운로드 파일들을 정리합니다."""
        return 0