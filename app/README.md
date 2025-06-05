# YDH Desktop App

Tauri + React application to browse local videos and query the DeepSeek RAG system.

## Prerequisites

- [Rust](https://rustup.rs) toolchain
- [Node.js](https://nodejs.org) (v18+) and [pnpm](https://pnpm.io)
- Python environment to run `vault/90_indices/rag.py`

The application expects your videos under `vault/10_videos` with each folder containing
`video.mp4` and `captions.md`.

## Development

```bash
# install dependencies
pnpm install

# start the dev server and Tauri window
pnpm tauri

# build standalone binaries
pnpm run build
```

The application expects the repository structure to include `vault/10_videos` and
`vault/90_indices/rag.py`.
