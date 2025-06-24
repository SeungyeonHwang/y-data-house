"""
Configuration management using Pydantic BaseSettings.
"""

import os
from pathlib import Path
from typing import List, Optional, Dict, Any

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Y-Data-House 설정 클래스."""
    
    # 기본 경로 설정
    vault_root: Path = Field(default_factory=lambda: Path("./vault"))
    download_path: Path = Field(default_factory=lambda: Path("./vault/downloads"))
    
    # 언어 설정
    language: str = "ko"
    
    # 다운로드 옵션
    max_quality: str = Field(default="720p", env="YDH_VIDEO_QUALITY")
    max_downloads_per_run: int = 0  # 무제한으로 변경
    delete_vtt_after_conversion: bool = True
    detailed_debug: bool = False
    
    # 브라우저 쿠키 설정 (봇 감지 회피)
    browser: str = "chrome"
    use_browser_cookies: bool = True
    
    # User-Agent 설정 (실제 브라우저로 위장)
    user_agent: str = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    
    # 프록시 설정
    use_proxy: bool = False
    proxies: Dict[str, str] = Field(default_factory=lambda: {
        'http': 'socks5://127.0.0.1:9050',
        'https': 'socks5://127.0.0.1:9050'
    })
    
    # 자막 언어 우선순위
    subtitle_languages: List[str] = Field(default_factory=lambda: ['ko', 'ko-KR', 'ko_KR'])
    
    # Obsidian Vault 설정
    vault_videos_folder: str = "10_videos"
    
    # 채널별 기본 태그 매핑
    channel_tags: Dict[str, List[str]] = Field(default_factory=dict)
    
    # 로깅 설정
    log_level: str = "INFO"
    log_file: Optional[Path] = None  # 로그 파일 비활성화
    log_rotation: str = "daily"
    
    class Config:
        env_file = Path.home() / ".ydh.toml"
        env_file_encoding = "utf-8"
        env_prefix = "YDH_"
        case_sensitive = False
    
    def get_vault_videos_path(self) -> Path:
        """Vault 내 영상 저장 경로를 반환합니다."""
        return self.vault_root / self.vault_videos_folder
    
    def get_channel_folder_path(self, channel_name: str, year: str) -> Path:
        """채널별 연도 폴더 경로를 반환합니다."""
        return self.get_vault_videos_path() / channel_name / year
    
    def get_video_folder_path(self, channel_name: str, year: str, date_title: str) -> Path:
        """개별 영상 폴더 경로를 반환합니다."""
        return self.get_channel_folder_path(channel_name, year) / date_title
    
    def ensure_vault_structure(self) -> None:
        """Vault 디렉토리 구조를 생성합니다."""
        self.get_vault_videos_path().mkdir(parents=True, exist_ok=True)
    
    def get_channel_tags(self, channel_name: str) -> List[str]:
        """채널에 해당하는 기본 태그를 반환합니다."""
        return self.channel_tags.get(channel_name, [])


# 전역 설정 인스턴스
settings = Settings() 