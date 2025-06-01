"""
Markdown generation with YAML frontmatter for Obsidian vault.
"""

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

from .config import settings
from .converter import CaptionConverter

logger = logging.getLogger(__name__)


class VaultWriter:
    """Obsidian Vault용 마크다운 노트 생성 클래스."""
    
    def __init__(self):
        """VaultWriter 초기화."""
        # Vault 구조 확인/생성
        settings.ensure_vault_structure()
    
    def sanitize_filename(self, name: str) -> str:
        """
        파일/폴더 이름에 사용할 수 없는 문자를 '_'로 대체합니다.
        
        Args:
            name: 원본 이름
            
        Returns:
            str: 정리된 이름
        """
        return re.sub(r'[\\/*?:"<>|]', "_", name)
    
    def extract_channel_name_from_url(self, channel_url: str) -> str:
        """
        채널 URL에서 채널 이름을 추출합니다.
        
        Args:
            channel_url: YouTube 채널 URL
            
        Returns:
            str: 채널 이름
        """
        try:
            # URL에서 채널 이름 추출 시도
            if "@" in channel_url:
                # @채널명 형태
                channel_name = channel_url.split("@")[-1].split("/")[0]
                # URL 디코딩
                import urllib.parse
                channel_name = urllib.parse.unquote(channel_name)
                return channel_name
            elif "/channel/" in channel_url:
                # /channel/ID 형태에서는 ID를 반환
                return channel_url.split("/channel/")[-1].split("/")[0]
            elif "/c/" in channel_url:
                # /c/채널명 형태
                return channel_url.split("/c/")[-1].split("/")[0]
            else:
                # 기본값
                return "Unknown_Channel"
        except Exception as e:
            logger.warning(f"채널 이름 추출 실패: {e}")
            return "Unknown_Channel"
    
    def create_video_vault_path(self, video_info: Dict[str, Any], 
                               channel_name: str) -> Path:
        """
        비디오용 Vault 경로를 생성합니다.
        
        Args:
            video_info: 비디오 정보
            channel_name: 채널 이름
            
        Returns:
            Path: Vault 내 비디오 폴더 경로
        """
        title = video_info.get('title', '제목 없음')
        upload_date = video_info.get('upload_date', '')
        
        # 날짜 형식 변환 (YYYYMMDD -> YYYY)
        year = upload_date[:4] if upload_date else "Unknown"
        
        # 제목 정리
        safe_title = self.sanitize_filename(title)
        if len(safe_title) > 50:
            safe_title = safe_title[:50]
        
        # 폴더명 형식: YYYYMMDD_제목
        folder_name = f"{upload_date}_{safe_title}"
        
        # 채널 이름도 정리
        safe_channel_name = self.sanitize_filename(channel_name)
        
        # Vault 경로: vault/10_videos/채널명/연도/날짜_제목/
        vault_path = settings.get_video_folder_path(safe_channel_name, year, folder_name)
        vault_path.mkdir(parents=True, exist_ok=True)
        
        return vault_path
    
    def generate_video_metadata(self, video_info: Dict[str, Any], 
                               channel_name: str) -> Dict[str, Any]:
        """
        비디오용 메타데이터를 생성합니다.
        
        Args:
            video_info: 비디오 정보
            channel_name: 채널 이름
            
        Returns:
            Dict[str, Any]: YAML frontmatter용 메타데이터
        """
        video_id = video_info.get('id', '')
        title = video_info.get('title', '제목 없음')
        upload_date = video_info.get('upload_date', '')
        description = video_info.get('description', '')
        duration = video_info.get('duration', 0)
        view_count = video_info.get('view_count', 0)
        uploader = video_info.get('uploader', channel_name)
        
        # 날짜 형식 변환 (YYYYMMDD -> YYYY-MM-DD)
        formatted_date = ""
        if upload_date and len(upload_date) >= 8:
            try:
                formatted_date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:8]}"
            except:
                formatted_date = upload_date
        
        # 기본 태그 생성
        tags = settings.get_channel_tags(channel_name) or []
        
        # 설명에서 추가 태그 추출 (해시태그)
        if description:
            hashtags = re.findall(r'#(\w+)', description)
            tags.extend(hashtags[:5])  # 최대 5개까지
        
        # 중복 제거
        tags = list(set(tags))
        
        # 소스 URL 생성
        source_url = f"https://www.youtube.com/watch?v={video_id}" if video_id else ""
        
        metadata = {
            'title': title,
            'upload': formatted_date,
            'channel': uploader,
            'video_id': video_id,
            'topic': tags,
            'source_url': source_url,
            'duration_seconds': duration,
            'view_count': view_count,
            'created_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
        
        return metadata
    
    def create_markdown_content(self, video_info: Dict[str, Any], 
                               channel_name: str, transcript_text: str = "") -> str:
        """
        마크다운 콘텐츠를 생성합니다.
        
        Args:
            video_info: 비디오 정보
            channel_name: 채널 이름
            transcript_text: 자막 텍스트
            
        Returns:
            str: 완성된 마크다운 콘텐츠
        """
        metadata = self.generate_video_metadata(video_info, channel_name)
        
        # YAML frontmatter 생성
        yaml_content = "---\n"
        for key, value in metadata.items():
            if isinstance(value, list):
                if value:  # 리스트가 비어있지 않은 경우만
                    yaml_content += f"{key}: {value}\n"
                else:
                    yaml_content += f"{key}: []\n"
            elif isinstance(value, str):
                # 특수 문자가 있는 경우 따옴표로 감싸기
                if any(char in value for char in ['"', "'", ':', '#', '[', ']']):
                    yaml_content += f'{key}: "{value.replace('"', '\\"')}"\n'
                else:
                    yaml_content += f"{key}: {value}\n"
            else:
                yaml_content += f"{key}: {value}\n"
        yaml_content += "---\n\n"
        
        # 본문 콘텐츠 생성
        content = yaml_content
        
        # 비디오 정보 섹션
        content += "## 📹 비디오 정보\n\n"
        content += f"- **제목**: {metadata['title']}\n"
        content += f"- **채널**: {metadata['channel']}\n"
        content += f"- **업로드**: {metadata['upload']}\n"
        
        if metadata.get('duration_seconds'):
            minutes = metadata['duration_seconds'] // 60
            seconds = metadata['duration_seconds'] % 60
            content += f"- **길이**: {minutes}분 {seconds}초\n"
        
        if metadata.get('view_count'):
            content += f"- **조회수**: {metadata['view_count']:,}회\n"
        
        content += f"- **링크**: [{metadata['source_url']}]({metadata['source_url']})\n\n"
        
        # 자막 섹션
        if transcript_text:
            content += "## 📝 자막 내용\n\n"
            
            # 자막 텍스트 정리
            cleaned_transcript = CaptionConverter.clean_transcript_text(transcript_text)
            
            # 문장 단위로 분리하여 가독성 향상
            sentences = CaptionConverter.split_into_sentences(cleaned_transcript)
            
            if sentences:
                # 문장을 문단으로 그룹화 (5문장씩)
                for i in range(0, len(sentences), 5):
                    paragraph = ". ".join(sentences[i:i+5])
                    if paragraph:
                        content += f"{paragraph}.\n\n"
            else:
                # 문장 분리가 안 된 경우 원본 사용
                content += f"{cleaned_transcript}\n\n"
        else:
            content += "## 📝 자막 내용\n\n"
            content += "*자막을 사용할 수 없습니다.*\n\n"
        
        # 태그 섹션
        if metadata.get('topic'):
            content += "## 🏷️ 태그\n\n"
            for tag in metadata['topic']:
                content += f"#{tag} "
            content += "\n\n"
        
        # 노트 섹션 (사용자가 추가할 수 있는 공간)
        content += "## 💭 노트\n\n"
        content += "*여기에 개인적인 생각이나 메모를 추가하세요.*\n\n"
        
        return content
    
    def save_video_to_vault(self, video_info: Dict[str, Any], 
                           channel_name: str, transcript_text: str = "",
                           source_video_path: Optional[Path] = None,
                           source_caption_path: Optional[Path] = None) -> bool:
        """
        비디오를 Vault에 저장합니다.
        
        Args:
            video_info: 비디오 정보
            channel_name: 채널 이름  
            transcript_text: 자막 텍스트
            source_video_path: 원본 비디오 파일 경로
            source_caption_path: 원본 자막 파일 경로
            
        Returns:
            bool: 저장 성공 여부
        """
        try:
            # Vault 경로 생성
            vault_path = self.create_video_vault_path(video_info, channel_name)
            
            # 파일명 정리
            title = video_info.get('title', '제목 없음')
            safe_title = self.sanitize_filename(title)
            
            # 마크다운 파일 경로
            md_file_path = vault_path / "captions.md"
            
            # 이미 존재하는지 확인
            if md_file_path.exists():
                logger.debug(f"이미 존재하는 마크다운 파일: {md_file_path}")
                return True
            
            # 마크다운 콘텐츠 생성
            markdown_content = self.create_markdown_content(
                video_info, channel_name, transcript_text
            )
            
            # 마크다운 파일 저장
            with open(md_file_path, 'w', encoding='utf-8') as f:
                f.write(markdown_content)
            
            logger.info(f"Vault 마크다운 생성: {md_file_path}")
            
            # 원본 비디오 파일이 있으면 복사/이동
            if source_video_path and source_video_path.exists():
                target_video_path = vault_path / "video.mp4"
                if not target_video_path.exists():
                    try:
                        # 파일 크기가 큰 경우를 대비해 이동 사용
                        import shutil
                        shutil.move(str(source_video_path), str(target_video_path))
                        logger.info(f"비디오 파일 이동: {target_video_path}")
                    except Exception as e:
                        logger.warning(f"비디오 파일 이동 실패: {e}")
            
            return True
            
        except Exception as e:
            logger.error(f"Vault 저장 중 오류 발생: {e}")
            return False
    
    def load_video_metadata(self, video_folder: Path) -> Dict[str, Any]:
        """
        비디오 폴더에서 메타데이터를 로드합니다.
        
        Args:
            video_folder: 비디오 폴더 경로
            
        Returns:
            Dict[str, Any]: 비디오 메타데이터
        """
        # 1. metadata.json 파일이 있는지 확인
        metadata_file = video_folder / 'metadata.json'
        if metadata_file.exists():
            try:
                import json
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"메타데이터 파일 읽기 실패: {e}")
        
        # 2. 폴더명에서 정보 추출 (fallback)
        return self._extract_metadata_from_folder_name(video_folder)
    
    def _extract_metadata_from_folder_name(self, video_folder: Path) -> Dict[str, Any]:
        """
        폴더명에서 메타데이터를 추출합니다 (fallback 방법).
        
        Args:
            video_folder: 비디오 폴더 경로
            
        Returns:
            Dict[str, Any]: 추출된 메타데이터
        """
        folder_name = video_folder.name
        
        # 폴더명 형식: YYYYMMDD_Title
        folder_parts = folder_name.split("_", 1)
        
        upload_date = ""
        title = "제목 없음"
        
        if len(folder_parts) >= 2:
            upload_date = folder_parts[0]
            title = folder_parts[1].replace("_", " ")
        elif len(folder_parts) == 1:
            # 날짜만 있는 경우 또는 제목만 있는 경우
            if folder_parts[0].isdigit() and len(folder_parts[0]) == 8:
                upload_date = folder_parts[0]
            else:
                title = folder_parts[0].replace("_", " ")
        
        # 🔥 NEW: 기존 파일에서 video_id 추출 시도
        video_id = self._extract_video_id_from_files(video_folder)
        
        return {
            'id': video_id,
            'title': title,
            'upload_date': upload_date,
            'uploader': '',
            'duration': 0,
            'view_count': 0,
            'description': '',
            'webpage_url': f"https://www.youtube.com/watch?v={video_id}" if video_id != 'unknown' else "",
            'channel_url': '',
            'channel_id': '',
            'tags': [],
            'categories': [],
            'thumbnail': '',
            'uploader_id': '',
        }
    
    def _extract_video_id_from_files(self, video_folder: Path) -> str:
        """
        비디오 폴더 내 파일들에서 video_id를 추출합니다.
        
        Args:
            video_folder: 비디오 폴더 경로
            
        Returns:
            str: 추출된 video_id 또는 'unknown'
        """
        # 1. VTT 파일명에서 추출 시도
        for vtt_file in video_folder.glob("*.vtt"):
            # 파일명 형식: title.ko.vtt 또는 title-videoID.ko.vtt
            if "-" in vtt_file.stem:
                parts = vtt_file.stem.split("-")
                for part in parts:
                    if len(part) == 11 and part.replace("-", "").replace("_", "").isalnum():
                        return part
        
        # 2. 자막 파일 내용에서 추출 시도
        txt_files = list(video_folder.glob("*.txt"))
        if txt_files:
            try:
                with open(txt_files[0], 'r', encoding='utf-8') as f:
                    content = f.read()
                    # "# Video ID: xxxxxxxx" 형식 찾기
                    import re
                    match = re.search(r'# Video ID:\s*([a-zA-Z0-9_-]{11})', content)
                    if match:
                        return match.group(1)
            except Exception:
                pass
        
        # 3. raw.md 파일에서 추출 시도
        raw_md_file = video_folder / 'raw.md'
        if raw_md_file.exists():
            try:
                with open(raw_md_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    # VTT 파일에서 URL 패턴 찾기
                    import re
                    # YouTube URL 패턴 매칭
                    url_match = re.search(r'youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})', content)
                    if url_match:
                        return url_match.group(1)
            except Exception:
                pass
        
        # 4. 파일명에서 YouTube ID 패턴 찾기 (11자리 영숫자)
        for file_path in video_folder.iterdir():
            if file_path.is_file():
                import re
                # 파일명에서 11자리 YouTube ID 패턴 찾기
                match = re.search(r'([a-zA-Z0-9_-]{11})', file_path.name)
                if match:
                    potential_id = match.group(1)
                    # YouTube ID 형식인지 검증 (보통 대소문자, 숫자, -, _ 포함)
                    if re.match(r'^[a-zA-Z0-9_-]{11}$', potential_id):
                        return potential_id
        
        return 'unknown'
    
    def batch_process_downloads(self, download_path: Path, 
                               channel_name: str = "") -> int:
        """
        다운로드 폴더의 모든 영상을 Vault로 처리합니다.
        
        Args:
            download_path: 다운로드 폴더 경로
            channel_name: 채널 이름
            
        Returns:
            int: 처리된 영상 수
        """
        processed_count = 0
        
        # 다운로드 폴더에서 영상별 폴더 찾기
        for video_folder in download_path.iterdir():
            if not video_folder.is_dir():
                continue
            
            try:
                # 🔥 UPDATED: 메타데이터 로드 (JSON 우선, 폴더명 fallback)
                video_info = self.load_video_metadata(video_folder)
                
                # 비디오 파일 찾기
                video_files = list(video_folder.glob("*.mp4"))
                if not video_files:
                    continue
                
                video_file = video_files[0]
                
                # 자막 파일 찾기
                transcript_text = ""
                txt_files = list(video_folder.glob("*.txt"))
                if txt_files:
                    try:
                        with open(txt_files[0], 'r', encoding='utf-8') as f:
                            content = f.read()
                            # 헤더 정보 제거하고 본문만 추출
                            lines = content.split('\n')
                            transcript_lines = []
                            for line in lines:
                                if not line.startswith('#'):
                                    transcript_lines.append(line)
                            transcript_text = '\n'.join(transcript_lines).strip()
                    except Exception as e:
                        logger.warning(f"자막 파일 읽기 실패: {e}")
                
                # 채널 이름 설정 (매개변수가 있으면 사용, 없으면 메타데이터에서)
                final_channel_name = channel_name or video_info.get('uploader', 'Unknown Channel')
                
                # Vault에 저장
                if self.save_video_to_vault(
                    video_info, final_channel_name, transcript_text, video_file
                ):
                    processed_count += 1
                    logger.info(f"Vault 처리 완료: {video_folder.name}")
                
            except Exception as e:
                logger.error(f"폴더 처리 중 오류: {video_folder} - {e}")
                continue
        
        logger.info(f"Vault 일괄 처리 완료: {processed_count}개 영상")
        return processed_count
    
    def cleanup_downloads_folder(self, download_path: Path) -> int:
        """
        vault로 이동 완료된 downloads 폴더를 정리합니다.
        
        Args:
            download_path: 다운로드 폴더 경로
            
        Returns:
            int: 정리된 폴더 수
        """
        cleaned_count = 0
        
        for video_folder in download_path.iterdir():
            if not video_folder.is_dir():
                continue
            
            try:
                # 해당 영상이 vault에 성공적으로 저장되었는지 확인
                folder_parts = video_folder.name.split("_", 1)
                if len(folder_parts) < 2:
                    continue
                
                upload_date, title_part = folder_parts
                
                # vault에서 해당 폴더 확인 (대략적으로)
                # 정확한 확인보다는 downloads 폴더 자체를 정리하는 것이 목적
                import shutil
                shutil.rmtree(video_folder)
                cleaned_count += 1
                logger.debug(f"downloads 폴더 정리: {video_folder.name}")
                
            except Exception as e:
                logger.warning(f"폴더 삭제 실패: {video_folder} - {e}")
                continue
        
        if cleaned_count > 0:
            logger.info(f"downloads 폴더 정리 완료: {cleaned_count}개 폴더 삭제")
        
        return cleaned_count 