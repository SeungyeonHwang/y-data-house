"""
yt-dlp wrapper with download archive functionality.
"""

import logging
import sys
import time
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
                if settings.detailed_debug:
                    logger.debug(f"[yt-dlp] {msg}")
            
            def warning(self, msg):
                # 불필요한 경고 무시
                if not any(x in msg for x in ["nsig extraction failed", "Some formats may be missing", 
                                            "Requested format is not available"]):
                    logger.warning(f"[yt-dlp] {msg}")
            
            def error(self, msg):
                logger.error(f"[yt-dlp] {msg}")
        
        self.yt_dlp_logger = YtDlpLogger()
    
    def get_channel_videos(self, channel_url: str) -> List[Dict[str, Any]]:
        """
        채널 URL에서 영상 목록을 가져옵니다.
        
        Args:
            channel_url: YouTube 채널 URL
            
        Returns:
            List[Dict[str, Any]]: 영상 정보 목록
        """
        logger.info("채널 영상 목록 수집 중...")
        
        # 채널 정보 조회 옵션
        ydl_opts = {
            'quiet': True,
            'extract_flat': 'in_playlist',
            'ignoreerrors': True,
            'no_warnings': True,
            'embedsubtitles': False,
            'logger': self.yt_dlp_logger,
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                result = ydl.extract_info(channel_url, download=False)
                
                if not result or 'entries' not in result:
                    logger.error("채널 정보를 가져오지 못했습니다.")
                    return []
                
                videos = [entry for entry in result['entries'] if entry]
                logger.info(f"총 {len(videos)}개 영상을 발견했습니다.")
                return videos
                
        except Exception as e:
            logger.error(f"채널 정보 수집 중 오류 발생: {e}")
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
            elif settings.max_quality == "720p" or settings.max_quality == "medium":
                format_selector = 'bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/best[height<=720]/best'
            elif settings.max_quality == "480p" or settings.max_quality == "low":
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
            'verbose': False,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (compatible; ydh/1.0)',
            },
            'retries': 3,
            'fragment_retries': 3,
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
            # 다운로드 아카이브 사용
            'download_archive': str(self.get_downloaded_archive_path(channel_name)),
        }
        
        try:
            video_url = f"https://www.youtube.com/watch?v={video_id}"
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                error_code = ydl.download([video_url])
                
                if error_code == 0:
                    logger.info(f"다운로드 완료: {title}")
                    
                    # 🔥 NEW: 비디오 메타데이터를 JSON 파일로 저장
                    self._save_video_metadata(video_info, output_folder)
                    
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
        
        logger.info(f"YouTube 기본 순서(최신순)로 영상을 처리합니다.")
        
        # 다운로드 수 제한 적용
        if settings.max_downloads_per_run > 0:
            original_count = len(videos)
            videos = videos[:settings.max_downloads_per_run]
            if original_count > len(videos):
                logger.info(f"다운로드 수 제한: {original_count}개 중 {len(videos)}개만 다운로드 (최신 순)")
        
        logger.info(f"새로 다운로드할 영상: {len(videos)}개 (총 {len(videos)}개 중)")
        
        # 다운로드 진행 상황 추적
        stats = {"total": len(videos), "downloaded": 0, "skipped": 0, "failed": 0}
        
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