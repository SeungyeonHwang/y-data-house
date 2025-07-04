#!/usr/bin/env python3
"""
Gemini 기반 RAG (Retrieval-Augmented Generation) 시스템
채널별로 완전 격리된 벡터 검색 + 질의응답 시스템

주요 기능:
1. 채널별 격리된 RAG 시스템 (각 채널마다 독립된 컬렉션)
2. 채널별 최적화된 프롬프트 자동 적용
3. 고급 질의 재작성 (HyDE 기법)
4. 스트리밍 답변 생성
5. 세션 기반 대화 기록 관리
"""

import os
import sys
from pathlib import Path
import chromadb
from chromadb.config import Settings as ChromaSettings
from local_gemini import LocalGeminiRAGInterface
from dotenv import load_dotenv
import argparse
import json
from typing import List, Dict, Optional, Any, Generator
import logging
from datetime import datetime
import re
from search_gemini import GeminiSearchEngine
from session_manager import SearchSessionManager, save_search_to_session
from prompt_manager import PromptManager

# 환경변수 로드
load_dotenv()

# 경로 설정
VAULT_ROOT = Path(__file__).parent.parent
CHROMA_GEMINI_PATH = VAULT_ROOT / "90_indices" / "chroma_gemini"

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class GeminiRAGSystem:
    """Gemini 기반 채널별 격리 RAG 시스템"""
    
    def __init__(self, channel_name: Optional[str] = None):
        self.channel_name = channel_name
        self.search_engine = None
        self.session_manager = SearchSessionManager()
        self.prompt_manager = PromptManager()
        
        self._setup_gemini_api()
        self._setup_search_engine()
        self._load_channel_prompt()
    
    def _setup_gemini_api(self):
        """로컬 Gemini 설정"""
        try:
            self.model = LocalGeminiRAGInterface()
            if not self.model.is_available():
                raise RuntimeError("로컬 gemini 명령어를 사용할 수 없습니다.")
            logger.info("✅ 로컬 Gemini 설정 완료")
        except Exception as e:
            logger.error(f"❌ 로컬 Gemini 설정 실패: {e}")
            raise
    
    def _setup_search_engine(self):
        """벡터 검색 엔진 초기화"""
        try:
            self.search_engine = GeminiSearchEngine()
            logger.info("✅ Gemini 검색 엔진 초기화 완료")
        except Exception as e:
            logger.error(f"❌ 검색 엔진 초기화 실패: {e}")
            raise
    
    def _load_channel_prompt(self):
        """채널별 최적화 프롬프트 로드"""
        if self.channel_name:
            try:
                prompt_data = self.prompt_manager.get_channel_prompt(self.channel_name)
                self.system_prompt = prompt_data.get('system_prompt', self._get_default_system_prompt())
                self.persona = prompt_data.get('persona', '전문 분석가')
                self.tone = prompt_data.get('tone', '친근하고 전문적인')
                logger.info(f"✅ '{self.channel_name}' 채널 프롬프트 로드 완료")
                logger.info(f"🎭 페르소나: {self.persona}")
            except Exception as e:
                logger.warning(f"⚠️ 채널 프롬프트 로드 실패, 기본 프롬프트 사용: {e}")
                self.system_prompt = self._get_default_system_prompt()
                self.persona = '전문 분석가'
                self.tone = '친근하고 전문적인'
        else:
            self.system_prompt = self._get_default_system_prompt()
            self.persona = '전문 분석가'
            self.tone = '친근하고 전문적인'
    
    def _get_default_system_prompt(self) -> str:
        """기본 시스템 프롬프트"""
        return """당신은 YouTube 비디오 콘텐츠를 분석하는 전문 AI 어시스턴트입니다.
제공된 영상 자막과 메타데이터를 바탕으로 정확하고 상세한 답변을 제공해주세요.

응답 규칙:
1. 한국어로 답변해주세요
2. 구체적인 예시와 함께 설명해주세요
3. 자막에 없는 내용은 "해당 정보가 영상에서 확인되지 않습니다"라고 말해주세요
4. 답변의 근거가 되는 영상 제목과 업로드 날짜를 명시해주세요
5. 여러 영상에서 정보를 종합할 때는 각각의 출처를 구분해서 설명해주세요"""
    
    def enhance_query(self, query: str) -> str:
        """HyDE 기법을 활용한 질의 개선"""
        enhancement_prompt = f"""
사용자 질문: "{query}"

이 질문에 대한 이상적인 답변에 포함될 만한 핵심 키워드와 개념들을 추출해주세요.
YouTube 영상 자막에서 찾을 수 있는 구체적인 용어들을 포함해서 검색에 최적화된 키워드를 생성해주세요.

키워드만 간단히 나열해주세요 (쉼표로 구분):
"""
        
        try:
            enhanced_keywords = self.model.client.generate_text(enhancement_prompt).strip()
            
            # 원본 질문과 키워드를 결합
            enhanced_query = f"{query} {enhanced_keywords}"
            logger.info(f"🔍 질의 개선: {query} → {enhanced_keywords}")
            return enhanced_query
            
        except Exception as e:
            logger.warning(f"⚠️ 질의 개선 실패, 원본 사용: {e}")
            return query
    
    def retrieve_context(self, query: str, n_results: int = 5) -> List[Dict[str, Any]]:
        """벡터 검색으로 관련 컨텍스트 검색"""
        try:
            # 질의 개선
            enhanced_query = self.enhance_query(query)
            
            # 벡터 검색 실행
            search_results = self.search_engine.search(
                query=enhanced_query,
                n_results=n_results,
                channel_filter=self.channel_name,
                save_to_session=False  # RAG에서는 별도 세션 관리
            )
            
            logger.info(f"📊 검색 결과: {len(search_results)}개 문서 발견")
            return search_results
            
        except Exception as e:
            logger.error(f"❌ 컨텍스트 검색 실패: {e}")
            return []
    
    def format_context(self, search_results: List[Dict[str, Any]]) -> str:
        """검색 결과를 컨텍스트 문자열로 포맷팅"""
        if not search_results:
            return "관련 영상 자막을 찾을 수 없습니다."
        
        context_parts = []
        for i, result in enumerate(search_results, 1):
            title = result.get('title', '제목 없음')
            upload_date = result.get('upload_date', '날짜 없음')
            content = result.get('content', '내용 없음')
            similarity = result.get('similarity', 0)
            
            context_part = f"""
[영상 {i}]
제목: {title}
업로드: {upload_date}
유사도: {similarity:.3f}
내용: {content}
"""
            context_parts.append(context_part)
        
        return "\n".join(context_parts)
    
    def generate_answer(self, query: str, context: str) -> str:
        """컨텍스트를 기반으로 답변 생성"""
        rag_prompt = f"""
{self.system_prompt}

당신의 역할: {self.persona}
답변 스타일: {self.tone}

제공된 컨텍스트:
{context}

사용자 질문: {query}

위의 영상 자막 내용을 바탕으로 질문에 답변해주세요. 
답변 시 반드시 관련 영상의 제목과 업로드 날짜를 출처로 명시해주세요.
"""
        
        try:
            answer = self.model.query_with_context(query, [context]).strip()
            logger.info("✅ RAG 답변 생성 완료")
            return answer
            
        except Exception as e:
            logger.error(f"❌ 답변 생성 실패: {e}")
            return f"죄송합니다. 답변 생성 중 오류가 발생했습니다: {e}"
    
    def generate_streaming_answer(self, query: str, context: str) -> Generator[str, None, None]:
        """스트리밍 방식으로 답변 생성"""
        rag_prompt = f"""
{self.system_prompt}

당신의 역할: {self.persona}
답변 스타일: {self.tone}

제공된 컨텍스트:
{context}

사용자 질문: {query}

위의 영상 자막 내용을 바탕으로 질문에 답변해주세요. 
답변 시 반드시 관련 영상의 제목과 업로드 날짜를 출처로 명시해주세요.
"""
        
        try:
            for chunk in self.model.query_with_context_stream(query, [context]):
                yield chunk
                    
        except Exception as e:
            logger.error(f"❌ 스트리밍 답변 생성 실패: {e}")
            yield f"죄송합니다. 답변 생성 중 오류가 발생했습니다: {e}"
    
    def query(self, 
              question: str, 
              stream: bool = False,
              n_results: int = 5,
              save_session: bool = True) -> str:
        """RAG 질의응답 메인 함수"""
        
        logger.info(f"🤖 Gemini RAG 질의 시작: '{question}'")
        if self.channel_name:
            logger.info(f"📺 대상 채널: {self.channel_name}")
        
        # 1. 벡터 검색으로 관련 컨텍스트 검색
        search_results = self.retrieve_context(question, n_results)
        
        if not search_results:
            no_context_answer = f"죄송합니다. '{question}'에 대한 관련 영상을 찾을 수 없습니다."
            if self.channel_name:
                no_context_answer += f"\n\n'{self.channel_name}' 채널에 해당 주제의 영상이 없을 수 있습니다."
            return no_context_answer
        
        # 2. 컨텍스트 포맷팅
        context = self.format_context(search_results)
        
        # 3. 답변 생성
        if stream:
            # 스트리밍 답변
            full_answer = ""
            print("🤖 답변 생성 중...\n")
            
            for chunk in self.generate_streaming_answer(question, context):
                print(chunk, end='', flush=True)
                full_answer += chunk
            
            print("\n")  # 마지막 줄바꿈
            answer = full_answer
        else:
            # 일반 답변
            answer = self.generate_answer(question, context)
        
        # 4. 세션 저장
        if save_session:
            try:
                # RAG 결과를 세션에 저장
                rag_entry = save_search_to_session(
                    query=question,
                    results=search_results,
                    channel_filter=self.channel_name,
                    answer=answer,
                    rag_mode=True
                )
                logger.info(f"💾 RAG 세션 저장 완료: {rag_entry['search_id']}")
            except Exception as e:
                logger.warning(f"⚠️ RAG 세션 저장 실패: {e}")
        
        return answer
    
    def list_available_channels(self) -> List[str]:
        """RAG 가능한 채널 목록 조회"""
        if self.search_engine:
            return self.search_engine.list_available_channels()
        return []
    
    def get_channel_stats(self) -> Dict[str, Any]:
        """현재 채널의 통계 정보"""
        if not self.channel_name or not self.search_engine:
            return {}
        
        try:
            stats = self.search_engine.get_channel_statistics(self.channel_name)
            return stats
        except Exception as e:
            logger.error(f"❌ 채널 통계 조회 실패: {e}")
            return {}

def create_rag_system(channel_name: Optional[str] = None) -> GeminiRAGSystem:
    """RAG 시스템 인스턴스 생성"""
    try:
        return GeminiRAGSystem(channel_name)
    except Exception as e:
        logger.error(f"❌ RAG 시스템 생성 실패: {e}")
        raise

def main():
    """CLI에서 직접 실행할 때의 메인 함수"""
    parser = argparse.ArgumentParser(description="Gemini RAG 질의응답 시스템")
    parser.add_argument("action", choices=["ask", "channels", "stats"], help="실행할 작업")
    parser.add_argument("query", nargs='?', help="질문 (ask 액션에서 필요)")
    parser.add_argument("-c", "--channel", help="대상 채널명")
    parser.add_argument("-n", "--num-results", type=int, default=5, help="검색 결과 개수 (기본: 5)")
    parser.add_argument("--stream", action="store_true", help="스트리밍 답변 생성")
    parser.add_argument("--no-session", action="store_true", help="세션 저장 안함")
    
    args = parser.parse_args()
    
    try:
        if args.action == "ask":
            if not args.query:
                print("❌ 질문이 필요합니다. 예: python rag_gemini.py ask \"머신러닝이 뭔가요?\"")
                return
            
            # RAG 시스템 초기화
            rag = create_rag_system(args.channel)
            
            # 질의응답 실행
            answer = rag.query(
                question=args.query,
                stream=args.stream,
                n_results=args.num_results,
                save_session=not args.no_session
            )
            
            if not args.stream:  # 스트리밍이 아닌 경우에만 출력
                print("🤖 답변:")
                print("=" * 60)
                print(answer)
                print("=" * 60)
        
        elif args.action == "channels":
            rag = create_rag_system()
            channels = rag.list_available_channels()
            
            print("📺 RAG 사용 가능한 채널 목록:")
            print("-" * 40)
            for i, channel in enumerate(channels, 1):
                print(f"{i:2d}. {channel}")
            print(f"\n총 {len(channels)}개 채널")
        
        elif args.action == "stats":
            if not args.channel:
                print("❌ --channel 옵션이 필요합니다.")
                return
                
            rag = create_rag_system(args.channel)
            stats = rag.get_channel_stats()
            
            if stats:
                print(f"📊 '{args.channel}' 채널 통계:")
                print("-" * 40)
                print(f"총 영상 수: {stats.get('total_videos', 0)}개")
                print(f"총 문서 수: {stats.get('total_documents', 0)}개")
                print(f"총 토큰 수: {stats.get('total_tokens', 0):,}개")
                print(f"마지막 업데이트: {stats.get('last_updated', 'N/A')}")
            else:
                print(f"❌ '{args.channel}' 채널 통계를 찾을 수 없습니다.")
    
    except KeyboardInterrupt:
        print("\n\n👋 사용자에 의해 중단되었습니다.")
    except Exception as e:
        logger.error(f"❌ 실행 오류: {e}")
        print(f"❌ 오류가 발생했습니다: {e}")

if __name__ == "__main__":
    main()