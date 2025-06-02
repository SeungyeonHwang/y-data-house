"""
Click-based CLI interface.
"""

import logging
import sys
import time
from pathlib import Path
from typing import Optional, List

import click

from .config import settings
from .downloader import VideoDownloader
from .transcript import TranscriptExtractor
from .converter import CaptionConverter
from .vault_writer import VaultWriter

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
def batch(channels_file: str, vault_only: bool, no_vault: bool) -> None:
    """channels.txt 파일의 모든 채널을 처리합니다."""
    channels_path = Path(channels_file)
    
    # 채널 목록 로드
    channels = load_channel_list(channels_path)
    
    if not channels:
        logger.error("처리할 채널이 없습니다. channels.txt 파일을 확인하세요.")
        sys.exit(1)
    
    logger.info(f"총 {len(channels)}개 채널 처리 시작")
    
    total_stats = {
        "processed_channels": 0,
        "total_downloaded": 0,
        "total_failed": 0,
        "total_vault_processed": 0
    }
    
    start_time = time.time()
    
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
            stats = downloader.download_channel_videos(channel_url, channel_name)
            
            total_stats["processed_channels"] += 1
            total_stats["total_downloaded"] += stats.get("downloaded", 0)
            total_stats["total_failed"] += stats.get("failed", 0)
            
            # Vault 생성
            if not no_vault and stats.get("downloaded", 0) > 0:
                logger.info("다운로드된 영상을 Vault로 처리 중...")
                
                transcript_extractor = TranscriptExtractor()
                vault_processed = 0
                
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
                

                
                total_stats["total_vault_processed"] += vault_processed
                
                # vault 처리 완료 후 downloads 폴더 정리
                if vault_processed > 0:
                    cleaned_count = vault_writer.cleanup_downloads_folder(settings.download_path)
                    logger.info(f"downloads 폴더 정리: {cleaned_count}개 폴더 삭제")
            
            # 채널 간 지연
            time.sleep(1)
            
        except Exception as e:
            logger.error(f"채널 처리 중 오류 발생: {channel_url} - {e}")
            continue
    
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


@main.command()
@click.argument('channel_url')
@click.option('--channel-name', help='채널 이름 (자동 감지되지 않는 경우)')
@click.option('--vault-only', is_flag=True, help='다운로드 없이 Vault 생성만')
@click.option('--no-vault', is_flag=True, help='다운로드만 하고 Vault 생성 안함')
def ingest(channel_url: str, channel_name: Optional[str], 
           vault_only: bool, no_vault: bool) -> None:
    """개별 채널 URL에서 새 영상을 다운로드하고 Vault에 저장합니다."""
    logger.info(f"채널 인제스트 시작: {channel_url}")
    
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
        stats = downloader.download_channel_videos(channel_url, channel_name)
        
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


if __name__ == '__main__':
    main() 