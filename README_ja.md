# illumo-flow

宣言的 DSL と Fail-Fast 実行モデルを備えたワークフローオーケストレーション基盤です。

## インストール
```bash
pip install illumo-flow
```

## クイックスタート
```python
from illumo_flow import Flow, FunctionNode

# コンテキスト辞書を扱うノード関数を定義

def extract(payload):
    return {"customer_id": 42, "source": "demo"}

def transform(payload, ctx):
    return {**payload, "normalized": True}

def load(payload, ctx):
    return f"stored:{payload['customer_id']}"

nodes = {
    "extract": FunctionNode(extract, name="extract", outputs="$ctx.data.raw"),
    "transform": FunctionNode(
        transform,
        name="transform",
        inputs="$ctx.data.raw",
        outputs="$ctx.data.normalized",
    ),
    "load": FunctionNode(
        load,
        name="load",
        inputs="$ctx.data.normalized",
        outputs="$ctx.data.persisted",
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
GitHub リポジトリには CLI（例: `python -m examples linear_etl`）とサンプル DSL が同梱されています。利用する場合はリポジトリを取得してください。
```bash
git clone https://github.com/kitfactory/illumo-flow.git
cd illumo-flow
python -m examples linear_etl
```

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
- 共有状態を読み書きする際は、ノードに渡されるコンテキストビュー（`ctx.get(...)`, `ctx.write(...)`, `ctx.route(...)`）を使用し、辞書を直接更新しないようにします。


### 式の書き方
- `$ctx.*`: 共有コンテキストを参照 (例: `$ctx.data.raw`)。`ctx.*` や短縮記法 `$.foo` と書いても内部的に同じく `$ctx.*` へ正規化されます。
- `$payload.*`: `context["payloads"]` を参照
- `$joins.*`: `context["joins"]` を参照
- `$env.VAR`: 環境変数を取得
- テンプレート構文 `"こんにちは {{ $ctx.user.name }}"` は `inputs` などで利用可能

## テスト（リポジトリ利用時）
```bash
pytest
```
`tests/test_flow_examples.py` がサンプル DSL を使ったスモークテストを提供します。

## ドキュメント
- 英語版アーキテクチャ: [docs/flow.md](docs/flow.md)
- 日本語版アーキテクチャ: [docs/flow_ja.md](docs/flow_ja.md)
- コンセプト概説: [docs/concept.md](docs/concept.md) / [docs/concept_ja.md](docs/concept_ja.md)
- チュートリアル: [docs/tutorial.md](docs/tutorial.md) / [docs/tutorial_ja.md](docs/tutorial_ja.md)

## ハイライト
- DSL エッジ (`A >> B`, `(A & B) >> C`)
- `context.input` / `context.output` でコンテキスト上の任意パスに読み書き
- ペイロード優先＋制約付きコンテキストビューによるコール可能インターフェース
- `Routing(next, confidence, reason)` による動的ルーティング
- 複数親ノードは自動的にジョイン処理
- ETL / 分岐 / 並列ジョイン / タイムアウト / 早期停止サンプル
