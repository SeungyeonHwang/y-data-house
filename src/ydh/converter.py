"""
VTT/SRT to clean text conversion.
"""

import re
import logging
from pathlib import Path
from typing import Optional, List

logger = logging.getLogger(__name__)


class CaptionConverter:
    """자막 파일을 텍스트로 변환하는 클래스."""
    
    @staticmethod
    def extract_text_from_vtt(vtt_file_path: Path) -> str:
        """
        VTT 파일에서 순수한 텍스트만 추출합니다.
        연속된 동일한 텍스트는 중복 제거합니다.
        
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
            previous_text = ""  # 이전 텍스트 저장
            
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
                
                # 3. 정리된 텍스트가 있으면 중복 확인 후 추가
                if clean_line.strip():
                    current_text = clean_line.strip()
                    
                    # 이전 텍스트와 동일하면 건너뛰기 (중복 제거)
                    if current_text != previous_text:
                        extracted_text.append(current_text)
                        previous_text = current_text
            
            # 모든 텍스트 합치기
            result = ' '.join(extracted_text)
            logger.debug(f"VTT 텍스트 추출 완료: {len(result)} 글자")
            return result
        
        except Exception as e:
            logger.error(f"VTT 파일 처리 중 오류 발생: {e}")
            return ""
    
    @staticmethod
    def extract_text_from_srt(srt_file_path: Path) -> str:
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
            result = " ".join(text_parts)
            logger.debug(f"SRT 텍스트 추출 완료: {len(result)} 글자")
            return result
        except Exception as e:
            logger.error(f"SRT 파일 처리 중 오류 발생: {e}")
            return ""
    
    @staticmethod
    def clean_transcript_text(text: str) -> str:
        """
        자막 텍스트를 정리합니다.
        
        Args:
            text: 원본 자막 텍스트
            
        Returns:
            str: 정리된 텍스트
        """
        if not text:
            return ""
        
        # 1. 불필요한 공백 정리
        text = re.sub(r'\s+', ' ', text)
        
        # 2. 특수 문자 정리 (일부 자막에서 나타나는 제어 문자들)
        text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', text)
        
        # 3. 중복된 문장 부호 정리
        text = re.sub(r'([.!?])\1+', r'\1', text)
        
        # 4. 괄호 안의 음향 효과나 설명 제거 ([음악], [박수소리] 등)
        text = re.sub(r'\[[^\]]*\]', '', text)
        text = re.sub(r'\([^)]*음[^)]*\)', '', text)  # (배경음악), (음성) 등
        
        # 5. 화자 표시 제거 (- 화자:, >> 등)
        text = re.sub(r'^[->]\s*[^:]*:\s*', '', text, flags=re.MULTILINE)
        
        # 6. 중복된 구문 제거 (YouTube 자동생성 자막의 특성)
        text = CaptionConverter._remove_duplicate_phrases(text)
        
        # 7. 앞뒤 공백 제거
        text = text.strip()
        
        return text
    
    @staticmethod
    def _remove_duplicate_phrases(text: str) -> str:
        """
        텍스트에서 연속으로 반복되는 구문을 제거합니다.
        YouTube 자동생성 자막의 VTT 타임스탬프로 인한 중복을 특히 처리합니다.
        
        Args:
            text: 입력 텍스트
            
        Returns:
            str: 중복 제거된 텍스트
        """
        if not text or len(text.split()) < 3:
            return text
        
        # 1단계: 연속된 동일 단어/구문 제거
        words = text.split()
        result_words = []
        i = 0
        
        while i < len(words):
            current_word = words[i]
            
            # 연속으로 같은 단어가 3번 이상 반복되는 경우
            consecutive_count = 1
            j = i + 1
            while j < len(words) and words[j] == current_word:
                consecutive_count += 1
                j += 1
            
            # 3번 이상 반복되면 1번만 남기기
            if consecutive_count >= 3:
                result_words.append(current_word)
                i = j
                continue
            
            # 패턴 기반 중복 제거 (2-8 단어 길이)
            pattern_found = False
            for pattern_length in range(2, min(9, len(words) - i + 1)):
                if i + pattern_length * 2 > len(words):
                    continue
                
                pattern = words[i:i + pattern_length]
                
                # 패턴이 2-3번 연속 반복되는지 확인
                repeat_count = 1
                pos = i + pattern_length
                
                while pos + pattern_length <= len(words):
                    next_segment = words[pos:pos + pattern_length]
                    if pattern == next_segment:
                        repeat_count += 1
                        pos += pattern_length
                    else:
                        break
                
                # 2번 이상 반복되면 1번만 남기기
                if repeat_count >= 2:
                    result_words.extend(pattern)
                    i = pos
                    pattern_found = True
                    break
            
            if not pattern_found:
                result_words.append(current_word)
                i += 1
        
        # 2단계: 문장 내 중복 구문 추가 정리
        text = " ".join(result_words)
        
        # 3단계: 특정 패턴 정리 (YouTube 자막 특성)
        # "A B A B A B" 형태의 교차 반복 제거
        words = text.split()
        final_words = []
        i = 0
        
        while i < len(words):
            if i + 5 < len(words):  # 최소 6단어 필요
                # A B A B A B 패턴 확인
                word1, word2 = words[i], words[i+1]
                if (words[i+2] == word1 and words[i+3] == word2 and 
                    words[i+4] == word1 and words[i+5] == word2):
                    # 패턴 발견시 A B 한 번만 남기기
                    final_words.extend([word1, word2])
                    i += 6
                    continue
            
            final_words.append(words[i])
            i += 1
        
        return " ".join(final_words)
    
    @staticmethod
    def split_into_sentences(text: str) -> List[str]:
        """
        텍스트를 문장 단위로 분리합니다.
        
        Args:
            text: 입력 텍스트
            
        Returns:
            List[str]: 문장 목록
        """
        if not text:
            return []
        
        # 한국어 문장 분리 패턴
        sentence_endings = r'[.!?]+'
        sentences = re.split(sentence_endings, text)
        
        # 빈 문장 제거 및 공백 정리
        sentences = [s.strip() for s in sentences if s.strip()]
        
        return sentences
    
    @staticmethod
    def convert_caption_file(input_file: Path, output_file: Path, 
                           video_id: str = "", title: str = "") -> bool:
        """
        자막 파일을 텍스트 파일로 변환합니다.
        
        Args:
            input_file: 입력 자막 파일 (VTT 또는 SRT)
            output_file: 출력 텍스트 파일
            video_id: 비디오 ID
            title: 비디오 제목
            
        Returns:
            bool: 변환 성공 여부
        """
        try:
            # 파일 확장자에 따라 변환 방법 결정
            if input_file.suffix.lower() == '.vtt':
                extracted_text = CaptionConverter.extract_text_from_vtt(input_file)
            elif input_file.suffix.lower() == '.srt':
                extracted_text = CaptionConverter.extract_text_from_srt(input_file)
            else:
                logger.error(f"지원하지 않는 자막 파일 형식: {input_file.suffix}")
                return False
            
            if not extracted_text:
                logger.warning(f"자막 파일에서 텍스트를 추출할 수 없음: {input_file}")
                return False
            
            # 텍스트 정리
            cleaned_text = CaptionConverter.clean_transcript_text(extracted_text)
            
            # 출력 파일 작성
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_file, 'w', encoding='utf-8') as f:
                # 메타데이터 헤더 작성
                if video_id:
                    f.write(f"# Video ID: {video_id}\n")
                if title:
                    f.write(f"# Title: {title}\n")
                if video_id or title:
                    f.write("\n")
                
                # 정리된 텍스트 작성
                f.write(cleaned_text)
            
            logger.info(f"자막 변환 완료: {input_file} -> {output_file}")
            return True
            
        except Exception as e:
            logger.error(f"자막 파일 변환 중 오류: {e}")
            return False
    
    @staticmethod
    def batch_convert_directory(directory: Path, delete_originals: bool = False) -> int:
        """
        디렉토리 내의 모든 자막 파일을 변환합니다.
        
        Args:
            directory: 변환할 디렉토리
            delete_originals: 원본 파일 삭제 여부
            
        Returns:
            int: 변환된 파일 수
        """
        converted_count = 0
        
        # VTT 파일 변환
        for vtt_file in directory.rglob("*.vtt"):
            if ".ko." in vtt_file.name or ".ko-" in vtt_file.name:
                output_file = vtt_file.with_suffix('.txt')
                
                if CaptionConverter.convert_caption_file(vtt_file, output_file):
                    converted_count += 1
                    
                    if delete_originals:
                        try:
                            vtt_file.unlink()
                            logger.debug(f"원본 VTT 파일 삭제: {vtt_file}")
                        except Exception as e:
                            logger.warning(f"VTT 파일 삭제 실패: {e}")
        
        # SRT 파일 변환
        for srt_file in directory.rglob("*.srt"):
            if ".ko." in srt_file.name or ".ko-" in srt_file.name:
                output_file = srt_file.with_suffix('.txt')
                
                if CaptionConverter.convert_caption_file(srt_file, output_file):
                    converted_count += 1
                    
                    if delete_originals:
                        try:
                            srt_file.unlink()
                            logger.debug(f"원본 SRT 파일 삭제: {srt_file}")
                        except Exception as e:
                            logger.warning(f"SRT 파일 삭제 실패: {e}")
        
        logger.info(f"일괄 변환 완료: {converted_count}개 파일")
        return converted_count 