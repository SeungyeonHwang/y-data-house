#!/usr/bin/env python3
"""
DeepSeek RAG 시스템 - 98개 영상 자막을 자연어로 검색하고 AI가 답변
개떡같이 말해도 찰떡같이 알아듣는 시스템 v4.0 - HyDE + Query Rewriting
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

아래는 98개 도쿄부동산 영상에서 찾은 **가장 관련성 높은** 내용들입니다. 직접적인 언급이 없어도 **비슷한 패턴, 투자 원칙, 지역 특성**을 바탕으로 최대한 도움되는 조언을 제공하세요.

## 컨텍스트 (관련 영상들)
{context}

## 사용자 질문
{query}

## 답변 작성 지침
1. **5개 영상의 정보만 활용**하여 집중된 조언 제공
2. **5개 이하 핵심 bullet**(`- `)로 작성하고, 각 bullet 끝에 `[영상 n]` 표시
3. 직접 언급이 없어도 **"도쿄/사이타마 사례로 유추하면..."** 식으로 연결해서 조언
4. **구체적 수치, 지역명, 투자 전략**을 포함하여 실용성 높이기
5. 마지막에 `### 💡 한 줄 요약:` 형식으로 핵심 정리
6. **무조건 도움되는 답변**을 만들어야 함 - "모르겠다" 금지

**중요**: 영상에서 직접 언급되지 않은 지역이라도, 비슷한 투자 패턴이나 원칙을 적용해서 조언해주세요.
"""

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

    def generate_hyde_documents(self, query: str, n_docs=2):
        """HyDE: 2개 가상 문서 생성 후 TOP-k 교차 선택"""
        hyde_docs = []
        
        for i in range(n_docs):
            try:
                response = self.client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[
                        {"role": "system", "content": "당신은 일본 부동산 투자 전문가입니다. 사용자 질문에 대한 완벽한 답변을 담은 150토큰 내외의 가상 문서를 작성하세요."},
                        {"role": "user", "content": f"다음 질문에 대한 완벽한 답변이 담긴 문서를 작성해주세요: '{query}'\n\n답변에는 구체적인 수치, 지역명, 투자 전략이 포함되어야 합니다. 변형 {i+1}번째 관점으로 작성하세요."}
                    ],
                    max_tokens=150,  # 토큰 길이 제한
                    temperature=0.7 + (i * 0.2)  # 다양성을 위한 온도 조절
                )
                
                hyde_doc = response.choices[0].message.content.strip()
                hyde_docs.append(hyde_doc)
                print(f"🎯 HyDE 문서 {i+1} 생성: {hyde_doc[:60]}...")
                
            except Exception as e:
                print(f"⚠️ HyDE 문서 {i+1} 생성 실패: {e}")
                continue
        
        return hyde_docs if hyde_docs else [None]

    def rewrite_query(self, query: str, context_sample: str = ""):
        """Query Rewriting: 검색 최적화된 질문으로 재작성 (60토큰 제한)"""
        try:
            prompt = f"""당신은 검색 전문가입니다. 사용자의 질문을 검색 엔진이 이해하기 쉬운 형태로 재작성하세요.

## 원본 질문
{query}

## 컨텍스트 샘플
{context_sample[:200]}

### 지시사항
원본 질문을 다음 중 하나로 변환하세요:
1. 핵심 키워드 + 필터가 포함된 검색 쿼리
2. 구체적인 조건과 용어가 명확한 질문

예시: "좋은 지역?" → "도쿄 사이타마 수익률 높은 부동산 투자 지역 추천"
**60토큰 이내로 간결하게 작성하세요.**
"""
            
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": "당신은 검색 질의 최적화 전문가입니다."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=60,  # 토큰 길이 제한 강화
                temperature=0.5
            )
            
            rewritten = response.choices[0].message.content.strip()
            print(f"🔄 Query Rewriting: {rewritten}")
            return rewritten
            
        except Exception as e:
            print(f"⚠️ Query Rewriting 실패: {e}")
            return query  # fallback to original

    def expand_keywords_with_llm(self, query: str):
        """LLM으로 키워드 동적 확장"""
        try:
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": "당신은 일본 부동산 투자 전문가입니다. 사용자 질문에서 핵심 키워드 3-5개를 추출하여 검색에 활용할 수 있게 도와주세요."},
                    {"role": "user", "content": f"다음 질문에서 일본 부동산 투자 관련 핵심 키워드를 3-5개 추출해주세요: '{query}'\n\n답변 형식: 키워드1, 키워드2, 키워드3"}
                ],
                max_tokens=100,
                temperature=0.3
            )
            
            keywords_text = response.choices[0].message.content.strip()
            keywords = [k.strip() for k in keywords_text.split(',')]
            print(f"🧠 LLM 키워드 확장: {keywords}")
            return keywords[:5]  # 최대 5개
            
        except Exception as e:
            print(f"⚠️ LLM 키워드 확장 실패: {e}")
            # fallback to manual extraction
            return self._manual_extract_keywords(query)

    def _manual_extract_keywords(self, query: str):
        """수동 키워드 추출 (LLM 실패시 fallback)"""
        keywords = []
        if "후쿠오카" in query:
            keywords.extend(["지방", "큐슈", "도시", "투자"])
        if "투자" in query:
            keywords.extend(["수익률", "재개발", "부동산"])
        if "지역" in query:
            keywords.extend(["도쿄", "사이타마", "위치"])
        if "원룸" in query:
            keywords.extend(["원룸", "임대", "단신"])
        
        return keywords[:3]

    def multi_search_v3(self, query: str):
        """HyDE + Query Rewriting + 다중 검색 전략 (v3.0 - Precision 보정)"""
        all_results = []
        
        # 1차: 원본 질문
        print(f"🔍 1차 검색: '{query}'")
        results1 = self._single_search(query, n_results=2)
        if results1:
            all_results.extend(self._format_results(results1, "원본질문"))
        
        # 2차: HyDE (2개 문서 생성 후 TOP-k 교차 선택)
        hyde_docs = self.generate_hyde_documents(query, n_docs=2)
        for i, hyde_doc in enumerate(hyde_docs):
            if hyde_doc:
                print(f"🔍 HyDE-{i+1} 검색")
                hyde_results = self._single_search(hyde_doc, n_results=1)  # 각각 1개씩만
                if hyde_results:
                    all_results.extend(self._format_results(hyde_results, f"HyDE-{i+1}"))
        
        # 3차: Query Rewriting (질문 재작성 후 검색)
        context_sample = all_results[0]['content'] if all_results else ""
        rewritten_query = self.rewrite_query(query, context_sample)
        if rewritten_query != query:
            print(f"🔍 Rewritten 검색")
            rewritten_results = self._single_search(rewritten_query, n_results=2)
            if rewritten_results:
                all_results.extend(self._format_results(rewritten_results, "Rewritten"))
        
        # 4차: LLM 기반 키워드 확장 검색 (상위 1개만)
        expanded_keywords = self.expand_keywords_with_llm(query)
        for keyword in expanded_keywords[:1]:  # 상위 1개만으로 축소
            print(f"🔍 확장 키워드: '{keyword}'")
            results = self._single_search(keyword, n_results=1)
            if results:
                all_results.extend(self._format_results(results, f"LLM키워드:{keyword}"))
        
        # 중복 제거 및 점수순 정렬
        unique_results = self._deduplicate_results(all_results)
        
        # Precision 보정: 유사도 컷오프 + 메타데이터 필터
        filtered_results = [
            r for r in unique_results 
            if r['similarity'] > 0.30  # 0.15 → 0.30으로 상향
            and ("부동산" in r['title'] or "투자" in r['title'] or "도쿄" in r['title'])  # 메타 키워드 필터
        ]
        
        # 필터링 결과가 너무 적으면 유사도만으로 fallback
        if len(filtered_results) < 2:
            print("⚠️ 메타 필터 결과 부족, 유사도만으로 fallback")
            filtered_results = [r for r in unique_results if r['similarity'] > 0.25]
        
        print(f"📊 필터링: {len(unique_results)} → {len(filtered_results)} (유사도≥0.30 + 메타필터)")
        
        return filtered_results[:5]  # 최대 5개 고품질 결과

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

    def _format_results(self, results, search_type):
        """검색 결과를 통합 포맷으로 변환 (duration 정보 추가)"""
        formatted = []
        for i, (doc, metadata, distance) in enumerate(zip(
            results['documents'][0],
            results['metadatas'][0], 
            results['distances'][0]
        )):
            # duration 정보 추출 (안전하게)
            duration = metadata.get('duration', 'N/A') if metadata else 'N/A'
            
            formatted.append({
                'video_id': metadata.get('video_id', 'unknown') if metadata else 'unknown',
                'title': metadata.get('title', 'Unknown Title') if metadata else 'Unknown Title',
                'content': doc,
                'metadata': metadata if metadata else {},
                'distance': distance,
                'search_type': search_type,
                'similarity': 1 - distance,
                'duration': duration
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
        """개선된 답변 생성 - 5개 영상으로 집중된 분석"""
        if not search_results:
            return "❌ 관련 영상을 찾을 수 없습니다."
        
        # 컨텍스트 구성 - 더 집중된 정보
        context_parts = []
        for i, result in enumerate(search_results):
            duration = result.get('duration', 'N/A')
            context_parts.append(
                f"[영상 {i+1}] {result['title']} (길이: {duration}, 유사도: {result['similarity']:.2f})\n"
                f"업로드: {result['metadata']['upload']} | 채널: {result['metadata']['channel']}\n"
                f"내용: {result['content'][:800]}...\n"  # 더 많은 컨텍스트
            )
        
        context = "\n---\n".join(context_parts)
        # .format() 에서 중괄호 충돌 방지
        context_safe = context.replace("{", "{{").replace("}", "}}")
        prompt = PROMPT_TEMPLATE.format(context=context_safe, query=query)

        try:
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": "당신은 일본 부동산 투자 전문가입니다. 제공된 5개 영상의 정보만을 최대한 활용하여 도움되는 답변을 제공하세요. 직접 언급이 없어도 비슷한 패턴을 유추해서 조언하고, '모르겠다'는 답변은 절대 금지입니다."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=2000,
                temperature=0.7  # 창의적 연결을 위해 적당한 수준
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            return f"❌ DeepSeek API 오류: {e}"

    def chat(self, query: str):
        """스마트 RAG 파이프라인 실행 (HyDE + Rewriting v3.0 - Precision 보정)"""
        print(f"🚀 HyDE + Rewriting RAG v3.0 시작: '{query}'")
        
        # HyDE + Query Rewriting + 다중 검색 전략 실행 (Precision 보정)
        search_results = self.multi_search_v3(query)
        
        if not search_results:
            print("❌ 모든 검색 전략 실패")
            return "❌ 관련 영상을 찾을 수 없습니다."
        
        print(f"✅ {len(search_results)}개 고품질 영상 발견 (Precision 보정 적용)")
        
        # 발견된 영상들 미리보기 (유사도 상세 표시)
        for i, result in enumerate(search_results):
            duration = result.get('duration', 'N/A')
            print(f"   {i+1}. [{result['similarity']:.3f}] {result['title'][:40]}... ({duration}, {result['search_type']})")
        
        # AI 답변 생성
        print("🤖 DeepSeek 최종 답변 생성 중...")
        answer = self.generate_answer(query, search_results)
        
        # 참고 영상 목록 (더 상세한 정보)
        references = "\n\n📚 **참고 영상 (Precision 보정 적용):**\n"
        for i, result in enumerate(search_results):
            duration = result.get('duration', 'N/A')
            references += f"{i+1}. {result['title']} ({result['metadata']['upload']}, {duration}) - 유사도 {result['similarity']:.1%} [{result['search_type']}]\n"
        
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