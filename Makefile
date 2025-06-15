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
	@echo "  5. make download                   # 영상 다운로드"
	@echo "  6. make check                      # 데이터 정합성 검사"
	@echo "  7. make embed                      # 벡터 임베딩 생성"
	@echo "  8. make ask QUERY=\"투자 전략은?\"    # AI 질문-답변 시스템"
	@echo ""
	@echo "📱 데스크톱 앱 사용법:"
	@echo "  1. make desktop-init               # 데스크톱 앱 개발환경 설정"
	@echo "  2. make desktop-dev                # 데스크톱 앱 실행"