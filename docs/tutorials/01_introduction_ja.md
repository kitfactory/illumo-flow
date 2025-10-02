# 1. はじめに & セットアップ

## やりたいこと
複雑なスクリプトに頼らず、LLM を組み合わせたフローを簡単に構築したい。Agent → Tracer → Policy の役割を最初から理解したい。

### illumo-flow が助けてくれる点
- `illumo_flow.nodes.Agent` などのエージェントノードでプロンプト・履歴・メタデータ管理が完結。
- `Flow` による明示的な制御と、Tracer / Policy で観測性・堅牢性を両立。
- CLI / YAML / Python API の複数インターフェースで運用しやすい。

## 開発者に響くポイント
- グルーコードとお別れ：プロンプト配線や履歴保存、採点ロジックを一気に任せられるので、夜な夜な JSON を手で整形する日々から解放されます。
- 観測が楽しい：設定をひとつ切り替えるだけで、ターミナルに色付き会話ログが流れたり、SQLite に全部残ったり。print デバッグの泥沼からの脱出です。
- 失敗制御が遊び心満点：試作中はリトライをゆるく設定、本番ではガッチリ Fail-Fast に、といった切り替えが設定変更だけで完結します。
- 試作と本番が地続き：CLI・YAML・Python が同じ設計図を共有するので、朝にデモしたフローをそのまま夕方の本番リリースに使えます。
- プロバイダを飛び回れる：OpenAI・Anthropic・LMStudio・Ollama などを切り替えても、`/v1` 付与などの細かい差分はランタイムが面倒を見てくれます。
- 実行ログがチームのネタ帳に：コンテキストがそのままミッションログになり、「この判断、なんでこうなった？」を即座に追跡して次の手を考えられます。

## セットアップ（数分で完了）
1. **インストール**
   ```bash
   pip install illumo-flow
   ```
   （開発版を触りたい場合は `git clone` → `uv pip install -e .`）
2. **資格情報の準備**
   - OpenAI API Key または LMStudio のベース URL (`http://192.168.11.16:1234`)
3. **動作確認**
   ```bash
   pytest tests/test_flow_examples.py::test_examples_run_without_error -q
   ```
4. **デフォルト設定**
   ```python
   from illumo_flow import FlowRuntime, ConsoleTracer
   FlowRuntime.configure(tracer=ConsoleTracer())
   ```

## 舞台裏メモ
- `FlowRuntime.configure` はモジュール内レジストリに tracer / policy を保存するため、CLI (`illumo run`) と Python スクリプトで同じ初期値が共有されます。
- 設定時に LLM ローダーがプロバイダ順序（OpenAI → Anthropic → Google → LMStudio → Ollama → OpenRouter）を読み込み、後の章でワンフリップ切替ができるよう準備します。
- ConsoleTracer は Agent の `instruction` / `input` / `response` を色付きで整形済み。ログ出力を自作しなくても会話の流れを追えるのはこの仕掛けのおかげです。
- 上記の `pytest` は Flow DSL パーサ、YAML ローダー、Tracer ブリッジをまとめて確認するプレビルドチェックになっています。最初に通しておくと後の章がスムーズです。

## さっそく遊んでみる
- 週末ハッカソンを想定して、レポジトリを clone → `pytest` → API Key を `.env` に記載、という流れを一気にやってみましょう。
- 環境変数で `ILLUMO_DEFAULT_PROVIDER=openai` や `lmstudio` を切り替えて同じスクリプトを実行してみると、`get_llm()` の挙動を肌で感じられます。
- これから増えていくコンテキストキー（`ctx.messages.*` や `ctx.metrics.*` など）を書き留めておくと、後の章でトレースや評価の結果を追いかけやすくなります。

## この先の流れ
- 第 2 章で `Agent` を体験
- 第 6 章でミニ・マルチエージェントアプリを構築
- 第 7-8 章で Tracer / Policy を習得

## この章で学んだこと
- illumo-flow は Agent → Tracer → Policy を軸に LLM フローを設計できる。
- インストールと初期設定が手軽で、すぐ試せる。
- 以降の章がこの構成要素を段階的に深掘りしていく。
