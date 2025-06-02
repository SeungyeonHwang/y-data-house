#!/usr/bin/env python3
"""
DeepSeek RAG 시스템 - 98개 영상 자막을 자연어로 검색하고 AI가 답변
실행: python vault/90_indices/rag.py "도쿄 원룸 투자 전략은?"
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import chromadb
from chromadb.config import Settings as ChromaSettings
from openai import OpenAI

# ---------------- Prompt template (easier to tweak) ----------------
PROMPT_TEMPLATE = """당신은 일본 부동산 투자 전문 AI 어시스턴트입니다.

## 컨텍스트 (관련 영상들)
{context}

## 사용자 질문
{query}

## 답변 작성 지침
1. **한국어**로 작성하되, 영상에서 언급된 **숫자·고유명사**는 원문 그대로 유지합니다.
2. **5개 이하 핵심 bullet**(`- `)로 요약하고, 각 bullet 마지막에 관련 영상 번호를 `[영상 n]` 형식으로 표시합니다.
3. 가능하다면 **타임스탬프**(분:초)나 **수치 예시**를 포함해 실행 가능성을 높이십시오.
4. 맨 마지막 줄에 `### 핵심 한 줄 요약:`으로 시작하는 1문장 요약을 추가합니다.
5. 불필요한 머리말·결론 없이 바로 bullet부터 시작합니다.
"""
# -------------------------------------------------------------------

# 환경변수 로드
load_dotenv()

# 경로 설정
VAULT_ROOT = Path(__file__).parent.parent
CHROMA_PATH = VAULT_ROOT / "90_indices" / "chroma"

class DeepSeekRAG:
    def __init__(self):
        """DeepSeek RAG 시스템 초기화"""
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
            self.collection = self.chroma_client.get_collection("video_transcripts")
            print(f"✅ ChromaDB 연결됨: {len(self.collection.get()['ids'])}개 영상")
        except Exception as e:
            raise ValueError(f"❌ ChromaDB 로드 실패: {e}\n'make embed'를 먼저 실행하세요.")

    def search(self, query: str, n_results: int = 5):
        """벡터 검색으로 관련 영상 찾기"""
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=n_results
            )
            return results
        except Exception as e:
            print(f"❌ 검색 오류: {e}")
            return None

    def generate_answer(self, query: str, search_results: dict):
        """DeepSeek으로 RAG 답변 생성"""
        if not search_results or not search_results['documents'][0]:
            return "❌ 관련 영상을 찾을 수 없습니다."
        
        # 컨텍스트 구성
        context_parts = []
        for i, (doc, metadata) in enumerate(zip(
            search_results['documents'][0], 
            search_results['metadatas'][0]
        )):
            context_parts.append(
                f"[영상 {i+1}] {metadata['title']}\n"
                f"업로드: {metadata['upload']} | 채널: {metadata['channel']}\n"
                f"내용: {doc[:500]}...\n"
            )
        
        context = "\n---\n".join(context_parts)

        # 프롬프트 구성
        prompt = PROMPT_TEMPLATE.format(context=context, query=query)

        try:
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": "당신은 일본 부동산 투자 전문 AI 어시스턴트입니다."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=1500,
                temperature=0.7
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            return f"❌ DeepSeek API 오류: {e}"

    def chat(self, query: str):
        """완전한 RAG 파이프라인 실행"""
        print(f"🔍 검색 중: '{query}'")
        
        # 1. 벡터 검색
        search_results = self.search(query, n_results=5)
        if not search_results:
            return "❌ 검색 실패"
        
        print(f"📄 {len(search_results['documents'][0])}개 관련 영상 발견")
        
        # 2. AI 답변 생성
        print("🤖 DeepSeek 답변 생성 중...")
        answer = self.generate_answer(query, search_results)
        
        # 3. 참고 영상 목록
        references = "\n\n📚 **참고 영상:**\n"
        for i, metadata in enumerate(search_results['metadatas'][0]):
            references += f"{i+1}. {metadata['title']} ({metadata['upload']})\n"
        
        return answer + references

def main():
    """메인 실행 함수"""
    if len(sys.argv) < 2:
        print("사용법: python vault/90_indices/rag.py \"질문\"")
        print("\n예시:")
        print('python vault/90_indices/rag.py "도쿄 원룸 투자할 때 주의점은?"')
        print('python vault/90_indices/rag.py "수익률 높은 지역은 어디?"')
        print('python vault/90_indices/rag.py "18년차 직장인의 투자 전략"')
        return
    
    query = " ".join(sys.argv[1:])
    
    try:
        # RAG 시스템 초기화
        rag = DeepSeekRAG()
        
        # 질문-답변 실행
        answer = rag.chat(query)
        
        print("\n" + "="*60)
        print(f"🎯 질문: {query}")
        print("="*60)
        print(answer)
        print("="*60)
        
    except Exception as e:
        print(f"❌ 오류: {e}")

if __name__ == "__main__":
    main() 