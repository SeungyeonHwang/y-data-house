#!/usr/bin/env python3
"""
프롬프트 관리 시스템 - Y-Data-House 채널별 프롬프트 CRUD
"""

import json
import os
from pathlib import Path
from typing import Dict, Optional, List
from datetime import datetime
import re
from dotenv import load_dotenv
from channel_analyzer import ChannelAnalyzer

# 환경변수 로드
load_dotenv()


class PromptManager:
    """채널별 프롬프트 관리 클래스"""
    
    def __init__(self, prompts_dir: Path = None, chroma_path: Path = None):
        """초기화"""
        self.prompts_dir = prompts_dir or Path(__file__).parent / "prompts"
        self.prompts_dir.mkdir(exist_ok=True)
        
        # 채널 분석기 초기화
        try:
            self.analyzer = ChannelAnalyzer(chroma_path or Path(__file__).parent / "chroma")
        except Exception as e:
            print(f"⚠️ ChannelAnalyzer 초기화 실패: {e}")
            self.analyzer = None
        
        print(f"✅ PromptManager 초기화 완료: {self.prompts_dir}")
    

    
    def sanitize_channel_name(self, channel_name: str) -> str:
        """채널명을 파일시스템에 안전한 형태로 변환"""
        sanitized = re.sub(r'[^\w가-힣\-_]', '_', channel_name)
        sanitized = re.sub(r'_+', '_', sanitized).strip('_')
        return sanitized[:50] if sanitized else "unknown_channel"
    
    def get_channel_prompt(self, channel_name: str) -> Dict:
        """채널별 활성 프롬프트 로드"""
        safe_name = self.sanitize_channel_name(channel_name)
        channel_dir = self.prompts_dir / safe_name
        
        if not channel_dir.exists():
            print(f"📂 {channel_name} 채널 프롬프트 폴더가 없음, 기본 프롬프트 반환")
            return self._get_default_prompt()
        
        # 활성 버전 확인
        active_file = channel_dir / "active.txt"
        if active_file.exists():
            try:
                version = int(active_file.read_text().strip())
            except ValueError:
                print(f"⚠️ active.txt 파일 읽기 실패, 버전 1 사용")
                version = 1
        else:
            version = 1
        
        # 프롬프트 파일 로드
        prompt_file = channel_dir / f"prompt_v{version}.json"
        if prompt_file.exists():
            try:
                with open(prompt_file, 'r', encoding='utf-8') as f:
                    prompt_data = json.load(f)
                    print(f"✅ {channel_name} 프롬프트 v{version} 로드됨")
                    return prompt_data
            except Exception as e:
                print(f"⚠️ 프롬프트 파일 읽기 실패: {e}")
                return self._get_default_prompt()
        
        print(f"📂 {channel_name} 프롬프트 파일 없음, 기본 프롬프트 반환")
        return self._get_default_prompt()
    
    def save_channel_prompt(self, channel_name: str, prompt_data: Dict) -> int:
        """새 프롬프트 버전 저장"""
        safe_name = self.sanitize_channel_name(channel_name)
        channel_dir = self.prompts_dir / safe_name
        channel_dir.mkdir(exist_ok=True)
        
        # 새 버전 번호 계산
        existing_versions = [
            int(f.stem.split('_v')[1]) 
            for f in channel_dir.glob("prompt_v*.json")
            if f.stem.split('_v')[1].isdigit()
        ]
        new_version = max(existing_versions, default=0) + 1
        
        # 프롬프트 메타데이터 업데이트
        prompt_data['version'] = new_version
        prompt_data['channel_name'] = channel_name
        prompt_data['created_at'] = datetime.now().isoformat()
        prompt_data['last_modified'] = datetime.now().isoformat()
        
        # 프롬프트 저장
        prompt_file = channel_dir / f"prompt_v{new_version}.json"
        try:
            with open(prompt_file, 'w', encoding='utf-8') as f:
                json.dump(prompt_data, f, ensure_ascii=False, indent=2)
            
            # 활성 버전 업데이트
            active_file = channel_dir / "active.txt"
            active_file.write_text(str(new_version))
            
            print(f"✅ {channel_name} 프롬프트 v{new_version} 저장 완료")
            return new_version
            
        except Exception as e:
            print(f"❌ 프롬프트 저장 실패: {e}")
            return 0
    
    def get_prompt_versions(self, channel_name: str) -> List[Dict]:
        """채널의 모든 프롬프트 버전 목록 반환"""
        safe_name = self.sanitize_channel_name(channel_name)
        channel_dir = self.prompts_dir / safe_name
        
        if not channel_dir.exists():
            return []
        
        versions = []
        for prompt_file in sorted(channel_dir.glob("prompt_v*.json")):
            try:
                with open(prompt_file, 'r', encoding='utf-8') as f:
                    prompt_data = json.load(f)
                    versions.append({
                        'version': prompt_data.get('version', 0),
                        'created_at': prompt_data.get('created_at', ''),
                        'persona': prompt_data.get('persona', '')[:100],  # 미리보기용
                        'auto_generated': prompt_data.get('auto_generated', False),
                        'file_path': str(prompt_file)
                    })
            except Exception as e:
                print(f"⚠️ 버전 파일 읽기 실패: {prompt_file} - {e}")
                continue
        
        return sorted(versions, key=lambda x: x['version'], reverse=True)
    
    def auto_generate_channel_prompt(self, channel_name: str) -> int:
        """채널 벡터 데이터를 분석하여 자동으로 프롬프트 생성"""
        if not self.analyzer:
            print("❌ ChannelAnalyzer가 초기화되지 않았습니다.")
            return 0
        
        print(f"🔍 {channel_name} 채널 벡터 데이터 분석 중...")
        
        # 1. 채널 벡터 데이터 분석
        channel_analysis = self.analyzer.analyze_channel_content(channel_name)
        if not channel_analysis:
            print(f"❌ {channel_name} 채널의 벡터 데이터를 찾을 수 없습니다.")
            return 0
        
        print(f"📊 분석 완료: {channel_analysis['total_videos']}개 영상, {channel_analysis['total_documents']}개 문서 분석")
        print(f"🔑 주요 키워드: {', '.join(list(channel_analysis['keywords'].keys())[:5])}")
        
        # 2. 자동 프롬프트 생성
        auto_prompt = self.analyzer.generate_auto_prompt(channel_analysis)
        
        # 3. 프롬프트 저장
        new_version = self.save_channel_prompt(channel_name, auto_prompt)
        
        if new_version > 0:
            print(f"✅ {channel_name} 채널 자동 프롬프트 v{new_version} 생성 완료!")
            print(f"📝 페르소나: {auto_prompt['persona']}")
            print(f"🎯 전문분야: {auto_prompt.get('expertise_keywords', [])[:3]}")
            print(f"🎭 스타일: {auto_prompt.get('tone', '전문적')}")
        
        return new_version
    
    def get_channel_analysis(self, channel_name: str) -> Dict:
        """채널 벡터 데이터 분석 결과 반환"""
        if not self.analyzer:
            print("❌ ChannelAnalyzer가 초기화되지 않았습니다.")
            return {}
        
        return self.analyzer.analyze_channel_content(channel_name)
    
    def list_available_channels_for_analysis(self) -> List[str]:
        """분석 가능한 채널 목록 반환"""
        if not self.analyzer:
            print("❌ ChannelAnalyzer가 초기화되지 않았습니다.")
            return []
        
        return self.analyzer.list_available_channels_for_analysis()
    
    def list_channels_with_prompts(self) -> List[Dict]:
        """프롬프트가 있는 채널 목록 반환"""
        channels_info = []
        
        for channel_dir in self.prompts_dir.iterdir():
            if channel_dir.is_dir() and not channel_dir.name.startswith('.'):
                # 활성 버전 확인
                active_file = channel_dir / "active.txt"
                active_version = 1
                if active_file.exists():
                    try:
                        active_version = int(active_file.read_text().strip())
                    except:
                        pass
                
                # 프롬프트 개수 확인
                prompt_files = list(channel_dir.glob("prompt_v*.json"))
                
                if prompt_files:
                    # 최신 프롬프트 정보 로드
                    latest_prompt_file = channel_dir / f"prompt_v{active_version}.json"
                    if latest_prompt_file.exists():
                        try:
                            with open(latest_prompt_file, 'r', encoding='utf-8') as f:
                                prompt_data = json.load(f)
                                
                            channels_info.append({
                                'name': prompt_data.get('channel_name', channel_dir.name),
                                'safe_name': channel_dir.name,
                                'active_version': active_version,
                                'total_versions': len(prompt_files),
                                'persona': prompt_data.get('persona', '')[:50],
                                'auto_generated': prompt_data.get('auto_generated', False),
                                'last_modified': prompt_data.get('last_modified', ''),
                                'expertise': prompt_data.get('expertise_keywords', [])[:3]
                            })
                        except Exception as e:
                            print(f"⚠️ 프롬프트 정보 읽기 실패: {channel_dir} - {e}")
        
        return sorted(channels_info, key=lambda x: x['last_modified'], reverse=True)
    
    def batch_generate_prompts(self) -> Dict[str, int]:
        """모든 채널에 대해 자동 프롬프트 생성"""
        if not self.analyzer:
            print("❌ ChannelAnalyzer가 초기화되지 않았습니다.")
            return {}
        
        channels = self.list_available_channels_for_analysis()
        results = {}
        
        print(f"🚀 {len(channels)}개 채널에 대해 자동 프롬프트 생성 시작...")
        
        for i, channel in enumerate(channels, 1):
            try:
                print(f"\n[{i}/{len(channels)}] {channel} 처리 중...")
                version = self.auto_generate_channel_prompt(channel)
                results[channel] = version
                print(f"  ✅ {channel}: v{version}")
            except Exception as e:
                print(f"  ❌ {channel}: 실패 - {e}")
                results[channel] = 0
        
        success_count = len([v for v in results.values() if v > 0])
        print(f"\n🎉 자동 프롬프트 생성 완료: {success_count}/{len(channels)} 성공")
        
        return results
    

    
    def delete_prompt_version(self, channel_name: str, version: int) -> bool:
        """특정 버전의 프롬프트 삭제"""
        safe_name = self.sanitize_channel_name(channel_name)
        channel_dir = self.prompts_dir / safe_name
        
        if not channel_dir.exists():
            print(f"❌ {channel_name} 채널 디렉토리가 없습니다.")
            return False
        
        prompt_file = channel_dir / f"prompt_v{version}.json"
        if not prompt_file.exists():
            print(f"❌ {channel_name} v{version} 프롬프트가 없습니다.")
            return False
        
        try:
            prompt_file.unlink()
            
            # 활성 버전이 삭제된 경우 다른 버전으로 업데이트
            active_file = channel_dir / "active.txt"
            if active_file.exists():
                current_active = int(active_file.read_text().strip())
                if current_active == version:
                    # 가장 높은 버전으로 변경
                    remaining_versions = [
                        int(f.stem.split('_v')[1]) 
                        for f in channel_dir.glob("prompt_v*.json")
                        if f.stem.split('_v')[1].isdigit()
                    ]
                    if remaining_versions:
                        new_active = max(remaining_versions)
                        active_file.write_text(str(new_active))
                        print(f"🔄 활성 버전을 v{new_active}로 변경")
                    else:
                        active_file.unlink()  # 모든 프롬프트 삭제됨
            
            print(f"✅ {channel_name} v{version} 프롬프트 삭제 완료")
            return True
            
        except Exception as e:
            print(f"❌ 프롬프트 삭제 실패: {e}")
            return False
    
    def set_active_version(self, channel_name: str, version: int) -> bool:
        """채널의 활성 프롬프트 버전 변경"""
        safe_name = self.sanitize_channel_name(channel_name)
        channel_dir = self.prompts_dir / safe_name
        
        if not channel_dir.exists():
            print(f"❌ {channel_name} 채널 디렉토리가 없습니다.")
            return False
        
        prompt_file = channel_dir / f"prompt_v{version}.json"
        if not prompt_file.exists():
            print(f"❌ {channel_name} v{version} 프롬프트가 없습니다.")
            return False
        
        try:
            active_file = channel_dir / "active.txt"
            active_file.write_text(str(version))
            print(f"✅ {channel_name} 활성 버전을 v{version}으로 변경")
            return True
        except Exception as e:
            print(f"❌ 활성 버전 변경 실패: {e}")
            return False
    
    def export_channel_prompts(self, channel_name: str) -> Dict:
        """채널의 모든 프롬프트를 내보내기"""
        versions = self.get_prompt_versions(channel_name)
        if not versions:
            return {}
        
        export_data = {
            'channel_name': channel_name,
            'export_timestamp': datetime.now().isoformat(),
            'prompts': []
        }
        
        for version_info in versions:
            try:
                with open(version_info['file_path'], 'r', encoding='utf-8') as f:
                    prompt_data = json.load(f)
                    export_data['prompts'].append(prompt_data)
            except Exception as e:
                print(f"⚠️ 버전 {version_info['version']} 내보내기 실패: {e}")
        
        return export_data
    
    def import_channel_prompts(self, import_data: Dict) -> bool:
        """채널 프롬프트 가져오기"""
        try:
            channel_name = import_data.get('channel_name')
            if not channel_name:
                print("❌ 채널명이 없습니다.")
                return False
            
            prompts = import_data.get('prompts', [])
            if not prompts:
                print("❌ 가져올 프롬프트가 없습니다.")
                return False
            
            success_count = 0
            for prompt_data in prompts:
                version = self.save_channel_prompt(channel_name, prompt_data)
                if version > 0:
                    success_count += 1
            
            print(f"✅ {channel_name} 채널에 {success_count}/{len(prompts)}개 프롬프트 가져오기 완료")
            return success_count > 0
            
        except Exception as e:
            print(f"❌ 프롬프트 가져오기 실패: {e}")
            return False
    
    def _get_default_prompt(self) -> Dict:
        """기본 프롬프트 반환"""
        return {
            "version": 1,
            "channel_name": "default",
            "created_at": datetime.now().isoformat(),
            "auto_generated": False,
            "persona": "YouTube 비디오 내용 전문 분석가",
            "tone": "친근하고 도움이 되는 스타일",
            "system_prompt": "사용자의 질문에 대해 비디오 내용을 바탕으로 정확하고 유용한 답변을 제공하세요.",
            "rules": [
                "비디오 내용 기반 답변",
                "정확한 정보 제공", 
                "친절한 톤 유지"
            ],
            "output_format": {
                "structure": "답변 → 근거 → 요약",
                "max_bullets": 3,
                "include_video_links": False
            }
        }


def main():
    """테스트 실행"""
    try:
        manager = PromptManager()
        
        print("📋 사용 가능한 채널:")
        channels = manager.list_available_channels_for_analysis()
        for i, channel in enumerate(channels, 1):
            print(f"  {i}. {channel}")
        
        print("\n📝 프롬프트가 있는 채널:")
        channels_with_prompts = manager.list_channels_with_prompts()
        for info in channels_with_prompts:
            print(f"  - {info['name']} (v{info['active_version']}, {info['total_versions']}개 버전)")
        
        # 첫 번째 채널로 테스트
        if channels:
            test_channel = channels[0]
            print(f"\n🧪 {test_channel} 프롬프트 로드 테스트...")
            prompt = manager.get_channel_prompt(test_channel)
            print(f"  페르소나: {prompt.get('persona', 'N/A')}")
            
    except Exception as e:
        print(f"❌ 오류: {e}")


if __name__ == "__main__":
    main()