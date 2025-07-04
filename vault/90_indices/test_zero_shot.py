#!/usr/bin/env python3
"""
제로샷 프롬프트 생성기 테스트 스크립트
"""

import os
import sys
from pathlib import Path
from prompt_manager import PromptManager
from zero_shot_prompt_generator import ZeroShotPromptGenerator

def test_zero_shot_generator():
    """제로샷 생성기 단독 테스트"""
    print("🧪 제로샷 프롬프트 생성기 단독 테스트")
    print("=" * 50)
    
    try:
        # 생성기 초기화
        generator = ZeroShotPromptGenerator(model="deepseek-chat")
        
        # 사용 가능한 채널 확인
        collections = generator.chroma_client.list_collections()
        if not collections:
            print("❌ 분석 가능한 채널이 없습니다")
            return False
        
        # 첫 번째 채널로 테스트
        test_channel = collections[0].name
        print(f"📺 테스트 채널: {test_channel}")
        
        # 채널 요약 정보 조회
        print("\n1️⃣ 채널 요약 정보 추출 중...")
        summary = generator.get_channel_summary(test_channel)
        
        if summary:
            print(f"✅ 채널 요약 완료:")
            print(f"  - 총 문서: {summary['total_documents']}개")
            print(f"  - 주요 키워드: {', '.join(summary['content_keywords'][:5])}")
            print(f"  - 영상 제목 수: {len(summary['video_titles'])}개")
        else:
            print("❌ 채널 요약 정보 추출 실패")
            return False
        
        # AI 프롬프트 생성
        print("\n2️⃣ AI 프롬프트 생성 중...")
        prompt_data = generator.generate_prompt_with_ai(summary)
        
        if prompt_data:
            print(f"✅ AI 프롬프트 생성 완료:")
            print(f"  - 페르소나: {prompt_data.get('persona', 'N/A')}")
            print(f"  - 톤: {prompt_data.get('tone', 'N/A')}")
            print(f"  - 전문분야: {', '.join(prompt_data.get('expertise_keywords', [])[:3])}")
            print(f"  - 생성 방법: {prompt_data.get('generation_method', 'N/A')}")
            return True
        else:
            print("❌ AI 프롬프트 생성 실패")
            return False
            
    except Exception as e:
        print(f"❌ 테스트 실패: {e}")
        return False

def test_prompt_manager_integration():
    """PromptManager 통합 테스트"""
    print("\n🧪 PromptManager 통합 테스트")
    print("=" * 50)
    
    try:
        # PromptManager 초기화
        manager = PromptManager()
        
        # 사용 가능한 채널 확인
        channels = manager.list_available_channels_for_analysis()
        if not channels:
            print("❌ 분석 가능한 채널이 없습니다")
            return False
        
        test_channel = channels[0]
        print(f"📺 테스트 채널: {test_channel}")
        
        # 제로샷 프롬프트 생성 (저장 안함)
        print("\n1️⃣ 제로샷 프롬프트 생성 테스트...")
        if manager.zero_shot_generator:
            prompt_data = manager.zero_shot_generator.generate_channel_prompt(test_channel)
            
            if prompt_data:
                print(f"✅ 제로샷 생성 성공:")
                print(f"  - 페르소나: {prompt_data.get('persona', 'N/A')[:50]}...")
                print(f"  - 모델: {prompt_data.get('model_used', 'N/A')}")
                return True
            else:
                print("❌ 제로샷 생성 실패")
                return False
        else:
            print("❌ ZeroShotPromptGenerator가 초기화되지 않음")
            return False
            
    except Exception as e:
        print(f"❌ 테스트 실패: {e}")
        return False

def test_cli_commands():
    """CLI 명령어 테스트 (실제 실행 안함)"""
    print("\n🧪 CLI 명령어 테스트 (가상)")
    print("=" * 50)
    
    print("📋 사용 가능한 CLI 명령어:")
    print("  1. python auto_prompt.py list")
    print("  2. python auto_prompt.py generate <채널명> -m zero_shot_ai")
    print("  3. python auto_prompt.py batch -m zero_shot_ai")
    print("  4. python auto_prompt.py status")
    
    return True

def main():
    """메인 테스트 실행"""
    print("🚀 제로샷 프롬프트 생성 시스템 테스트")
    print("=" * 60)
    
    # 환경 변수 확인
    print("🔧 환경 설정 확인...")
    api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ DEEPSEEK_API_KEY 또는 OPENAI_API_KEY 환경변수가 설정되지 않았습니다")
        print("💡 .env 파일에 API 키를 설정해주세요:")
        print("   DEEPSEEK_API_KEY=your_api_key_here")
        return
    else:
        print("✅ API 키 설정 확인됨")
    
    # ChromaDB 경로 확인
    chroma_path = Path(__file__).parent / "chroma"
    if not chroma_path.exists():
        print(f"❌ ChromaDB 경로가 없습니다: {chroma_path}")
        print("💡 먼저 'python embed.py'로 벡터 임베딩을 생성하세요")
        return
    else:
        print(f"✅ ChromaDB 경로 확인됨: {chroma_path}")
    
    # 테스트 실행
    tests = [
        ("제로샷 생성기 단독", test_zero_shot_generator),
        ("PromptManager 통합", test_prompt_manager_integration),
        ("CLI 명령어", test_cli_commands)
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} 테스트 중 오류: {e}")
            results.append((test_name, False))
    
    # 결과 요약
    print("\n📊 테스트 결과 요약")
    print("=" * 60)
    for test_name, success in results:
        status = "✅ 성공" if success else "❌ 실패"
        print(f"  {test_name}: {status}")
    
    success_count = sum(1 for _, success in results if success)
    print(f"\n총 {success_count}/{len(results)} 테스트 성공")
    
    if success_count == len(results):
        print("\n🎉 모든 테스트가 성공했습니다!")
        print("\n📚 사용법:")
        print("  python auto_prompt.py generate <채널명> -m zero_shot_ai")
        print("  python auto_prompt.py batch -m zero_shot_ai")
    else:
        print("\n⚠️ 일부 테스트가 실패했습니다. 설정을 다시 확인해주세요.")

if __name__ == "__main__":
    main() 