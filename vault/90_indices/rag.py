#!/usr/bin/env python3
"""
DeepSeek RAG 시스템 - 채널별 완전 격리 검색
개떡같이 말해도 찰떡같이 알아듣는 시스템 v6.0 - 채널별 완전 격리 + HyDE + Query Rewriting
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import chromadb
from chromadb.config import Settings as ChromaSettings
from openai import OpenAI
import re
from prompt_manager import PromptManager

# ---------------- 개선된 Prompt template ----------------
PROMPT_TEMPLATE = """당신은 일본 부동산 투자 전문 AI 어시스턴트입니다.

아래는 **{channel_name} 채널**에서 찾은 **가장 관련성 높은** 내용들입니다. 직접적인 언급이 없어도 **비슷한 패턴, 투자 원칙, 지역 특성**을 바탕으로 최대한 도움되는 조언을 제공하세요.

## 컨텍스트 (관련 영상들)
{context}

## 사용자 질문
{query}

## 답변 작성 지침
1. **{channel_name} 채널의 정보만 활용**하여 집중된 조언 제공
2. **5개 이하 핵심 bullet**(`- `)로 작성하고, 각 bullet 끝에 `[영상 n]` 표시
3. 직접 언급이 없어도 **"이 채널의 다른 사례로 유추하면..."** 식으로 연결해서 조언
4. **구체적 수치, 지역명, 투자 전략**을 포함하여 실용성 높이기
5. 마지막에 `### 💡 한 줄 요약:` 형식으로 핵심 정리
6. **무조건 도움되는 답변**을 만들어야 함 - "모르겠다" 금지

**중요**: 영상에서 직접 언급되지 않은 지역이라도, 이 채널의 다른 투자 패턴이나 원칙을 적용해서 조언해주세요.
"""

# 환경변수 로드
load_dotenv()

# DeepSeek 클라이언트 초기화
def create_deepseek_client():
    """DeepSeek API 클라이언트 생성"""
    api_key = os.getenv('DEEPSEEK_API_KEY')
    if not api_key:
        raise ValueError("❌ DEEPSEEK_API_KEY 환경변수가 설정되지 않았습니다.")
    
    client = OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com/v1"
    )
    return client

# 경로 설정
VAULT_ROOT = Path(__file__).parent.parent
CHROMA_PATH = VAULT_ROOT / "90_indices" / "chroma"

def sanitize_collection_name(name: str) -> str:
    """ChromaDB 컬렉션 이름 정리 (특수문자 제거)"""
    sanitized = re.sub(r'[^\w가-힣]', '_', name)
    sanitized = re.sub(r'_+', '_', sanitized).strip('_')
    return sanitized[:50] if sanitized else "unknown_channel"

class ChannelRAG:
    def __init__(self, model: str = "deepseek-chat"):
        """채널별 격리 RAG 시스템 초기화"""
        # 모델명 저장
        self.model = model
        print(f"🤖 사용 모델: {model}")
        
        # DeepSeek 클라이언트 초기화
        try:
            self.client = create_deepseek_client()
            print("✅ DeepSeek API 클라이언트 초기화 완료")
        except Exception as e:
            raise ValueError(f"❌ DeepSeek API 초기화 실패: {e}")
        
        # ChromaDB 클라이언트 초기화
        try:
            self.chroma_client = chromadb.PersistentClient(
                path=str(CHROMA_PATH),
                settings=ChromaSettings(anonymized_telemetry=False)
            )
            print(f"✅ ChromaDB 연결됨: {CHROMA_PATH}")
        except Exception as e:
            raise ValueError(f"❌ ChromaDB 로드 실패: {e}\n'python embed.py'를 먼저 실행하세요.")
        
        # 프롬프트 매니저 초기화
        try:
            self.prompt_manager = PromptManager(chroma_path=CHROMA_PATH)
            print(f"✅ PromptManager 초기화 완료: {CHROMA_PATH.parent}/prompts")
        except Exception as e:
            print(f"⚠️ 프롬프트 매니저 초기화 실패: {e}")
            self.prompt_manager = None
    
    def list_available_channels(self):
        """사용 가능한 채널 목록 반환"""
        try:
            collections = self.chroma_client.list_collections()
            channels = []
            
            for collection in collections:
                if collection.name.startswith("channel_"):
                    try:
                        data = collection.get()
                        if data['metadatas'] and len(data['metadatas']) > 0:
                            channel_name = data['metadatas'][0].get('channel', 'Unknown')
                            video_count = len(data['ids']) if data['ids'] else 0
                            isolated = data['metadatas'][0].get('isolated_channel', False)
                            
                            channels.append({
                                'name': channel_name,
                                'collection_name': collection.name,
                                'video_count': video_count,
                                'isolated': isolated
                            })
                    except Exception:
                        continue
            
            return sorted(channels, key=lambda x: x['video_count'], reverse=True)
        except Exception as e:
            print(f"⚠️ 채널 목록 조회 실패: {e}")
            return []

    def get_collection_by_channel(self, channel_name: str):
        """채널명으로 컬렉션 가져오기"""
        try:
            collections = self.chroma_client.list_collections()
            
            for collection in collections:
                if collection.name.startswith("channel_"):
                    # 컬렉션에서 샘플 데이터 가져와서 채널명 확인
                    try:
                        sample = collection.get(limit=1, include=['metadatas'])
                        if sample['metadatas'] and sample['metadatas'][0]:
                            metadata_channel = sample['metadatas'][0].get('channel', '')
                            if metadata_channel == channel_name:
                                return collection
                    except:
                        continue
            
            return None
        except Exception as e:
            print(f"❌ 컬렉션 검색 실패: {e}")
            return None

    def generate_channel_specific_hyde(self, query: str, channel_name: str, channel_prompt: dict = None):
        """채널 특화 HyDE 문서 생성"""
        if not channel_prompt and self.prompt_manager:
            channel_prompt = self.prompt_manager.get_channel_prompt(channel_name)
        
        try:
            persona = channel_prompt.get('persona', '전문가') if channel_prompt else '전문가'
            tone = channel_prompt.get('tone', '전문적인 스타일') if channel_prompt else '전문적인 스타일'
            
            prompt = f"""당신은 {channel_name} 채널의 {persona}입니다. 
{tone}로 다음 질문에 대한 완벽한 답변이 담긴 150토큰 내외의 가상 문서를 작성하세요.

질문: {query}

이 채널의 관점에서 구체적인 수치, 지역명, 전략이 포함된 답변을 작성해주세요."""

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": f"당신은 {channel_name} 채널 전문가입니다."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=150,
                temperature=0.7
            )
            
            hyde_doc = response.choices[0].message.content.strip()
            print(f"🎯 {channel_name} 채널 특화 HyDE: {hyde_doc[:50]}...")
            return hyde_doc
            
        except Exception as e:
            print(f"⚠️ 채널 특화 HyDE 생성 실패: {e}")
            return None

    def generate_hyde_documents(self, query: str, channel_name: str, n_docs=1):
        """기존 HyDE + 채널 특화 HyDE"""
        hyde_docs = []
        
        # 1. 채널 특화 HyDE
        if self.prompt_manager:
            channel_hyde = self.generate_channel_specific_hyde(query, channel_name)
            if channel_hyde:
                hyde_docs.append(channel_hyde)
        
        # 2. 기존 방식 HyDE (보완용)
        for i in range(n_docs):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": f"당신은 {channel_name} 채널의 일본 부동산 투자 전문가입니다."},
                        {"role": "user", "content": f"다음 질문에 대한 완벽한 답변이 담긴 문서를 {channel_name} 채널 관점에서 작성해주세요: '{query}'\n\n답변에는 구체적인 수치, 지역명, 투자 전략이 포함되어야 합니다."}
                    ],
                    max_tokens=150,
                    temperature=0.7
                )
                
                hyde_doc = response.choices[0].message.content.strip()
                hyde_docs.append(hyde_doc)
                print(f"🎯 {channel_name} 기본 HyDE {i+1}: {hyde_doc[:50]}...")
                
            except Exception as e:
                print(f"⚠️ HyDE 문서 생성 실패: {e}")
                continue
        
        return hyde_docs if hyde_docs else [None]

    def rewrite_query(self, query: str, channel_name: str, context_sample: str = ""):
        """Query Rewriting: 특정 채널 맥락에서 검색 최적화"""
        # 채널 프롬프트 가져오기
        channel_prompt = {}
        if self.prompt_manager:
            channel_prompt = self.prompt_manager.get_channel_prompt(channel_name)
        
        try:
            # 채널 특성 반영
            expertise_keywords = channel_prompt.get('expertise_keywords', [])
            keywords_hint = f"주요 키워드: {', '.join(expertise_keywords[:5])}" if expertise_keywords else ""
            
            prompt = f"""당신은 {channel_name} 채널 전문 검색 전문가입니다. 사용자의 질문을 이 채널의 컨텐츠에서 검색하기 쉬운 형태로 재작성하세요.

## 원본 질문
{query}

## 채널 컨텍스트
{context_sample[:200]}

## 채널 특성
{keywords_hint}

### 지시사항
{channel_name} 채널의 영상에서 찾을 수 있는 핵심 키워드와 개념을 포함한 검색 쿼리로 재작성하세요.
**60토큰 이내로 간결하게 작성하세요.**
"""
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": f"당신은 {channel_name} 채널 전문 검색 질의 최적화 전문가입니다."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=60,
                temperature=0.3
            )
            
            rewritten = response.choices[0].message.content.strip()
            print(f"🔄 {channel_name} Query Rewriting: {rewritten}")
            return rewritten
            
        except Exception as e:
            print(f"⚠️ Query Rewriting 실패: {e}")
            return query

    def channel_search(self, query: str, channel_name: str):
        """채널별 격리 검색 (HyDE + Query Rewriting)"""
        collection = self.get_collection_by_channel(channel_name)
        if not collection:
            return []
        
        print(f"🔍 {channel_name} 채널 검색 시작")
        
        all_results = []
        
        # 1차: 원본 질문
        print(f"  📝 1차 검색: '{query}'")
        results1 = self._single_search_on_collection(collection, query, n_results=3)
        if results1:
            all_results.extend(self._format_results(results1, f"원본질문", channel_name))
        
        # 2차: HyDE
        hyde_docs = self.generate_hyde_documents(query, channel_name, n_docs=1)
        for hyde_doc in hyde_docs:
            if hyde_doc:
                print(f"  🎯 HyDE 검색")
                hyde_results = self._single_search_on_collection(collection, hyde_doc, n_results=3)
                if hyde_results:
                    all_results.extend(self._format_results(hyde_results, f"HyDE", channel_name))
        
        # 3차: Query Rewriting
        context_sample = all_results[0]['content'] if all_results else ""
        rewritten_query = self.rewrite_query(query, channel_name, context_sample)
        if rewritten_query != query:
            print(f"  🔄 Rewritten 검색")
            rewritten_results = self._single_search_on_collection(collection, rewritten_query, n_results=3)
            if rewritten_results:
                all_results.extend(self._format_results(rewritten_results, f"Rewritten", channel_name))
        
        # 중복 제거 및 점수순 정렬
        unique_results = self._deduplicate_results(all_results)
        
        # LLM Re-Ranker
        if len(unique_results) > 5:
            candidates = unique_results[:8]
            filtered_results = self._llm_rerank_filter(query, candidates, channel_name)
        else:
            filtered_results = self._llm_rerank_filter(query, unique_results, channel_name)
            if len(filtered_results) < 2:
                print("⚠️ LLM 필터 결과 부족, 유사도 0.25+ fallback")
                filtered_results = [r for r in unique_results if r['similarity'] > 0.25]
        
        print(f"📊 {channel_name} 검색 완료: {len(unique_results)} → {len(filtered_results)}")
        
        return filtered_results[:5]

    def _single_search_on_collection(self, collection, query: str, n_results: int = 5):
        """단일 컬렉션에서 검색 실행"""
        try:
            results = collection.query(
                query_texts=[query],
                n_results=n_results,
                include=["distances", "metadatas", "documents"]
            )
            return results if results["documents"][0] else None
        except Exception as e:
            print(f"⚠️ 검색 오류: {e}")
            return None

    def _format_results(self, results, search_type, channel_name):
        """검색 결과를 통합 포맷으로 변환"""
        formatted = []
        for i, (doc, metadata, distance) in enumerate(zip(
            results['documents'][0],
            results['metadatas'][0], 
            results['distances'][0]
        )):
            duration = metadata.get('duration', 'N/A') if metadata else 'N/A'
            
            formatted.append({
                'video_id': metadata.get('video_id', 'unknown') if metadata else 'unknown',
                'title': metadata.get('title', 'Unknown Title') if metadata else 'Unknown Title',
                'content': doc,
                'metadata': metadata if metadata else {},
                'distance': distance,
                'search_type': search_type,
                'similarity': 1 - distance,
                'duration': duration,
                'channel': channel_name
            })
        return formatted

    def _deduplicate_results(self, all_results):
        """video_id 기준으로 중복 제거 및 최고 점수 유지"""
        seen_videos = {}
        for result in all_results:
            video_id = result['video_id']
            if video_id not in seen_videos or result['similarity'] > seen_videos[video_id]['similarity']:
                seen_videos[video_id] = result
        
        return sorted(seen_videos.values(), key=lambda x: x['similarity'], reverse=True)

    def _llm_rerank_filter(self, query: str, candidates: list, channel_name: str):
        """LLM Re-Ranker: 채널별 관련성 판단"""
        if not candidates:
            return []
        
        try:
            candidate_info = []
            for i, result in enumerate(candidates):
                candidate_info.append(
                    f"영상 {i+1}: {result['title']}\n"
                    f"내용: {result['content'][:200]}...\n"
                    f"유사도: {result['similarity']:.3f}"
                )
            
            candidates_text = "\n---\n".join(candidate_info)
            
            prompt = f"""당신은 {channel_name} 채널의 일본 부동산 투자 전문가입니다. 사용자 질문에 가장 도움이 될 이 채널의 영상들을 선별해주세요.

## 사용자 질문
{query}

## {channel_name} 채널 후보 영상들
{candidates_text}

### 평가 기준
1. **{channel_name} 채널의 관점**에서 질문과 직접 관련된 내용
2. **이 채널의 투자 철학**과 일치하는 간접적 유용성
3. **실용적 가치**: 구체적 수치, 전략, 경험담 포함
4. **채널 일관성**: 이 채널의 다른 영상과 연결되는 내용

### 출력 형식
선별된 영상 번호를 우선순위대로 나열하세요. (예: 1,3,5,2)
최대 5개까지 선택하되, 정말 관련 없는 영상은 제외하세요."""

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": f"당신은 {channel_name} 채널 전문 컨텐츠 관련성 평가 전문가입니다."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=50,
                temperature=0.1
            )
            
            selection = response.choices[0].message.content.strip()
            print(f"🤖 {channel_name} LLM 선별: {selection}")
            
            try:
                selected_indices = [int(x.strip()) - 1 for x in selection.replace(' ', '').split(',') if x.strip().isdigit()]
                filtered = [candidates[i] for i in selected_indices if 0 <= i < len(candidates)]
                
                if len(filtered) >= 2:
                    return filtered
                else:
                    print("⚠️ LLM 선별 결과 부족, 유사도 기반 fallback")
                    return [r for r in candidates if r['similarity'] > 0.3][:5]
                    
            except Exception:
                print("⚠️ LLM 선별 파싱 실패, 유사도 기반 fallback")
                return [r for r in candidates if r['similarity'] > 0.3][:5]
                
        except Exception as e:
            print(f"⚠️ LLM Re-Ranking 실패: {e}")
            return [r for r in candidates if r['similarity'] > 0.3][:5]

    def generate_answer_with_channel_prompt(self, query: str, search_results: list, channel_name: str):
        """채널별 프롬프트를 활용한 답변 생성"""
        if not search_results:
            return f"죄송합니다. {channel_name} 채널에서 관련된 정보를 찾을 수 없습니다."
        
        # 채널별 프롬프트 로드
        channel_prompt = {}
        if self.prompt_manager:
            channel_prompt = self.prompt_manager.get_channel_prompt(channel_name)
        
        # 컨텍스트 구성
        context_parts = []
        for i, result in enumerate(search_results):
            title = result['title']
            content_preview = result['content'][:600]
            video_id = result.get('video_id', '')
            context_parts.append(f"[영상 {i+1}] {title}\n내용: {content_preview}\n영상ID: {video_id}")
        
        context = "\n\n".join(context_parts)
        
        # 채널별 맞춤 프롬프트 구성
        system_prompt = channel_prompt.get('system_prompt', '').replace('{{channel_name}}', channel_name)
        if not system_prompt:
            system_prompt = f"당신은 {channel_name} 채널 전문 AI 어시스턴트입니다."
        
        rules = "\n".join([f"- {rule}" for rule in channel_prompt.get('rules', [])])
        output_format = channel_prompt.get('output_format', {})
        structure = output_format.get('structure', '답변 → 근거 → 요약')
        
        final_prompt = f"""{system_prompt}

## 답변 규칙
{rules}

## 답변 구조
{structure}

## 검색된 컨텍스트 ({channel_name} 채널)
{context}

## 사용자 질문
{query}

위 규칙과 구조에 따라 {channel_name} 채널의 정보만을 바탕으로 답변해주세요."""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": f"당신은 {channel_name} 채널 전문 AI 어시스턴트입니다."},
                    {"role": "user", "content": final_prompt}
                ],
                max_tokens=800,
                temperature=0.7
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            return f"답변 생성 중 오류가 발생했습니다: {e}"

    def generate_answer(self, query: str, search_results: list, channel_name: str):
        """기존 답변 생성 (호환성 유지)"""
        if self.prompt_manager:
            return self.generate_answer_with_channel_prompt(query, search_results, channel_name)
        
        # 프롬프트 매니저가 없는 경우 기존 방식 사용
        if not search_results:
            return f"죄송합니다. {channel_name} 채널에서 관련된 정보를 찾을 수 없습니다. 다른 키워드로 다시 시도해보세요."
        
        # 컨텍스트 구성
        context_parts = []
        for i, result in enumerate(search_results):
            title = result['title']
            content_preview = result['content'][:800]
            context_parts.append(f"[영상 {i+1}] {title}\n{content_preview}")
        
        context = "\n\n".join(context_parts)
        
        prompt = PROMPT_TEMPLATE.format(
            context=context,
            query=query,
            channel_name=channel_name
        )
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": f"당신은 {channel_name} 채널 전문 일본 부동산 투자 AI 어시스턴트입니다. 이 채널의 정보만을 바탕으로 실용적이고 구체적인 조언을 제공하세요."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=800,
                temperature=0.7
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            return f"답변 생성 중 오류가 발생했습니다: {e}"

    def chat(self, query: str, channel_name: str, show_progress: bool = False):
        """메인 대화 함수 - 채널별 격리 검색"""
        if show_progress:
            # 진행 상황 출력
            import json
            import sys
            import time
            
            # 1. 벡터 검색 시작
            progress_data = {
                "step": "벡터 검색",
                "message": f"🔍 {channel_name} 채널에서 벡터 검색 중...",
                "progress": 10.0,
                "details": f"질문: {query[:50]}..."
            }
            print(f"PROGRESS:{json.dumps(progress_data, ensure_ascii=False)}")
            sys.stdout.flush()
            time.sleep(0.5)
            
        print(f"🤔 질문: {query}")
        print(f"🎯 채널: {channel_name}")
        
        # 채널별 검색 실행
        search_results = self.channel_search(query, channel_name)
        
        if show_progress:
            # 2. 답변 생성 시작
            progress_data = {
                "step": "답변 생성",
                "message": f"🤖 DeepSeek으로 답변 생성 중...",
                "progress": 80.0,
                "details": f"검색 결과: {len(search_results)}개"
            }
            print(f"PROGRESS:{json.dumps(progress_data, ensure_ascii=False)}")
            sys.stdout.flush()
            time.sleep(0.5)
        
        if not search_results:
            return f"{channel_name} 채널에서 관련된 정보를 찾을 수 없습니다. 다른 키워드로 시도해보세요."
        
        # 답변 생성
        answer = self.generate_answer(query, search_results, channel_name)
        
        if show_progress:
            # 3. 완료
            progress_data = {
                "step": "완료",
                "message": "✅ 답변 생성 완료",
                "progress": 100.0,
                "details": None
            }
            print(f"PROGRESS:{json.dumps(progress_data, ensure_ascii=False)}")
            sys.stdout.flush()
            print("FINAL_ANSWER:")
            sys.stdout.flush()
        
        return answer

def main():
    """메인 실행 함수"""
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
        
        rag = ChannelRAG(model=model)
        
        if len(sys.argv) < 2:
            print("🤖 Y-Data House RAG v6.0 (채널별 완전 격리)")
            print("\n📋 사용법:")
            print("  python rag.py channels                   # 사용 가능한 채널 목록")
            print("  python rag.py '질문' 채널명              # 특정 채널에서 검색")
            print("\n📚 예시:")
            print("  python rag.py '도쿄 투자 전략' takaki_takehana")
            print("  python rag.py '수익률 좋은 지역' 도쿄부동산")
            
            # 사용 가능한 채널 표시
            channels = rag.list_available_channels()
            if channels:
                print(f"\n📺 사용 가능한 채널 ({len(channels)}개):")
                for i, ch in enumerate(channels, 1):
                    status = "🔐 격리됨" if ch['isolated'] else "📂 일반"
                    print(f"  {i}. {ch['name']} ({ch['video_count']}개 영상) {status}")
            
            return
        
        command = sys.argv[1]
        
        if command == "channels":
            # 채널 목록 출력
            channels = rag.list_available_channels()
            if channels:
                print(f"📺 사용 가능한 채널 ({len(channels)}개):")
                for i, ch in enumerate(channels, 1):
                    status = "🔐 격리됨" if ch['isolated'] else "📂 일반"
                    print(f"  {i}. {ch['name']} ({ch['video_count']}개 영상) {status}")
            else:
                print("사용 가능한 채널이 없습니다. 'python embed.py'를 먼저 실행하세요.")
            return
        
        # 질문 + 채널 처리
        if len(sys.argv) < 3:
            print("❌ 채널명이 필요합니다.")
            print("사용법: python rag.py '질문' 채널명 [--progress]")
            print("예시: python rag.py '도쿄 투자 전략' takaki_takehana")
            print("예시: python rag.py '도쿄 투자 전략' takaki_takehana --progress")
            return
        
        query = command
        channel_name = sys.argv[2]
        
        # --progress 옵션 확인
        show_progress = "--progress" in sys.argv
        
        # 채널 존재 확인
        if not rag.get_collection_by_channel(channel_name):
            print(f"❌ 채널 '{channel_name}'을 찾을 수 없습니다.")
            
            # 사용 가능한 채널 제안
            channels = rag.list_available_channels()
            if channels:
                print(f"\n사용 가능한 채널:")
                for ch in channels:
                    print(f"  - {ch['name']}")
            return
        
        # RAG 검색 및 답변 생성
        answer = rag.chat(query, channel_name, show_progress)
        
        if not show_progress:
            print(f"\n🤖 **{channel_name} 채널 답변:**")
        print(answer)
        
    except Exception as e:
        print(f"❌ 오류: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 