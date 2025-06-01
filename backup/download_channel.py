import sys
import os
import re
import json
import datetime
import time
import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
from youtube_transcript_api.formatters import TextFormatter
from tqdm import tqdm
import traceback
import glob
import http.cookiejar
import tempfile
import random
import base64

CHANNEL_URL = "https://www.youtube.com/@%EB%8F%84%EC%BF%84%EB%B6%80%EB%8F%99%EC%82%B0/videos"
DOWNLOAD_PATH = "./result"
PROGRESS_FILE = "./download_progress.json"

LANGUAGE = "ko"
BROWSER = "chrome"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
USE_PROXY = False
PROXIES = {
    'http': 'socks5://127.0.0.1:9050',
    'https': 'socks5://127.0.0.1:9050'
}

# VTT 파일을 TXT로 변환한 후 원본 VTT 파일 삭제 여부
DELETE_VTT_AFTER_CONVERSION = True

# 트랜스크립션 시 인증을 위한 쿠키 파일 지정
USE_COOKIES_FOR_TRANSCRIPT = True
COOKIES_FILE = None  # 자동으로 생성될 예정
DETAILED_DEBUG = False  # 디버깅 메시지 비활성화

def sanitize_filename(name: str) -> str:
    """
    파일/폴더 이름에 사용할 수 없는 문자를 '_'로 대체합니다.
    """
    return re.sub(r'[\\/*?:"<>|]', "_", name)

def get_browser_cookies(browser_name):
    """
    지정된 브라우저에서 쿠키를 추출하여 임시 파일로 저장합니다.
    """
    try:
        # 임시 파일 생성
        temp_cookie_file = tempfile.NamedTemporaryFile(delete=False, suffix='.txt')
        temp_cookie_file.close()
        
        try:
            # 최신 버전 yt-dlp에서 변경된 API 사용
            with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
                ydl.cookiejar = http.cookiejar.MozillaCookieJar(temp_cookie_file.name)
                ydl._load_cookies_from_browser(browser_name)
                ydl.cookiejar.save(ignore_discard=True, ignore_expires=True)
            return temp_cookie_file.name
        except AttributeError:
            # 이전 버전 호환성 시도
            try:
                from browser_cookie3 import chrome, firefox, safari, opera, edge
                
                cookiejar = None
                if browser_name.lower() == 'chrome':
                    cookiejar = chrome(domain_name='.youtube.com')
                elif browser_name.lower() == 'firefox':
                    cookiejar = firefox(domain_name='.youtube.com')
                elif browser_name.lower() == 'safari':
                    cookiejar = safari(domain_name='.youtube.com')
                elif browser_name.lower() == 'opera':
                    cookiejar = opera(domain_name='.youtube.com')
                elif browser_name.lower() == 'edge':
                    cookiejar = edge(domain_name='.youtube.com')
                
                if cookiejar:
                    jar = http.cookiejar.MozillaCookieJar(temp_cookie_file.name)
                    for cookie in cookiejar:
                        if '.youtube.com' in cookie.domain:
                            jar.set_cookie(cookie)
                    jar.save(ignore_discard=True, ignore_expires=True)
                    return temp_cookie_file.name
            except ImportError:
                print("browser_cookie3 모듈을 설치하려면: pip install browser_cookie3")
                return None
            except Exception as e:
                print(f"browser_cookie3 사용 중 오류: {e}")
                return None
    except Exception as e:
        print(f"브라우저 쿠키 추출 오류: {e}")
        if os.path.exists(temp_cookie_file.name):
            try:
                os.remove(temp_cookie_file.name)
            except:
                pass
        return None

def has_korean_transcript(video_id: str) -> bool:
    """
    비디오에 한국어 자막이 있는지 확인합니다.
    쿠키와 프록시를 사용하여 IP 차단을 우회합니다.
    """
    global COOKIES_FILE
    
    try:
        # 트랜스크립트 API 옵션 설정
        kwargs = {
            'continue_after_error': True
        }
        
        # 쿠키 사용 설정
        if USE_COOKIES_FOR_TRANSCRIPT and COOKIES_FILE:
            kwargs['cookies'] = COOKIES_FILE
            
        # 프록시 사용 여부에 따라 트랜스크립트 목록 가져오기
        if USE_PROXY:
            kwargs['proxies'] = PROXIES
            
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id, **kwargs)
        available_languages = [t.language_code for t in transcript_list]
        
        if 'ko' in available_languages:
            return True
        elif 'ko-KR' in available_languages:
            return True
        elif 'ko_KR' in available_languages:
            return True
        
        # 한국어와 유사한 언어 코드 체크 (대소문자 구분없이)
        for lang in available_languages:
            if lang.lower().startswith('ko'):
                return True
        
        return False
    except Exception as e:
        # 조용히 실패 처리
        return False

def fetch_transcript(video_id: str) -> str:
    """
    youtube-transcript-api를 사용하여 특정 video_id의 한국어 트랜스크립션을 추출합니다.
    한국어 자막만 가져옵니다.
    쿠키와 프록시 옵션이 포함되어 있습니다.
    """
    global COOKIES_FILE
    
    try:
        if DETAILED_DEBUG:
            print(f"[디버그] fetch_transcript 시작: 비디오 ID {video_id}")
        
        # 방법 1: youtube-transcript-api를 사용한 직접 추출
        if DETAILED_DEBUG:
            print("[디버그] 방법 1: 직접 API 호출로 자막 추출 시도")
            
        try:
            # 호환성 문제를 해결하기 위해 인수 수정
            transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['ko', 'ko-KR', 'ko_KR'])
            if transcript_list:
                if DETAILED_DEBUG:
                    print(f"[디버그] 자막 추출 성공: {len(transcript_list)}개 항목")
                
                # TextFormatter를 사용하여 더 보기 좋은 포맷으로 변환
                formatter = TextFormatter()
                formatted_transcript = formatter.format_transcript(transcript_list)
                
                if DETAILED_DEBUG:
                    print(f"[디버그] 자막 변환 완료: {len(formatted_transcript)} 바이트")
                    if formatted_transcript:
                        print(f"[디버그] 자막 샘플: {formatted_transcript[:100]}...")
                
                return formatted_transcript.strip()
            else:
                if DETAILED_DEBUG:
                    print("[디버그] 자막 추출 성공했으나 내용이 없음")
        except Exception as e:
            if DETAILED_DEBUG:
                print(f"[디버그] 방법 1 실패: {e}")
        
        # 방법 2: 언어 목록 조회 후 사용 가능한 자막 사용
        if DETAILED_DEBUG:
            print("[디버그] 방법 2: 사용 가능한 자막 목록 조회 후 추출 시도")
            
        try:
            # 호환성 문제를 해결하기 위해 인수 수정
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            available_transcripts = list(transcript_list)
            
            if available_transcripts:
                if DETAILED_DEBUG:
                    print(f"[디버그] 자막 목록 발견: {len(available_transcripts)}개")
                    for i, t in enumerate(available_transcripts):
                        print(f"[디버그] 자막 {i+1}: 언어={t.language_code}, 자동생성={t.is_generated}")
                
                # 한국어 자막만 찾기
                ko_transcript = None
                for t in available_transcripts:
                    if t.language_code in ['ko', 'ko-KR', 'ko_KR'] or t.language_code.lower().startswith('ko'):
                        ko_transcript = t
                        break
                
                if ko_transcript:
                    if DETAILED_DEBUG:
                        print(f"[디버그] 한국어 자막 사용: 언어={ko_transcript.language_code}")
                    
                    transcript_list = ko_transcript.fetch()
                    
                    # TextFormatter를 사용하여 더 보기 좋은 포맷으로 변환
                    formatter = TextFormatter()
                    formatted_transcript = formatter.format_transcript(transcript_list)
                    
                    if DETAILED_DEBUG:
                        print(f"[디버그] 자막 변환 완료: {len(formatted_transcript)} 바이트")
                        if formatted_transcript:
                            print(f"[디버그] 자막 샘플: {formatted_transcript[:100]}...")
                    
                    return formatted_transcript.strip()
                else:
                    if DETAILED_DEBUG:
                        print("[디버그] 한국어 자막을 찾을 수 없음")
            else:
                if DETAILED_DEBUG:
                    print("[디버그] 사용 가능한 자막이 없음")
        except Exception as e:
            if DETAILED_DEBUG:
                print(f"[디버그] 방법 2 실패: {e}")
        
        # 방법 3: yt-dlp를 사용하여 자막 추출 시도
        if DETAILED_DEBUG:
            print("[디버그] 방법 3: yt-dlp를 사용하여 자막 추출 시도")
        
        try:
            # 임시 디렉토리 생성
            temp_dir = tempfile.mkdtemp()
            temp_file_path = os.path.join(temp_dir, "temp_subtitle")
            
            # yt-dlp 옵션 설정
            ydl_opts = {
                'skip_download': True,
                'writesubtitles': True,
                'writeautomaticsub': True,
                'subtitleslangs': ['ko', 'ko-KR', 'ko_KR'],  # 한국어만 다운로드
                'subtitlesformat': 'vtt',  # VTT 형식으로 다운로드
                'quiet': not DETAILED_DEBUG,
                'no_warnings': not DETAILED_DEBUG,
                'outtmpl': temp_file_path,
                'embedsubtitles': False,  # 자막 합성 안함
                'noembedsubtitles': True,  # 자막 합성 안함 (추가 옵션)
            }
            
            # 쿠키 사용 설정
            if USE_COOKIES_FOR_TRANSCRIPT and COOKIES_FILE:
                ydl_opts['cookiefile'] = COOKIES_FILE
            
            # 다운로드 시도
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                video_url = f"https://www.youtube.com/watch?v={video_id}"
                ydl.download([video_url])
            
            # 생성된 자막 파일 검색 (VTT 형식)
            subtitle_files = glob.glob(os.path.join(temp_dir, "temp_subtitle.ko*.vtt"))
            if not subtitle_files:
                subtitle_files = glob.glob(os.path.join(temp_dir, "temp_subtitle*.vtt"))
            
            if DETAILED_DEBUG:
                print(f"[디버그] 다운로드된 자막 파일: {subtitle_files}")
            
            if subtitle_files:
                # VTT 파일 처리
                transcript_text = extract_text_from_vtt(subtitle_files[0])
                
                if transcript_text:
                    if DETAILED_DEBUG:
                        print(f"[디버그] 자막 추출 성공: {len(transcript_text)} 바이트")
                        print(f"[디버그] 자막 샘플: {transcript_text[:100]}...")
                    
                    # 임시 파일 정리
                    for sf in subtitle_files:
                        try:
                            os.remove(sf)
                        except:
                            pass
                    
                    try:
                        os.rmdir(temp_dir)
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
            if DETAILED_DEBUG:
                print(f"[디버그] 방법 3 실패: {e}")
            
            # 임시 디렉토리 정리
            try:
                import shutil
                shutil.rmtree(temp_dir, ignore_errors=True)
            except:
                pass
        
        return ""
    except Exception as e:
        if DETAILED_DEBUG:
            print(f"[디버그] 자막 처리 중 오류 발생: {e}")
        # 조용히 실패 처리
        return ""

def load_progress_file():
    """
    다운로드 진행 상황 파일을 로드합니다.
    파일이 없으면 빈 딕셔너리를 반환합니다.
    """
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"진행 상황 파일을 읽는 중 오류 발생: {e}")
            return {"downloaded_videos": []}
    else:
        return {"downloaded_videos": []}

def save_progress_file(progress_data):
    """
    다운로드 진행 상황 파일을 저장합니다.
    """
    try:
        # 디렉토리가 없으면 생성
        os.makedirs(os.path.dirname(PROGRESS_FILE), exist_ok=True)
        
        with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
            json.dump(progress_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"진행 상황 파일을 저장하는 중 오류 발생: {e}")

# 경고 메시지를 캡처하기 위한 표준 에러 리디렉션 클래스
class WarningCapturer:
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

def get_channel_videos(channel_url):
    """
    채널 URL에서 영상 목록을 가져옵니다.
    """
    print("채널 영상 목록 수집 중...")
    
    # 채널 정보 조회 옵션
    ydl_opts = {
        'quiet': True,
        'extract_flat': 'in_playlist',
        'ignoreerrors': True,
        'no_warnings': True,
        'embedsubtitles': False,  # 자막 합성 안함
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            result = ydl.extract_info(channel_url, download=False)
            
            if not result or 'entries' not in result:
                print("채널 정보를 가져오지 못했습니다.")
                return []
            
            videos = [entry for entry in result['entries'] if entry]
            print(f"총 {len(videos)}개 영상을 발견했습니다.")
            return videos
    except Exception as e:
        print(f"채널 정보 수집 중 오류 발생: {e}")
        return []

def create_video_folder(download_path, video_id, title, upload_date):
    """
    각 영상별 폴더를 생성합니다.
    폴더명은 '업로드날짜_제목' 형식입니다.
    """
    # 제목에서 폴더명에 적합하지 않은 문자 제거
    safe_title = sanitize_filename(title)
    # 제목이 너무 길면 잘라서 사용
    if len(safe_title) > 50:
        safe_title = safe_title[:50]
    
    # 폴더명 형식: YYYYMMDD_Title (ID 제거)
    folder_name = f"{upload_date}_{safe_title}"
    folder_path = os.path.join(download_path, folder_name)
    
    # 폴더가 없으면 생성
    if not os.path.exists(folder_path):
        os.makedirs(folder_path, exist_ok=True)
    
    return folder_path

def download_channel_videos(channel_url: str, download_path: str, browser: str = BROWSER) -> None:
    """
    채널 URL에서 영상을 다운로드하고 트랜스크립션도 함께 저장하는 함수.
    이미 다운로드한 영상은 건너뜁니다.
    각 영상은 별도의 폴더에 저장됩니다.
    
    Args:
        channel_url (str): 다운로드할 YouTube 채널 URL.
        download_path (str): 파일이 저장될 경로.
        browser (str): 쿠키를 가져올 브라우저 (chrome, firefox, safari 등)
    """
    # 다운로드 경로가 없으면 생성
    if not os.path.exists(download_path):
        try:
            os.makedirs(download_path)
        except Exception as e:
            print(f"다운로드 경로 생성 실패: {e}", file=sys.stderr)
            sys.exit(1)
    
    # 진행 상황 파일 로드
    progress_data = load_progress_file()
    downloaded_videos = set(progress_data["downloaded_videos"])
    
    # 채널에서 영상 목록 가져오기
    videos = get_channel_videos(channel_url)
    
    if not videos:
        print("다운로드할 영상이 없습니다.")
        return
    
    # 이미 다운로드한 영상 필터링
    new_videos = [v for v in videos if v['id'] not in downloaded_videos]
    
    if not new_videos:
        print("모든 영상이 이미 다운로드되었습니다.")
        return
    
    print(f"새로 다운로드할 영상: {len(new_videos)}개 (총 {len(videos)}개 중)")
    print(f"이미 다운로드된 영상: {len(downloaded_videos)}개")
    
    # 다운로드 진행 상황 추적을 위한 변수
    downloaded_count = 0
    total_videos = len(new_videos)
    skipped_count = 0
    
    # 프로그레스 바 초기화 (더 간단한 형태로 출력)
    pbar = tqdm(total=total_videos, desc="다운로드 진행률", unit="개", ncols=80, leave=False, bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt}')
    
    class MyLogger:
        def debug(self, msg):
            pass
        
        def warning(self, msg):
            # 불필요한 경고 무시
            pass
        
        def error(self, msg):
            # 중요한 오류만 출력
            if not any(x in msg for x in ["nsig extraction failed", "Some formats may be missing", "Requested format is not available"]):
                print(f"오류: {msg}", file=sys.stderr)
    
    # 메인 다운로드 코드
    print(f"채널 영상 다운로드 시작: {channel_url}")
    print(f"새로 다운로드할 영상: {len(new_videos)}개 (총 {len(videos)}개 중)")
    print(f"이미 다운로드된 영상: {len(downloaded_videos)}개")
    print("-" * 50)
    
    # 개별 영상 다운로드 (전체 채널 URL이 아닌 개별 비디오 URL을 사용)
    try:
        with WarningCapturer():
            for idx, video in enumerate(new_videos):
                video_id = video.get('id')
                if not video_id:
                    if not DETAILED_DEBUG:
                        pbar.update(1)
                    continue
                
                # 이미 다운로드된 동영상이면 건너뛰기
                if video_id in downloaded_videos:
                    if not DETAILED_DEBUG:
                        pbar.update(1)
                    continue
                
                if DETAILED_DEBUG:
                    print(f"\n[{idx+1}/{len(new_videos)}] 영상 {video_id} 처리중...")
                video_url = f"https://www.youtube.com/watch?v={video_id}"
                video_info = None
                download_success = False
                folder_path = None
                
                try:
                    # yt-dlp 옵션 설정
                    ydl_opts = {
                        # 각 영상별 폴더 생성 (절대 경로 사용)
                        'outtmpl': os.path.abspath(os.path.join(download_path, '%(upload_date)s_%(title).50s', '%(title)s.%(ext)s')),
                        'format': 'bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[height<=1080]/best',  # 최대 1080p 화질 우선, 없으면 최상 화질
                        'merge_output_format': 'mp4',  # 병합 형식 지정
                        'logger': MyLogger(),
                        'ignoreerrors': True,
                        'quiet': True,
                        'no_warnings': True,
                        'verbose': False,
                        'cookiesfrombrowser': (browser, None, None, None),  # 브라우저 쿠키 사용
                        'http_headers': {  # 클라우드플레어 우회를 위한 헤더
                            'User-Agent': USER_AGENT,
                        },
                        'retries': 3,
                        'fragment_retries': 3,
                        # 자막 다운로드 옵션 추가
                        'writesubtitles': True,
                        'writeautomaticsub': True,
                        'subtitleslangs': ['ko', 'ko-KR', 'ko_KR'],  # 한국어 자막만 다운로드
                        'subtitlesformat': 'vtt',  # VTT 형식으로 통일
                        'embedsubtitles': False,  # 영상에 자막 합성 안함
                        'noembedsubtitles': True,  # 자막 합성 안함 (추가 옵션)
                        'embedthumbnails': False,  # 썸네일 합성 안함
                        'nopostoverwrites': True,  # 후처리로 기존 파일 덮어쓰기 방지
                        'postprocessor_args': {
                            'ffmpeg': ['-c', 'copy', '-sn'],  # 자막 스트림 제외하고 복사
                        },
                    }
                    
                    # 간단한 방식으로 다운로드 시도
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        try:
                            # 영상 정보 추출 및 다운로드 시도
                            video_info = ydl.extract_info(video_url, download=False)
                            if video_info:
                                # 실제 다운로드
                                error_code = ydl.download([video_url])
                                if error_code == 0:  # 성공적으로 다운로드
                                    download_success = True
                                    title = video_info.get('title', '제목 없음')
                                    
                                    # 영상이 저장된 폴더 경로 생성
                                    folder_path = os.path.abspath(os.path.join(
                                        download_path, 
                                        f"{video_info.get('upload_date', '')}_{sanitize_filename(title)[:50]}"
                                    ))
                                    
                                    print(f"다운로드 완료: {title}")
                                    print(f"저장 위치: {folder_path}")
                                    
                                    # 다운로드 성공한 비디오 ID를 진행 상황에 추가
                                    if video_id not in progress_data["downloaded_videos"]:
                                        progress_data["downloaded_videos"].append(video_id)
                                        save_progress_file(progress_data)
                                    
                                    # 다운로드가 완료된 직후에 해당 영상의 자막 처리
                                    if folder_path and os.path.exists(folder_path):
                                        if DETAILED_DEBUG:
                                            print(f"\n[{idx+1}/{len(new_videos)}] 영상 {video_id}의 자막 처리 시작...")
                                        
                                        # 영상 파일 경로
                                        video_filename = os.path.join(folder_path, f"{title}.mp4")
                                        
                                        # 1. 먼저 VTT 파일이 있는지 확인
                                        vtt_files = glob.glob(os.path.join(folder_path, "*.vtt"))
                                        if vtt_files:
                                            if DETAILED_DEBUG:
                                                print(f"VTT 자막 파일 발견: {len(vtt_files)}개")
                                            
                                            # 한국어 VTT 파일 찾기
                                            ko_vtt_files = [f for f in vtt_files if ".ko." in f or ".ko-KR." in f or ".ko_KR." in f]
                                            if ko_vtt_files:
                                                if DETAILED_DEBUG:
                                                    print(f"한국어 VTT 파일 발견: {len(ko_vtt_files)}개")
                                                
                                                # 자막 텍스트 파일 경로
                                                txt_file = os.path.join(folder_path, f"{sanitize_filename(title)}.txt")
                                                
                                                # VTT 파일을 텍스트로 변환
                                                transcript_text = extract_text_from_vtt(ko_vtt_files[0])
                                                if transcript_text:
                                                    with open(txt_file, 'w', encoding='utf-8') as f:
                                                        f.write(f"# Video ID: {video_id}\n# Title: {title}\n\n")
                                                        f.write(transcript_text)
                                                    if DETAILED_DEBUG:
                                                        print(f"자막 텍스트 저장 완료: {txt_file}")
                                                    
                                                    # TXT 생성 후 원본 VTT 파일 삭제 옵션
                                                    if DELETE_VTT_AFTER_CONVERSION:
                                                        try:
                                                            os.remove(ko_vtt_files[0])
                                                            if DETAILED_DEBUG:
                                                                print(f"원본 VTT 파일 삭제 완료: {ko_vtt_files[0]}")
                                                        except Exception as e:
                                                            if DETAILED_DEBUG:
                                                                print(f"VTT 파일 삭제 중 오류: {e}")
                                                else:
                                                    if DETAILED_DEBUG:
                                                        print(f"VTT 파일에서 텍스트 추출 실패")
                                            else:
                                                if DETAILED_DEBUG:
                                                    print("한국어 VTT 파일을 찾지 못했습니다.")
                                        
                                        # 2. SRT 파일이 있는지 확인
                                        srt_files = glob.glob(os.path.join(folder_path, "*.srt"))
                                        if srt_files and not os.path.exists(os.path.join(folder_path, f"{sanitize_filename(title)}.txt")):
                                            if DETAILED_DEBUG:
                                                print(f"SRT 자막 파일 발견: {len(srt_files)}개")
                                            
                                            # 한국어 SRT 파일 찾기
                                            ko_srt_files = [f for f in srt_files if ".ko." in f or ".ko-KR." in f or ".ko_KR." in f]
                                            if ko_srt_files:
                                                if DETAILED_DEBUG:
                                                    print(f"한국어 SRT 파일 발견: {len(ko_srt_files)}개")
                                                
                                                # 자막 텍스트 파일 경로
                                                txt_file = os.path.join(folder_path, f"{sanitize_filename(title)}.txt")
                                                
                                                # SRT 파일을 텍스트로 변환
                                                transcript_text = extract_text_from_srt(ko_srt_files[0])
                                                if transcript_text:
                                                    with open(txt_file, 'w', encoding='utf-8') as f:
                                                        f.write(f"# Video ID: {video_id}\n# Title: {title}\n\n")
                                                        f.write(transcript_text)
                                                    if DETAILED_DEBUG:
                                                        print(f"자막 텍스트 저장 완료: {txt_file}")
                                                    
                                                    # TXT 생성 후 원본 SRT 파일 삭제 옵션
                                                    if DELETE_VTT_AFTER_CONVERSION:
                                                        try:
                                                            os.remove(ko_srt_files[0])
                                                            if DETAILED_DEBUG:
                                                                print(f"원본 SRT 파일 삭제 완료: {ko_srt_files[0]}")
                                                        except Exception as e:
                                                            if DETAILED_DEBUG:
                                                                print(f"SRT 파일 삭제 중 오류: {e}")
                                                else:
                                                    if DETAILED_DEBUG:
                                                        print(f"SRT 파일에서 텍스트 추출 실패")
                                            else:
                                                if DETAILED_DEBUG:
                                                    print("한국어 SRT 파일을 찾지 못했습니다.")
                                        
                                        # 3. VTT나 SRT 파일이 없으면 API로 자막 추출 시도
                                        if not os.path.exists(os.path.join(folder_path, f"{sanitize_filename(title)}.txt")):
                                            if DETAILED_DEBUG:
                                                print("자막 파일을 찾지 못했습니다. API 사용 시도...")
                                            
                                            # API로 자막 추출 시도
                                            transcript_text = fetch_transcript(video_id)
                                            if transcript_text:
                                                # 자막 텍스트 파일 경로
                                                txt_file = os.path.join(folder_path, f"{sanitize_filename(title)}.txt")
                                                
                                                with open(txt_file, 'w', encoding='utf-8') as f:
                                                    f.write(f"# Video ID: {video_id}\n# Title: {title}\n\n")
                                                    f.write(transcript_text)
                                                if DETAILED_DEBUG:
                                                    print(f"API 자막 텍스트 저장 완료: {txt_file}")
                                            else:
                                                if DETAILED_DEBUG:
                                                    print("API에서 자막을 가져오지 못했습니다.")
                                        
                                        if DETAILED_DEBUG:
                                            print(f"[{idx+1}/{len(new_videos)}] 영상 {video_id}의 처리 완료")
                                        
                                        # 프로그레스바 업데이트
                                        downloaded_count += 1
                                        pbar.update(1)
                                    else:
                                        if DETAILED_DEBUG:
                                            print(f"저장 폴더를 찾을 수 없습니다: {folder_path}")
                                        skipped_count += 1
                                        pbar.update(1)
                                else:
                                    # 다운로드 실패한 경우
                                    if DETAILED_DEBUG:
                                        print(f"영상 다운로드 실패: {video_id}")
                                    if video_id not in progress_data["downloaded_videos"]:
                                        progress_data["downloaded_videos"].append(video_id)
                                        save_progress_file(progress_data)
                                    skipped_count += 1
                                    pbar.update(1)
                            else:
                                # 정보 추출 실패한 영상도 건너뛰기 대상으로 표시
                                if DETAILED_DEBUG:
                                    print(f"영상 정보 추출 실패: {video_id}")
                                if video_id not in progress_data["downloaded_videos"]:
                                    progress_data["downloaded_videos"].append(video_id)
                                    save_progress_file(progress_data)
                                skipped_count += 1
                                pbar.update(1)
                        except yt_dlp.utils.DownloadError as de:
                            # 다운로드 오류 발생한 경우
                            if DETAILED_DEBUG:
                                print(f"영상 다운로드 오류: {video_id} - {str(de)}")
                            if video_id not in progress_data["downloaded_videos"]:
                                progress_data["downloaded_videos"].append(video_id)
                                save_progress_file(progress_data)
                            skipped_count += 1
                            pbar.update(1)
                    
                    # 다운로드 후 약간의 지연 추가 (서버 부하 방지)
                    time.sleep(0.5)
                except Exception as e:
                    # 영상 처리 실패 시 건너뛰기
                    if DETAILED_DEBUG:
                        print(f"영상 처리 중 예외 발생: {e}")
                    if video_id not in progress_data["downloaded_videos"]:
                        progress_data["downloaded_videos"].append(video_id)
                        save_progress_file(progress_data)
                    skipped_count += 1
                    pbar.update(1)
                    continue
        
        # 다운로드 완료 후 프로그레스바 수동 종료
        pbar.close()
        print("-" * 50)
        print(f"영상 다운로드 완료: 총 {downloaded_count}개 영상")
        print(f"건너뛴 영상: {skipped_count}개")
        print(f"다운로드 위치: {os.path.abspath(download_path)}")
    except Exception as e:
        pbar.close()
        print("-" * 50)
        print(f"오류 발생: {str(e)}")
        print(f"완료: {downloaded_count}개, 건너뜀: {skipped_count}개")
        print(f"다운로드 위치: {os.path.abspath(download_path)}")
        sys.exit(1)

def extract_transcripts_for_videos(video_info_list):
    """
    다운로드된 비디오 정보 목록에서 자막을 추출하여 저장합니다.
    
    Args:
        video_info_list: 비디오 정보 (id, title, filename) 목록
    """
    if not video_info_list:
        return
    
    transcript_count = 0
    failed_count = 0
    
    print(f"총 {len(video_info_list)}개 영상의 자막을 추출합니다...")
    
    # 자막 추출 진행률 표시
    transcript_pbar = tqdm(total=len(video_info_list), desc="자막 추출 진행률", unit="개", ncols=80, leave=False, bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt}')
    
    for video_info in video_info_list:
        video_id = video_info.get('id')
        video_title = video_info.get('title', '제목 없음')
        filename = video_info.get('filename', '')
        
        if not video_id or not filename:
            transcript_pbar.update(1)
            failed_count += 1
            continue
        
        try:
            # 영상 파일 폴더 경로 확인
            video_folder = os.path.dirname(filename) if filename else None
            if not video_folder or not os.path.exists(video_folder):
                transcript_pbar.update(1)
                failed_count += 1
                continue
            
            # 자막 파일 경로 생성
            safe_title = sanitize_filename(video_title)
            transcript_filename = os.path.join(video_folder, f"{safe_title}.txt")
            
            # 자막 파일이 이미 존재하는 경우 건너뛰기
            if os.path.exists(transcript_filename):
                transcript_pbar.update(1)
                transcript_count += 1
                continue
            
            # 먼저 VTT 파일이 이미 존재하는지 확인
            vtt_files = glob.glob(os.path.join(video_folder, "*.vtt"))
            if vtt_files:
                # VTT 파일이 있으면 이를 처리
                transcript_text = extract_text_from_vtt(vtt_files[0])
                if transcript_text:
                    # 텍스트 추출에 성공한 경우
                    with open(transcript_filename, 'w', encoding='utf-8') as f:
                        f.write(f"# Video ID: {video_id}\n# Title: {video_title}\n\n")
                        f.write(transcript_text)
                    transcript_count += 1
                    transcript_pbar.update(1)
                    continue
            
            # SRT 파일이 이미 존재하는지 확인
            srt_files = glob.glob(os.path.join(video_folder, "*.srt"))
            if srt_files:
                # SRT 파일이 있으면 이를 처리
                transcript_text = extract_text_from_srt(srt_files[0])
                if transcript_text:
                    # 텍스트 추출에 성공한 경우
                    with open(transcript_filename, 'w', encoding='utf-8') as f:
                        f.write(f"# Video ID: {video_id}\n# Title: {video_title}\n\n")
                        f.write(transcript_text)
                    transcript_count += 1
                    transcript_pbar.update(1)
                    continue
            
            # 파일이 없으면 YouTube API를 통해 자막 추출 시도
            has_transcript = False
            transcript_text = ""
            
            with WarningCapturer():
                # 프록시 사용 여부에 따라 트랜스크립트 확인
                try:
                    if USE_PROXY:
                        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id, proxies=PROXIES)
                    else:
                        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
                    
                    available_languages = [t.language_code for t in transcript_list]
                    has_transcript = LANGUAGE in available_languages
                    
                    if has_transcript:
                        # 프록시 사용 여부에 따라 트랜스크립트 가져오기
                        if USE_PROXY:
                            transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=[LANGUAGE], proxies=PROXIES)
                        else:
                            transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=[LANGUAGE])
                        
                        # TextFormatter를 사용하여 더 보기 좋은 포맷으로 변환
                        formatter = TextFormatter()
                        transcript_text = formatter.format_transcript(transcript_list)
                except Exception as e:
                    print(f"\n[자막] 자막 추출 실패 ({video_id}): {e}")
                    has_transcript = False
            
            # 자막 파일 저장
            if has_transcript and transcript_text:
                with open(transcript_filename, 'w', encoding='utf-8') as f:
                    f.write(f"# Video ID: {video_id}\n# Title: {video_title}\n\n")
                    f.write(transcript_text)
                transcript_count += 1
            else:
                failed_count += 1
            
            # 프로그레스바 업데이트
            transcript_pbar.update(1)
            
            # 서버 부하 방지를 위한 딜레이
            time.sleep(0.5)
        except Exception as e:
            print(f"\n[자막] 자막 처리 오류 ({video_id}): {e}")
            transcript_pbar.update(1)
            failed_count += 1
    
    # 프로그레스바 종료
    transcript_pbar.close()
    
    print(f"\n자막 추출 완료: {transcript_count}개 성공, {failed_count}개 실패")

def extract_text_from_vtt(vtt_file_path):
    """
    VTT 파일에서 순수한 텍스트만 추출합니다.
    예시와 같은 VTT 형식을 처리하도록 최적화되었습니다.
    
    Args:
        vtt_file_path: VTT 파일 경로
        
    Returns:
        str: 추출된 텍스트
    """
    try:
        with open(vtt_file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 결과 텍스트를 저장할 리스트
        extracted_text = []
        
        # 내용을 줄 단위로 분리
        lines = content.split('\n')
        
        # WEBVTT 헤더 이후의 내용만 처리
        start_processing = False
        
        for i, line in enumerate(lines):
            # 헤더 건너뛰기
            if not start_processing:
                if line.strip() == '' or 'WEBVTT' in line or 'Kind:' in line or 'Language:' in line:
                    continue
                if '-->' in line and re.search(r'\d{2}:\d{2}:\d{2}', line):
                    start_processing = True
                    continue
            
            # 시간 정보 라인 건너뛰기 (00:00:00.000 --> 00:00:00.000)
            if '-->' in line and re.search(r'\d{2}:\d{2}:\d{2}', line):
                continue
            
            # 빈 줄 건너뛰기
            if not line.strip():
                continue
            
            # 위치 정보 제거 (align:start position:0%)
            if 'align:' in line and 'position:' in line:
                continue
            
            # 실제 자막 텍스트 처리
            # 1. 태그 제거
            clean_line = re.sub(r'<[^>]+>', '', line)
            
            # 2. 타임코드 제거 (<00:00:00.520>)
            clean_line = re.sub(r'<\d{2}:\d{2}:\d{2}\.\d{3}>', '', clean_line)
            
            # 정리된 텍스트가 있으면 추가
            if clean_line.strip():
                extracted_text.append(clean_line.strip())
        
        # 모든 텍스트 합치기
        return ' '.join(extracted_text)
    
    except Exception as e:
        print(f"VTT 파일 처리 중 오류 발생: {e}")
        return ""

def extract_text_from_srt(srt_file_path):
    """
    SRT 파일에서 순수한 텍스트만 추출합니다.
    
    Args:
        srt_file_path: SRT 파일 경로
        
    Returns:
        str: 추출된 텍스트
    """
    try:
        with open(srt_file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 결과 텍스트를 저장할 리스트
        text_parts = []
        
        # 라인별로 처리
        lines = content.split('\n')
        i = 0
        
        while i < len(lines):
            # SRT 형식: 번호, 시간, 텍스트, 빈 줄 순서
            if i + 1 < len(lines) and re.match(r'^\d+$', lines[i].strip()) and '-->' in lines[i+1]:
                i += 2  # 번호와 시간 건너뛰기
                
                # 빈 줄이 나올 때까지 텍스트 모으기
                text_line = ""
                while i < len(lines) and lines[i].strip():
                    text_line += lines[i].strip() + " "
                    i += 1
                
                # 정리된 텍스트 라인 추가
                if text_line.strip():
                    text_parts.append(text_line.strip())
            else:
                i += 1
        
        # 모든 텍스트 합치기
        return " ".join(text_parts)
    except Exception as e:
        print(f"SRT 파일 처리 중 오류 발생: {e}")
        return ""

def convert_all_vtt_to_txt(download_path):
    """
    다운로드 폴더에 있는 모든 VTT 파일을 TXT 파일로 변환합니다.
    이 함수는 독립적으로 실행할 수 있습니다.
    DELETE_VTT_AFTER_CONVERSION 옵션이 True인 경우 변환 후 원본 VTT 파일을 삭제합니다.
    
    Args:
        download_path: 다운로드 폴더 경로
    """
    print(f"폴더 내 모든 VTT 파일을 TXT로 변환합니다: {download_path}")
    
    # 모든 VTT 파일 찾기
    vtt_files = []
    for root, dirs, files in os.walk(download_path):
        for file in files:
            if file.endswith(".vtt") and ".ko." in file:  # 한국어 자막만 처리
                vtt_files.append(os.path.join(root, file))
    
    print(f"총 {len(vtt_files)}개의 한국어 VTT 파일을 찾았습니다.")
    
    if not vtt_files:
        print("변환할 VTT 파일이 없습니다.")
        return
    
    # 변환 진행
    success_count = 0
    failed_count = 0
    deleted_count = 0
    
    # 프로그레스 바 설정
    pbar = tqdm(total=len(vtt_files), desc="VTT -> TXT 변환", unit="파일", ncols=80, leave=False, bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt}')
    
    for vtt_file in vtt_files:
        try:
            # VTT 파일 경로로부터 출력 TXT 파일 경로 생성
            txt_file = vtt_file.replace(".ko.vtt", ".txt")
            
            # TXT 파일이 이미 존재하면 건너뛰기
            if os.path.exists(txt_file):
                # 원본 VTT 파일 삭제 옵션
                if DELETE_VTT_AFTER_CONVERSION:
                    try:
                        os.remove(vtt_file)
                        deleted_count += 1
                    except Exception as e:
                        if DETAILED_DEBUG:
                            print(f"VTT 파일 삭제 중 오류: {e}")
                
                pbar.update(1)
                success_count += 1
                continue
            
            # VTT 파일에서 텍스트 추출
            extracted_text = extract_text_from_vtt(vtt_file)
            
            if extracted_text:
                # 비디오 ID와 제목 추출 시도
                video_id = "unknown"
                try:
                    # 폴더명이나 파일명에서 영상 제목 추출
                    title = os.path.basename(vtt_file).replace(".ko.vtt", "")
                except:
                    title = "Unknown Title"
                
                # 텍스트 파일 저장
                with open(txt_file, 'w', encoding='utf-8') as f:
                    f.write(f"# Video ID: {video_id}\n# Title: {title}\n\n")
                    f.write(extracted_text)
                
                # 원본 VTT 파일 삭제 옵션
                if DELETE_VTT_AFTER_CONVERSION:
                    try:
                        os.remove(vtt_file)
                        deleted_count += 1
                    except Exception as e:
                        if DETAILED_DEBUG:
                            print(f"VTT 파일 삭제 중 오류: {e}")
                
                success_count += 1
            else:
                failed_count += 1
        except Exception as e:
            if DETAILED_DEBUG:
                print(f"VTT 파일 변환 중 오류 발생: {vtt_file}\n{e}")
            failed_count += 1
        
        pbar.update(1)
    
    pbar.close()
    print("-" * 50)
    if DELETE_VTT_AFTER_CONVERSION:
        print(f"VTT -> TXT 변환 완료: {success_count}개 성공, {failed_count}개 실패, {deleted_count}개 VTT 파일 삭제됨")
    else:
        print(f"VTT -> TXT 변환 완료: {success_count}개 성공, {failed_count}개 실패")

def main() -> None:
    """
    하드코딩된 채널 URL, 다운로드 경로로 다운로드 함수를 호출하는 메인 함수.
    아규먼트로 채널 URL, 다운로드 경로를 지정할 수도 있습니다.
    """
    # 시작 시간 기록
    start_time = time.time()
    
    # 커맨드 라인 인자 처리
    channel_url = CHANNEL_URL
    download_path = DOWNLOAD_PATH
    browser = BROWSER
    
    # 진행 상황 파일 경로 설정
    global PROGRESS_FILE
    
    # 명령행 인자가 있는 경우 처리
    if len(sys.argv) > 1:
        # 첫 번째 인자가 'convert' 명령인 경우 VTT -> TXT 변환만 수행
        if sys.argv[1] == "convert":
            convert_path = DOWNLOAD_PATH
            if len(sys.argv) > 2:
                convert_path = sys.argv[2]
            convert_all_vtt_to_txt(convert_path)
            return
        # 원본 VTT 파일만 삭제하는 명령
        elif sys.argv[1] == "cleanvtt":
            convert_path = DOWNLOAD_PATH
            if len(sys.argv) > 2:
                convert_path = sys.argv[2]
            # DELETE_VTT_AFTER_CONVERSION 옵션을 강제로 True로 설정
            global DELETE_VTT_AFTER_CONVERSION
            DELETE_VTT_AFTER_CONVERSION = True
            convert_all_vtt_to_txt(convert_path)
            return
        
        channel_url = sys.argv[1]
    
    if len(sys.argv) > 2:
        download_path = sys.argv[2]
    
    if len(sys.argv) > 3:
        browser = sys.argv[3]
    
    # 네 번째 인자가 있으면 진행 상황 파일 경로로 사용
    if len(sys.argv) > 4:
        PROGRESS_FILE = sys.argv[4]
        print(f"진행 상황 파일 경로: {PROGRESS_FILE}")
    
    # 프록시 사용 안내
    if USE_PROXY:
        print(f"프록시 사용 활성화: {PROXIES}")
    
    print(f"채널 URL: {channel_url}")
    print(f"다운로드 경로: {download_path}")
    print(f"사용할 브라우저: {browser}")
    
    # 프로그레스 파일 확인
    if os.path.exists(PROGRESS_FILE):
        progress_data = load_progress_file()
        if progress_data and "downloaded_videos" in progress_data:
            print(f"진행 상황 파일 발견: {len(progress_data['downloaded_videos'])}개 영상이 이미 다운로드됨")
    
    try:
        download_channel_videos(channel_url, download_path, browser)
        
        # 종료 시간 및 총 소요 시간 계산
        end_time = time.time()
        total_time = end_time - start_time
        hours, remainder = divmod(total_time, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        print(f"총 소요 시간: {int(hours)}시간 {int(minutes)}분 {int(seconds)}초")
    except Exception as e:
        print(f"다운로드 중 오류 발생: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main() 