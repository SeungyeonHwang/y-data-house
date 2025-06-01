"""
YouTube transcript extraction using youtube-transcript-api.
"""

import logging
import tempfile
import time
from pathlib import Path
from typing import Optional, List, Dict, Any

from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
from youtube_transcript_api.formatters import TextFormatter

from .config import settings

logger = logging.getLogger(__name__)


class TranscriptExtractor:
    """YouTube 자막 추출 클래스."""
    
    def __init__(self):
        """TranscriptExtractor 초기화."""
        self.formatter = TextFormatter()
    
    def has_korean_transcript(self, video_id: str) -> bool:
        """
        비디오에 한국어 자막이 있는지 확인합니다.
        
        Args:
            video_id: YouTube 비디오 ID
            
        Returns:
            bool: 한국어 자막 존재 여부
        """
        try:
            # 트랜스크립트 API 옵션 설정
            kwargs = {'continue_after_error': True}
            

                
            # 프록시 사용 여부에 따라 트랜스크립트 목록 가져오기
            if settings.use_proxy:
                kwargs['proxies'] = settings.proxies
                
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id, **kwargs)
            available_languages = [t.language_code for t in transcript_list]
            
            # 한국어 언어 코드 확인
            for lang_code in settings.subtitle_languages:
                if lang_code in available_languages:
                    return True
            
            # 한국어와 유사한 언어 코드 체크 (대소문자 구분없이)
            for lang in available_languages:
                if lang.lower().startswith('ko'):
                    return True
            
            return False
            
        except Exception as e:
            logger.debug(f"자막 존재 확인 실패: {video_id} - {e}")
            return False
    
    def fetch_transcript(self, video_id: str) -> str:
        """
        YouTube 비디오의 한국어 자막을 추출합니다.
        
        여러 방법을 순차적으로 시도:
        1. 직접 API 호출
        2. 사용 가능한 자막 목록 조회 후 추출
        3. yt-dlp를 통한 자막 다운로드
        
        Args:
            video_id: YouTube 비디오 ID
            
        Returns:
            str: 추출된 자막 텍스트
        """
        logger.debug(f"자막 추출 시작: {video_id}")
        
        # 방법 1: 직접 API 호출
        transcript_text = self._fetch_direct_api(video_id)
        if transcript_text:
            logger.debug(f"방법 1 성공: 직접 API 호출")
            return transcript_text
        
        # 방법 2: 사용 가능한 자막 목록 조회 후 추출
        transcript_text = self._fetch_via_transcript_list(video_id)
        if transcript_text:
            logger.debug(f"방법 2 성공: 자막 목록 조회")
            return transcript_text
        
        # 방법 3: yt-dlp를 통한 자막 다운로드
        transcript_text = self._fetch_via_ytdlp(video_id)
        if transcript_text:
            logger.debug(f"방법 3 성공: yt-dlp")
            return transcript_text
        
        logger.warning(f"모든 방법으로 자막 추출 실패: {video_id}")
        return ""
    
    def _fetch_direct_api(self, video_id: str) -> str:
        """직접 API 호출로 자막을 가져옵니다."""
        try:
            transcript_list = YouTubeTranscriptApi.get_transcript(
                video_id, 
                languages=settings.subtitle_languages
            )
            
            if transcript_list:
                formatted_transcript = self.formatter.format_transcript(transcript_list)
                return formatted_transcript.strip()
                
        except Exception as e:
            logger.debug(f"직접 API 호출 실패: {e}")
        
        return ""
    
    def _fetch_via_transcript_list(self, video_id: str) -> str:
        """사용 가능한 자막 목록을 조회한 후 자막을 가져옵니다."""
        try:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            available_transcripts = list(transcript_list)
            
            if not available_transcripts:
                return ""
            
            # 한국어 자막 찾기
            ko_transcript = None
            for t in available_transcripts:
                if t.language_code in settings.subtitle_languages:
                    ko_transcript = t
                    break
                elif t.language_code.lower().startswith('ko'):
                    ko_transcript = t
                    break
            
            if ko_transcript:
                transcript_data = ko_transcript.fetch()
                formatted_transcript = self.formatter.format_transcript(transcript_data)
                return formatted_transcript.strip()
                
        except Exception as e:
            logger.debug(f"자막 목록 조회 실패: {e}")
        
        return ""
    
    def _fetch_via_ytdlp(self, video_id: str) -> str:
        """yt-dlp를 사용하여 자막을 다운로드합니다."""
        try:
            import yt_dlp
            from .converter import CaptionConverter
            
            # 임시 디렉토리 생성
            temp_dir = Path(tempfile.mkdtemp())
            temp_file_path = temp_dir / "temp_subtitle"
            
            # yt-dlp 옵션 설정
            ydl_opts = {
                'skip_download': True,
                'writesubtitles': True,
                'writeautomaticsub': True,
                'subtitleslangs': settings.subtitle_languages,
                'subtitlesformat': 'vtt',
                'quiet': not settings.detailed_debug,
                'no_warnings': not settings.detailed_debug,
                'outtmpl': str(temp_file_path),
                'embedsubtitles': False,
                'noembedsubtitles': True,
            }
            

            
            # 다운로드 시도
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                video_url = f"https://www.youtube.com/watch?v={video_id}"
                ydl.download([video_url])
            
            # 생성된 자막 파일 검색
            subtitle_files = list(temp_dir.glob("temp_subtitle.ko*.vtt"))
            if not subtitle_files:
                subtitle_files = list(temp_dir.glob("temp_subtitle*.vtt"))
            
            if subtitle_files:
                # VTT 파일 처리
                transcript_text = CaptionConverter.extract_text_from_vtt(subtitle_files[0])
                
                # 임시 파일 정리
                for sf in subtitle_files:
                    try:
                        sf.unlink()
                    except:
                        pass
                
                try:
                    temp_dir.rmdir()
                except:
                    pass
                
                return transcript_text
            
            # 임시 디렉토리 정리
            try:
                import shutil
                shutil.rmtree(temp_dir, ignore_errors=True)
            except:
                pass
            
        except Exception as e:
            logger.debug(f"yt-dlp 자막 추출 실패: {e}")
            
            # 임시 디렉토리 정리
            try:
                import shutil
                shutil.rmtree(temp_dir, ignore_errors=True)
            except:
                pass
        
        return ""
    
    def get_available_languages(self, video_id: str) -> List[Dict[str, str]]:
        """
        비디오에서 사용 가능한 자막 언어 목록을 반환합니다.
        
        Args:
            video_id: YouTube 비디오 ID
            
        Returns:
            List[Dict[str, str]]: 언어 정보 목록
        """
        try:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            languages = []
            
            for transcript in transcript_list:
                languages.append({
                    'language_code': transcript.language_code,
                    'language': transcript.language,
                    'is_generated': transcript.is_generated,
                    'is_translatable': transcript.is_translatable
                })
            
            return languages
            
        except Exception as e:
            logger.warning(f"사용 가능한 언어 조회 실패: {video_id} - {e}")
            return []
    
    def batch_extract_transcripts(self, video_ids: List[str], 
                                delay: float = 0.5) -> Dict[str, str]:
        """
        여러 비디오의 자막을 일괄 추출합니다.
        
        Args:
            video_ids: 비디오 ID 목록
            delay: 요청 간 지연 시간 (초)
            
        Returns:
            Dict[str, str]: 비디오 ID와 자막 텍스트 매핑
        """
        results = {}
        
        for i, video_id in enumerate(video_ids):
            logger.info(f"자막 추출 진행: {i+1}/{len(video_ids)} - {video_id}")
            
            transcript_text = self.fetch_transcript(video_id)
            if transcript_text:
                results[video_id] = transcript_text
                logger.debug(f"자막 추출 성공: {video_id}")
            else:
                logger.warning(f"자막 추출 실패: {video_id}")
            
            # 서버 부하 방지를 위한 지연
            if delay > 0 and i < len(video_ids) - 1:
                time.sleep(delay)
        
        logger.info(f"일괄 자막 추출 완료: {len(results)}/{len(video_ids)}개 성공")
        return results 