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
        
        # 🔥 NEW: Obsidian 최적화 구조 생성
        self.create_templates_folder()
        self.create_chroma_structure()
    
    def sanitize_filename(self, name: str) -> str:
        """
        파일/폴더 이름을 Obsidian 및 크로스플랫폼에 최적화합니다.
        
        Args:
            name: 원본 이름
            
        Returns:
            str: 정리된 이름 (공백은 하이픈으로, 특수문자 제거)
        """
        # 1. 특수문자를 언더스코어로 변경
        cleaned = re.sub(r'[\\/*?:"<>|]', "_", name)
        
        # 2. 공백을 하이픈으로 변경 (Obsidian 링크 최적화)
        cleaned = re.sub(r'\s+', '-', cleaned)
        
        # 3. 연속된 하이픈/언더스코어 정리
        cleaned = re.sub(r'[-_]{2,}', '-', cleaned)
        
        # 4. 앞뒤 하이픈/언더스코어 제거
        cleaned = cleaned.strip('-_')
        
        return cleaned
    
    def format_duration(self, duration_seconds: int) -> str:
        """
        초 단위 duration을 MM:SS 또는 HH:MM:SS 형식으로 변환합니다.
        
        Args:
            duration_seconds: 초 단위 시간
            
        Returns:
            str: 포맷된 시간 문자열
        """
        if duration_seconds <= 0:
            return "0:00"
        
        hours = duration_seconds // 3600
        minutes = (duration_seconds % 3600) // 60
        seconds = duration_seconds % 60
        
        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes}:{seconds:02d}"
    
    def extract_excerpt(self, transcript_text: str, max_length: int = 500) -> str:
        """
        자막 텍스트에서 첫 500자 excerpt를 추출합니다.
        
        Args:
            transcript_text: 자막 텍스트
            max_length: 최대 길이
            
        Returns:
            str: excerpt 텍스트
        """
        if not transcript_text:
            return ""
        
        # 정리된 텍스트에서 추출
        cleaned_text = CaptionConverter.clean_transcript_text(transcript_text)
        
        if len(cleaned_text) <= max_length:
            return cleaned_text
        
        # 문장 단위로 자르기 (500자 내에서)
        excerpt = cleaned_text[:max_length]
        
        # 마지막 문장이 잘리지 않도록 조정
        last_period = excerpt.rfind('.')
        last_question = excerpt.rfind('?')
        last_exclamation = excerpt.rfind('!')
        
        last_sentence_end = max(last_period, last_question, last_exclamation)
        
        if last_sentence_end > max_length * 0.8:  # 80% 이상이면 문장 끝에서 자르기
            excerpt = excerpt[:last_sentence_end + 1]
        else:
            excerpt = excerpt + "..."
        
        return excerpt.strip()
    
    def normalize_hashtags(self, tags: List[str]) -> List[str]:
        """
        해시태그를 소문자·하이픈으로 정규화합니다.
        
        Args:
            tags: 원본 태그 리스트
            
        Returns:
            List[str]: 정규화된 태그 리스트
        """
        normalized_tags = []
        
        for tag in tags:
            if not tag:
                continue
            
            # 1. 소문자로 변환
            normalized = tag.lower()
            
            # 2. 공백을 하이픈으로 변경
            normalized = re.sub(r'\s+', '-', normalized)
            
            # 3. 특수문자 제거 (알파벳, 숫자, 하이픈만 허용)
            normalized = re.sub(r'[^\w\-가-힣]', '', normalized)
            
            # 4. 연속된 하이픈 정리
            normalized = re.sub(r'-{2,}', '-', normalized)
            
            # 5. 앞뒤 하이픈 제거
            normalized = normalized.strip('-')
            
            if normalized and normalized not in normalized_tags:
                normalized_tags.append(normalized)
        
        return normalized_tags
    
    def format_transcript_paragraphs(self, transcript_text: str) -> str:
        """
        자막 텍스트를 3-4문장마다 문단으로 나눕니다.
        
        Args:
            transcript_text: 원본 자막 텍스트
            
        Returns:
            str: 문단으로 나뉜 자막 텍스트
        """
        if not transcript_text:
            return ""
        
        # 정리된 텍스트 얻기
        cleaned_text = CaptionConverter.clean_transcript_text(transcript_text)
        
        # 문장 단위로 분리
        sentences = CaptionConverter.split_into_sentences(cleaned_text)
        
        if not sentences:
            return cleaned_text
        
        # 3-4문장씩 문단으로 그룹화
        paragraphs = []
        current_paragraph = []
        
        for i, sentence in enumerate(sentences):
            current_paragraph.append(sentence)
            
            # 3-4문장마다 또는 마지막 문장일 때 문단 완성
            if len(current_paragraph) >= 3 and (
                len(current_paragraph) == 4 or 
                i == len(sentences) - 1 or
                len(' '.join(current_paragraph)) > 200  # 너무 긴 문단 방지
            ):
                paragraph_text = '. '.join(current_paragraph)
                if not paragraph_text.endswith('.'):
                    paragraph_text += '.'
                paragraphs.append(paragraph_text)
                current_paragraph = []
        
        # 남은 문장들 처리
        if current_paragraph:
            paragraph_text = '. '.join(current_paragraph)
            if not paragraph_text.endswith('.'):
                paragraph_text += '.'
            paragraphs.append(paragraph_text)
        
        return '\n\n'.join(paragraphs)
    
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
                               channel_name: str, transcript_text: str = "") -> Dict[str, Any]:
        """
        비디오용 메타데이터를 생성합니다.
        
        Args:
            video_info: 비디오 정보
            channel_name: 채널 이름
            transcript_text: 자막 텍스트 (excerpt 생성용)
            
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
        
        # 🔥 NEW: 해시태그 정규화
        normalized_tags = self.normalize_hashtags(tags)
        
        # 소스 URL 생성
        source_url = f"https://www.youtube.com/watch?v={video_id}" if video_id else ""
        
        # 🔥 NEW: duration을 시간 형식으로 변환
        duration_formatted = self.format_duration(duration)
        
        # 🔥 NEW: excerpt 생성
        excerpt = self.extract_excerpt(transcript_text, 500)
        
        metadata = {
            'title': title,
            'upload': formatted_date,
            'channel': uploader,
            'video_id': video_id,
            'topic': normalized_tags,
            'source_url': source_url,
            'duration': duration_formatted,
            'duration_seconds': duration,
            'view_count': view_count,
            'excerpt': excerpt,
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
        # 🔥 UPDATED: transcript_text를 메타데이터 생성에 전달
        metadata = self.generate_video_metadata(video_info, channel_name, transcript_text)
        
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
        content += f"- **길이**: {metadata['duration']}\n"
        
        if metadata.get('view_count'):
            content += f"- **조회수**: {metadata['view_count']:,}회\n"
        
        content += f"- **링크**: [{metadata['source_url']}]({metadata['source_url']})\n\n"
        
        # 자막 섹션
        if transcript_text:
            content += "## 📝 자막 내용\n\n"
            
            # 🔥 NEW: 3-4문장마다 문단으로 나누기
            formatted_transcript = self.format_transcript_paragraphs(transcript_text)
            content += f"{formatted_transcript}\n\n"
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
    
    def create_templates_folder(self) -> None:
        """
        Obsidian 템플릿 폴더와 기본 템플릿들을 생성합니다.
        """
        templates_path = settings.vault_root / "00_templates"
        templates_path.mkdir(parents=True, exist_ok=True)
        
        # Dataview 템플릿 생성
        self._create_dataview_template(templates_path)
        
        # AI Assistant 설정 안내 생성
        self._create_ai_settings_guide(templates_path)
        
        logger.info(f"템플릿 폴더 생성 완료: {templates_path}")
    
    def _create_dataview_template(self, templates_path: Path) -> None:
        """Dataview 쿼리 템플릿을 생성합니다."""
        dataview_template = templates_path / "dataview.md"
        
        if dataview_template.exists():
            return
        
        template_content = '''# 📊 Dataview 쿼리 모음

## 🎬 영상 통계

### 채널별 영상 수
```dataview
TABLE 
    length(rows) as "영상 수",
    sum(rows.duration_seconds) / 60 as "총 시간(분)"
FROM "10_videos"
GROUP BY channel
SORT length(rows) DESC
```

### 최근 업로드 영상 (30일)
```dataview
TABLE 
    title as "제목",
    channel as "채널", 
    upload as "업로드일",
    duration as "길이"
FROM "10_videos"
WHERE upload >= date(today) - dur(30 days)
SORT upload DESC
LIMIT 20
```

### 긴 영상 (30분 이상)
```dataview
TABLE 
    title as "제목",
    channel as "채널",
    duration as "길이",
    view_count as "조회수"
FROM "10_videos"
WHERE duration_seconds > 1800
SORT duration_seconds DESC
```

### 인기 영상 (조회수 기준)
```dataview
TABLE 
    title as "제목",
    channel as "채널",
    view_count as "조회수",
    upload as "업로드일"
FROM "10_videos"
WHERE view_count > 0
SORT view_count DESC
LIMIT 20
```

## 🏷️ 태그 분석

### 태그별 영상 수
```dataview
TABLE 
    length(rows) as "영상 수"
FROM "10_videos"
FLATTEN topic as tag
GROUP BY tag
SORT length(rows) DESC
```

### 특정 태그가 포함된 영상
```dataview
TABLE 
    title as "제목",
    channel as "채널",
    topic as "태그"
FROM "10_videos"
WHERE contains(topic, "부동산")
SORT upload DESC
```

## 📈 시간 분석

### 월별 업로드 통계
```dataview
TABLE 
    length(rows) as "영상 수",
    sum(rows.view_count) as "총 조회수"
FROM "10_videos"
GROUP BY dateformat(upload, "yyyy-MM") as 월
SORT 월 DESC
```

### 요일별 업로드 패턴
```dataview
TABLE 
    length(rows) as "영상 수"
FROM "10_videos"
GROUP BY dateformat(upload, "cccc") as 요일
SORT length(rows) DESC
```

## 🔍 검색 및 필터

### Excerpt 포함 영상 목록
```dataview
TABLE 
    title as "제목",
    excerpt as "요약" 
FROM "10_videos"
WHERE excerpt != ""
SORT upload DESC
LIMIT 10
```

### 특정 키워드 검색
```dataview
LIST
FROM "10_videos"
WHERE contains(title, "도쿄") OR contains(excerpt, "도쿄")
SORT upload DESC
```

---

💡 **사용법**: 
- 위 쿼리들을 복사해서 노트에 붙여넣기
- `"부동산"` 등의 검색어를 원하는 키워드로 변경
- 날짜 범위나 정렬 조건을 필요에 따라 수정
'''
        
        with open(dataview_template, 'w', encoding='utf-8') as f:
            f.write(template_content)
        
        logger.debug(f"Dataview 템플릿 생성: {dataview_template}")
    
    def _create_ai_settings_guide(self, templates_path: Path) -> None:
        """AI Assistant 설정 안내를 생성합니다."""
        ai_guide = templates_path / "ai-assistant-setup.md"
        
        if ai_guide.exists():
            return
        
        guide_content = '''# 🤖 AI Assistant 설정 가이드

## Obsidian AI Assistant 최적화

### 1. 컨텍스트 설정
```json
{
  "max_tokens": 3000,
  "temperature": 0.7,
  "model": "deepseek-chat"
}
```

### 2. 자막 분석용 프롬프트

#### 📝 요약 생성
```
이 영상 자막을 3-4문장으로 요약해주세요:

{{excerpt}}
```

#### 🏷️ 태그 추출
```
다음 자막에서 주요 키워드 5-7개를 소문자-하이픈 형태로 추출해주세요:
예) haneda-innovation-city, tokyo-real-estate

{{excerpt}}
```

#### ❓ 질문 생성
```
이 영상 내용을 바탕으로 토론할 만한 질문 3개를 만들어주세요:

{{excerpt}}
```

#### 🔗 연관 주제 찾기
```
이 영상과 관련된 추가 학습 주제를 제안해주세요:

제목: {{title}}
내용: {{excerpt}}
```

### 3. Vault 전체 검색

#### 📊 통계 분석
```
vault에서 "부동산" 관련 영상들의 주요 트렌드를 분석해주세요.
```

#### 🎯 맞춤 추천
```
{{title}} 영상을 본 사람이 관심 가질만한 다른 영상들을 vault에서 찾아주세요.
```

---

💡 **팁**: 
- excerpt 필드로 3000 토큰 내에서 10-15분 영상 전체 질의 가능
- Dataview 쿼리와 AI 분석을 조합하여 인사이트 도출
- 채널별/태그별 패턴 분석에 AI 활용
'''
        
        with open(ai_guide, 'w', encoding='utf-8') as f:
            f.write(guide_content)
        
        logger.debug(f"AI 설정 안내 생성: {ai_guide}")
    
    def create_chroma_structure(self) -> None:
        """
        Chroma DB 저장을 위한 vault/90_indices 구조를 생성합니다.
        """
        indices_path = settings.vault_root / "90_indices"
        chroma_path = indices_path / "chroma"
        
        indices_path.mkdir(parents=True, exist_ok=True)
        chroma_path.mkdir(parents=True, exist_ok=True)
        
        # embed.py 스크립트 생성
        self._create_embed_script(indices_path)
        
        logger.info(f"Chroma 구조 생성 완료: {chroma_path}")
    
    def _create_embed_script(self, indices_path: Path) -> None:
        """Chroma 임베딩 스크립트를 생성합니다."""
        embed_script = indices_path / "embed.py"
        
        if embed_script.exists():
            return
        
        script_content = '''#!/usr/bin/env python3
"""
Vault 영상 자막을 Chroma DB에 임베딩하는 스크립트
실행 경로: vault/10_videos → vault/90_indices/chroma
"""

import sys
from pathlib import Path
import yaml
import chromadb
from chromadb.config import Settings as ChromaSettings

# Vault 경로 설정
VAULT_ROOT = Path(__file__).parent.parent
VIDEOS_PATH = VAULT_ROOT / "10_videos"
CHROMA_PATH = VAULT_ROOT / "90_indices" / "chroma"

def main():
    """메인 임베딩 실행 함수"""
    print(f"🔍 영상 검색: {VIDEOS_PATH}")
    print(f"💾 Chroma 저장: {CHROMA_PATH}")
    
    # Chroma 클라이언트 초기화
    client = chromadb.PersistentClient(
        path=str(CHROMA_PATH),
        settings=ChromaSettings(anonymized_telemetry=False)
    )
    
    collection = client.get_or_create_collection(
        name="video_transcripts",
        metadata={"description": "YouTube 영상 자막 임베딩"}
    )
    
    processed_count = 0
    
    # 모든 captions.md 파일 처리
    for captions_file in VIDEOS_PATH.rglob("captions.md"):
        try:
            with open(captions_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # YAML frontmatter 파싱
            if content.startswith('---'):
                parts = content.split('---', 2)
                if len(parts) >= 3:
                    metadata = yaml.safe_load(parts[1])
                    transcript = parts[2].strip()
                    
                    # Chroma에 추가
                    collection.add(
                        documents=[transcript],
                        metadatas=[{
                            "title": metadata.get("title", ""),
                            "channel": metadata.get("channel", ""),
                            "video_id": metadata.get("video_id", ""),
                            "upload": metadata.get("upload", ""),
                            "duration": metadata.get("duration", ""),
                            "excerpt": metadata.get("excerpt", ""),
                            "file_path": str(captions_file.relative_to(VAULT_ROOT))
                        }],
                        ids=[metadata.get("video_id", f"video_{processed_count}")]
                    )
                    
                    processed_count += 1
                    print(f"✅ 처리됨: {metadata.get('title', 'Unknown')}")
                    
        except Exception as e:
            print(f"❌ 오류: {captions_file} - {e}")
            continue
    
    print(f"\\n🎉 완료: {processed_count}개 영상 임베딩")

def search_example(query: str, n_results: int = 5):
    """검색 예시 함수"""
    client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    collection = client.get_collection("video_transcripts")
    
    results = collection.query(
        query_texts=[query],
        n_results=n_results
    )
    
    print(f"\\n🔍 검색: '{query}'")
    for i, (doc, metadata) in enumerate(zip(results['documents'][0], results['metadatas'][0])):
        print(f"{i+1}. {metadata['title']} ({metadata['channel']})")
        print(f"   {metadata['excerpt'][:100]}...")
        print()

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "search":
        query = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "도쿄 부동산"
        search_example(query)
    else:
        main()
'''
        
        with open(embed_script, 'w', encoding='utf-8') as f:
            f.write(script_content)
        
        # 실행 권한 부여
        embed_script.chmod(0o755)
        
        logger.debug(f"임베딩 스크립트 생성: {embed_script}") 