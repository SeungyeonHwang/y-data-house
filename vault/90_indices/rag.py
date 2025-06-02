#!/usr/bin/env python3
"""
DeepSeek RAG 시스템 - 98개 영상 자막을 자연어로 검색하고 AI가 답변
개떡같이 말해도 찰떡같이 알아듣는 시스템 v4.0 - HyDE + Query Rewriting + LLM Re-Ranker
하드코딩 필터 완전 제거, LLM이 창의적으로 관련성 판단
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

    def generate_hyde_documents(self, query: str, n_docs=1):
        """HyDE: 1개 가상 문서 생성 (벡터 분산 방지)"""
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



    def multi_search_v3(self, query: str):
        """HyDE + Query Rewriting + 다중 검색 전략 (v3.0 - Precision 보정)"""
        all_results = []
        
        # 1차: 원본 질문
        print(f"🔍 1차 검색: '{query}'")
        results1 = self._single_search(query, n_results=2)
        if results1:
            all_results.extend(self._format_results(results1, "원본질문"))
        
        # 2차: HyDE (1개 문서 생성으로 노이즈 감소)
        hyde_docs = self.generate_hyde_documents(query, n_docs=1)
        for i, hyde_doc in enumerate(hyde_docs):
            if hyde_doc:
                print(f"🔍 HyDE 검색")
                hyde_results = self._single_search(hyde_doc, n_results=2)  # 1개 문서지만 2개 결과
                if hyde_results:
                    all_results.extend(self._format_results(hyde_results, "HyDE"))
        
        # 3차: Query Rewriting (질문 재작성 후 검색)
        context_sample = all_results[0]['content'] if all_results else ""
        rewritten_query = self.rewrite_query(query, context_sample)
        if rewritten_query != query:
            print(f"🔍 Rewritten 검색")
            rewritten_results = self._single_search(rewritten_query, n_results=3)  # 2→3으로 증가
            if rewritten_results:
                all_results.extend(self._format_results(rewritten_results, "Rewritten"))
        
        # 4차: LLM 키워드 확장 검색 제거 (LLM Re-Ranker로 대체)
        
        # 중복 제거 및 점수순 정렬
        unique_results = self._deduplicate_results(all_results)
        
        # LLM Re-Ranker: 창의적 관련성 판단으로 하드코딩 필터 대체
        if len(unique_results) > 5:
            # 상위 8개만 LLM에게 보내서 평가 (비용 최적화)
            candidates = unique_results[:8]
            filtered_results = self._llm_rerank_filter(query, candidates)
        else:
            # 결과가 적으면 LLM 평가 후 유사도만으로 fallback
            filtered_results = self._llm_rerank_filter(query, unique_results)
            if len(filtered_results) < 2:
                print("⚠️ LLM 필터 결과 부족, 유사도 0.25+ fallback")
                filtered_results = [r for r in unique_results if r['similarity'] > 0.25]  # 0.35 → 0.25 복원
        
        print(f"📊 LLM Re-Ranking: {len(unique_results)} → {len(filtered_results)} (창의적 관련성 판단)")
        
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

    def _llm_rerank_filter(self, query: str, candidates: list):
        """LLM Re-Ranker: 창의적 관련성 판단으로 영상 필터링"""
        if not candidates:
            return []
        
        try:
            # 후보 영상들을 LLM에게 평가 요청
            candidate_info = []
            for i, result in enumerate(candidates):
                candidate_info.append(
                    f"영상 {i+1}: {result['title']}\n"
                    f"내용: {result['content'][:200]}...\n"
                    f"유사도: {result['similarity']:.3f}"
                )
            
            candidates_text = "\n---\n".join(candidate_info)
            
            prompt = f"""당신은 일본 부동산 투자 전문가입니다. 아래 영상들이 사용자 질문과 얼마나 관련이 있는지 창의적으로 판단해주세요.

## 사용자 질문
{query}

## 후보 영상들
{candidates_text}

## 평가 기준
- 직접적 관련성: 질문과 정확히 일치하는 내용 (9-10점)
- 간접적 관련성: 비슷한 투자 패턴이나 원칙 적용 가능 (7-8점)
- 창의적 연결: 다른 지역/상황이지만 인사이트 추출 가능 (6-7점)
- 약간 관련: 부동산 투자와 관련은 있지만 도움 제한적 (4-5점)
- 무관: 부동산 투자와 관련 없음 (1-3점)

각 영상에 대해 1-10점으로 평가하고, 6점 이상만 선택하세요.
응답 형식: "영상번호:점수" (예: 1:9, 3:8, 5:7)"""

            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": "당신은 관련성 평가 전문가입니다. 창의적이지만 정확한 판단을 내리세요."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=200,
                temperature=0.3  # 일관성을 위해 낮은 온도
            )
            
            # LLM 응답 파싱
            llm_response = response.choices[0].message.content.strip()
            print(f"🤖 LLM 관련성 평가: {llm_response}")
            
            # 점수 파싱 및 필터링 (개선된 파싱)
            selected_indices = []
            import re
            
            # 정규식으로 "숫자:점수" 패턴 추출 (괄호 설명 무시)
            pattern = r'(\d+):(\d+)'
            matches = re.findall(pattern, llm_response)
            
            for idx_str, score_str in matches:
                try:
                    idx = int(idx_str) - 1  # 1-based to 0-based
                    score = int(score_str)
                    if score >= 6 and 0 <= idx < len(candidates):
                        selected_indices.append(idx)
                        print(f"   ✅ 영상 {idx+1}: {score}점 선택")
                    else:
                        print(f"   ❌ 영상 {idx+1}: {score}점 제외 (6점 미만)")
                except ValueError:
                    continue
            
            # 선택된 영상들 반환 (LLM 점수 순서 유지)
            filtered = [candidates[i] for i in selected_indices]
            
            print(f"🎯 LLM 선택: {len(selected_indices)}개 영상 (6점 이상)")
            return filtered
            
        except Exception as e:
            print(f"⚠️ LLM Re-Ranker 실패: {e}, 유사도 0.25+ fallback")
            # LLM 실패시 유사도만으로 필터링 (0.35 → 0.25 복원)
            return [r for r in candidates if r['similarity'] > 0.25]

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
        """스마트 RAG 파이프라인 실행 (v4.1 - 세컨드오피니언 반영)"""
        import time
        start_time = time.time()
        
        print(f"🚀 HyDE + Rewriting RAG v4.1 시작: '{query}' (세컨드오피니언 반영)")
        
        # HyDE + Query Rewriting + LLM Re-Ranker 파이프라인 실행
        search_results = self.multi_search_v3(query)
        
        if not search_results:
            print("❌ 모든 검색 전략 실패")
            return "❌ 관련 영상을 찾을 수 없습니다."
        
        print(f"✅ {len(search_results)}개 고품질 영상 발견 (LLM 창의적 관련성 판단)")
        
        # 발견된 영상들 미리보기 (유사도 상세 표시)
        for i, result in enumerate(search_results):
            duration = result.get('duration', 'N/A')
            print(f"   {i+1}. [{result['similarity']:.3f}] {result['title'][:40]}... ({duration}, {result['search_type']})")
        
        # AI 답변 생성
        print("🤖 DeepSeek 최종 답변 생성 중...")
        answer = self.generate_answer(query, search_results)
        
        # 성능 및 비용 모니터링 로깅
        elapsed_time = time.time() - start_time
        estimated_tokens = len(query) + sum(len(r['content'][:800]) for r in search_results) + len(answer)
        print(f"📊 성능 로그: {elapsed_time:.1f}초, 추정토큰: {estimated_tokens:,}, 영상수: {len(search_results)}")
        
        # 참고 영상 목록 (더 상세한 정보)
        references = "\n\n📚 **참고 영상 (v4.1 - 세컨드오피니언 반영):**\n"
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