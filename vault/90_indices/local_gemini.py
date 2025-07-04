#!/usr/bin/env python3
"""
로컬 Gemini 도구 인터페이스
Google Gemini API 대신 로컬 설치된 gemini 명령어를 사용
"""

import subprocess
import json
import logging
from typing import Optional, Dict, Any, Generator
from pathlib import Path

logger = logging.getLogger(__name__)

class LocalGeminiClient:
    """로컬 gemini 명령어를 사용하는 클라이언트"""
    
    def __init__(self, model: str = "gemini-2.5-pro"):
        self.model = model
        self.gemini_path = self._find_gemini_executable()
        
    def _find_gemini_executable(self) -> str:
        """gemini 실행 파일 경로 찾기"""
        try:
            result = subprocess.run(
                ["which", "gemini"], 
                capture_output=True, 
                text=True, 
                check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            raise RuntimeError("gemini 명령어를 찾을 수 없습니다. 설치되어 있는지 확인해주세요.")
    
    def generate_text(self, prompt: str, **kwargs) -> str:
        """텍스트 생성"""
        try:
            cmd = [self.gemini_path, "-m", self.model, "-p", prompt]
            
            # 추가 옵션 처리
            if kwargs.get("debug", False):
                cmd.extend(["-d"])
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                timeout=60  # 60초 타임아웃
            )
            
            return result.stdout.strip()
            
        except subprocess.TimeoutExpired:
            logger.error("Gemini 명령어 실행 시간 초과")
            raise RuntimeError("응답 생성 시간이 초과되었습니다.")
        except subprocess.CalledProcessError as e:
            logger.error(f"Gemini 명령어 실행 실패: {e}")
            raise RuntimeError(f"텍스트 생성 실패: {e}")
    
    def generate_content_stream(self, prompt: str, **kwargs) -> Generator[str, None, None]:
        """스트리밍 텍스트 생성 (로컬 gemini는 스트리밍 미지원이므로 전체 응답을 청크로 나누어 반환)"""
        try:
            response = self.generate_text(prompt, **kwargs)
            
            # 응답을 적당한 크기로 나누어 스트리밍 효과 구현
            words = response.split()
            chunk_size = 5  # 5단어씩 청크로 나누기
            
            for i in range(0, len(words), chunk_size):
                chunk = " ".join(words[i:i + chunk_size])
                if i + chunk_size < len(words):
                    chunk += " "
                yield chunk
                
        except Exception as e:
            logger.error(f"스트리밍 생성 실패: {e}")
            yield f"오류: {str(e)}"
    
    def generate_with_context(self, prompt: str, context: str, **kwargs) -> str:
        """컨텍스트와 함께 텍스트 생성"""
        combined_prompt = f"""다음 YouTube 영상 자막 내용을 참고하여 질문에 답변해주세요:

영상 자막 컨텍스트:
{context}

사용자 질문:
{prompt}

답변 규칙:
1. 한국어로 답변해주세요
2. 제공된 자막 내용을 바탕으로 구체적이고 정확한 답변 제공
3. 자막에 없는 내용은 "해당 정보가 영상에서 확인되지 않습니다"라고 말해주세요
4. 답변의 근거가 되는 영상 정보를 명시해주세요

답변:"""
        
        return self.generate_text(combined_prompt, **kwargs)
    
    def is_available(self) -> bool:
        """로컬 gemini 사용 가능 여부 확인"""
        try:
            result = subprocess.run(
                [self.gemini_path, "--version"],
                capture_output=True,
                text=True,
                check=True
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False


class LocalGeminiRAGInterface:
    """로컬 Gemini를 사용하는 RAG 인터페이스"""
    
    def __init__(self, model: str = "gemini-2.5-pro"):
        self.client = LocalGeminiClient(model)
        
    def query_with_context(self, query: str, context_chunks: list, **kwargs) -> str:
        """컨텍스트 청크들과 함께 질의"""
        # 컨텍스트 청크들을 하나의 문자열로 결합
        context = "\n\n".join([
            f"[문서 {i+1}]\n{chunk}" 
            for i, chunk in enumerate(context_chunks)
        ])
        
        return self.client.generate_with_context(query, context, **kwargs)
    
    def query_with_context_stream(self, query: str, context_chunks: list, **kwargs) -> Generator[str, None, None]:
        """컨텍스트 청크들과 함께 스트리밍 질의"""
        context = "\n\n".join([
            f"[문서 {i+1}]\n{chunk}" 
            for i, chunk in enumerate(context_chunks)
        ])
        
        combined_prompt = f"""다음 컨텍스트를 참고하여 질문에 답변해주세요:

컨텍스트:
{context}

질문:
{query}

답변:"""
        
        yield from self.client.generate_content_stream(combined_prompt, **kwargs)
    
    def rewrite_query(self, query: str, **kwargs) -> str:
        """질의 재작성"""
        rewrite_prompt = f"""다음 질문을 더 구체적이고 검색하기 좋은 형태로 재작성해주세요:

원본 질문: {query}

재작성된 질문:"""
        
        return self.client.generate_text(rewrite_prompt, **kwargs)
    
    def is_available(self) -> bool:
        """사용 가능 여부 확인"""
        return self.client.is_available()


def test_local_gemini():
    """로컬 gemini 테스트"""
    try:
        client = LocalGeminiClient()
        
        if not client.is_available():
            print("❌ 로컬 gemini를 사용할 수 없습니다.")
            return False
        
        print("✅ 로컬 gemini 사용 가능")
        
        # 간단한 테스트
        response = client.generate_text("안녕하세요!")
        print(f"테스트 응답: {response}")
        
        return True
        
    except Exception as e:
        print(f"❌ 테스트 실패: {e}")
        return False


if __name__ == "__main__":
    test_local_gemini()