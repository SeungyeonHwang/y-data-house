"""
Click-based CLI interface.
"""

import logging
import sys
import time
import subprocess
import json
import warnings
import os
from pathlib import Path
from typing import Optional, List

import click

from .config import settings
from .downloader import VideoDownloader
from .transcript import TranscriptExtractor
from .converter import CaptionConverter
from .vault_writer import VaultWriter

# multiprocessing 경고 억제
warnings.filterwarnings("ignore", category=UserWarning, module="multiprocessing.resource_tracker")
os.environ.setdefault("PYTHONUNBUFFERED", "1")  # 실시간 로그 출력

# 로깅 설정
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(settings.log_file) if settings.log_file else logging.NullHandler()
    ]
)

logger = logging.getLogger(__name__)


def load_channel_list(channels_file: Path) -> List[str]:
    """채널 목록 파일을 로드합니다."""
    channels = []
    
    if not channels_file.exists():
        logger.error(f"채널 목록 파일을 찾을 수 없습니다: {channels_file}")
        return channels
    
    try:
        with open(channels_file, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                # 빈 줄이나 주석 건너뛰기
                if not line or line.startswith('#'):
                    continue
                
                # URL 유효성 간단 체크
                if 'youtube.com' in line or 'youtu.be' in line:
                    channels.append(line)
                else:
                    logger.warning(f"잘못된 URL 형식 (줄 {line_num}): {line}")
        
        logger.info(f"채널 목록 로드 완료: {len(channels)}개 채널")
        return channels
        
    except Exception as e:
        logger.error(f"채널 목록 파일 읽기 실패: {e}")
        return []


@click.group(invoke_without_command=True)
@click.option('--debug', is_flag=True, help='디버그 모드 활성화')
@click.option('--config', type=click.Path(exists=True), help='설정 파일 경로')
@click.pass_context
@click.version_option()
def main(ctx: click.Context, debug: bool, config: Optional[str]) -> None:
    """Y-Data-House: YouTube 영상 다운로드 및 Obsidian Vault 생성 도구"""
    if debug:
        settings.detailed_debug = True
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("디버그 모드 활성화")
    
    if config:
        logger.info(f"설정 파일 로드: {config}")
    
    # Vault 구조 확인
    settings.ensure_vault_structure()
    logger.info(f"Vault 경로: {settings.vault_root}")
    
    # 명령어가 없으면 도움말 표시
    if ctx.invoked_subcommand is None:
        click.echo("Y-Data-House - YouTube 영상 다운로드 및 Vault 생성 도구")
        click.echo("")
        click.echo("주요 명령어:")
        click.echo("  batch           - channels.txt의 모든 채널 처리")
        click.echo("  ingest <URL>    - 개별 채널 처리")
        click.echo("  stats           - 다운로드 통계")
        click.echo("  config-show     - 설정 확인")
        click.echo("")
        click.echo("사용법: python -m ydh <명령어> [옵션]")


@main.command()
@click.option('--channels-file', type=click.Path(exists=True), default='channels.txt',
              help='채널 목록 파일 경로 (기본: channels.txt)')
@click.option('--vault-only', is_flag=True, help='다운로드 없이 Vault 생성만')
@click.option('--no-vault', is_flag=True, help='다운로드만 하고 Vault 생성 안함')
@click.option('--parallel', is_flag=True, help='🚀 병렬 처리로 성능 향상 (실험적)')
@click.option('--max-workers', type=int, default=3, help='병렬 처리 최대 워커 수 (기본: 3)')
@click.option('--full-scan', is_flag=True, help='🔍 전체 무결성 검사 모드 (모든 영상 확인)')
def batch(channels_file: str, vault_only: bool, no_vault: bool, parallel: bool, max_workers: int, full_scan: bool) -> None:
    """
    channels.txt 파일의 모든 채널을 처리합니다.
    
    두 가지 모드:
    - 기본 모드: 빠른 확인으로 최신 영상만 체크 (수초 완료)
    - --full-scan: 전체 무결성 검사로 누락 영상 복구 (몇 분 소요)
    
    🔄 중단/재개 기능:
    - 다운로드 중단 시 downloads 폴더의 진행중인 영상은 자동으로 건너뜀
    - 다시 실행하면 중단된 지점부터 이어서 다운로드
    """
    
    # 🔥 DEBUG: 환경변수 상태 로그 출력
    import os
    logger.info("=== 환경변수 상태 ===")
    logger.info(f"YDH_YTDLP_SLEEP_INTERVAL: {os.getenv('YDH_YTDLP_SLEEP_INTERVAL', 'NOT SET')}")
    logger.info(f"YDH_YTDLP_MAX_SLEEP_INTERVAL: {os.getenv('YDH_YTDLP_MAX_SLEEP_INTERVAL', 'NOT SET')}")
    logger.info(f"YDH_YTDLP_SLEEP_REQUESTS: {os.getenv('YDH_YTDLP_SLEEP_REQUESTS', 'NOT SET')}")
    logger.info(f"YDH_YTDLP_SOCKET_TIMEOUT: {os.getenv('YDH_YTDLP_SOCKET_TIMEOUT', 'NOT SET')}")
    logger.info(f"YDH_YTDLP_RETRIES: {os.getenv('YDH_YTDLP_RETRIES', 'NOT SET')}")
    logger.info(f"PYTHONUNBUFFERED: {os.getenv('PYTHONUNBUFFERED', 'NOT SET')}")
    logger.info("==================")
    
    channels_path = Path(channels_file)
    
    # 채널 목록 로드
    channels = load_channel_list(channels_path)
    
    if not channels:
        logger.error("처리할 채널이 없습니다. channels.txt 파일을 확인하세요.")
        sys.exit(1)
    
    # 모드별 로깅
    mode_text = "전체 무결성 검사" if full_scan else "빠른 확인"
    logger.info(f"🚀 {mode_text} 모드로 총 {len(channels)}개 채널 처리 시작")
    
    if full_scan:
        logger.warning("⏰ 전체 무결성 검사 모드는 시간이 오래 걸릴 수 있습니다...")
    
    total_stats = {
        "processed_channels": 0,
        "total_downloaded": 0,
        "total_failed": 0,
        "total_vault_processed": 0
    }
    
    start_time = time.time()
    
    # 🚀 병렬 처리 또는 순차 처리 선택
    if parallel and len(channels) > 1:
        logger.info(f"🚀 병렬 처리 모드 활성화 (워커: {max_workers}개)")
        total_stats = _process_channels_parallel(
            channels, vault_only, no_vault, full_scan, max_workers, total_stats
        )
    else:
        logger.info("🔄 순차 처리 모드")
        total_stats = _process_channels_sequential(
            channels, vault_only, no_vault, full_scan, total_stats
        )
    
    # 전체 결과 출력
    end_time = time.time()
    duration = end_time - start_time
    hours, remainder = divmod(duration, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    logger.info(f"\n{'='*60}")
    logger.info("일괄 처리 완료")
    logger.info(f"{'='*60}")
    logger.info(f"처리된 채널: {total_stats['processed_channels']}/{len(channels)}")
    logger.info(f"다운로드된 영상: {total_stats['total_downloaded']}개")
    logger.info(f"실패한 영상: {total_stats['total_failed']}개")
    logger.info(f"Vault 처리된 영상: {total_stats['total_vault_processed']}개")
    logger.info(f"총 소요 시간: {int(hours)}시간 {int(minutes)}분 {int(seconds)}초")
    
    # 🚀 성능 개선 효과 표시
    if parallel:
        logger.info(f"🚀 병렬 처리 사용: {max_workers}개 워커로 성능 향상")

def _process_channels_sequential(channels: List[str], vault_only: bool, no_vault: bool, full_scan: bool, total_stats: dict) -> dict:
    """순차적으로 채널들을 처리합니다."""
    for i, channel_url in enumerate(channels, 1):
        logger.info(f"\n{'='*60}")
        logger.info(f"채널 처리 중 ({i}/{len(channels)}): {channel_url}")
        logger.info(f"{'='*60}")
        
        try:
            # 채널 이름 추출
            vault_writer = VaultWriter()
            channel_name = vault_writer.extract_channel_name_from_url(channel_url)
            
            # Vault만 생성하는 경우
            if vault_only:
                processed = vault_writer.batch_process_downloads(
                    settings.download_path, channel_name
                )
                total_stats["total_vault_processed"] += processed
                total_stats["processed_channels"] += 1
                continue
            
            # 다운로드 수행
            downloader = VideoDownloader()
            stats = downloader.download_channel_videos(channel_url, channel_name, full_scan)
            
            total_stats["processed_channels"] += 1
            total_stats["total_downloaded"] += stats.get("downloaded", 0)
            total_stats["total_failed"] += stats.get("failed", 0)
            
            # Vault 생성
            if not no_vault and stats.get("downloaded", 0) > 0:
                vault_processed = _process_vault_for_channel(channel_name)
                total_stats["total_vault_processed"] += vault_processed
            
            # 채널 간 지연
            time.sleep(1)
            
        except Exception as e:
            logger.error(f"채널 처리 중 오류 발생: {channel_url} - {e}")
            continue
    
    return total_stats

def _process_channels_parallel(channels: List[str], vault_only: bool, no_vault: bool, full_scan: bool, max_workers: int, total_stats: dict) -> dict:
    """병렬로 채널들을 처리합니다."""
    import concurrent.futures
    import threading
    
    # 스레드 안전 카운터
    stats_lock = threading.Lock()
    
    def process_single_channel(channel_url: str) -> dict:
        """단일 채널을 처리하는 함수"""
        local_stats = {"processed": 0, "downloaded": 0, "failed": 0, "vault_processed": 0}
        
        try:
            logger.info(f"🔄 병렬 처리 시작: {channel_url}")
            
            # 채널 이름 추출
            vault_writer = VaultWriter()
            channel_name = vault_writer.extract_channel_name_from_url(channel_url)
            
            # Vault만 생성하는 경우
            if vault_only:
                processed = vault_writer.batch_process_downloads(
                    settings.download_path, channel_name
                )
                local_stats["vault_processed"] = processed
                local_stats["processed"] = 1
                return local_stats
            
            # 다운로드 수행
            downloader = VideoDownloader()
            stats = downloader.download_channel_videos(channel_url, channel_name, full_scan)
            
            local_stats["processed"] = 1
            local_stats["downloaded"] = stats.get("downloaded", 0)
            local_stats["failed"] = stats.get("failed", 0)
            
            # Vault 생성
            if not no_vault and stats.get("downloaded", 0) > 0:
                vault_processed = _process_vault_for_channel(channel_name)
                local_stats["vault_processed"] = vault_processed
            
            logger.info(f"✅ 병렬 처리 완료: {channel_url}")
            return local_stats
            
        except Exception as e:
            logger.error(f"❌ 병렬 처리 실패: {channel_url} - {e}")
            return local_stats
    
    # ThreadPoolExecutor로 병렬 처리
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_channel = {
            executor.submit(process_single_channel, channel_url): channel_url 
            for channel_url in channels
        }
        
        for future in concurrent.futures.as_completed(future_to_channel):
            channel_url = future_to_channel[future]
            try:
                local_stats = future.result()
                
                # 스레드 안전하게 통계 업데이트
                with stats_lock:
                    total_stats["processed_channels"] += local_stats["processed"]
                    total_stats["total_downloaded"] += local_stats["downloaded"]
                    total_stats["total_failed"] += local_stats["failed"]
                    total_stats["total_vault_processed"] += local_stats["vault_processed"]
                    
            except Exception as e:
                logger.error(f"병렬 처리 결과 수집 실패: {channel_url} - {e}")
    
    return total_stats

def _process_vault_for_channel(channel_name: str) -> int:
    """채널의 다운로드된 영상을 Vault로 처리합니다."""
    logger.info("다운로드된 영상을 Vault로 처리 중...")
    
    vault_writer = VaultWriter()
    transcript_extractor = TranscriptExtractor()
    vault_processed = 0
    
    # 새로 다운로드된 영상들 처리
    for video_folder in settings.download_path.iterdir():
        if not video_folder.is_dir():
            continue
        
        try:
            # 메타데이터 로드
            video_info = vault_writer.load_video_metadata(video_folder)
            
            # 비디오 파일 확인
            video_files = list(video_folder.glob("*.mp4"))
            if not video_files:
                continue
            
            video_file = video_files[0]
            
            # 자막 로드
            transcript_text = ""
            txt_files = list(video_folder.glob("*.txt"))
            if txt_files:
                try:
                    with open(txt_files[0], 'r', encoding='utf-8') as f:
                        content = f.read()
                        lines = content.split('\n')
                        transcript_lines = [line for line in lines if not line.startswith('#')]
                        transcript_text = '\n'.join(transcript_lines).strip()
                except Exception as e:
                    logger.warning(f"자막 파일 읽기 실패: {e}")
            
            # VTT/SRT 파일에서 자막 추출
            if not transcript_text:
                vtt_files = list(video_folder.glob("*.vtt"))
                srt_files = list(video_folder.glob("*.srt"))
                
                if vtt_files:
                    transcript_text = CaptionConverter.extract_text_from_vtt(vtt_files[0])
                elif srt_files:
                    transcript_text = CaptionConverter.extract_text_from_srt(srt_files[0])
            
            # 채널 이름 설정
            final_channel_name = channel_name or video_info.get('uploader', 'Unknown Channel')
            
            # Vault에 저장
            if vault_writer.save_video_to_vault(
                video_info, final_channel_name, transcript_text, video_file
            ):
                vault_processed += 1
            
        except Exception as e:
            logger.error(f"Vault 처리 중 오류: {video_folder} - {e}")
    
    # vault 처리 완료 후 downloads 폴더 정리
    if vault_processed > 0:
        cleaned_count = vault_writer.cleanup_downloads_folder(settings.download_path)
        logger.info(f"downloads 폴더 정리: {cleaned_count}개 폴더 삭제")
    
    return vault_processed


@main.command()
@click.argument('channel_url')
@click.option('--channel-name', help='채널 이름 (자동 감지되지 않는 경우)')
@click.option('--vault-only', is_flag=True, help='다운로드 없이 Vault 생성만')
@click.option('--no-vault', is_flag=True, help='다운로드만 하고 Vault 생성 안함')
@click.option('--full-scan', is_flag=True, help='🔍 전체 무결성 검사 모드 (모든 영상 확인)')
def ingest(channel_url: str, channel_name: Optional[str], 
           vault_only: bool, no_vault: bool, full_scan: bool) -> None:
    """
    개별 채널 URL에서 새 영상을 다운로드하고 Vault에 저장합니다.
    
    두 가지 모드:
    - 기본 모드: 빠른 확인으로 최신 영상만 체크 (수초 완료)
    - --full-scan: 전체 무결성 검사로 누락 영상 복구 (몇 분 소요)
    
    🔄 중단/재개 기능:
    - 다운로드 중단 시 downloads 폴더의 진행중인 영상은 자동으로 건너뜀
    - 다시 실행하면 중단된 지점부터 이어서 다운로드
    """
    mode_text = "전체 무결성 검사" if full_scan else "빠른 확인"
    logger.info(f"🚀 {mode_text} 모드로 채널 인제스트 시작: {channel_url}")
    
    if full_scan:
        logger.warning("⏰ 전체 무결성 검사 모드는 시간이 오래 걸릴 수 있습니다...")
    
    start_time = time.time()
    
    try:
        # 채널 이름 추출
        if not channel_name:
            vault_writer = VaultWriter()
            channel_name = vault_writer.extract_channel_name_from_url(channel_url)
        
        logger.info(f"채널 이름: {channel_name}")
        
        # Vault만 생성하는 경우
        if vault_only:
            vault_writer = VaultWriter()
            processed = vault_writer.batch_process_downloads(
                settings.download_path, channel_name
            )
            
            logger.info(f"Vault 전용 처리 완료: {processed}개 영상")
            return
        
        # 다운로드 수행
        downloader = VideoDownloader()
        stats = downloader.download_channel_videos(channel_url, channel_name, full_scan)
        
        logger.info(f"다운로드 통계: {stats}")
        
        # Vault 생성 (no_vault 플래그가 없는 경우)
        if not no_vault and stats['downloaded'] > 0:
            logger.info("다운로드된 영상을 Vault로 처리 중...")
            
            vault_writer = VaultWriter()
            transcript_extractor = TranscriptExtractor()
            
            # 새로 다운로드된 영상들 처리
            for video_folder in settings.download_path.iterdir():
                if not video_folder.is_dir():
                    continue
                
                try:
                    # 🔥 UPDATED: vault_writer의 메타데이터 로드 함수 사용
                    video_info = vault_writer.load_video_metadata(video_folder)
                    
                    # 비디오 파일 확인
                    video_files = list(video_folder.glob("*.mp4"))
                    if not video_files:
                        continue
                    
                    video_file = video_files[0]
                    
                    # 자막 로드
                    transcript_text = ""
                    
                    # 기존 자막 파일 확인
                    txt_files = list(video_folder.glob("*.txt"))
                    if txt_files:
                        try:
                            with open(txt_files[0], 'r', encoding='utf-8') as f:
                                content = f.read()
                                lines = content.split('\n')
                                transcript_lines = [line for line in lines if not line.startswith('#')]
                                transcript_text = '\n'.join(transcript_lines).strip()
                        except Exception as e:
                            logger.warning(f"자막 파일 읽기 실패: {e}")
                    
                    # VTT/SRT 파일에서 자막 추출
                    if not transcript_text:
                        vtt_files = list(video_folder.glob("*.vtt"))
                        srt_files = list(video_folder.glob("*.srt"))
                        
                        if vtt_files:
                            transcript_text = CaptionConverter.extract_text_from_vtt(vtt_files[0])
                        elif srt_files:
                            transcript_text = CaptionConverter.extract_text_from_srt(srt_files[0])
                    
                    # 채널 이름 설정
                    final_channel_name = channel_name or video_info.get('uploader', 'Unknown Channel')
                    
                    # Vault에 저장
                    if vault_writer.save_video_to_vault(
                        video_info, final_channel_name, transcript_text, video_file
                    ):
                        vault_processed += 1
                    
                except Exception as e:
                    logger.error(f"Vault 처리 중 오류: {video_folder} - {e}")
            
            # vault 처리 완료 후 downloads 폴더 정리
            logger.info("vault 처리 완료, downloads 폴더 정리 중...")
            cleaned_count = vault_writer.cleanup_downloads_folder(settings.download_path)
            logger.info(f"downloads 폴더 정리 완료: {cleaned_count}개 폴더 삭제")
        
        # 실행 시간 출력
        end_time = time.time()
        duration = end_time - start_time
        hours, remainder = divmod(duration, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        logger.info(f"총 소요 시간: {int(hours)}시간 {int(minutes)}분 {int(seconds)}초")
        
    except Exception as e:
        logger.error(f"인제스트 중 오류 발생: {e}")
        sys.exit(1)


@main.command()
@click.argument('input_path', type=click.Path(exists=True))
@click.option('--delete-originals', is_flag=True, help='원본 자막 파일 삭제')
def convert(input_path: str, delete_originals: bool) -> None:
    """VTT/SRT 파일을 텍스트로 변환합니다."""
    input_directory = Path(input_path)
    
    if not input_directory.is_dir():
        logger.error("입력 경로가 디렉토리가 아닙니다.")
        sys.exit(1)
    
    logger.info(f"자막 파일 변환 시작: {input_directory}")
    
    converted_count = CaptionConverter.batch_convert_directory(
        input_directory, delete_originals
    )
    
    logger.info(f"변환 완료: {converted_count}개 파일")


@main.command()
@click.argument('input_path', type=click.Path(exists=True))
def cleanvtt(input_path: str) -> None:
    """VTT/SRT 파일을 텍스트로 변환하고 원본 파일을 삭제합니다."""
    input_directory = Path(input_path)
    
    if not input_directory.is_dir():
        logger.error("입력 경로가 디렉토리가 아닙니다.")
        sys.exit(1)
    
    logger.info(f"자막 파일 변환 및 원본 삭제 시작: {input_directory}")
    
    # 항상 원본 파일 삭제
    converted_count = CaptionConverter.batch_convert_directory(
        input_directory, delete_originals=True
    )
    
    logger.info(f"변환 및 원본 삭제 완료: {converted_count}개 파일")


@main.command()
@click.option('--retry', is_flag=True, help='실패한 다운로드 재시도')
@click.option('--cleanup', is_flag=True, help='불완전한 파일 정리')
def maintenance(retry: bool, cleanup: bool) -> None:
    """시스템 유지보수 작업을 수행합니다."""
    downloader = VideoDownloader()
    
    if cleanup:
        logger.info("불완전한 다운로드 파일 정리 중...")
        cleaned = downloader.cleanup_incomplete_downloads()
        logger.info(f"정리 완료: {cleaned}개 파일")
    
    if retry:
        logger.info("실패한 다운로드 재시도 중...")
        stats = downloader.retry_failed_downloads()
        logger.info(f"재시도 결과: {stats}")


@main.command()
@click.argument('input_path', type=click.Path(exists=True))
@click.argument('channel_name')
def vault(input_path: str, channel_name: str) -> None:
    """다운로드된 영상을 Vault로 변환합니다."""
    input_directory = Path(input_path)
    
    if not input_directory.is_dir():
        logger.error("입력 경로가 디렉토리가 아닙니다.")
        sys.exit(1)
    
    logger.info(f"Vault 변환 시작: {input_directory} -> {channel_name}")
    
    vault_writer = VaultWriter()
    processed = vault_writer.batch_process_downloads(input_directory, channel_name)
    
    # vault 처리 완료 후 downloads 폴더 정리
    if processed > 0:
        cleaned_count = vault_writer.cleanup_downloads_folder(input_directory)
        logger.info(f"downloads 폴더 정리: {cleaned_count}개 폴더 삭제")
    
    logger.info(f"Vault 변환 완료: {processed}개 영상")


@main.command()
def config_show() -> None:
    """현재 설정을 표시합니다."""
    click.echo("\n=== Y-Data-House 설정 ===")
    click.echo(f"Vault 경로: {settings.vault_root}")
    click.echo(f"다운로드 경로: {settings.download_path}")
    click.echo(f"언어: {settings.language}")
    click.echo(f"최대 화질: {settings.max_quality}")
    click.echo(f"VTT 삭제: {settings.delete_vtt_after_conversion}")
    click.echo(f"프록시 사용: {settings.use_proxy}")
    click.echo(f"디버그 모드: {settings.detailed_debug}")


@main.command()
@click.confirmation_option(prompt='vault의 모든 captions.txt 파일을 삭제하시겠습니까? (captions.md에 이미 포함됨)')
def cleanup_txt() -> None:
    """vault에서 중복된 captions.txt 파일들을 정리합니다."""
    vault_videos_path = settings.get_vault_videos_path()
    
    if not vault_videos_path.exists():
        logger.error("vault 폴더가 존재하지 않습니다.")
        return
    
    deleted_count = 0
    
    # vault 폴더를 재귀적으로 탐색하여 captions.txt 파일 삭제
    for txt_file in vault_videos_path.rglob("captions.txt"):
        try:
            # 같은 폴더에 captions.md가 있는지 확인
            md_file = txt_file.parent / "captions.md"
            if md_file.exists():
                txt_file.unlink()
                deleted_count += 1
                logger.debug(f"삭제: {txt_file}")
            else:
                logger.warning(f"captions.md가 없어 보존: {txt_file}")
        except Exception as e:
            logger.error(f"파일 삭제 실패: {txt_file} - {e}")
    
    logger.info(f"captions.txt 정리 완료: {deleted_count}개 파일 삭제")


@main.command()
@click.argument('vault_path', type=click.Path(exists=True))
def fix_video_ids(vault_path: str) -> None:
    """기존 Vault 파일들의 video_id를 실제 값으로 업데이트합니다."""
    vault_directory = Path(vault_path)
    
    if not vault_directory.is_dir():
        logger.error("입력 경로가 디렉토리가 아닙니다.")
        sys.exit(1)
    
    logger.info(f"Video ID 수정 시작: {vault_directory}")
    
    vault_writer = VaultWriter()
    fixed_count = 0
    
    # Vault 내 모든 captions.md 파일 찾기
    for captions_file in vault_directory.rglob("captions.md"):
        try:
            # 해당 폴더에서 video_id 추출
            video_folder = captions_file.parent
            extracted_video_id = vault_writer._extract_video_id_from_files(video_folder)
            
            if extracted_video_id != 'unknown':
                # captions.md 파일 내용 읽기
                with open(captions_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # video_id와 source_url 업데이트
                updated_content = content.replace(
                    'video_id: unknown',
                    f'video_id: {extracted_video_id}'
                ).replace(
                    'source_url: "https://www.youtube.com/watch?v=unknown"',
                    f'source_url: "https://www.youtube.com/watch?v={extracted_video_id}"'
                )
                
                # 파일에 다시 쓰기
                with open(captions_file, 'w', encoding='utf-8') as f:
                    f.write(updated_content)
                
                fixed_count += 1
                logger.info(f"Video ID 수정 완료: {captions_file.relative_to(vault_directory)} -> {extracted_video_id}")
            else:
                logger.warning(f"Video ID를 추출할 수 없음: {captions_file.relative_to(vault_directory)}")
                
        except Exception as e:
            logger.error(f"파일 처리 중 오류: {captions_file} - {e}")
            continue
    
    logger.info(f"Video ID 수정 완료: {fixed_count}개 파일")


@main.command()
def config_validate():
    """Vault 데이터 정합성을 검증합니다."""
    from pathlib import Path
    import yaml
    import re
    
    click.echo("🔍 데이터 정합성 검사 시작...")
    
    # 통계
    total_videos = 0
    valid_videos = 0
    invalid_videos = 0
    missing_files = 0
    yaml_errors = 0
    
    vault_videos_path = settings.vault_root / "10_videos"
    
    if not vault_videos_path.exists():
        click.echo("❌ vault/10_videos 폴더가 존재하지 않습니다.")
        return
    
    click.echo(f"📁 검사 경로: {vault_videos_path}")
    
    # 모든 captions.md 파일 찾기
    caption_files = list(vault_videos_path.rglob("captions.md"))
    total_videos = len(caption_files)
    
    click.echo(f"📊 총 {total_videos}개 영상 발견")
    
    required_fields = ['title', 'upload', 'channel', 'video_id', 'topic', 'source_url']
    
    with click.progressbar(caption_files, label='검증 중') as bar:
        for caption_file in bar:
            try:
                with open(caption_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # YAML frontmatter 파싱
                if content.startswith('---'):
                    parts = content.split('---', 2)
                    if len(parts) >= 3:
                        try:
                            metadata = yaml.safe_load(parts[1])
                            
                            # 필수 필드 검사
                            missing_fields = [field for field in required_fields if field not in metadata]
                            if missing_fields:
                                click.echo(f"⚠️  {caption_file.relative_to(vault_videos_path)}: 누락 필드 {missing_fields}")
                                invalid_videos += 1
                                continue
                            
                            # 날짜 형식 검사
                            upload_date = metadata.get('upload')
                            if upload_date and not re.match(r'\d{4}-\d{2}-\d{2}', str(upload_date)):
                                click.echo(f"⚠️  {caption_file.relative_to(vault_videos_path)}: 잘못된 날짜 형식 {upload_date}")
                                invalid_videos += 1
                                continue
                            
                            # video_id 검사
                            video_id = metadata.get('video_id')
                            if video_id and not re.match(r'^[a-zA-Z0-9_-]{11}$', str(video_id)):
                                click.echo(f"⚠️  {caption_file.relative_to(vault_videos_path)}: 잘못된 video_id {video_id}")
                                invalid_videos += 1
                                continue
                            
                            # 동반 파일 검사 (video.mp4)
                            video_file = caption_file.parent / "video.mp4"
                            if not video_file.exists():
                                click.echo(f"📹 {caption_file.relative_to(vault_videos_path)}: video.mp4 누락")
                                missing_files += 1
                            
                            valid_videos += 1
                            
                        except yaml.YAMLError as ye:
                            click.echo(f"❌ {caption_file.relative_to(vault_videos_path)}: YAML 파싱 오류 - {ye}")
                            yaml_errors += 1
                    else:
                        click.echo(f"❌ {caption_file.relative_to(vault_videos_path)}: YAML frontmatter 형식 오류")
                        yaml_errors += 1
                else:
                    click.echo(f"❌ {caption_file.relative_to(vault_videos_path)}: YAML frontmatter 없음")
                    yaml_errors += 1
                    
            except Exception as e:
                click.echo(f"💥 {caption_file.relative_to(vault_videos_path)}: 파일 읽기 오류 - {e}")
                invalid_videos += 1
    
    # 결과 요약
    click.echo("\n" + "=" * 50)
    click.echo("📋 검증 결과 요약")
    click.echo("=" * 50)
    click.echo(f"✅ 유효한 영상: {valid_videos}개")
    click.echo(f"⚠️  오류 영상: {invalid_videos}개") 
    click.echo(f"🎬 비디오 파일 누락: {missing_files}개")
    click.echo(f"📝 YAML 오류: {yaml_errors}개")
    
    success_rate = (valid_videos / total_videos * 100) if total_videos > 0 else 0
    click.echo(f"📊 성공률: {success_rate:.1f}%")
    
    if success_rate >= 95:
        click.echo("🎉 데이터 정합성 검사 통과!")
    elif success_rate >= 80:
        click.echo("⚠️  일부 문제가 있지만 대체로 양호합니다.")
    else:
        click.echo("❌ 심각한 데이터 정합성 문제가 발견되었습니다.")


@main.command()
@click.argument('video_path', type=click.Path(exists=True))
@click.option('--quality', default='480p', type=click.Choice(['480p', '720p', '1080p', 'keep']),
              help='변환할 화질 (기본: 480p)')
@click.option('--codec', default='h264', type=click.Choice(['h264', 'h265']),
              help='변환할 코덱 (기본: h264)')
@click.option('--backup/--no-backup', default=True, help='원본 파일 백업 여부')
@click.option('--progress/--no-progress', default=True, help='진행률 표시 여부')
@click.option('--force', is_flag=True, help='코덱 확인 없이 강제 변환')
def convert_single(video_path: str, quality: str, codec: str, backup: bool, progress: bool, force: bool) -> None:
    """단일 비디오 파일을 AV1에서 H.264/H.265로 변환합니다."""
    video_file = Path(video_path)
    
    if not video_file.exists():
        logger.error(f"비디오 파일을 찾을 수 없습니다: {video_file}")
        sys.exit(1)
    
    # 코덱 확인 (강제 모드가 아닌 경우)
    if not force:
        try:
            codec_info = _get_video_codec(video_file)
            logger.info(f"현재 코덱: {codec_info}")
            
            if 'av01' not in codec_info.lower() and 'av1' not in codec_info.lower():
                logger.info("AV1 코덱이 아닙니다. 변환을 건너뜁니다.")
                logger.info("강제 변환하려면 --force 옵션을 사용하세요.")
                return
                
        except Exception as e:
            logger.warning(f"코덱 확인 실패: {e}")
            logger.info("코덱 확인에 실패했지만 변환을 계속 진행합니다.")
    
    # 변환 수행
    logger.info(f"🔄 비디오 변환 시작: {video_file.name}")
    quality_desc = "원본 해상도 유지" if quality == "keep" else f"{quality} 해상도로 변경"
    logger.info(f"📊 설정: {quality_desc}, {codec} 코덱")
    
    try:
        success = _convert_video_file(video_file, quality, codec, backup, progress)
        if success:
            logger.info("✅ 변환 완료!")
        else:
            logger.error("❌ 변환 실패")
            sys.exit(1)
    except Exception as e:
        logger.error(f"변환 중 오류 발생: {e}")
        sys.exit(1)


@main.command()
def test_ffmpeg() -> None:
    """FFmpeg 설치 및 기본 기능을 테스트합니다."""
    logger.info("🔧 FFmpeg 테스트 시작")
    
    # FFmpeg 설치 확인
    if not _check_ffmpeg_installation():
        sys.exit(1)
    
    # 지원되는 인코더 확인
    try:
        result = subprocess.run(['ffmpeg', '-encoders'], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            encoders = result.stdout
            h264_found = 'libx264' in encoders
            h265_found = 'libx265' in encoders
            
            logger.info(f"✅ H.264 인코더 (libx264): {'지원됨' if h264_found else '지원되지 않음'}")
            logger.info(f"✅ H.265 인코더 (libx265): {'지원됨' if h265_found else '지원되지 않음'}")
            
            if not h264_found:
                logger.warning("⚠️ libx264 인코더가 없습니다. FFmpeg를 다시 설치해보세요.")
        else:
            logger.error("❌ FFmpeg 인코더 목록 조회 실패")
    except Exception as e:
        logger.error(f"❌ FFmpeg 인코더 확인 중 오류: {e}")
    
    logger.info("✅ FFmpeg 테스트 완료")


def _get_video_codec(video_file: Path) -> str:
    """FFprobe를 사용하여 비디오 코덱 정보를 가져옵니다."""
    cmd = [
        'ffprobe', '-v', 'quiet', '-print_format', 'json',
        '-show_streams', '-select_streams', 'v:0', str(video_file)
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise Exception(f"FFprobe 실행 실패: {result.stderr}")
    
    data = json.loads(result.stdout)
    if not data.get('streams'):
        raise Exception("비디오 스트림을 찾을 수 없습니다")
    
    codec_name = data['streams'][0].get('codec_name', 'unknown')
    return codec_name


def _detect_hardware_acceleration() -> str:
    """사용 가능한 하드웨어 가속을 감지합니다."""
    try:
        result = subprocess.run(['ffmpeg', '-hide_banner', '-encoders'], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            return 'software'
            
        encoders = result.stdout
        
        # macOS에서는 VideoToolbox 하드웨어 가속 확인
        if 'h264_videotoolbox' in encoders:
            return 'videotoolbox'
        # Intel Quick Sync Video 확인
        elif 'h264_qsv' in encoders:
            return 'qsv'
        # Linux VAAPI 확인  
        elif 'h264_vaapi' in encoders:
            return 'vaapi'
        else:
            return 'software'
    except Exception as e:
        logger.debug(f"하드웨어 가속 감지 실패: {e}")
        return 'software'


def _check_ffmpeg_installation() -> bool:
    """FFmpeg 설치 여부를 확인합니다."""
    try:
        result = subprocess.run(['ffmpeg', '-version'], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            version_line = result.stdout.split('\n')[0]
            logger.info(f"✅ FFmpeg 발견: {version_line}")
            return True
        else:
            logger.error("❌ FFmpeg 실행 실패")
            return False
    except FileNotFoundError:
        logger.error("❌ FFmpeg를 찾을 수 없습니다. FFmpeg를 설치해주세요.")
        logger.error("설치 방법:")
        logger.error("  macOS: brew install ffmpeg")
        logger.error("  Ubuntu: sudo apt install ffmpeg")
        logger.error("  Windows: https://ffmpeg.org/download.html")
        return False
    except subprocess.TimeoutExpired:
        logger.error("❌ FFmpeg 버전 확인 시간 초과")
        return False
    except Exception as e:
        logger.error(f"❌ FFmpeg 확인 중 오류: {e}")
        return False


def _convert_video_file(video_file: Path, quality: str, codec: str, backup: bool, progress: bool) -> bool:
    """실제 비디오 변환을 수행합니다."""
    output_file = video_file.with_suffix('.converted.mp4')
    backup_file = video_file.with_suffix('.av1.backup') if backup else None
    
    # FFmpeg 설치 확인
    if not _check_ffmpeg_installation():
        return False
    
    # 변환 시작 전 원본 백업 (backup 옵션이 활성화된 경우)
    if backup and backup_file:
        try:
            # 기존 백업 파일이 있으면 삭제
            if backup_file.exists():
                backup_file.unlink()
                logger.info(f"🗑️ 기존 백업 파일 삭제: {backup_file.name}")
            
            # 원본을 백업으로 복사
            import shutil
            shutil.copy2(video_file, backup_file)
            logger.info(f"💾 원본 백업 생성: {backup_file.name}")
        except Exception as e:
            logger.error(f"❌ 백업 생성 실패: {e}")
            return False
    
    try:
        # 하드웨어 가속 감지
        hw_accel = _detect_hardware_acceleration()
        logger.info(f"🚀 하드웨어 가속: {hw_accel}")
        
        # FFmpeg 명령어 구성
        cmd = ['ffmpeg', '-y', '-i', str(video_file)]
        
        # 비디오 코덱 설정
        if codec == 'h264':
            if hw_accel == 'videotoolbox':
                cmd.extend(['-c:v', 'h264_videotoolbox'])
                cmd.extend(['-b:v', '2M'])  # VideoToolbox는 bitrate 사용
            elif hw_accel == 'qsv':
                cmd.extend(['-c:v', 'h264_qsv'])
                cmd.extend(['-q', '23'])
            elif hw_accel == 'vaapi':
                cmd.extend(['-vaapi_device', '/dev/dri/renderD128'])
                cmd.extend(['-c:v', 'h264_vaapi'])
                cmd.extend(['-qp', '23'])
            else:
                cmd.extend(['-c:v', 'libx264'])
                cmd.extend(['-crf', '23'])
                cmd.extend(['-preset', 'medium'])
        elif codec == 'h265':
            if hw_accel == 'videotoolbox':
                cmd.extend(['-c:v', 'hevc_videotoolbox'])
                cmd.extend(['-b:v', '2M'])
            elif hw_accel == 'qsv':
                cmd.extend(['-c:v', 'hevc_qsv'])
                cmd.extend(['-q', '23'])
            elif hw_accel == 'vaapi':
                cmd.extend(['-vaapi_device', '/dev/dri/renderD128'])
                cmd.extend(['-c:v', 'hevc_vaapi'])
                cmd.extend(['-qp', '23'])
            else:
                cmd.extend(['-c:v', 'libx265'])
                cmd.extend(['-crf', '23'])
                cmd.extend(['-preset', 'medium'])
        
        # 화질 설정
        if quality == '480p':
            cmd.extend(['-vf', 'scale=854:480'])
        elif quality == '720p':
            cmd.extend(['-vf', 'scale=1280:720'])
        elif quality == '1080p':
            cmd.extend(['-vf', 'scale=1920:1080'])
        # 'keep'이면 해상도 변경 없음
        
        # 오디오 복사 (재인코딩 없음)
        cmd.extend(['-c:a', 'copy'])
        
        # 호환성을 위한 픽셀 포맷
        cmd.extend(['-pix_fmt', 'yuv420p'])
        
        cmd.append(str(output_file))
        
        logger.info(f"🔧 실행 명령어: {' '.join(cmd)}")
        
        # 변환 실행
        if progress:
            # 진행률 표시와 함께 실행
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, 
                                     stderr=subprocess.PIPE, text=True)
            
            stderr_output = []
            while True:
                output = process.stderr.readline()
                if output == '' and process.poll() is not None:
                    break
                if output:
                    stderr_output.append(output.strip())
                    if 'time=' in output or 'frame=' in output:
                        # 간단한 진행률 표시
                        if 'time=' in output:
                            time_part = output.split('time=')[1].split(' ')[0]
                            logger.info(f"⏱️  변환 진행: {time_part}")
                    elif 'error' in output.lower() or 'failed' in output.lower():
                        logger.error(f"FFmpeg 에러: {output.strip()}")
            
            rc = process.poll()
            
            if rc != 0:
                logger.error("FFmpeg 변환 실패")
                logger.error("FFmpeg stderr 출력:")
                for line in stderr_output[-10:]:  # 마지막 10줄만 표시
                    logger.error(f"  {line}")
                
                # 변환 실패 시 복구 처리
                _handle_conversion_failure(output_file, backup_file, video_file)
                return False
        else:
            # 진행률 없이 실행
            result = subprocess.run(cmd, capture_output=True, text=True)
            rc = result.returncode
            
            if rc != 0:
                logger.error("FFmpeg 변환 실패")
                logger.error(f"FFmpeg stdout: {result.stdout}")
                logger.error(f"FFmpeg stderr: {result.stderr}")
                
                # 변환 실패 시 복구 처리
                _handle_conversion_failure(output_file, backup_file, video_file)
                return False
        
        # 변환 성공 시 파일 교체
        output_file.rename(video_file)
        logger.info(f"✅ 변환 완료: {video_file.name}")
        
        # 성공 시 백업 파일 삭제 (원본은 이미 변환된 파일로 교체됨)
        if backup and backup_file and backup_file.exists():
            backup_file.unlink()
            logger.info(f"🗑️ 백업 파일 삭제: {backup_file.name}")
        
        return True
        
    except Exception as e:
        logger.error(f"변환 중 오류: {e}")
        # 예외 발생 시에도 복구 처리
        _handle_conversion_failure(output_file, backup_file, video_file)
        return False


def _handle_conversion_failure(output_file: Path, backup_file: Path, video_file: Path) -> None:
    """변환 실패 시 복구 처리를 수행합니다."""
    try:
        # converted 파일이 있으면 삭제
        if output_file.exists():
            output_file.unlink()
            logger.info(f"🗑️ 변환 실패 파일 삭제: {output_file.name}")
        
        # 백업 파일이 있으면 원본으로 복구
        if backup_file and backup_file.exists():
            # 원본 파일이 손상되었을 가능성에 대비하여 백업에서 복구
            if not video_file.exists():
                backup_file.rename(video_file)
                logger.info(f"🔄 백업에서 원본 복구: {video_file.name}")
            else:
                # 원본이 여전히 존재하면 백업만 삭제
                backup_file.unlink()
                logger.info(f"🗑️ 백업 파일 정리: {backup_file.name}")
        
        logger.info("✅ 변환 실패 후 정리 완료")
        
    except Exception as e:
        logger.error(f"❌ 복구 처리 중 오류: {e}")


@main.command()
def cleanup_backups() -> None:
    """Vault에서 AV1 백업 파일들을 정리하여 디스크 공간을 절약합니다."""
    vault_path = settings.vault_root / "10_videos"
    
    if not vault_path.exists():
        logger.error(f"Vault 경로를 찾을 수 없습니다: {vault_path}")
        return
    
    backup_files = []
    total_size = 0
    
    # 백업 파일 검색
    for backup_file in vault_path.rglob("*.av1.backup"):
        size = backup_file.stat().st_size
        backup_files.append((backup_file, size))
        total_size += size
    
    if not backup_files:
        logger.info("✅ 정리할 백업 파일이 없습니다.")
        return
    
    # 발견된 백업 파일 정보 표시
    logger.info(f"🔍 발견된 백업 파일: {len(backup_files)}개")
    logger.info(f"💾 총 크기: {total_size / (1024*1024):.1f} MB")
    
    # 사용자 확인
    if not click.confirm(f"\n{len(backup_files)}개의 백업 파일 ({total_size / (1024*1024):.1f} MB)을 삭제하시겠습니까?"):
        logger.info("❌ 작업이 취소되었습니다.")
        return
    
    # 백업 파일 삭제
    deleted_count = 0
    freed_space = 0
    
    for backup_file, size in backup_files:
        try:
            backup_file.unlink()
            deleted_count += 1
            freed_space += size
            logger.info(f"🗑️  삭제: {backup_file.name} ({size / (1024*1024):.1f} MB)")
        except Exception as e:
            logger.error(f"❌ 삭제 실패: {backup_file.name} - {e}")
    
    logger.info(f"✅ 정리 완료!")
    logger.info(f"📁 삭제된 파일: {deleted_count}개")
    logger.info(f"💾 확보된 공간: {freed_space / (1024*1024):.1f} MB")


# ========================== 세션 관리 명령어 ==========================


# 세션 관리 명령어
@main.command('list-sessions')
@click.option('--limit', default=20, help='표시할 세션 수 (기본값: 20)')
@click.option('--channel', help='특정 채널의 세션만 필터링')
def list_sessions(limit: int, channel: Optional[str]) -> None:
    """
    저장된 검색 세션 목록 표시
    
    예시:
    python -m ydh list-sessions
    python -m ydh list-sessions --limit 10 --channel "채널명"
    """
    try:
        from vault.indices_90.session_manager import SearchSessionManager
        
        session_manager = SearchSessionManager()
        sessions = session_manager.list_sessions(limit=limit, channel_filter=channel)
        
        if not sessions:
            click.echo("📑 저장된 세션이 없습니다")
            return
            
        click.echo(f"📚 검색 세션 목록 ({len(sessions)}개)")
        click.echo("=" * 60)
        
        for session in sessions:
            click.echo(f"🔍 {session['search_id']}")
            click.echo(f"   질문: {session['query']}")
            click.echo(f"   시간: {session['timestamp']}")
            if session.get('channel_filter'):
                click.echo(f"   채널: {session['channel_filter']}")
            click.echo(f"   결과: {len(session['results'])}개")
            click.echo()
            
    except Exception as e:
        click.echo(f"❌ 에러 발생: {e}")
        raise click.ClickException(str(e))


@main.command('delete-session')
@click.argument('session_id')
@click.option('--confirm', is_flag=True, help='확인 없이 바로 삭제')
def delete_session(session_id: str, confirm: bool) -> None:
    """
    특정 검색 세션 삭제
    
    예시:
    python -m ydh delete-session search_20231220_143052_abc123
    python -m ydh delete-session search_20231220_143052_abc123 --confirm
    """
    try:
        from vault.indices_90.session_manager import SearchSessionManager
        
        session_manager = SearchSessionManager()
        
        # 세션 존재 확인
        session = session_manager.get_session(session_id)
        if not session:
            click.echo(f"❌ 세션을 찾을 수 없습니다: {session_id}")
            return
            
        # 삭제 확인
        if not confirm:
            click.echo(f"🗑️ 삭제할 세션 정보:")
            click.echo(f"   ID: {session['search_id']}")
            click.echo(f"   질문: {session['query']}")
            click.echo(f"   시간: {session['timestamp']}")
            click.confirm('정말로 삭제하시겠습니까?', abort=True)
            
        # 삭제 실행
        session_manager.delete_session(session_id)
        click.echo(f"✅ 세션 삭제 완료: {session_id}")
        
    except Exception as e:
        click.echo(f"❌ 에러 발생: {e}")
        raise click.ClickException(str(e))


@main.command('export-session')
@click.argument('session_id')
@click.option('--format', default='html', type=click.Choice(['html', 'json', 'txt']), help='출력 형식')
@click.option('--output', help='출력 파일 경로 (기본값: 자동 생성)')
def export_session(session_id: str, format: str, output: Optional[str]) -> None:
    """
    검색 세션을 파일로 내보내기
    
    예시:
    python -m ydh export-session search_20231220_143052_abc123 --format html
    python -m ydh export-session search_20231220_143052_abc123 --format json --output result.json
    """
    try:
        from vault.indices_90.session_manager import SearchSessionManager
        
        session_manager = SearchSessionManager()
        
        # 세션 존재 확인
        session = session_manager.get_session(session_id)
        if not session:
            click.echo(f"❌ 세션을 찾을 수 없습니다: {session_id}")
            return
            
        # 출력 파일 경로 생성
        if not output:
            timestamp = session['timestamp'].replace(':', '-').replace(' ', '_')
            output = f"session_{timestamp}_{session_id[:8]}.{format}"
            
        # 내보내기 실행
        exported_path = session_manager.export_session(session_id, output_path=output, format=format)
        
        click.echo(f"📄 세션 내보내기 완료: {exported_path}")
        
    except Exception as e:
        click.echo(f"❌ 에러 발생: {e}")
        raise click.ClickException(str(e))


@main.command('clean-sessions')
@click.option('--days', default=30, help='보관할 일수 (기본값: 30일)')
@click.option('--confirm', is_flag=True, help='확인 없이 바로 삭제')
def clean_sessions(days: int, confirm: bool) -> None:
    """
    오래된 검색 세션 정리
    
    예시:
    python -m ydh clean-sessions --days 7
    python -m ydh clean-sessions --days 30 --confirm
    """
    try:
        from vault.indices_90.session_manager import SearchSessionManager
        
        session_manager = SearchSessionManager()
        
        # 삭제할 세션 목록 확인
        old_sessions = session_manager.get_old_sessions(days=days)
        
        if not old_sessions:
            click.echo(f"🧹 {days}일 이전 세션이 없습니다")
            return
            
        click.echo(f"🗑️ {days}일 이전 세션 {len(old_sessions)}개 발견")
        
        if not confirm:
            click.echo("삭제할 세션들:")
            for session in old_sessions[:5]:  # 최대 5개만 표시
                click.echo(f"  - {session['search_id']}: {session['query'][:50]}...")
            if len(old_sessions) > 5:
                click.echo(f"  ... 외 {len(old_sessions) - 5}개")
            click.confirm('정말로 삭제하시겠습니까?', abort=True)
            
        # 삭제 실행
        deleted_count = session_manager.clean_old_sessions(days=days)
        click.echo(f"✅ {deleted_count}개 세션 정리 완료")
        
    except Exception as e:
        click.echo(f"❌ 에러 발생: {e}")
        raise click.ClickException(str(e))





if __name__ == '__main__':
    main() 