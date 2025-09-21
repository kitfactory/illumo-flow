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

def extract(ctx, _):
    return {"customer_id": 42, "source": "demo"}

def transform(ctx, payload):
    return {**payload, "normalized": True}

def load(ctx, payload):
    return f"stored:{payload['customer_id']}"

nodes = {
    "extract": FunctionNode(extract, outputs="data.raw"),
    "transform": FunctionNode(transform, inputs="data.raw", outputs="data.normalized"),
    "load": FunctionNode(load, inputs="data.normalized", outputs="data.persisted"),
}

flow = Flow.from_dsl(
    nodes=nodes,
    entry="extract",
    edges=["extract >> transform", "transform >> load"],
)

context = {}
result = flow.run(context)
print(result)                       # stored:42
print(context["data"]["persisted"])  # stored:42
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
      callable: examples.ops.extract
      context:
        outputs: data.raw
    transform:
      type: illumo_flow.core.FunctionNode
      callable: examples.ops.transform
      context:
        inputs: data.raw
        outputs: data.normalized
    load:
      type: illumo_flow.core.FunctionNode
      callable: examples.ops.load
      context:
        inputs: data.normalized
        outputs: data.persisted
  edges:
    - extract >> transform
    - transform >> load
```

```python
from illumo_flow import Flow

flow = Flow.from_config("./flow.yaml")
context = {}
flow.run(context)
print(context["data"]["persisted"])
```

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
- `Routing(next, confidence, reason)` による動的ルーティング
- 複数親ノードは自動的にジョイン処理
- ETL / 分岐 / 並列ジョイン / タイムアウト / 早期停止サンプル
