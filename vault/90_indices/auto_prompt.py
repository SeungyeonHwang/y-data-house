#!/usr/bin/env python3
"""
채널별 자동 프롬프트 생성 CLI 도구 - Y-Data-House
"""

import sys
import argparse
from pathlib import Path
from prompt_manager import PromptManager


def setup_argument_parser():
    """명령행 인수 파서 설정"""
    parser = argparse.ArgumentParser(
        description="🤖 Y-Data House 자동 프롬프트 생성기",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
사용 예시:
  python auto_prompt.py list                     # 분석 가능한 채널 목록
  python auto_prompt.py analyze takaki_takehana  # 특정 채널 분석
  python auto_prompt.py generate takaki_takehana # 특정 채널 프롬프트 생성
  python auto_prompt.py batch                    # 모든 채널 프롬프트 생성
  python auto_prompt.py status                   # 프롬프트 현황 확인
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='사용할 명령어')
    
    # list 명령어
    list_parser = subparsers.add_parser('list', help='분석 가능한 채널 목록 조회')
    list_parser.add_argument('--detailed', '-d', action='store_true', 
                           help='상세 정보 포함')
    
    # analyze 명령어
    analyze_parser = subparsers.add_parser('analyze', help='특정 채널 분석')
    analyze_parser.add_argument('channel_name', help='분석할 채널명')
    analyze_parser.add_argument('--export', '-e', help='분석 결과를 JSON 파일로 저장')
    
    # generate 명령어
    generate_parser = subparsers.add_parser('generate', help='특정 채널 프롬프트 생성')
    generate_parser.add_argument('channel_name', help='프롬프트를 생성할 채널명')
    generate_parser.add_argument('--force', '-f', action='store_true',
                               help='기존 프롬프트가 있어도 강제로 새 버전 생성')
    
    # batch 명령어
    batch_parser = subparsers.add_parser('batch', help='모든 채널 자동 프롬프트 생성')
    batch_parser.add_argument('--skip-existing', '-s', action='store_true',
                            help='이미 프롬프트가 있는 채널 건너뛰기')
    
    # status 명령어
    status_parser = subparsers.add_parser('status', help='프롬프트 현황 확인')
    status_parser.add_argument('--export-summary', '-e', help='현황을 JSON 파일로 저장')
    
    # versions 명령어
    versions_parser = subparsers.add_parser('versions', help='채널의 프롬프트 버전 관리')
    versions_parser.add_argument('channel_name', help='채널명')
    versions_parser.add_argument('--set-active', type=int, help='활성 버전 설정')
    versions_parser.add_argument('--delete', type=int, help='특정 버전 삭제')
    
    return parser


def cmd_list(args, manager: PromptManager):
    """채널 목록 조회"""
    channels = manager.list_available_channels_for_analysis()
    
    if not channels:
        print("❌ 분석 가능한 채널이 없습니다.")
        print("💡 먼저 'python embed.py'로 벡터 임베딩을 생성하세요.")
        return
    
    print(f"📺 분석 가능한 채널 ({len(channels)}개):")
    
    if args.detailed:
        # 상세 정보 포함
        for i, channel in enumerate(channels, 1):
            print(f"\n{i}. {channel}")
            
            # 분석 정보 조회
            try:
                analysis = manager.get_channel_analysis(channel)
                if analysis:
                    print(f"   📊 총 영상: {analysis.get('total_videos', 0)}개")
                    print(f"   📄 총 문서: {analysis.get('total_documents', 0)}개")
                    keywords = list(analysis.get('keywords', {}).keys())[:3]
                    print(f"   🔑 주요 키워드: {', '.join(keywords)}")
                    
                    # 프롬프트 상태 확인
                    prompt = manager.get_channel_prompt(channel)
                    if prompt.get('auto_generated'):
                        print(f"   ✅ 자동 프롬프트 있음 (v{prompt.get('version', 1)})")
                    else:
                        print(f"   📝 수동 프롬프트 또는 기본 프롬프트")
                else:
                    print(f"   ⚠️  분석 데이터 없음")
            except Exception as e:
                print(f"   ❌ 분석 실패: {e}")
    else:
        # 간단한 목록
        for i, channel in enumerate(channels, 1):
            print(f"  {i}. {channel}")


def cmd_analyze(args, manager: PromptManager):
    """특정 채널 분석"""
    channel_name = args.channel_name
    print(f"🔍 {channel_name} 채널 분석 시작...")
    
    analysis = manager.get_channel_analysis(channel_name)
    
    if not analysis:
        print(f"❌ {channel_name} 채널을 찾을 수 없습니다.")
        available_channels = manager.list_available_channels_for_analysis()
        if available_channels:
            print("\n사용 가능한 채널:")
            for ch in available_channels[:5]:
                print(f"  - {ch}")
            if len(available_channels) > 5:
                print(f"  ... 및 {len(available_channels) - 5}개 더")
        return
    
    # 분석 결과 출력
    print(f"\n📊 {channel_name} 채널 분석 결과:")
    print(f"  📹 총 영상 수: {analysis['total_videos']}")
    print(f"  📄 총 문서 수: {analysis['total_documents']}")
    
    # 주요 키워드 (상위 10개)
    keywords = analysis.get('keywords', {})
    print(f"\n🔑 주요 키워드 (상위 10개):")
    for i, (keyword, count) in enumerate(list(keywords.items())[:10], 1):
        print(f"  {i:2d}. {keyword} ({count}회)")
    
    # 콘텐츠 패턴
    patterns = analysis.get('content_patterns', {})
    print(f"\n📈 콘텐츠 패턴:")
    print(f"  투자 용어 빈도: {patterns.get('investment_terms', 0)}")
    print(f"  지역 언급 빈도: {patterns.get('location_mentions', 0)}")
    print(f"  수치 데이터 수: {patterns.get('numerical_data', 0)}")
    print(f"  경험 공유 표현: {patterns.get('experience_sharing', 0)}")
    print(f"  분석 깊이: {patterns.get('analysis_depth', 'medium')}")
    
    # 톤 분석
    tone_analysis = analysis.get('tone_analysis', {})
    print(f"\n🎭 톤 & 스타일 분석:")
    print(f"  주요 톤: {tone_analysis.get('primary_tone', 'N/A')}")
    print(f"  스타일 설명: {tone_analysis.get('style_description', 'N/A')}")
    
    # 메타데이터 분석
    metadata = analysis.get('metadata_insights', {})
    if metadata.get('avg_duration'):
        avg_min = int(metadata['avg_duration'] // 60)
        avg_sec = int(metadata['avg_duration'] % 60)
        print(f"\n📊 메타데이터:")
        print(f"  평균 영상 길이: {avg_min}분 {avg_sec}초")
        
        if metadata.get('popular_topics'):
            print(f"  인기 토픽: {', '.join(metadata['popular_topics'][:3])}")
    
    # 분석 결과 내보내기
    if args.export:
        import json
        export_path = Path(args.export)
        try:
            with open(export_path, 'w', encoding='utf-8') as f:
                json.dump(analysis, f, ensure_ascii=False, indent=2)
            print(f"\n💾 분석 결과가 {export_path}에 저장되었습니다.")
        except Exception as e:
            print(f"\n❌ 내보내기 실패: {e}")


def cmd_generate(args, manager: PromptManager):
    """특정 채널 프롬프트 생성"""
    channel_name = args.channel_name
    
    # 기존 프롬프트 확인
    existing_prompt = manager.get_channel_prompt(channel_name)
    if existing_prompt.get('auto_generated') and not args.force:
        print(f"⚠️  {channel_name} 채널에 이미 자동 생성된 프롬프트가 있습니다.")
        print(f"    기존 버전: v{existing_prompt.get('version', 1)}")
        print(f"    생성일: {existing_prompt.get('created_at', 'N/A')}")
        print(f"    페르소나: {existing_prompt.get('persona', 'N/A')}")
        print("\n강제로 새 버전을 생성하려면 --force 옵션을 사용하세요.")
        return
    
    # 자동 프롬프트 생성
    version = manager.auto_generate_channel_prompt(channel_name)
    
    if version > 0:
        print(f"\n🎉 {channel_name} 채널 자동 프롬프트 v{version} 생성 완료!")
        
        # 생성된 프롬프트 미리보기
        new_prompt = manager.get_channel_prompt(channel_name)
        print(f"\n📝 생성된 프롬프트 미리보기:")
        print(f"  페르소나: {new_prompt.get('persona', 'N/A')}")
        print(f"  톤: {new_prompt.get('tone', 'N/A')}")
        print(f"  전문 키워드: {', '.join(new_prompt.get('expertise_keywords', [])[:5])}")
        print(f"  답변 규칙 수: {len(new_prompt.get('rules', []))}")
    else:
        print(f"❌ {channel_name} 채널 프롬프트 생성 실패")


def cmd_batch(args, manager: PromptManager):
    """모든 채널 일괄 프롬프트 생성"""
    channels = manager.list_available_channels_for_analysis()
    
    if not channels:
        print("❌ 분석 가능한 채널이 없습니다.")
        return
    
    if args.skip_existing:
        # 기존 프롬프트가 있는 채널 필터링
        existing_channels = [info['name'] for info in manager.list_channels_with_prompts()]
        channels = [ch for ch in channels if ch not in existing_channels]
        print(f"📋 기존 프롬프트가 있는 채널 건너뛰기: {len(existing_channels)}개")
    
    if not channels:
        print("✅ 생성할 채널이 없습니다. 모든 채널에 프롬프트가 있습니다.")
        return
    
    print(f"🚀 {len(channels)}개 채널에 대해 자동 프롬프트 생성 시작...")
    
    results = {}
    for i, channel in enumerate(channels, 1):
        try:
            print(f"\n[{i}/{len(channels)}] {channel} 처리 중...")
            version = manager.auto_generate_channel_prompt(channel)
            results[channel] = version
            
            if version > 0:
                print(f"  ✅ 성공: v{version}")
            else:
                print(f"  ❌ 실패")
                
        except Exception as e:
            print(f"  ❌ 오류: {e}")
            results[channel] = 0
    
    # 결과 요약
    success_count = len([v for v in results.values() if v > 0])
    total_count = len(results)
    
    print(f"\n🎉 일괄 생성 완료:")
    print(f"  성공: {success_count}/{total_count}")
    
    if success_count < total_count:
        failed_channels = [ch for ch, v in results.items() if v == 0]
        print(f"\n❌ 실패한 채널:")
        for ch in failed_channels:
            print(f"  - {ch}")


def cmd_status(args, manager: PromptManager):
    """프롬프트 현황 확인"""
    available_channels = manager.list_available_channels_for_analysis()
    channels_with_prompts = manager.list_channels_with_prompts()
    
    print("📊 Y-Data House 프롬프트 현황")
    print(f"  분석 가능한 채널: {len(available_channels)}개")
    print(f"  프롬프트 보유 채널: {len(channels_with_prompts)}개")
    
    if not channels_with_prompts:
        print("\n💡 아직 생성된 프롬프트가 없습니다.")
        print("    'python auto_prompt.py batch' 명령으로 일괄 생성하세요.")
        return
    
    print(f"\n📝 프롬프트 보유 채널 상세:")
    for info in channels_with_prompts:
        auto_mark = "🤖" if info['auto_generated'] else "✏️"
        print(f"  {auto_mark} {info['name']}")
        print(f"     버전: v{info['active_version']} (총 {info['total_versions']}개)")
        print(f"     페르소나: {info['persona']}...")
        print(f"     전문분야: {', '.join(info['expertise'])}")
        if info['last_modified']:
            print(f"     수정일: {info['last_modified'][:10]}")
        print()
    
    # 미생성 채널
    prompt_channel_names = {info['name'] for info in channels_with_prompts}
    missing_channels = [ch for ch in available_channels if ch not in prompt_channel_names]
    
    if missing_channels:
        print(f"⚠️  프롬프트 미생성 채널 ({len(missing_channels)}개):")
        for ch in missing_channels:
            print(f"  - {ch}")
    
    # 현황 내보내기
    if args.export_summary:
        summary_data = {
            'timestamp': manager.analyzer.list_available_channels_for_analysis()[0] if available_channels else '',
            'total_available_channels': len(available_channels),
            'channels_with_prompts': len(channels_with_prompts),
            'coverage_rate': len(channels_with_prompts) / len(available_channels) if available_channels else 0,
            'channels_detail': channels_with_prompts,
            'missing_channels': missing_channels
        }
        
        import json
        try:
            with open(args.export_summary, 'w', encoding='utf-8') as f:
                json.dump(summary_data, f, ensure_ascii=False, indent=2)
            print(f"\n💾 현황 요약이 {args.export_summary}에 저장되었습니다.")
        except Exception as e:
            print(f"\n❌ 내보내기 실패: {e}")


def cmd_versions(args, manager: PromptManager):
    """채널의 프롬프트 버전 관리"""
    channel_name = args.channel_name
    
    if args.set_active is not None:
        # 활성 버전 설정
        success = manager.set_active_version(channel_name, args.set_active)
        if success:
            print(f"✅ {channel_name} 활성 버전을 v{args.set_active}로 변경했습니다.")
        return
    
    if args.delete is not None:
        # 버전 삭제
        success = manager.delete_prompt_version(channel_name, args.delete)
        if success:
            print(f"✅ {channel_name} v{args.delete} 프롬프트를 삭제했습니다.")
        return
    
    # 버전 목록 조회
    versions = manager.get_prompt_versions(channel_name)
    
    if not versions:
        print(f"❌ {channel_name} 채널의 프롬프트가 없습니다.")
        return
    
    current_prompt = manager.get_channel_prompt(channel_name)
    active_version = current_prompt.get('version', 1)
    
    print(f"📚 {channel_name} 채널 프롬프트 버전:")
    for version_info in versions:
        active_mark = "🟢" if version_info['version'] == active_version else "⚪"
        auto_mark = "🤖" if version_info['auto_generated'] else "✏️"
        
        print(f"  {active_mark} v{version_info['version']} {auto_mark}")
        print(f"     생성일: {version_info['created_at'][:10] if version_info['created_at'] else 'N/A'}")
        print(f"     페르소나: {version_info['persona']}")
        print()


def main():
    """메인 실행 함수"""
    parser = setup_argument_parser()
    
    # 인수가 없으면 도움말 출력
    if len(sys.argv) == 1:
        parser.print_help()
        return
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    try:
        # PromptManager 초기화
        manager = PromptManager()
        
        # 명령어 실행
        if args.command == 'list':
            cmd_list(args, manager)
        elif args.command == 'analyze':
            cmd_analyze(args, manager)
        elif args.command == 'generate':
            cmd_generate(args, manager)
        elif args.command == 'batch':
            cmd_batch(args, manager)
        elif args.command == 'status':
            cmd_status(args, manager)
        elif args.command == 'versions':
            cmd_versions(args, manager)
        else:
            print(f"❌ 알 수 없는 명령어: {args.command}")
            parser.print_help()
    
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()