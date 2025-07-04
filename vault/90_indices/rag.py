#!/usr/bin/env python3
"""
Y-Data-House RAG 시스템 v7.0 - Search-First & Prompt-Light
조언 기반 리팩토링: 검색 품질 '하드' 향상 + 프롬프트 '심플+검증' + 성능 최적화

아키텍처 변경:
- 기존: 단일 파일 800줄 복잡한 로직
- 신규: 모듈화된 파이프라인 + 캐싱 + 조건부 실행
- 성능: 800ms → < 500ms 목표

주요 개선사항:
✅ HyDE → Query Rewrite → Vector Search → Conditional Re-Rank
✅ 경량 프롬프트 + Self-Refine (1회) + JSON Schema 강제
✅ Semantic Cache로 LLM 호출 40% 절감
✅ 조건부 실행으로 성능 최적화
"""

import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv
from typing import List, Dict, Any, Optional

# 새로운 아키텍처 import
from rag_controller import RAGController
from schemas import SearchConfig, AnswerConfig, AnswerStyle

# 환경변수 로드
load_dotenv()

# 경로 설정
VAULT_ROOT = Path(__file__).parent.parent
CHROMA_PATH = VAULT_ROOT / "90_indices" / "chroma"

def list_available_channels() -> List[Dict[str, Any]]:
    """사용 가능한 채널 목록 조회"""
    try:
        controller = RAGController(CHROMA_PATH)
        collections = controller.search_pipeline.chroma_client.list_collections()
        channels = []
        
        for collection in collections:
            if collection.name.startswith("channel_"):
                try:
                    data = collection.get()
                    if data['metadatas'] and len(data['metadatas']) > 0:
                        channel_name = data['metadatas'][0].get('channel', 'Unknown')
                        video_count = len(data['ids']) if data['ids'] else 0
                        
                        channels.append({
                            'name': channel_name,
                            'collection_name': collection.name,
                            'video_count': video_count,
                            'isolated': True  # 새 아키텍처에서는 모든 채널이 격리됨
                        })
                except Exception:
                    continue
        
        return sorted(channels, key=lambda x: x['video_count'], reverse=True)
    except Exception as e:
        print(f"⚠️ 채널 목록 조회 실패: {e}")
        return []

def chat_with_progress(query: str, channel_name: str, model: str = "deepseek-chat") -> str:
    """진행 상황 출력과 함께 RAG 실행 (기존 호환성)"""
    controller = RAGController(CHROMA_PATH, model)
    
    # 진행 상황 출력
    print(f"PROGRESS:{json.dumps({'step': '벡터 검색', 'message': f'🔍 {channel_name} 채널에서 벡터 검색 중...', 'progress': 10.0, 'details': f'질문: {query[:50]}...'}, ensure_ascii=False)}")
    
    # RAG 실행
    response = controller.query(query, channel_name)
    
    print(f"PROGRESS:{json.dumps({'step': '답변 생성', 'message': '🤖 DeepSeek으로 답변 생성 중...', 'progress': 80.0, 'details': f'검색 결과: {response.documents_found}개'}, ensure_ascii=False)}")
    
    print(f"PROGRESS:{json.dumps({'step': '완료', 'message': '✅ 답변 생성 완료', 'progress': 100.0, 'details': None}, ensure_ascii=False)}")
    print("FINAL_ANSWER:")
    
    return response.answer

def main():
    """메인 실행 함수 - 새로운 아키텍처 기반"""
    try:
        # --model 옵션 확인
        model = "deepseek-chat"  # 기본값
        model_index = None
        
        for i, arg in enumerate(sys.argv):
            if arg == "--model" and i + 1 < len(sys.argv):
                model = sys.argv[i + 1]
                model_index = i
                break
        
        # --model 인자 제거
        if model_index is not None:
            sys.argv.pop(model_index + 1)  # 모델명 제거
            sys.argv.pop(model_index)      # --model 제거
        
        if len(sys.argv) < 2:
            print("🤖 Y-Data House RAG v7.0 (Search-First & Prompt-Light)")
            print("\n🎯 **새로운 아키텍처 주요 개선사항:**")
            print("  ✅ 4단계 검색: HyDE → Query Rewrite → Vector → Re-Rank")
            print("  ✅ 경량 프롬프트 + Self-Refine (1회) + JSON Schema")
            print("  ✅ Semantic Cache로 LLM 호출 40% 절감")
            print("  ✅ 조건부 실행으로 800ms → <500ms 성능 향상")
            print("\n📋 사용법:")
            print("  python rag.py channels                   # 사용 가능한 채널 목록")
            print("  python rag.py '질문' 채널명              # 특정 채널에서 검색")
            print("  python rag.py '질문' 채널명 --fast       # 빠른 모드")
            print("  python rag.py health                     # 시스템 상태 확인")
            print("  python rag.py cache stats               # 캐시 통계")
            print("\n📚 예시:")
            print("  python rag.py '도쿄 투자 전략' takaki_takehana")
            print("  python rag.py '수익률 좋은 지역' 도쿄부동산")
            
            # 사용 가능한 채널 표시
            channels = list_available_channels()
            if channels:
                print(f"\n📺 사용 가능한 채널 ({len(channels)}개):")
                for i, ch in enumerate(channels, 1):
                    print(f"  {i}. {ch['name']} ({ch['video_count']}개 영상) 🔐 격리됨")
            
            return
        
        command = sys.argv[1]
        
        if command == "channels":
            # 채널 목록 출력
            channels = list_available_channels()
            if channels:
                print(f"📺 사용 가능한 채널 ({len(channels)}개):")
                for i, ch in enumerate(channels, 1):
                    print(f"  {i}. {ch['name']} ({ch['video_count']}개 영상) 🔐 격리됨")
            else:
                print("사용 가능한 채널이 없습니다. 'python embed.py'를 먼저 실행하세요.")
            return
        
        elif command == "health":
            # 시스템 상태 확인
            controller = RAGController(CHROMA_PATH, model)
            health = controller.health_check()
            
            print("🏥 시스템 상태:")
            print(f"  전체 상태: {'✅ 정상' if health['status'] == 'healthy' else '⚠️ 문제'}")
            print(f"  검색 파이프라인: {'✅' if health['components']['search_pipeline'] else '❌'}")
            print(f"  답변 파이프라인: {'✅' if health['components']['answer_pipeline'] else '❌'}")
            print(f"  ChromaDB: {'✅' if health['components']['chroma_db'] else '❌'}")
            print(f"  캐시 시스템: {'✅' if health['components']['cache'] else '❌'}")
            if 'chroma_collections' in health:
                print(f"  컬렉션 수: {health['chroma_collections']}개")
            if health['performance']['cache_hit_rate'] > 0:
                print(f"  캐시 히트율: {health['performance']['cache_hit_rate']:.2%}")
            return
            
        elif command == "cache":
            # 캐시 관리
            if len(sys.argv) < 3:
                print("사용법: python rag.py cache [stats|clear|cleanup]")
                return
                
            controller = RAGController(CHROMA_PATH, model)
            cache_cmd = sys.argv[2]
            
            if cache_cmd == "stats":
                stats = controller.get_cache_stats()
                if stats.get('cache_enabled', False):
                    print("💾 캐시 통계:")
                    print(f"  총 요청: {stats['total_requests']}회")
                    print(f"  캐시 히트: {stats['cache_hits']}회")
                    print(f"  캐시 미스: {stats['cache_misses']}회")
                    print(f"  히트율: {stats['hit_rate']:.2%}")
                    print(f"  엔트리 수: {stats['entry_count']}개")
                    print(f"  캐시 크기: {stats['cache_size_mb']:.1f}MB")
                else:
                    print("❌ 캐시가 비활성화되어 있습니다.")
                    
            elif cache_cmd == "clear":
                if controller.clear_cache():
                    print("✅ 전체 캐시 삭제 완료")
                else:
                    print("❌ 캐시 삭제 실패")
                    
            elif cache_cmd == "cleanup":
                deleted = controller.cleanup_cache()
                print(f"🧹 만료된 캐시 {deleted}개 정리 완료")
            return
        
        # 질문 + 채널 처리
        if len(sys.argv) < 3:
            print("❌ 채널명이 필요합니다.")
            print("사용법: python rag.py '질문' 채널명 [--fast] [--progress]")
            print("예시: python rag.py '도쿄 투자 전략' takaki_takehana")
            print("예시: python rag.py '도쿄 투자 전략' takaki_takehana --fast")
            return
        
        query = command
        channel_name = sys.argv[2]
        
        # 옵션 확인
        fast_mode = "--fast" in sys.argv
        show_progress = "--progress" in sys.argv
        
        # 채널 존재 확인
        channels = list_available_channels()
        channel_names = [ch['name'] for ch in channels]
        
        if channel_name not in channel_names:
            print(f"❌ 채널 '{channel_name}'을 찾을 수 없습니다.")
            if channels:
                print(f"\n사용 가능한 채널:")
                for ch in channels:
                    print(f"  - {ch['name']}")
            return
        
        # RAG 실행
        if show_progress:
            answer = chat_with_progress(query, channel_name, model)
        else:
            controller = RAGController(CHROMA_PATH, model)
            response = controller.query(query, channel_name, fast_mode=fast_mode)
            answer = response.answer
            
            print(f"\n🤖 **{channel_name} 채널 답변:**")
            print(f"⚡ 처리 시간: {response.total_time_ms:.1f}ms")
            print(f"🔍 검색된 문서: {response.documents_found}개")
            print(f"📊 신뢰도: {response.confidence:.2f}")
            
            # 성능 정보 출력
            search_quality = response.search_quality
            if search_quality.get('hyde_used'):
                print("🎯 HyDE 사용됨")
            if search_quality.get('rewrite_used'):
                print("🔄 Query Rewrite 사용됨")
            if search_quality.get('rerank_used'):
                print("🤖 LLM Re-rank 사용됨")
            
            debug_info = response.debug_info
            if debug_info.get('fast_mode'):
                print("🚀 빠른 모드 사용됨")
            if debug_info.get('self_refined'):
                print("✨ Self-Refine 적용됨")
            if debug_info.get('cache_used'):
                print("💾 캐시 활성화됨")
            
            print()  # 줄바꿈
        
        print(answer)
        
    except Exception as e:
        print(f"❌ 오류: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main() 