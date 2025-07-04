VENV_NAME = venv
PYTHON = $(VENV_NAME)/bin/python
PIP = $(VENV_NAME)/bin/pip
YDH = $(PYTHON) -m ydh

# Default target - Optimized download
.PHONY: download
download: $(VENV_NAME)
	@echo "🚀 최적화된 다운로드 시작..."
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
	$(YDH) batch --channels-file channels.txt
	@echo "✅ 최적화된 다운로드 완료!"

# Fast parallel download
.PHONY: download-fast
download-fast: $(VENV_NAME)
	@echo "🚀 병렬 다운로드 시작 (3개 워커)..."
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
	$(YDH) batch --channels-file channels.txt --parallel --max-workers 3
	@echo "✅ 병렬 다운로드 완료!"

# Full integrity scan download
.PHONY: download-full-scan
download-full-scan: $(VENV_NAME)
	@echo "🔍 전체 무결성 검사 다운로드 시작..."
	@echo "⏰ 이 작업은 오래 걸릴 수 있습니다 (모든 영상을 확인합니다)"
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
	$(YDH) batch --channels-file channels.txt --full-scan
	@echo "✅ 전체 무결성 검사 완료!"

# Combined full scan with parallel processing
.PHONY: download-full-scan-fast
download-full-scan-fast: $(VENV_NAME)
	@echo "🔍🚀 병렬 전체 무결성 검사 다운로드 시작..."
	@echo "⏰ 이 작업은 오래 걸릴 수 있습니다 (모든 영상을 병렬로 확인)"
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
	$(YDH) batch --channels-file channels.txt --full-scan --parallel --max-workers 3
	@echo "✅ 병렬 전체 무결성 검사 완료!"

# Legacy download (individual channel processing)
.PHONY: download-legacy
download-legacy: $(VENV_NAME)
	@echo "📺 채널 리스트에서 새 영상 다운로드 중 (기존 방식)..."
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
	@echo ""
	@echo "📱 데스크톱 앱을 사용하려면:"
	@echo "   make desktop-init    # 데스크톱 앱 개발환경 설정"
	@echo "   make desktop-dev     # 데스크톱 앱 실행"

# Initialize desktop app environment
.PHONY: desktop-init
desktop-init: check-tools install-rust install-node
	@echo "📦 환경변수 로딩 중..."
	@bash -c "source ~/.cargo/env 2>/dev/null || true"
	@bash -c "source ~/.asdf/asdf.sh 2>/dev/null || true"
	@echo "📱 데스크톱 앱 의존성 설치 중..."
	@bash -c "source ~/.asdf/asdf.sh 2>/dev/null || true && cd app && pnpm install" || { \
		echo "❌ pnpm으로 설치 실패. 환경변수 문제일 수 있습니다."; \
		echo "🔧 수동 해결 방법:"; \
		echo "  1. source ~/.asdf/asdf.sh"; \
		echo "  2. asdf reshim nodejs"; \
		echo "  3. cd app && pnpm install"; \
		exit 1; \
	}
	@echo "🧹 캐시 정리 중..."
	@bash -c "source ~/.asdf/asdf.sh 2>/dev/null || true && cd app && rm -rf node_modules pnpm-lock.yaml" || { \
		echo "⚠️  캐시 정리 실패 (무시하고 계속)"; \
	}
	@echo "🔄 의존성 재설치 중..."
	@bash -c "source ~/.asdf/asdf.sh 2>/dev/null || true && cd app && pnpm install" || { \
		echo "❌ 의존성 재설치 실패"; \
		exit 1; \
	}
	@echo "🦀 Rust lockfile 생성 중..."
	@bash -c "source ~/.cargo/env 2>/dev/null || true && cd app/src-tauri && cargo generate-lockfile" || { \
		echo "⚠️  Cargo lockfile 생성 실패 (무시하고 계속)"; \
	}
	@echo "✅ 데스크톱 앱 환경 설정 완료!"
	@echo ""
	@echo "🚀 데스크톱 앱 실행:"
	@echo "   make desktop-dev"

# Check required tools
.PHONY: check-tools
check-tools:
	@echo "🔍 필수 도구 확인 중..."
	@command -v python3 >/dev/null 2>&1 || { echo "❌ Python3가 설치되지 않았습니다"; exit 1; }
	@echo "✅ Python3: $(shell python3 --version)"

# Install Rust toolchain
.PHONY: install-rust
install-rust:
	@echo "🦀 Rust toolchain 확인 중..."
	@if ! command -v rustc >/dev/null 2>&1; then \
		echo "📦 Rust toolchain 설치 중..."; \
		curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y; \
		echo "✅ Rust toolchain 설치 완료"; \
		echo "🔄 새 터미널을 열거나 'source ~/.cargo/env'를 실행하세요"; \
	else \
		echo "✅ Rust: $(shell rustc --version)"; \
	fi

# Install Node.js and pnpm
.PHONY: install-node
install-node:
	@echo "🟢 Node.js 환경 확인 중..."
	@bash -c "source ~/.asdf/asdf.sh 2>/dev/null || true; \
		if ! command -v node >/dev/null 2>&1; then \
			echo '📦 Node.js 설치가 필요합니다'; \
			echo '다음 명령 중 하나를 사용하여 Node.js를 설치하세요:'; \
			echo '  - asdf: asdf install nodejs 22.14.0 && asdf local nodejs 22.14.0'; \
			echo '  - Homebrew: brew install node'; \
			echo '  - mise: mise install nodejs@lts'; \
			echo '  - nvm: nvm install --lts'; \
			exit 1; \
		else \
			echo '✅ Node.js:' $$(node --version); \
		fi"
	@bash -c "source ~/.asdf/asdf.sh 2>/dev/null || true; \
		if ! command -v pnpm >/dev/null 2>&1; then \
			echo '📦 pnpm 설치 중...'; \
			npm install -g pnpm; \
			asdf reshim nodejs 2>/dev/null || true; \
			echo '✅ pnpm 설치 완료'; \
		else \
			echo '✅ pnpm:' $$(pnpm --version); \
		fi"

# Run desktop app in development mode
.PHONY: desktop-dev
desktop-dev:
	@echo "🚀 데스크톱 앱 개발 모드 실행 중..."
	@if [ ! -d "app/node_modules" ]; then \
		echo "❌ 데스크톱 앱 의존성이 설치되지 않았습니다"; \
		echo "   'make desktop-init'를 먼저 실행하세요"; \
		exit 1; \
	fi
	@if [ ! -f "app/src-tauri/tauri.conf.json" ]; then \
		echo "❌ tauri.conf.json 파일이 없습니다"; \
		echo "   프로젝트 구조를 확인하세요"; \
		exit 1; \
	fi
	@echo "🔧 환경변수 로딩 중..."
	@bash -c "source ~/.cargo/env 2>/dev/null || true && source ~/.asdf/asdf.sh 2>/dev/null || true && cd app && pnpm run tauri:dev" || { \
		echo "❌ 데스크톱 앱 실행 실패"; \
		echo "🔧 수동 실행 방법:"; \
		echo "  1. source ~/.cargo/env"; \
		echo "  2. source ~/.asdf/asdf.sh"; \
		echo "  3. cd app"; \
		echo "  4. pnpm run tauri:dev"; \
		echo ""; \
		echo "🔍 디버깅 정보:"; \
		echo "  - tauri.conf.json 위치: app/src-tauri/tauri.conf.json"; \
		echo "  - Cargo.toml 위치: app/src-tauri/Cargo.toml"; \
		exit 1; \
	}

# Build desktop app for production
.PHONY: desktop-build
desktop-build:
	@echo "🏗️  데스크톱 앱 프로덕션 빌드 중..."
	@if [ ! -d "app/node_modules" ]; then \
		echo "❌ 데스크톱 앱 의존성이 설치되지 않았습니다"; \
		echo "   'make desktop-init'를 먼저 실행하세요"; \
		exit 1; \
	fi
	@cd app && pnpm run build
	@echo "✅ 데스크톱 앱 빌드 완료!"

# Clean desktop app
.PHONY: desktop-clean
desktop-clean:
	@echo "🧹 데스크톱 앱 정리 중..."
	@if [ -d "app/node_modules" ]; then \
		rm -rf app/node_modules; \
		echo "✅ Node.js 의존성 삭제 완료"; \
	fi
	@if [ -d "app/src-tauri/target" ]; then \
		rm -rf app/src-tauri/target; \
		echo "✅ Rust 빌드 캐시 삭제 완료"; \
	fi
	@if [ -d "app/dist" ]; then \
		rm -rf app/dist; \
		echo "✅ 빌드 결과물 삭제 완료"; \
	fi

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

# ========================== Gemini 벡터 검색 시스템 ==========================

# Gemini 임베딩 생성
.PHONY: gemini-embed
gemini-embed: $(VENV_NAME)
	@echo "🤖 Gemini 벡터 임베딩 생성 중..."
	@if ! $(PYTHON) -c "import ydh" 2>/dev/null; then \
		echo "❌ Y-Data-House 모듈이 설치되지 않았습니다."; \
		echo ""; \
		echo "다음 명령을 실행하세요:"; \
		echo "  source venv/bin/activate"; \
		echo "  make install"; \
		echo ""; \
		exit 1; \
	fi
	@if [ -z "$$GEMINI_API_KEY" ]; then \
		echo "❌ GEMINI_API_KEY 환경변수가 설정되지 않았습니다."; \
		echo "다음 방법 중 하나를 사용하여 API 키를 설정하세요:"; \
		echo "  1. export GEMINI_API_KEY='your_api_key_here'"; \
		echo "  2. .env 파일에 GEMINI_API_KEY=your_api_key_here 추가"; \
		exit 1; \
	fi
	$(YDH) gemini-embed
	@echo "✅ Gemini 벡터 임베딩 완료!"

# 특정 채널만 Gemini 임베딩
.PHONY: gemini-embed-channels
gemini-embed-channels: $(VENV_NAME)
	@echo "🤖 특정 채널 Gemini 임베딩 생성 중..."
	@if [ -z "$(CHANNELS)" ]; then \
		echo "사용법: make gemini-embed-channels CHANNELS=\"채널1,채널2\""; \
		echo "예시: make gemini-embed-channels CHANNELS=\"도쿄부동산,takaki_takehana\""; \
		exit 1; \
	fi
	@if [ -z "$$GEMINI_API_KEY" ]; then \
		echo "❌ GEMINI_API_KEY 환경변수가 설정되지 않았습니다."; \
		exit 1; \
	fi
	$(YDH) gemini-embed --channels "$(CHANNELS)"
	@echo "✅ 선택된 채널 Gemini 임베딩 완료!"

# Gemini 벡터 검색
.PHONY: search-gemini
search-gemini: $(VENV_NAME)
	@echo "🔍 Gemini 벡터 검색..."
	@if [ -z "$(QUERY)" ]; then \
		echo "사용법: make search-gemini QUERY=\"검색어\""; \
		echo "예시:"; \
		echo "  make search-gemini QUERY=\"도쿄 부동산 투자 전략\""; \
		echo "  make search-gemini QUERY=\"원룸 수익률\" CHANNEL=\"도쿄부동산\""; \
		echo "  make search-gemini QUERY=\"투자 전략\" YEAR=\"2023\""; \
		exit 1; \
	fi
	@if [ -z "$$GEMINI_API_KEY" ]; then \
		echo "❌ GEMINI_API_KEY 환경변수가 설정되지 않았습니다."; \
		exit 1; \
	fi
	@cmd="$(YDH) search-gemini \"$(QUERY)\""; \
	if [ -n "$(CHANNEL)" ]; then \
		cmd="$$cmd --channel \"$(CHANNEL)\""; \
	fi; \
	if [ -n "$(YEAR)" ]; then \
		cmd="$$cmd --year \"$(YEAR)\""; \
	fi; \
	if [ -n "$(NUM)" ]; then \
		cmd="$$cmd --num-results $(NUM)"; \
	fi; \
	if [ -n "$(MIN_SIM)" ]; then \
		cmd="$$cmd --min-similarity $(MIN_SIM)"; \
	fi; \
	eval $$cmd

# Gemini 채널 목록 조회
.PHONY: gemini-channels
gemini-channels: $(VENV_NAME)
	@echo "📺 Gemini 검색 가능한 채널 조회..."
	@if ! $(PYTHON) -c "import ydh" 2>/dev/null; then \
		echo "❌ Y-Data-House 모듈이 설치되지 않았습니다."; \
		exit 1; \
	fi
	$(YDH) gemini-channels

# Gemini 데이터베이스 통계
.PHONY: gemini-stats
gemini-stats: $(VENV_NAME)
	@echo "📊 Gemini 데이터베이스 통계 조회..."
	@if ! $(PYTHON) -c "import ydh" 2>/dev/null; then \
		echo "❌ Y-Data-House 모듈이 설치되지 않았습니다."; \
		exit 1; \
	fi
	$(YDH) gemini-stats

# Gemini 임베딩 데이터베이스 정리
.PHONY: gemini-clean
gemini-clean:
	@echo "🧹 Gemini 임베딩 데이터베이스 초기화 중..."
	@if [ -d "vault/90_indices/chroma_gemini" ]; then \
		rm -rf vault/90_indices/chroma_gemini; \
		echo "✅ Gemini 임베딩 데이터베이스가 삭제되었습니다"; \
	else \
		echo "ℹ️  삭제할 Gemini 임베딩 데이터베이스가 없습니다"; \
	fi
	@echo "💡 다음 'make gemini-embed' 실행 시 모든 영상이 새로 임베딩됩니다"

# Gemini 시스템 전체 재구축
.PHONY: gemini-rebuild
gemini-rebuild: gemini-clean gemini-embed
	@echo "🎉 Gemini 벡터 검색 시스템 재구축 완료!"

# 세션 관리 명령어
.PHONY: list-sessions
list-sessions: $(VENV_NAME)  ## 📚 저장된 검색 세션 목록 표시
	@echo "📚 저장된 검색 세션 목록 조회..."
	@if ! $(PYTHON) -c "import ydh" 2>/dev/null; then \
		echo "❌ Y-Data-House 모듈이 설치되지 않았습니다."; \
		exit 1; \
	fi
	$(YDH) list-sessions

.PHONY: list-sessions-channel
list-sessions-channel: $(VENV_NAME)  ## 📚 특정 채널의 세션만 표시
	@echo "📚 특정 채널의 세션 목록 조회..."
	@if [ -z "$(CHANNEL)" ]; then \
		echo "❌ 채널명이 필요합니다. CHANNEL=\"채널명\"을 지정하세요."; \
		exit 1; \
	fi
	@if ! $(PYTHON) -c "import ydh" 2>/dev/null; then \
		echo "❌ Y-Data-House 모듈이 설치되지 않았습니다."; \
		exit 1; \
	fi
	$(YDH) list-sessions --channel "$(CHANNEL)"

.PHONY: delete-session
delete-session: $(VENV_NAME)  ## 🗑️ 특정 세션 삭제
	@echo "🗑️ 세션 삭제 중..."
	@if [ -z "$(SESSION_ID)" ]; then \
		echo "❌ 세션 ID가 필요합니다. SESSION_ID=\"세션ID\"를 지정하세요."; \
		exit 1; \
	fi
	@if ! $(PYTHON) -c "import ydh" 2>/dev/null; then \
		echo "❌ Y-Data-House 모듈이 설치되지 않았습니다."; \
		exit 1; \
	fi
	$(YDH) delete-session "$(SESSION_ID)"

.PHONY: delete-session-force
delete-session-force: $(VENV_NAME)  ## 🗑️ 확인 없이 세션 삭제
	@echo "🗑️ 세션 강제 삭제 중..."
	@if [ -z "$(SESSION_ID)" ]; then \
		echo "❌ 세션 ID가 필요합니다. SESSION_ID=\"세션ID\"를 지정하세요."; \
		exit 1; \
	fi
	@if ! $(PYTHON) -c "import ydh" 2>/dev/null; then \
		echo "❌ Y-Data-House 모듈이 설치되지 않았습니다."; \
		exit 1; \
	fi
	$(YDH) delete-session "$(SESSION_ID)" --confirm

.PHONY: export-session
export-session: $(VENV_NAME)  ## 📄 세션을 HTML로 내보내기
	@echo "📄 세션 내보내기 중..."
	@if [ -z "$(SESSION_ID)" ]; then \
		echo "❌ 세션 ID가 필요합니다. SESSION_ID=\"세션ID\"를 지정하세요."; \
		exit 1; \
	fi
	@if ! $(PYTHON) -c "import ydh" 2>/dev/null; then \
		echo "❌ Y-Data-House 모듈이 설치되지 않았습니다."; \
		exit 1; \
	fi
	$(YDH) export-session "$(SESSION_ID)"

.PHONY: export-session-json
export-session-json: $(VENV_NAME)  ## 📄 세션을 JSON으로 내보내기
	@echo "📄 세션 JSON 내보내기 중..."
	@if [ -z "$(SESSION_ID)" ]; then \
		echo "❌ 세션 ID가 필요합니다. SESSION_ID=\"세션ID\"를 지정하세요."; \
		exit 1; \
	fi
	@if ! $(PYTHON) -c "import ydh" 2>/dev/null; then \
		echo "❌ Y-Data-House 모듈이 설치되지 않았습니다."; \
		exit 1; \
	fi
	$(YDH) export-session "$(SESSION_ID)" --format json

.PHONY: clean-sessions
clean-sessions: $(VENV_NAME)  ## 🧹 30일 이상 된 세션 정리
	@echo "🧹 30일 이상 된 세션 정리 중..."
	@if ! $(PYTHON) -c "import ydh" 2>/dev/null; then \
		echo "❌ Y-Data-House 모듈이 설치되지 않았습니다."; \
		exit 1; \
	fi
	$(YDH) clean-sessions --days 30

.PHONY: clean-sessions-week
clean-sessions-week: $(VENV_NAME)  ## 🧹 7일 이상 된 세션 정리
	@echo "🧹 7일 이상 된 세션 정리 중..."
	@if ! $(PYTHON) -c "import ydh" 2>/dev/null; then \
		echo "❌ Y-Data-House 모듈이 설치되지 않았습니다."; \
		exit 1; \
	fi
	$(YDH) clean-sessions --days 7

.PHONY: clean-sessions-force
clean-sessions-force: $(VENV_NAME)  ## 🧹 확인 없이 30일 이상 된 세션 정리
	@echo "🧹 30일 이상 된 세션 강제 정리 중..."
	@if ! $(PYTHON) -c "import ydh" 2>/dev/null; then \
		echo "❌ Y-Data-House 모듈이 설치되지 않았습니다."; \
		exit 1; \
	fi
	$(YDH) clean-sessions --days 30 --confirm

# Gemini RAG 질의응답 명령어
.PHONY: ask-gemini
ask-gemini: $(VENV_NAME)  ## 🤖 Gemini RAG 질의응답
	@echo "🤖 Gemini RAG 질의응답..."
	@if [ -z "$(QUERY)" ]; then \
		echo "❌ 질문이 필요합니다. QUERY=\"질문 내용\"을 지정하세요."; \
		echo "예시: make ask-gemini QUERY=\"머신러닝이 뭔가요?\""; \
		exit 1; \
	fi
	@if ! command -v printenv >/dev/null || [ -z "$$(printenv GEMINI_API_KEY)" ]; then \
		echo "❌ GEMINI_API_KEY 환경변수가 설정되지 않았습니다."; \
		exit 1; \
	fi
	@if ! $(PYTHON) -c "import ydh" 2>/dev/null; then \
		echo "❌ Y-Data-House 모듈이 설치되지 않았습니다."; \
		exit 1; \
	fi
	$(YDH) ask-gemini "$(QUERY)"

.PHONY: ask-gemini-channel
ask-gemini-channel: $(VENV_NAME)  ## 🤖 특정 채널 RAG 질의응답
	@echo "🤖 특정 채널 Gemini RAG 질의응답..."
	@if [ -z "$(QUERY)" ]; then \
		echo "❌ 질문이 필요합니다. QUERY=\"질문 내용\"을 지정하세요."; \
		exit 1; \
	fi
	@if [ -z "$(CHANNEL)" ]; then \
		echo "❌ 채널명이 필요합니다. CHANNEL=\"채널명\"을 지정하세요."; \
		exit 1; \
	fi
	@if ! command -v printenv >/dev/null || [ -z "$$(printenv GEMINI_API_KEY)" ]; then \
		echo "❌ GEMINI_API_KEY 환경변수가 설정되지 않았습니다."; \
		exit 1; \
	fi
	@if ! $(PYTHON) -c "import ydh" 2>/dev/null; then \
		echo "❌ Y-Data-House 모듈이 설치되지 않았습니다."; \
		exit 1; \
	fi
	$(YDH) ask-gemini "$(QUERY)" --channel "$(CHANNEL)"

.PHONY: ask-gemini-stream
ask-gemini-stream: $(VENV_NAME)  ## 🤖 스트리밍 RAG 답변
	@echo "🤖 스트리밍 Gemini RAG 질의응답..."
	@if [ -z "$(QUERY)" ]; then \
		echo "❌ 질문이 필요합니다. QUERY=\"질문 내용\"을 지정하세요."; \
		exit 1; \
	fi
	@if ! command -v printenv >/dev/null || [ -z "$$(printenv GEMINI_API_KEY)" ]; then \
		echo "❌ GEMINI_API_KEY 환경변수가 설정되지 않았습니다."; \
		exit 1; \
	fi
	@if ! $(PYTHON) -c "import ydh" 2>/dev/null; then \
		echo "❌ Y-Data-House 모듈이 설치되지 않았습니다."; \
		exit 1; \
	fi
	@cmd="$(YDH) ask-gemini \"$(QUERY)\" --stream"; \
	if [ -n "$(CHANNEL)" ]; then \
		cmd="$$cmd --channel \"$(CHANNEL)\""; \
	fi; \
	eval $$cmd

.PHONY: generate-prompts
generate-prompts: $(VENV_NAME)  ## 🎯 Gemini로 채널별 프롬프트 자동 생성
	@echo "🎯 Gemini로 채널별 프롬프트 자동 생성..."
	@if ! command -v printenv >/dev/null || [ -z "$$(printenv GEMINI_API_KEY)" ]; then \
		echo "❌ GEMINI_API_KEY 환경변수가 설정되지 않았습니다."; \
		exit 1; \
	fi
	@if ! $(PYTHON) -c "import ydh" 2>/dev/null; then \
		echo "❌ Y-Data-House 모듈이 설치되지 않았습니다."; \
		exit 1; \
	fi
	$(YDH) generate-prompts --method gemini

.PHONY: generate-prompts-channel
generate-prompts-channel: $(VENV_NAME)  ## 🎯 특정 채널 프롬프트 생성
	@echo "🎯 특정 채널 프롬프트 생성..."
	@if [ -z "$(CHANNEL)" ]; then \
		echo "❌ 채널명이 필요합니다. CHANNEL=\"채널명\"을 지정하세요."; \
		exit 1; \
	fi
	@if ! command -v printenv >/dev/null || [ -z "$$(printenv GEMINI_API_KEY)" ]; then \
		echo "❌ GEMINI_API_KEY 환경변수가 설정되지 않았습니다."; \
		exit 1; \
	fi
	@if ! $(PYTHON) -c "import ydh" 2>/dev/null; then \
		echo "❌ Y-Data-House 모듈이 설치되지 않았습니다."; \
		exit 1; \
	fi
	$(YDH) generate-prompts --channels "$(CHANNEL)" --method gemini

.PHONY: list-prompts
list-prompts: $(VENV_NAME)  ## 📝 저장된 채널 프롬프트 목록 조회
	@echo "📝 저장된 채널 프롬프트 목록 조회..."
	@if ! $(PYTHON) -c "import ydh" 2>/dev/null; then \
		echo "❌ Y-Data-House 모듈이 설치되지 않았습니다."; \
		exit 1; \
	fi
	@cmd="$(YDH) list-prompts"; \
	if [ -n "$(CHANNEL)" ]; then \
		cmd="$$cmd --channel \"$(CHANNEL)\""; \
	fi; \
	eval $$cmd

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
	@echo "🚀 CLI 도구 명령어:"
	@echo "  make init                 - 기본 환경 설정 (가상환경 생성, 초기 파일 생성)"
	@echo "  make install              - 의존성 설치 (가상환경 활성화 후 실행)"
	@echo "  make download             - 🚀 최적화된 다운로드 (신규 영상 빠른 확인)"
	@echo "  make download-fast        - ⚡ 병렬 다운로드 (3개 워커, 더 빠름)"
	@echo "  make download-full-scan   - 🔍 전체 무결성 검사 (누락 영상 복구)"
	@echo "  make download-full-scan-fast - 🔍🚀 병렬 전체 무결성 검사"
	@echo "  make download-legacy      - 📺 기존 방식 다운로드 (개별 채널 처리)"
	@echo "  make check                - Vault 데이터 정합성 검사"
	@echo "  make embed                - 벡터 임베딩 생성 (AI 검색 기반 구축)"
	@echo "  make search               - 벡터 검색 테스트 (QUERY=\"검색어\" 필요)"
	@echo "  make ask                  - DeepSeek RAG 질문-답변 (QUERY=\"질문\" 필요)"
	@echo "  make embed-clean          - 벡터 임베딩 데이터베이스 초기화"
	@echo "  make clean                - 가상환경 삭제"
	@echo ""
	@echo "🤖 Gemini 벡터 검색 시스템:"
	@echo "  make gemini-embed           - Gemini 벡터 임베딩 생성"
	@echo "  make gemini-embed-channels  - 특정 채널만 임베딩 (CHANNELS=\"채널1,채널2\")"
	@echo "  make search-gemini          - Gemini 벡터 검색 (QUERY=\"검색어\")"
	@echo "  make gemini-channels        - 검색 가능한 채널 목록"
	@echo "  make gemini-stats           - Gemini 데이터베이스 통계"
	@echo "  make gemini-clean           - Gemini 임베딩 데이터베이스 삭제"
	@echo "  make gemini-rebuild         - Gemini 시스템 전체 재구축"
	@echo ""
	@echo "📚 검색 세션 관리:"
	@echo "  make list-sessions          - 저장된 검색 세션 목록 표시"
	@echo "  make list-sessions-channel  - 특정 채널의 세션만 표시 (CHANNEL=\"채널명\")"
	@echo "  make delete-session         - 특정 세션 삭제 (SESSION_ID=\"세션ID\")"
	@echo "  make export-session         - 세션을 HTML로 내보내기 (SESSION_ID=\"세션ID\")"
	@echo "  make clean-sessions         - 30일 이상 된 세션 정리"
	@echo "  make clean-sessions-week    - 7일 이상 된 세션 정리"
	@echo ""
	@echo "🤖 Gemini RAG 질의응답:"
	@echo "  make ask-gemini            - Gemini RAG 질의응답 (QUERY=\"질문\")"
	@echo "  make ask-gemini-channel    - 특정 채널 RAG 질의응답 (QUERY=\"질문\" CHANNEL=\"채널명\")"
	@echo "  make ask-gemini-stream     - 스트리밍 RAG 답변 (QUERY=\"질문\")"
	@echo "  make generate-prompts      - Gemini로 채널별 프롬프트 자동 생성"
	@echo "  make generate-prompts-channel - 특정 채널 프롬프트 생성 (CHANNEL=\"채널명\")"
	@echo "  make list-prompts          - 저장된 채널 프롬프트 목록 조회"
	@echo ""
	@echo "📱 데스크톱 앱 명령어:"
	@echo "  make desktop-init  - 데스크톱 앱 개발환경 설정 (Rust, Node.js, pnpm)"
	@echo "  make desktop-dev   - 데스크톱 앱 개발 모드 실행"
	@echo "  make desktop-build - 데스크톱 앱 프로덕션 빌드"
	@echo "  make desktop-clean - 데스크톱 앱 정리 (node_modules, 빌드 파일 삭제)"
	@echo ""
	@echo "💡 CLI 도구 사용법:"
	@echo "  1. make init                       # 기본 환경 설정"
	@echo "  2. source venv/bin/activate        # 가상환경 활성화"
	@echo "  3. make install                    # 의존성 설치"
	@echo "  4. channels.txt 편집                # 다운로드할 채널 URL 추가"
	@echo "  5. make download                   # 영상 다운로드 (빠른 확인)"
	@echo "  6. make download-full-scan         # 전체 무결성 검사 (누락 영상 복구)"
	@echo "  7. make check                      # 데이터 정합성 검사"
	@echo "  8. make embed                      # 벡터 임베딩 생성"
	@echo "  9. make ask QUERY=\"투자 전략은?\"    # AI 질문-답변 시스템"
	@echo ""
	@echo "🤖 Gemini 검색 사용법:"
	@echo "  1. export GEMINI_API_KEY=\"키\"       # Gemini API 키 설정"
	@echo "  2. make gemini-embed               # Gemini 임베딩 생성"
	@echo "  3. make search-gemini QUERY=\"검색어\" # Gemini 벡터 검색"
	@echo "  4. make gemini-stats               # 검색 데이터베이스 통계"
	@echo ""
	@echo "🔍 Gemini 검색 고급 옵션:"
	@echo "  make search-gemini QUERY=\"검색어\" CHANNEL=\"채널명\"  # 특정 채널에서만"
	@echo "  make search-gemini QUERY=\"검색어\" YEAR=\"2023\"     # 특정 연도만"
	@echo "  make search-gemini QUERY=\"검색어\" NUM=5            # 결과 개수 제한"
	@echo ""
	@echo "📱 데스크톱 앱 사용법:"
	@echo "  1. make desktop-init               # 데스크톱 앱 개발환경 설정"
	@echo "  2. make desktop-dev                # 데스크톱 앱 실행"