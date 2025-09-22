# Flow チュートリアル

PyPI からインストールしたライブラリを前提に説明します。

```bash
pip install illumo-flow
```

Python のスクリプト / REPL があれば十分です。サンプル CLI を使いたい場合のみ GitHub リポジトリを取得してください。

## 1. 最小フロー
```python
from illumo_flow import Flow, FunctionNode

def extract(payload):
    return {"customer_id": 42, "source": "demo"}

def transform(payload, ctx):
    return {**payload, "normalized": True}

def store(payload, ctx):
    return f"stored:{payload['customer_id']}"

nodes = {
    "extract": FunctionNode(extract, name="extract", outputs="$ctx.data.raw"),
    "transform": FunctionNode(
        transform,
        name="transform",
        inputs="$ctx.data.raw",
        outputs="$ctx.data.normalized",
    ),
    "store": FunctionNode(
        store,
        name="store",
        inputs="$ctx.data.normalized",
        outputs="$ctx.data.persisted",
    ),
}

flow = Flow.from_dsl(nodes=nodes, entry="extract", edges=["extract >> transform", "transform >> store"])
context = {}
flow.run(context)
print(context["data"]["persisted"])  # stored:42

Flow.run は更新後の `context` を返し、各ノードの最終出力は
`context["payloads"][node_id]` に格納されます。
```

## 2. Fail-Fast の確認
`transform` で例外を投げると即座に停止し、`context["failed_node_id"]` や `context["errors"]` に情報が残ります。

## 3. ルーティング分岐
```python
from illumo_flow import Flow, FunctionNode

def classify(payload, ctx):
    ctx.route(next="approve", confidence=90, reason="demo")

nodes = {
    "classify": FunctionNode(classify, name="classify"),
    "approve": FunctionNode(
        lambda payload, ctx: "approved",
        name="approve",
        outputs="$ctx.decisions.auto",
    ),
    "reject": FunctionNode(
        lambda payload, ctx: "rejected",
        name="reject",
        outputs="$ctx.decisions.auto",
    ),
}

flow = Flow.from_dsl(nodes=nodes, entry="classify", edges=["classify >> (approve | reject)"])
ctx = {"inputs": {"application": {}}}
flow.run(ctx)
print(ctx["decisions"]["auto"])  # approved
```
`Routing.next` を省略すると全ての後続を実行します。`default_route` を設定すればフォールバック遷移も可能です。

## 4. ファンアウト / ファンイン
```python
from illumo_flow import Flow, FunctionNode

def seed(payload, ctx):
    return {"id": 1}

def geo(payload, ctx):
    return {"country": "JP"}

def risk(payload, ctx):
    return {"score": 0.2}

def merge(payload, ctx):
    return {"geo": payload["geo"], "risk": payload["risk"]}

nodes = {
    "seed": FunctionNode(seed, name="seed", outputs="$ctx.data.customer"),
    "geo": FunctionNode(
        geo,
        name="geo",
        inputs="$ctx.data.customer",
        outputs="$ctx.data.geo",
    ),
    "risk": FunctionNode(
        risk,
        name="risk",
        inputs="$ctx.data.customer",
        outputs="$ctx.data.risk",
    ),
    "merge": FunctionNode(
        merge,
        name="merge",
        inputs="$joins.merge",
        outputs="$ctx.data.profile",
    ),
}

flow = Flow.from_dsl(nodes=nodes, entry="seed", edges=["seed >> (geo | risk)", "(geo & risk) >> merge"])
ctx = {}
flow.run(ctx)
print(ctx["data"]["profile"])  # {'geo': {...}, 'risk': {...}}
```
複数の親エッジを持つノードは自動的に全ての親が完了するまで待機し、親ノード名→ペイロードの辞書を受け取ります（`context["joins"][node_id]`）。

## 5. 複数入力・複数出力
```python
from illumo_flow import Flow, FunctionNode

def split(payload, ctx):
    return {"left": payload[::2], "right": payload[1::2]}

def combine(payload, ctx):
    return payload["left"] + payload["right"]

nodes = {
    "seed": FunctionNode(lambda payload, ctx: "abcdef", name="seed", outputs="$ctx.data.source"),
    "split": FunctionNode(
        split,
        name="split",
        inputs="$ctx.data.source",
        outputs={"left": "$ctx.data.left", "right": "$ctx.data.right"},
    ),
    "combine": FunctionNode(
        combine,
        name="combine",
        inputs={"left": "$ctx.data.left", "right": "$ctx.data.right"},
        outputs="$ctx.data.result",
    ),
}

flow = Flow.from_dsl(nodes=nodes, entry="seed", edges=["seed >> split", "split >> combine"])
ctx = {}
flow.run(ctx)
print(ctx["data"]["result"])  # 'abcdef'
```

YAML 例:

```yaml
flow:
  entry: seed
  nodes:
    seed:
      type: illumo_flow.core.FunctionNode
      name: seed
      context:
        inputs:
          callable: examples.ops.seed
        outputs: $ctx.data.source
    split:
      type: illumo_flow.core.FunctionNode
      name: split
      context:
        inputs:
          callable: examples.ops.split_text
          payload: $ctx.data.source
        outputs:
          left: $ctx.data.left
          right: $ctx.data.right
    combine:
      type: illumo_flow.core.FunctionNode
      name: combine
      context:
        inputs:
          callable: examples.ops.combine_text
          left: $ctx.data.left
          right: $ctx.data.right
        outputs: $ctx.data.result
  edges:
    - seed >> split
    - split >> combine
```

`Flow.from_config("flow.yaml")` で同じ処理を再現できます。


## 6. ノード内リトライ / タイムアウト
```python
import time
from illumo_flow import Flow, FunctionNode

attempts = {"count": 0}

def call_api(payload, ctx):
    attempts["count"] += 1
    if attempts["count"] < 3:
        time.sleep(0.1)
        raise RuntimeError("temporary failure")
    return {"status": 200}

flow = Flow.from_dsl(
    nodes={"call": FunctionNode(call_api, name="call", outputs="$ctx.data.api")},
    entry="call",
    edges=[],
)
flow.run({})
print(attempts["count"])  # 3
```
Flow 自体は Fail-Fast のまま、リトライ制御はノードで完結させる構成です。

## 7. 早期停止
```python
from illumo_flow import Flow, FunctionNode

def guard(payload, ctx):
    ctx.route(next=None, reason="threshold", confidence=100)

nodes = {
    "guard": FunctionNode(guard, name="guard"),
    "downstream": FunctionNode(
        lambda payload, ctx: "should_not_run",
        name="downstream",
    ),
}

flow = Flow.from_dsl(nodes=nodes, entry="guard", edges=["guard >> downstream"])
ctx = {}
flow.run(ctx)
print(ctx["steps"])  # downstream は実行されない
```

## 8. リポジトリのサンプル
CLI (`python -m examples <id>`) や pytest 等の追加デモを利用したい場合は GitHub リポジトリを取得してください。

## 9. 次のステップ
- 上記コードを基に独自ノードと DSL を組み立てる。
- Pytest 等でユニットテストを整備（リポジトリの `tests/test_flow_examples.py` 参照）。
- 詳細仕様は [docs/flow.md](flow.md) / [docs/flow_ja.md](flow_ja.md) を参照。
