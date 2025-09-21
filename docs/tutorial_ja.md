# Flow チュートリアル

PyPI からインストールしたライブラリを前提に説明します。

```bash
pip install illumo-flow
```

Python のスクリプト / REPL があれば十分です。サンプル CLI を使いたい場合のみ GitHub リポジトリを取得してください。

## 1. 最小フロー
```python
from illumo_flow import Flow, FunctionNode

def extract(ctx, _):
    return {"customer_id": 42, "source": "demo"}

def transform(ctx, payload):
    return {**payload, "normalized": True}

def store(ctx, payload):
    return f"stored:{payload['customer_id']}"

nodes = {
    "extract": FunctionNode(extract, outputs="data.raw"),
    "transform": FunctionNode(transform, inputs="data.raw", outputs="data.normalized"),
    "store": FunctionNode(store, inputs="data.normalized", outputs="data.persisted"),
}

flow = Flow.from_dsl(nodes=nodes, entry="extract", edges=["extract >> transform", "transform >> store"])
context = {}
result = flow.run(context)
print(result)                      # stored:42
print(context["data"]["persisted"])  # stored:42
```

## 2. Fail-Fast の確認
`transform` で例外を投げると即座に停止し、`context["failed_node_id"]` や `context["errors"]` に情報が残ります。

## 3. ルーティング分岐
```python
from illumo_flow import Flow, FunctionNode, Routing

def classify(ctx, payload):
    ctx["routing"]["classify"] = Routing(next="approve", confidence=90, reason="demo")

nodes = {
    "classify": FunctionNode(classify),
    "approve": FunctionNode(lambda ctx, payload: "approved", outputs="decisions.auto"),
    "reject": FunctionNode(lambda ctx, payload: "rejected", outputs="decisions.auto"),
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

def seed(ctx, _):
    return {"id": 1}

def geo(ctx, payload):
    return {"country": "JP"}

def risk(ctx, payload):
    return {"score": 0.2}

def merge(ctx, payload):
    return {"geo": payload["geo"], "risk": payload["risk"]}

nodes = {
    "seed": FunctionNode(seed, outputs="data.customer"),
    "geo": FunctionNode(geo, inputs="data.customer", outputs="data.geo"),
    "risk": FunctionNode(risk, inputs="data.customer", outputs="data.risk"),
    "merge": FunctionNode(merge, inputs="joins.merge", outputs="data.profile"),
}

flow = Flow.from_dsl(nodes=nodes, entry="seed", edges=["seed >> (geo | risk)", "(geo & risk) >> merge"])
ctx = {}
flow.run(ctx)
print(ctx["data"]["profile"])  # {'geo': {...}, 'risk': {...}}
```
複数の親エッジを持つノードは自動的に全ての親が完了するまで待機し、親ノード名→ペイロードの辞書を受け取ります（`context["joins"][node_id]`）。

## 5. ノード内リトライ / タイムアウト
```python
import time
from illumo_flow import Flow, FunctionNode

attempts = {"count": 0}

def call_api(ctx, _):
    attempts["count"] += 1
    if attempts["count"] < 3:
        time.sleep(0.1)
        raise RuntimeError("temporary failure")
    return {"status": 200}

flow = Flow.from_dsl(nodes={"call": FunctionNode(call_api, outputs="data.api")}, entry="call", edges=[])
flow.run({})
print(attempts["count"])  # 3
```
Flow 自体は Fail-Fast のまま、リトライ制御はノードで完結させる構成です。

## 6. 早期停止
```python
from illumo_flow import Flow, FunctionNode, Routing

def guard(ctx, payload):
    ctx["routing"]["guard"] = Routing(next=None, reason="threshold")

nodes = {
    "guard": FunctionNode(guard),
    "downstream": FunctionNode(lambda ctx, payload: "should_not_run"),
}

flow = Flow.from_dsl(nodes=nodes, entry="guard", edges=["guard >> downstream"])
ctx = {}
flow.run(ctx)
print(ctx["steps"])  # downstream は実行されない
```

## 7. リポジトリのサンプル
CLI (`python -m examples <id>`) や pytest 等の追加デモを利用したい場合は GitHub リポジトリを取得してください。

## 8. 次のステップ
- 上記コードを基に独自ノードと DSL を組み立てる。
- Pytest 等でユニットテストを整備（リポジトリの `tests/test_flow_examples.py` 参照）。
- 詳細仕様は [docs/flow.md](flow.md) / [docs/flow_ja.md](flow_ja.md) を参照。
