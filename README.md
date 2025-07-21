# Y-Data-House

YouTubeビデオのダウンロードと文字起こしを行い、Obsidianボルトに構造化されたメタデータと共に自動保存するデスクトップアプリケーションです。

## 概要

このプロジェクトは、YouTubeコンテンツの管理と分析を効率化するために開発されました。ビデオのダウンロード、字幕の抽出、テキスト変換、そしてAIを活用した質問応答システムを統合しています。

## 技術スタック

### フロントエンド
- React 18.2.0 + TypeScript 5.4.0
- Tauri 2.5.1（デスクトップアプリフレームワーク）
- Fuse.js（ファジー検索）

### バックエンド
- Rust（Tokio、Warp）
- Python（Click CLI、Pydantic）
- yt-dlp、youtube-transcript-api

### AI/データベース
- DeepSeek API（LLM）
- ChromaDB（ベクトルデータベース）
- OpenAI Embeddings

## 主な機能

1. **ビデオダウンロード**
   - YouTubeチャンネルの一括ダウンロード
   - 並列処理による高速化（最大3倍の性能向上）
   - 中断・再開機能

2. **文字起こし処理**
   - 多言語字幕の自動抽出（韓国語優先）
   - VTTからMarkdownへの変換
   - タイムスタンプ付きテキスト生成

3. **構造化ストレージ**
   - Obsidianボルト形式での保存
   - チャンネル別・年月別の階層構造
   - メタデータ付きMarkdownファイル

4. **AI質問応答システム**
   - RAG（Retrieval-Augmented Generation）実装
   - チャンネル別の独立したベクトルDB
   - HyDE（Hypothetical Document Embeddings）技術の活用

## システムアーキテクチャ

```
y-data-house/
├── app/                    # Tauriデスクトップアプリ
│   ├── src/               # Reactフロントエンド
│   └── src-tauri/         # Rustバックエンド
├── src/ydh/               # Python CLIパッケージ
├── vault/                 # データストレージ
│   ├── 10_videos/         # ダウンロードしたビデオ
│   └── 90_indices/        # AI/RAGシステム
└── tests/                 # テストファイル
```

## セットアップ

### 必要な環境
- Python 3.8+
- Node.js 18+
- Rust 1.70+
- pnpm

### インストール

```bash
# 環境の初期化
make init

# 開発モードで実行
make desktop-dev
```

### 環境変数

`.env.example`ファイルを参考に、以下の環境変数を設定してください：

```bash
DEEPSEEK_API_KEY=your_api_key
OPENAI_API_KEY=your_openai_key  # 埋め込み用
```

## 使用方法

### CLIコマンド

```bash
# 個別チャンネルのダウンロード
python -m ydh ingest <channel_url>

# 一括ダウンロード（最適化済み）
python -m ydh batch --parallel

# ベクトル埋め込みの生成
python -m ydh embed --channels <channel_names>

# AI質問応答
make ask QUERY="質問内容"
```

### デスクトップアプリ

1. ビデオブラウジング：チャンネル別・年度別の階層表示
2. リアルタイム検索：ファジー検索による高速フィルタリング
3. AI対話：チャンネル別の質問応答インターフェース

## パフォーマンス最適化

- **高速ダウンロード**: 最新20件の動画を優先チェック（90%の時間短縮）
- **並列処理**: 複数チャンネルの同時処理
- **スマートスキャン**: 新規動画がない場合は全体スキャンをスキップ
- **メモリ効率**: 選択的ロードによる50%のメモリ使用量削減

## ライセンス

このプロジェクトは個人使用を目的としており、YouTubeの利用規約に準拠しています。

## 開発者

Y-Data-House Team