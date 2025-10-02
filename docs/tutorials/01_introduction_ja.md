# 1. はじめに & セットアップ

## 何を作るか
- illumo-flow の全体像（フロー指向 / LLM ノード / 宣言的設定）を理解します。
- すぐにエージェントを動かせる開発環境を整えます。

## illumo-flow を使うと楽しい理由
- 手探りのスクリプトから卒業し、LLM ステップ・リトライ・分岐がすべて明示的なパイプラインを構築できます。
- このチュートリアルでは「ミニマルなマルチエージェントアプリ」を作りながら、仕組みを楽しく学びます。

## 必要条件
- Python 3.10 以上
- OpenAI 互換の LLM エンドポイント（OpenAI `gpt-4.1-nano` または LMStudio `openai/gpt-oss-20b` @ `http://192.168.11.16:1234`）
- Git と `uv`（任意ですが推奨）

## ステップ
1. **リポジトリを取得・インストール**
   ```bash
   git clone https://github.com/kitfactory/illumo-flow.git
   cd illumo-flow
   uv pip install -e .
   ```
   (`pip install -e .` でも可)
2. **環境変数の準備**
   - OpenAI API Key または LMStudio のベース URL を用意します。
   - `.env` の設定は任意。チュートリアルでは主に直接引数で渡します。
3. **動作確認**
   ```bash
   pytest tests/test_flow_examples.py::test_examples_run_without_error -q
   ```
   成功すれば準備完了です。

## この先に待つもの
- 第 2 章で `Agent` ノードを作り、`ctx` に応答を保存します。
- 第 6 章では Agent/Router/Evaluation を組み合わせたミニアプリを構築します。
- 第 7-8 章で Tracer / Policy による観測性と堅牢性を習得します。

お気に入りの飲み物を用意して、マルチエージェントの世界を楽しみましょう！
