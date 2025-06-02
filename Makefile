VENV_NAME = venv
PYTHON = $(VENV_NAME)/bin/python
PIP = $(VENV_NAME)/bin/pip
YDH = $(PYTHON) -m ydh

# Default target
.PHONY: download
download: $(VENV_NAME)
	@echo "📺 채널 리스트에서 새 영상 다운로드 중..."
	@if [ ! -f channels.txt ]; then \
		echo "❌ channels.txt 파일이 없습니다. 'make init'을 먼저 실행하세요."; \
		exit 1; \
	fi
	@if ! $(PYTHON) -c "import ydh" 2>/dev/null; then \
		echo "❌ Y-Data-House 모듈이 설치되지 않았습니다."; \
		echo ""; \
		echo "다음 명령을 실행하세요:"; \
		echo "  source venv/bin/activate"; \
		echo "  make install"; \
		echo ""; \
		exit 1; \
	fi
	@while IFS= read -r line || [ -n "$$line" ]; do \
		if [ -n "$$line" ] && [ "$${line#\#}" = "$$line" ]; then \
			echo "🔄 채널 처리 중: $$line"; \
			$(YDH) ingest "$$line" || echo "⚠️  채널 처리 실패: $$line"; \
		fi; \
	done < channels.txt
	@echo "✅ 모든 채널 처리 완료!"

# Initialize environment
.PHONY: init
init: venv-create channels.txt vault
	@echo "🎉 Y-Data-House 기본 환경 설정 완료!"
	@echo ""
	@echo "🔧 다음 단계:"
	@echo "1. 가상환경을 활성화하세요:"
	@echo "   source venv/bin/activate"
	@echo ""
	@echo "2. 의존성을 설치하세요:"
	@echo "   make install"
	@echo ""
	@echo "3. channels.txt 파일을 편집하여 다운로드할 채널 URL을 추가하세요"
	@echo "4. 'make download' 명령으로 영상을 다운로드하세요"

# Create virtual environment only
.PHONY: venv-create
venv-create:
	@if [ ! -d "$(VENV_NAME)" ]; then \
		echo "🐍 Python 가상환경 생성 중..."; \
		python3 -m venv $(VENV_NAME); \
		echo "✅ 가상환경 생성 완료"; \
	else \
		echo "✅ 가상환경이 이미 존재합니다"; \
	fi

# Install dependencies (run after activating venv)
.PHONY: install
install:
	@echo "📦 의존성 설치 중..."
	@if [ -n "$$VIRTUAL_ENV" ]; then \
		pip install --upgrade pip; \
		pip install -e .; \
		echo "✅ 의존성 설치 완료"; \
	else \
		echo "❌ 가상환경이 활성화되지 않았습니다."; \
		echo "   먼저 'source venv/bin/activate'를 실행하세요."; \
		exit 1; \
	fi

# Simple venv target - just ensure venv exists
$(VENV_NAME): venv-create

# Create channels.txt if it doesn't exist
channels.txt:
	@echo "📝 채널 목록 파일 생성 중..."
	@echo "# Y-Data-House 채널 목록" > channels.txt
	@echo "# 한 줄에 하나씩 YouTube 채널 URL을 입력하세요" >> channels.txt
	@echo "# '#'로 시작하는 줄은 주석으로 처리됩니다" >> channels.txt
	@echo "#" >> channels.txt
	@echo "# 예시:" >> channels.txt
	@echo "# https://www.youtube.com/@리베라루츠대학" >> channels.txt
	@echo "# https://www.youtube.com/@채널명2" >> channels.txt
	@echo "#" >> channels.txt
	@echo "# 아래에 다운로드할 채널 URL을 추가하세요:" >> channels.txt
	@echo "" >> channels.txt
	@echo "✅ channels.txt 파일이 생성되었습니다"

# Create vault directory
vault:
	@echo "📚 Vault 디렉토리 생성 중..."
	@mkdir -p vault/10_videos
	@echo "✅ Vault 디렉토리 생성 완료"

# Data integrity check
.PHONY: check
check: $(VENV_NAME)
	@echo "🔍 데이터 정합성 검사 실행 중..."
	@if ! $(PYTHON) -c "import ydh" 2>/dev/null; then \
		echo "❌ Y-Data-House 모듈이 설치되지 않았습니다."; \
		echo ""; \
		echo "다음 명령을 실행하세요:"; \
		echo "  source venv/bin/activate"; \
		echo "  make install"; \
		echo ""; \
		exit 1; \
	fi
	$(YDH) config-validate

# Vector embedding creation
.PHONY: embed
embed: $(VENV_NAME)
	@echo "🧠 벡터 임베딩 생성 중..."
	@if ! $(PYTHON) -c "import ydh" 2>/dev/null; then \
		echo "❌ Y-Data-House 모듈이 설치되지 않았습니다."; \
		echo ""; \
		echo "다음 명령을 실행하세요:"; \
		echo "  source venv/bin/activate"; \
		echo "  make install"; \
		echo ""; \
		exit 1; \
	fi
	@if ! $(PYTHON) -c "import chromadb" 2>/dev/null; then \
		echo "❌ chromadb가 설치되지 않았습니다."; \
		echo "   'make install'을 다시 실행하세요."; \
		exit 1; \
	fi
	$(PYTHON) vault/90_indices/embed.py
	@echo "✅ 벡터 임베딩 완료!"

# Vector search test
.PHONY: search
search: $(VENV_NAME)
	@echo "🔍 벡터 검색 테스트..."
	@if [ -z "$(QUERY)" ]; then \
		echo "사용법: make search QUERY=\"검색어\""; \
		echo "예시: make search QUERY=\"도쿄 원룸 투자\""; \
		exit 1; \
	fi
	$(PYTHON) vault/90_indices/embed.py search $(QUERY)

# DeepSeek RAG Q&A system
.PHONY: ask
ask: $(VENV_NAME)
	@echo "🤖 DeepSeek RAG 질문-답변..."
	@if [ -z "$(QUERY)" ]; then \
		echo "사용법: make ask QUERY=\"질문\""; \
		echo "예시:"; \
		echo "  make ask QUERY=\"도쿄 원룸 투자할 때 주의점은?\""; \
		echo "  make ask QUERY=\"수익률 높은 지역은 어디?\""; \
		echo "  make ask QUERY=\"18년차 직장인의 투자 전략\""; \
		exit 1; \
	fi
	@if ! $(PYTHON) -c "import openai" 2>/dev/null; then \
		echo "❌ openai 패키지가 설치되지 않았습니다."; \
		echo "   'make install'을 다시 실행하세요."; \
		exit 1; \
	fi
	$(PYTHON) vault/90_indices/rag.py $(QUERY)

# Clean vector embeddings
.PHONY: embed-clean
embed-clean:
	@echo "🧹 벡터 임베딩 데이터베이스 초기화 중..."
	@if [ -d "vault/90_indices/chroma" ]; then \
		rm -rf vault/90_indices/chroma; \
		echo "✅ 벡터 임베딩 데이터베이스가 삭제되었습니다"; \
	else \
		echo "ℹ️  벡터 임베딩 데이터베이스가 존재하지 않습니다"; \
	fi
	@echo "💡 다음 'make embed' 실행 시 모든 영상이 새로 임베딩됩니다"

# Clean up
.PHONY: clean
clean:
	@echo "🧹 가상환경 정리 중..."
	@rm -rf $(VENV_NAME)
	@echo "✅ 정리 완료"

# Help
.PHONY: help
help:
	@echo "Y-Data-House Makefile 명령어"
	@echo "=========================="
	@echo ""
	@echo "🚀 주요 명령어:"
	@echo "  make init       - 기본 환경 설정 (가상환경 생성, 초기 파일 생성)"
	@echo "  make install    - 의존성 설치 (가상환경 활성화 후 실행)"
	@echo "  make download   - channels.txt의 모든 채널에서 새 영상 다운로드"
	@echo "  make check      - Vault 데이터 정합성 검사"
	@echo "  make embed      - 벡터 임베딩 생성 (AI 검색 기반 구축)"
	@echo "  make search     - 벡터 검색 테스트 (QUERY=\"검색어\" 필요)"
	@echo "  make ask        - DeepSeek RAG 질문-답변 (QUERY=\"질문\" 필요)"
	@echo "  make embed-clean - 벡터 임베딩 데이터베이스 초기화"
	@echo "  make clean      - 가상환경 삭제"
	@echo ""
	@echo "💡 사용법:"
	@echo "  1. make init                       # 기본 환경 설정"
	@echo "  2. source venv/bin/activate        # 가상환경 활성화"
	@echo "  3. make install                    # 의존성 설치"
	@echo "  4. channels.txt 편집                # 다운로드할 채널 URL 추가"
	@echo "  5. make download                   # 영상 다운로드"
	@echo "  6. make check                      # 데이터 정합성 검사"
	@echo "  7. make embed                      # 벡터 임베딩 생성"
	@echo "  8. make ask QUERY=\"투자 전략은?\"    # AI 질문-답변 시스템"