"""
Y-Data-House: YouTube video downloader and Obsidian vault generator.
"""

__version__ = "0.1.0"
__author__ = "Y-Data-House"
__email__ = "admin@y-data-house.dev"

from .config import Settings
from .downloader import VideoDownloader
from .transcript import TranscriptExtractor
from .converter import CaptionConverter
from .vault_writer import VaultWriter

__all__ = [
    "Settings",
    "VideoDownloader", 
    "TranscriptExtractor",
    "CaptionConverter",
    "VaultWriter",
] 