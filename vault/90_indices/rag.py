#!/usr/bin/env python3
"""
DeepSeek RAG 시스템 - 98개 영상 자막을 자연어로 검색하고 AI가 답변
개떡같이 말해도 찰떡같이 알아듣는 시스템 v2.0
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import chromadb
from chromadb.config import Settings as ChromaSettings
from openai import OpenAI

# ---------------- 개선된 Prompt template ----------------
PROMPT_TEMPLATE = """당신은 일본 부동산 투자 전문 AI 어시스턴트입니다.

아래는 98개 도쿄부동산 영상에서 찾은 관련 내용들입니다. 직접적인 언급이 없어도 **비슷한 패턴, 투자 원칙, 지역 특성**을 바탕으로 최대한 도움되는 조언을 제공하세요.

## 컨텍스트 (관련 영상들)
{context}

## 사용자 질문
{query}

## 답변 작성 지침
1. **98개 영상 내 정보만 활용**하여 최대한 유용한 답변을 구성하세요
2. **5개 이하 핵심 bullet**(`- `)로 작성하고, 각 bullet 끝에 `[영상 n]` 표시
3. 직접 언급이 없어도 **"도쿄/사이타마 사례로 유추하면..."** 식으로 연결해서 조언
4. **구체적 수치, 지역명, 투자 전략**을 포함하여 실용성 높이기
5. 마지막에 `### 💡 한 줄 요약:` 형식으로 핵심 정리
6. **무조건 도움되는 답변**을 만들어야 함 - "모르겠다" 금지

**중요**: 영상에서 직접 언급되지 않은 지역이라도, 비슷한 투자 패턴이나 원칙을 적용해서 조언해주세요.
"""

# 초관대한 임계값 - 거의 모든 결과 수용
SIMILARITY_THRESHOLD = 1.5   # 0.4 → 1.5로 대폭 완화

# 환경변수 로드
load_dotenv()

# 경로 설정
VAULT_ROOT = Path(__file__).parent.parent
CHROMA_PATH = VAULT_ROOT / "90_indices" / "chroma"

class SmartRAG:
    def __init__(self):
        """스마트 RAG 시스템 초기화"""
        self.api_key = os.getenv("DEEPSEEK_API_KEY")
        if not self.api_key:
            raise ValueError("❌ DEEPSEEK_API_KEY가 설정되지 않았습니다. .env 파일을 확인하세요.")
        
        # DeepSeek 클라이언트 초기화
        self.client = OpenAI(
            api_key=self.api_key,
            base_url="https://api.deepseek.com"
        )
        
        # ChromaDB 클라이언트 초기화
        try:
            self.chroma_client = chromadb.PersistentClient(
                path=str(CHROMA_PATH),
                settings=ChromaSettings(anonymized_telemetry=False)
            )
            self.collection = self.chroma_client.get_collection(
                "video_transcripts",
                embedding_function=None  # 이미 임베딩 저장됨
            )
            print(f"✅ ChromaDB 연결됨: {len(self.collection.get()['ids'])}개 영상")
        except Exception as e:
            raise ValueError(f"❌ ChromaDB 로드 실패: {e}\n'make embed'를 먼저 실행하세요.")

    def multi_search(self, query: str):
        """다중 검색 전략으로 관련 영상 최대한 찾기"""
        all_results = []
        
        # 1차: 원본 질문
        print(f"🔍 1차 검색: '{query}'")
        results1 = self._single_search(query, n_results=5)
        if results1:
            all_results.extend(self._format_results(results1, "원본질문"))
        
        # 2차: 키워드 추출 검색
        keywords = self._extract_keywords(query)
        for keyword in keywords:
            print(f"🔍 키워드 검색: '{keyword}'")
            results = self._single_search(keyword, n_results=3)
            if results:
                all_results.extend(self._format_results(results, f"키워드:{keyword}"))
        
        # 3차: 관련 투자 용어로 확장 검색
        investment_terms = ["투자", "수익률", "재개발", "부동산", "원룸"]
        for term in investment_terms:
            combined_query = f"{query} {term}"
            print(f"🔍 확장 검색: '{combined_query}'")
            results = self._single_search(combined_query, n_results=2)
            if results:
                all_results.extend(self._format_results(results, f"확장:{term}"))
        
        # 중복 제거 및 점수순 정렬
        unique_results = self._deduplicate_results(all_results)
        return unique_results[:8]  # 최대 8개 결과 반환

    def _single_search(self, query: str, n_results: int = 5):
        """단일 검색 실행"""
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=n_results,
                include=["distances", "metadatas", "documents"]
            )
            return results if results["documents"][0] else None
        except Exception as e:
            print(f"⚠️ 검색 오류: {e}")
            return None

    def _extract_keywords(self, query: str):
        """질문에서 핵심 키워드 추출"""
        # 간단한 키워드 추출 (향후 더 정교하게 개선 가능)
        keywords = []
        if "후쿠오카" in query:
            keywords.extend(["지방", "큐슈", "도시", "투자"])
        if "투자" in query:
            keywords.extend(["수익률", "재개발", "부동산"])
        if "지역" in query:
            keywords.extend(["도쿄", "사이타마", "위치"])
        
        return keywords[:3]  # 최대 3개 키워드

    def _format_results(self, results, search_type):
        """검색 결과를 통합 포맷으로 변환"""
        formatted = []
        for i, (doc, metadata, distance) in enumerate(zip(
            results['documents'][0],
            results['metadatas'][0], 
            results['distances'][0]
        )):
            formatted.append({
                'video_id': metadata['video_id'],
                'title': metadata['title'],
                'content': doc,
                'metadata': metadata,
                'distance': distance,
                'search_type': search_type,
                'similarity': 1 - distance
            })
        return formatted

    def _deduplicate_results(self, all_results):
        """video_id 기준으로 중복 제거 및 최고 점수 유지"""
        seen_videos = {}
        for result in all_results:
            video_id = result['video_id']
            if video_id not in seen_videos or result['similarity'] > seen_videos[video_id]['similarity']:
                seen_videos[video_id] = result
        
        # 유사도 순으로 정렬
        return sorted(seen_videos.values(), key=lambda x: x['similarity'], reverse=True)

    def generate_answer(self, query: str, search_results: list):
        """개선된 답변 생성 - 무조건 도움되는 정보 제공"""
        if not search_results:
            return "❌ 관련 영상을 찾을 수 없습니다."
        
        # 컨텍스트 구성
        context_parts = []
        for i, result in enumerate(search_results):
            context_parts.append(
                f"[영상 {i+1}] {result['title']} (유사도: {result['similarity']:.2f}, {result['search_type']})\n"
                f"업로드: {result['metadata']['upload']} | 채널: {result['metadata']['channel']}\n"
                f"내용: {result['content'][:700]}...\n"
            )
        
        context = "\n---\n".join(context_parts)
        prompt = PROMPT_TEMPLATE.format(context=context, query=query)

        try:
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": "당신은 일본 부동산 투자 전문가입니다. 98개 영상의 정보만을 활용하여 최대한 도움되는 답변을 제공하세요. 직접 언급이 없어도 비슷한 패턴을 유추해서 조언하고, '모르겠다'는 답변은 절대 금지입니다."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=2000,
                temperature=0.8  # 창의적 연결을 위해 약간 높임
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            return f"❌ DeepSeek API 오류: {e}"

    def chat(self, query: str):
        """스마트 RAG 파이프라인 실행"""
        print(f"🧠 스마트 검색 시작: '{query}'")
        
        # 다중 검색 전략 실행
        search_results = self.multi_search(query)
        
        if not search_results:
            print("❌ 모든 검색 전략 실패")
            return "❌ 관련 영상을 찾을 수 없습니다."
        
        print(f"✅ {len(search_results)}개 관련 영상 발견 (다중 검색)")
        
        # 발견된 영상들 미리보기
        for i, result in enumerate(search_results[:3]):
            print(f"   {i+1}. [{result['similarity']:.2f}] {result['title'][:50]}... ({result['search_type']})")
        
        # AI 답변 생성
        print("🤖 DeepSeek 답변 생성 중...")
        answer = self.generate_answer(query, search_results)
        
        # 참고 영상 목록
        references = "\n\n📚 **참고 영상:**\n"
        for i, result in enumerate(search_results):
            references += f"{i+1}. {result['title']} ({result['metadata']['upload']}) - 유사도 {result['similarity']:.1%} ({result['search_type']})\n"
        
        return answer + references

def main():
    """메인 실행 함수"""
    if len(sys.argv) < 2:
        print("사용법: python vault/90_indices/rag.py \"질문\"")
        print("\n예시:")
        print('python vault/90_indices/rag.py "후쿠오카는 투자처로 어떻게 생각해"')
        print('python vault/90_indices/rag.py "수익률 높은 지역은 어디?"')
        print('python vault/90_indices/rag.py "18년차 직장인의 투자 전략"')
        return
    
    query = " ".join(sys.argv[1:])
    
    try:
        # 스마트 RAG 시스템 초기화
        rag = SmartRAG()
        
        # 질문-답변 실행
        answer = rag.chat(query)
        
        print("\n" + "="*70)
        print(f"🎯 질문: {query}")
        print("="*70)
        print(answer)
        print("="*70)
        
    except Exception as e:
        print(f"❌ 오류: {e}")

if __name__ == "__main__":
    main() 