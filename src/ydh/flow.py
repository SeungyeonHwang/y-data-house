"""
Prefect workflow orchestration.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Any

from prefect import flow, task
from prefect.tasks import task_input_hash
from datetime import timedelta

from .config import settings
from .downloader import VideoDownloader
from .transcript import TranscriptExtractor
from .converter import CaptionConverter
from .vault_writer import VaultWriter
from .progress import progress_tracker

logger = logging.getLogger(__name__)


@task(cache_key_fn=task_input_hash, cache_expiration=timedelta(hours=1))
def extract_channel_info(channel_url: str) -> Dict[str, Any]:
    """채널 정보를 추출합니다."""
    logger.info(f"채널 정보 추출 시작: {channel_url}")
    
    downloader = VideoDownloader()
    videos = downloader.get_channel_videos(channel_url)
    
    vault_writer = VaultWriter()
    channel_name = vault_writer.extract_channel_name_from_url(channel_url)
    
    return {
        "channel_url": channel_url,
        "channel_name": channel_name,
        "videos": videos,
        "video_count": len(videos)
    }


@task
def filter_new_videos(videos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """새 영상만 필터링합니다."""
    downloaded_videos = progress_tracker.get_downloaded_videos()
    new_videos = [v for v in videos if v.get('id') not in downloaded_videos]
    
    logger.info(f"새 영상 필터링: {len(new_videos)}개 (전체 {len(videos)}개 중)")
    return new_videos


@task
def download_videos(channel_url: str, channel_name: str) -> Dict[str, int]:
    """영상들을 다운로드합니다."""
    logger.info(f"영상 다운로드 시작: {channel_name}")
    
    downloader = VideoDownloader()
    stats = downloader.download_channel_videos(channel_url, channel_name)
    
    logger.info(f"다운로드 완료: {stats}")
    return stats


@task
def extract_transcripts(video_ids: List[str]) -> Dict[str, str]:
    """자막을 추출합니다."""
    logger.info(f"자막 추출 시작: {len(video_ids)}개 영상")
    
    extractor = TranscriptExtractor()
    transcripts = extractor.batch_extract_transcripts(video_ids)
    
    logger.info(f"자막 추출 완료: {len(transcripts)}개")
    return transcripts


@task
def convert_captions(download_path: Path) -> int:
    """자막 파일들을 변환합니다."""
    logger.info(f"자막 변환 시작: {download_path}")
    
    converted_count = CaptionConverter.batch_convert_directory(
        download_path, settings.delete_vtt_after_conversion
    )
    
    logger.info(f"자막 변환 완료: {converted_count}개")
    return converted_count


@task
def create_vault_notes(download_path: Path, channel_name: str) -> int:
    """Vault 노트들을 생성합니다."""
    logger.info(f"Vault 노트 생성 시작: {channel_name}")
    
    vault_writer = VaultWriter()
    processed_count = vault_writer.batch_process_downloads(download_path, channel_name)
    
    if processed_count > 0:
        # 채널 인덱스 생성
        vault_writer.create_channel_index(channel_name)
    
    logger.info(f"Vault 노트 생성 완료: {processed_count}개")
    return processed_count


@task
def cleanup_files() -> int:
    """불필요한 파일들을 정리합니다."""
    logger.info("파일 정리 시작")
    
    downloader = VideoDownloader()
    cleaned_count = downloader.cleanup_incomplete_downloads()
    
    logger.info(f"파일 정리 완료: {cleaned_count}개")
    return cleaned_count


@flow(name="channel-ingest")
def channel_ingest_flow(channel_url: str, 
                       vault_enabled: bool = True,
                       cleanup_enabled: bool = True) -> Dict[str, Any]:
    """
    채널 인제스트 워크플로우.
    
    Args:
        channel_url: YouTube 채널 URL
        vault_enabled: Vault 생성 여부
        cleanup_enabled: 파일 정리 여부
        
    Returns:
        Dict[str, Any]: 실행 결과
    """
    logger.info(f"채널 인제스트 워크플로우 시작: {channel_url}")
    
    # 1. 채널 정보 추출
    channel_info = extract_channel_info(channel_url)
    channel_name = channel_info["channel_name"]
    videos = channel_info["videos"]
    
    # 2. 새 영상 필터링
    new_videos = filter_new_videos(videos)
    
    if not new_videos:
        logger.info("다운로드할 새 영상이 없습니다.")
        return {
            "channel_name": channel_name,
            "total_videos": len(videos),
            "new_videos": 0,
            "downloaded": 0,
            "vault_processed": 0,
            "cleaned_files": 0
        }
    
    # 3. 영상 다운로드
    download_stats = download_videos(channel_url, channel_name)
    
    # 4. 자막 변환
    converted_count = 0
    if download_stats["downloaded"] > 0:
        converted_count = convert_captions(settings.download_path)
    
    # 5. Vault 노트 생성
    vault_processed = 0
    if vault_enabled and download_stats["downloaded"] > 0:
        vault_processed = create_vault_notes(settings.download_path, channel_name)
    
    # 6. 파일 정리
    cleaned_files = 0
    if cleanup_enabled:
        cleaned_files = cleanup_files()
    
    result = {
        "channel_name": channel_name,
        "total_videos": len(videos),
        "new_videos": len(new_videos),
        "downloaded": download_stats["downloaded"],
        "failed": download_stats["failed"],
        "converted_captions": converted_count,
        "vault_processed": vault_processed,
        "cleaned_files": cleaned_files
    }
    
    logger.info(f"채널 인제스트 워크플로우 완료: {result}")
    return result


@flow(name="batch-process")
def batch_process_flow(download_path: Path, 
                      channel_name: str,
                      convert_captions_enabled: bool = True,
                      vault_enabled: bool = True) -> Dict[str, Any]:
    """
    일괄 처리 워크플로우.
    
    Args:
        download_path: 다운로드 폴더 경로
        channel_name: 채널 이름
        convert_captions_enabled: 자막 변환 여부
        vault_enabled: Vault 생성 여부
        
    Returns:
        Dict[str, Any]: 실행 결과
    """
    logger.info(f"일괄 처리 워크플로우 시작: {download_path} -> {channel_name}")
    
    # 1. 자막 변환
    converted_count = 0
    if convert_captions_enabled:
        converted_count = convert_captions(download_path)
    
    # 2. Vault 노트 생성
    vault_processed = 0
    if vault_enabled:
        vault_processed = create_vault_notes(download_path, channel_name)
    
    # 3. 파일 정리
    cleaned_files = cleanup_files()
    
    result = {
        "channel_name": channel_name,
        "converted_captions": converted_count,
        "vault_processed": vault_processed,
        "cleaned_files": cleaned_files
    }
    
    logger.info(f"일괄 처리 워크플로우 완료: {result}")
    return result


@flow(name="maintenance")
def maintenance_flow(retry_failed: bool = True,
                    cleanup_files_enabled: bool = True) -> Dict[str, Any]:
    """
    유지보수 워크플로우.
    
    Args:
        retry_failed: 실패한 다운로드 재시도 여부
        cleanup_files_enabled: 파일 정리 여부
        
    Returns:
        Dict[str, Any]: 실행 결과
    """
    logger.info("유지보수 워크플로우 시작")
    
    # 1. 실패한 다운로드 재시도
    retry_stats = {"total": 0, "downloaded": 0, "failed": 0}
    if retry_failed:
        downloader = VideoDownloader()
        retry_stats = downloader.retry_failed_downloads()
    
    # 2. 파일 정리
    cleaned_files = 0
    if cleanup_files_enabled:
        cleaned_files = cleanup_files()
    
    result = {
        "retry_total": retry_stats["total"],
        "retry_success": retry_stats["downloaded"],
        "retry_failed": retry_stats["failed"],
        "cleaned_files": cleaned_files
    }
    
    logger.info(f"유지보수 워크플로우 완료: {result}")
    return result


# 스케줄링된 플로우들
@flow(name="daily-maintenance")
def daily_maintenance_flow():
    """일일 유지보수 플로우."""
    return maintenance_flow(retry_failed=True, cleanup_files_enabled=True)


@flow(name="weekly-cleanup")
def weekly_cleanup_flow():
    """주간 정리 플로우."""
    # 더 강력한 정리 작업
    result = maintenance_flow(retry_failed=False, cleanup_files_enabled=True)
    
    # 진행 상황 통계 로깅
    stats = progress_tracker.get_overall_stats()
    logger.info(f"주간 통계 - 다운로드: {stats['total_downloaded']}, "
               f"실패: {stats['total_failed']}, 자막: {stats['total_transcripts']}")
    
    return result


# 유틸리티 함수들
def run_channel_ingest(channel_url: str, **kwargs) -> Dict[str, Any]:
    """채널 인제스트를 실행합니다."""
    return channel_ingest_flow(channel_url, **kwargs)


def run_batch_process(download_path: str, channel_name: str, **kwargs) -> Dict[str, Any]:
    """일괄 처리를 실행합니다."""
    return batch_process_flow(Path(download_path), channel_name, **kwargs)


def run_maintenance(**kwargs) -> Dict[str, Any]:
    """유지보수를 실행합니다."""
    return maintenance_flow(**kwargs)


if __name__ == "__main__":
    # 예시 실행
    import sys
    
    if len(sys.argv) > 1:
        channel_url = sys.argv[1]
        result = run_channel_ingest(channel_url)
        print(f"실행 결과: {result}")
    else:
        print("사용법: python -m ydh.flow <채널URL>")
        print("또는:")
        print("from ydh.flow import run_channel_ingest")
        print("result = run_channel_ingest('https://www.youtube.com/@channel')") 