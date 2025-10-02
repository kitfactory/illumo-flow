# illumo-flow

宣言的 DSL と Fail-Fast 実行モデルを備えたワークフローオーケストレーション基盤です。

## 開発者に選ばれる理由
1. **様々な言語モデルを簡単に**: ランタイムがプロバイダ差分を吸収し、OpenAI / Anthropic / LM Studio / Ollama などを同じコードで動かせるため、`/v1` 付与などの細かな違いを気にせず実験から本番へ移行できます。
2. **エージェントのフロー制御を簡単に**: DSL でフローを記述し、オーケストレーターから明示的に制御できるので、会話ノードや分岐の動作を見通し良く管理できます。
3. **トレース（記録・デバッグ）が簡単に**: 色付きコンソールの会話ログから SQLite 永続化（将来的には OTEL 連携）まで切り替え一つ。print 依存のデバッグから卒業できます。
4. **制御管理の切り替えが簡単に**: 開発中は緩いリトライ、本番は厳格な Fail-Fast といった切替を設定だけで実現でき、コードを触らずにフローの挙動を調整できます。

### トレーシングの切り替え
```python
from illumo_flow import FlowRuntime, SQLiteTracer

FlowRuntime.configure(
    tracer=SQLiteTracer(db_path="illumo_trace.db"),
)
```

```python
from illumo_flow import FlowRuntime, OtelTracer

FlowRuntime.configure(
    tracer=OtelTracer(exporter=my_otlp_exporter),
)
```

CLI からは以下のように指定できます。

```bash
illumo run flow.yaml --context '{"payload": {}}' --tracer sqlite --trace-db illumo_trace.db
illumo run flow.yaml --context '{"payload": {}}' --tracer otel --service-name demo-service
```

ConsoleTracer は即時デバッグ用、SQLite / Tempo バックエンドは履歴保管・監視向けに活用してください。


### トレース検索の例
```python
from illumo_flow.tracing_db import SQLiteTraceReader

reader = SQLiteTraceReader('illumo_trace.db')
for span in reader.spans(kind='node', limit=5):
    print(span.name, span.status)
```

## インストール
```bash
pip install illumo-flow
```

## クイックスタート
```python
from illumo_flow import Flow, FunctionNode, NodeConfig

# まずはペイロードだけを扱う関数を定義（共有コンテキストは必要時のみアクセス）

def extract(payload):
    return {"customer_id": 42, "source": "demo"}

def transform(payload):
    return {**payload, "normalized": True}

def load(payload):
    return f"stored:{payload['customer_id']}"

nodes = {
    "extract": FunctionNode(
        config=NodeConfig(
            name="extract",
            setting={"callable": {"type": "string", "value": f"{__name__}.extract"}},
            outputs={"raw": {"type": "expression", "value": "$ctx.data.raw"}},
        )
    ),
    "transform": FunctionNode(
        config=NodeConfig(
            name="transform",
            setting={"callable": {"type": "string", "value": f"{__name__}.transform"}},
            inputs={"payload": {"type": "expression", "value": "$ctx.data.raw"}},
            outputs={
                "normalized": {"type": "expression", "value": "$ctx.data.normalized"}
            },
        )
    ),
    "load": FunctionNode(
        config=NodeConfig(
            name="load",
            setting={"callable": {"type": "string", "value": f"{__name__}.load"}},
            inputs={
                "payload": {"type": "expression", "value": "$ctx.data.normalized"}
            },
            outputs={
                "persisted": {"type": "expression", "value": "$ctx.data.persisted"}
            },
        )
    ),
}

flow = Flow.from_dsl(
    nodes=nodes,
    entry="extract",
    edges=["extract >> transform", "transform >> load"],
)

context = {}
flow.run(context)
print(context["data"]["persisted"])  # stored:42

# Flow.run は加工後のコンテキストを返します。各ノードの出力も
# `context["payloads"]` に保持されます。
```

## サンプル / CLI
GitHub リポジトリには CLI とサンプル DSL が同梱されています。利用する場合はリポジトリを取得してください。
```bash
git clone https://github.com/kitfactory/illumo-flow.git
cd illumo-flow

# YAML フローを CLI から実行
illumo run examples/multi_agent/chat_bot/chatbot_flow.yaml --context '{"chat": {"history": []}}'

# TraceQL 風クエリでトレースを検索
illumo trace list --traceql 'traces{} | pick(trace_id, root_service, start_time) | limit 10'
illumo trace search --traceql 'span.attributes["node_id"] == "inspect"'
illumo trace show --traceql 'trace_id == "TRACE_ID"' --format json --no-events

# 失敗レポートとタイムアウトフィルタ
illumo run flow.yaml --context @ctx.json --report-path logs/failure.json --report-format markdown --log-dir logs
illumo trace search --timeout-only --format json
```

`illumo run` は失敗時にトレース ID・失敗ノード・ポリシー情報を含むサマリを出力します。`--report-path` / `--report-format` で JSON / Markdown レポートを保存し、`--log-dir` で `runtime_execution.log` の出力先を切り替えられます。`trace list/show/search` には `--format table|json|markdown` を追加しており、`trace show --format tree` は DAG 表示、`trace search --timeout-only` はタイムアウトした span のみを抽出します。

## YAML 設定からの構築
設定ファイルだけでフローを定義することも可能です:

```yaml
flow:
  entry: extract
  nodes:
    extract:
      type: illumo_flow.core.FunctionNode
      name: extract
      context:
        inputs:
          callable: examples.ops.extract
        outputs: $ctx.data.raw
    transform:
      type: illumo_flow.core.FunctionNode
      name: transform
      context:
        inputs:
          callable: examples.ops.transform
          payload: $ctx.data.raw
        outputs: $ctx.data.normalized
    load:
      type: illumo_flow.core.FunctionNode
      name: load
      context:
        inputs:
          callable: examples.ops.load
          payload: $ctx.data.normalized
        outputs: $ctx.data.persisted
  edges:
    - extract >> transform
    - transform >> load
```

各ノードの Python 関数は `context.inputs.callable` で指定します。文字列リテラルはビルド時にインポートされ、`$ctx.registry.func` のような式は実行時に解決されます。

## モジュール構成
- `illumo_flow.core` — フロー／ノードのオーケストレーションと DSL・YAML ローダー
- `illumo_flow.policy` — リトライ・タイムアウト・on_error を表すポリシーモデル群
- `illumo_flow.runtime` — `FlowRuntime` と `get_llm` を含むグローバル設定レイヤー
- `illumo_flow.tracing` — Agents SDK 互換の Console／SQLite／OTel トレーサーアダプタ
- `illumo_flow.llm` — Agent 連携で共有する標準 LLM クライアントヘルパー

### Agent ノード
- `illumo_flow.nodes.Agent` — `output_path` / `history_path` / `metadata_path` / `structured_path` を使い分けて応答や履歴を保存（未指定時は `ctx.agents.<node_id>` へ格納）
- `illumo_flow.nodes.RouterAgent` — `choices` で指定した分岐候補から 1 つを選び、理由とともに記録
- `illumo_flow.nodes.EvaluationAgent` — `target` の内容を評価し、スコア・理由・構造化 JSON を保存

```python
from illumo_flow import FlowRuntime, Agent, RouterAgent, EvaluationAgent, NodeConfig

FlowRuntime.configure()

ctx = {"request": "テストはすべて成功しました。"}

greeter = Agent(
    config=NodeConfig(
        name="Greeter",
        setting={
            "model": {"type": "string", "value": "gpt-4.1-nano"},
            "prompt": {"type": "string", "value": "レビュワーに挨拶してください。"},
            "output_path": {"type": "string", "value": "$ctx.messages.greeting"},
        },
    )
)

router = RouterAgent(
    config=NodeConfig(
        name="Decision",
        setting={
            "prompt": {"type": "string", "value": "Context: {{ $ctx.request }}"},
            "choices": {"type": "sequence", "value": ["Ship", "Refine"]},
            "output_path": {"type": "string", "value": "$ctx.route.decision"},
            "metadata_path": {"type": "string", "value": "$ctx.route.reason"},
        },
    )
)

review = EvaluationAgent(
    config=NodeConfig(
        name="Review",
        setting={
            "prompt": {"type": "string", "value": "'score' と 'reasons' を含む JSON で回答してください。"},
            "target": {"type": "string", "value": "$ctx.messages.greeting"},
            "output_path": {"type": "string", "value": "$ctx.metrics.score"},
            "structured_path": {"type": "string", "value": "$ctx.metrics.details"},
        },
    )
)

greeter.bind("greeter")
router.bind("decision")
review.bind("review")

greeter._execute({}, ctx)
routing = router._execute({}, ctx)
score = review._execute({}, ctx)
```

### トレーサー設定
```python
from illumo_flow import FlowRuntime, ConsoleTracer, SQLiteTracer, OtelTracer

# ConsoleTracer はデフォルト。FlowRuntime.configure を呼ばなくても色分けログが出力される
FlowRuntime.configure(tracer=ConsoleTracer())

# SQLiteTracer は span / event を SQLite に永続化
FlowRuntime.configure(tracer=SQLiteTracer(db_path="./trace.db"))

# OtelTracer は span を外部エクスポーターへ送信
FlowRuntime.configure(
    tracer=OtelTracer(service_name="illumo-flow", exporter=my_exporter)
)
```

CLI でも指定可能です。
```bash
illumo run flow.yaml --context '{"payload": {}}' --tracer sqlite --trace-db illumo_trace.db
illumo run flow.yaml --context '{"payload": {}}' --tracer otel --service-name demo-service
```

### ポリシー設定
`Policy` を使うと fail-fast / retry / timeout / on_error を宣言的に制御できます。
```python
from illumo_flow import FlowRuntime, Policy, Retry, OnError

FlowRuntime.configure(
    policy=Policy(
        fail_fast=True,
        timeout="15s",
        retry=Retry(max_attempts=2, delay="500ms", mode="exponential"),
        on_error=OnError(action="goto", target="fallback"),
    )
)
```
各ノードの `policy` 設定でグローバル設定を上書きできます。

```python
from illumo_flow import Flow

flow = Flow.from_config("./flow.yaml")
context = {}
flow.run(context)
print(context["data"]["persisted"])
```

### ペイロードとコンテキストの違い
- `inputs` に従って Flow が各ノードの `payload` を算出します。
- ノードは次の `payload` を返却し、Flow が `context["payloads"][node_id]` および `outputs` へ書き込みます。
- 基本方針はペイロード重視です。共有コンテキストが必要な場合は `self.request_context()` を実行中に呼び出し、`context.setdefault("metrics", {})` など操作するキーを事前に取り決めます。

### ブランチング
- 動的に分岐させたい場合は、`{"successor_id": payload}` 形式の辞書を戻り値として返します。そのキーに対応する後続ノードだけが実行されます。
- 空の辞書 `{}` を返すと後続が停止し、複数キーを返すと複数の後続へペイロードをブロードキャストできます。


### 式の書き方
- `$ctx.*`: 共有コンテキストを参照 (例: `$ctx.data.raw`)。`ctx.*` や短縮記法 `$.foo` と書いても内部的に同じく `$ctx.*` へ正規化されます。
- `$payload.*`: `context["payloads"]` を参照
- `$joins.*`: `context["joins"]` を参照
- `$env.VAR`: 環境変数を取得
- テンプレート構文 `"こんにちは {{ $ctx.user.name }}"` は `inputs` などで利用可能

## テスト（リポジトリ利用時）
テストは常に 1 件ずつ実行し、ハングを防ぎながら確実に確認します。

- テストコードは `tests/test_flow_examples.py` に追記・更新します。
- 各ケースは `pytest tests/test_flow_examples.py::TEST_NAME` で個別実行し、ループ検証時は `FLOW_DEBUG_MAX_STEPS=200` を設定してハングを防ぎます。
- 進捗管理は `docs/test_checklist_ja.md` で行い、回帰前には全項目を未チェックへ戻します。

最新のチェックリストは `docs/test_checklist_ja.md` を参照してください。

## ドキュメント
- 英語版アーキテクチャ: [docs/flow.md](docs/flow.md)
- 日本語版アーキテクチャ: [docs/flow_ja.md](docs/flow_ja.md)
- コンセプト概説: [docs/concept.md](docs/concept.md) / [docs/concept_ja.md](docs/concept_ja.md)
- チュートリアル（クイックリファレンス）: [docs/tutorial.md](docs/tutorial.md) / [docs/tutorial_ja.md](docs/tutorial_ja.md)
- 章立てチュートリアル（設計思想とサンプル）: [docs/tutorials/README.md](docs/tutorials/README.md) / [docs/tutorials/README_ja.md](docs/tutorials/README_ja.md)

## ハイライト
- DSL エッジ (`A >> B`, `(A & B) >> C`)
- `inputs` / `outputs` 宣言でコンテキスト上の読取・書込パスを明示
- ペイロード優先（共有コンテキストへアクセスする際は `request_context()` で明示的に扱う）
- LoopNode での逐次ループ処理（例: `loop >> loop`, `loop >> worker` のように body ルートを指定）
- `{successor: payload}` を戻り値とする動的ブランチング
- 複数親ノードは自動的にジョイン処理
- ETL / 分岐 / 並列ジョイン / タイムアウト / 早期停止サンプル
