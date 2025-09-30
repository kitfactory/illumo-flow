# 第3章 · 分岐・ルーティング・ループ

条件分岐と繰り返しを伴うフローを構築するため、まずはルーティング結果の扱いとループノードの動作を整理し、そのうえで実装例を確認します。

## 3.1 ルーティング関連クラスの責務
- **RoutingNode**: `Node` を継承した意思決定ノード。`routing_rule(payload)` を呼び出し、`Routing` もしくは `(Routing, payload)` を 1 件または複数件返して後続ノードを宣言します。
- **Routing**: 単一の後続に対する判断結果で、`target`（行き先）と任意の `confidence` / `reason` を持ちます。ペイロードを上書きしたい場合は `(Routing(...), payload)` の形で返します。

これにより「判断をデータとして記述する層」と「実際に分岐を実行する層」を分離し、DSL 配線と合わせて宣言的なフロー設計を実現します。

## 3.2 ルーティングインターフェース
- `RoutingNode(..., routing_rule=callable)` は、`callable(payload)` が `Routing`、`(Routing, payload)`、またはそれらのシーケンスを返すことを要求します。各 `Routing.target` は DSL で宣言したブランチ名（例: `approve`, `review`）と一致させます。
- 条件を実際に評価するのは `routing_rule` であり、その判断結果を **データ構造として** `Routing` に詰めて Flow に返します。
- Flow は `context['routing'][node_id]` に `Routing.to_context()` の一覧（`{target, confidence, reason}`）を記録し、選択履歴や監査情報として参照できるようにします。
- 空のリスト（`[]`）を返すと後続ノードは実行されず、安全に停止できます。

> ✅ **ポイント**: `routing_rule` が判断を行い、結果を `Routing` の列として Flow に渡します。含まれる `target` は実際に実行したいブランチだけで、条件式そのものは含まれません。複数件返せばファンアウト、空リストを返せば早期停止です。

## 3.3 サンプルフローの狙い
本章のサンプルでは以下の意思決定を想定しています。
- スコアに応じて `approve` または `review` へペイロードを引き渡す。
- ブランチごとに監査用メタデータ（信頼度や理由）を残す。
- 監査ログとして後から判断の妥当性を確認できるようにする。

### ブランチと条件分岐の捉え方
- `Routing.target` は `if/elif/else` で選択する行き先と同じ役割を担います。
- `if score >= 0.8: go approve else: go review` のような命令的コードと結果は同じですが、判断結果をデータとして宣言している点が異なります。
- `confidence` や `reason` を併記できるため、`if/else` よりもリッチに説明情報を残せます。DSL 配線と組み合わせることで、条件と実行順序の宣言を分離し、監査しやすいフローを維持できます。

## 3.4 ルーティング実装例
```python
from illumo_flow import Flow, CustomRoutingNode, Routing, FunctionNode, NodeConfig

def classify(payload):
    score = payload.get("score", 0.85)
    if score >= 0.8:
        target = "approve"
        reason = "score>=0.8"
    else:
        target = "review"
        reason = "score<0.8"

    decision_payload = {**payload, "decision": target}
    return Routing(
        target=target,
        confidence=score,
        reason=reason,
    ), decision_payload



def approve(payload):
    return "approved"


def review(payload):
    return "pending"

MODULE = __name__

def routing_node(name, rule_path):
    return CustomRoutingNode(
        config=NodeConfig(
            name=name,
            setting={"routing_rule": {"type": "string", "value": rule_path}},
        )
    )


def fn_node(name, func_path, *, outputs):
    return FunctionNode(
        config=NodeConfig(
            name=name,
            setting={"callable": {"type": "string", "value": func_path}},
            outputs=outputs,
        )
    )


nodes = {
    "classify": routing_node("classify", f"{MODULE}.classify"),
    "approve": fn_node(
        "approve",
        f"{MODULE}.approve",
        outputs={"auto": {"type": "expression", "value": "$ctx.decisions.auto"}},
    ),
    "review": fn_node(
        "review",
        f"{MODULE}.review",
        outputs={"manual": {"type": "expression", "value": "$ctx.decisions.manual"}},
    ),
}

flow = Flow.from_dsl(nodes=nodes, entry="classify", edges=["classify >> (approve | review)"])
ctx = {}
flow.run(ctx, user_input={"score": 0.92})
```

実行後に `context['routing']['classify']` を確認すると、選択されたターゲットと信頼度・理由が記録されています。Flow はここで宣言されたターゲットだけを実行します。

## 3.5 ループのメンタルモデル
- `LoopNode` はユーザー入力やコンテキスト内のシーケンスを順番に取り出し、ボディノード（`body_route`）へ引き渡します。次の要素が残っていれば自分自身を再度キューに積みます。
- `enumerate_items=True` を指定すると、各イテレーションに `{"item": 値, "index": i}` が渡されるため、インデックス情報を活用できます。
- ループ内のノードは複数回実行されるため、副作用は冪等に保ち、共有コンテキストを扱う場合は `request_context()` で扱うキーを明示します。

## 3.6 ループ実装例
```python
from illumo_flow import Flow, FunctionNode, LoopNode, NodeConfig

def collect(payload, context):
    context.setdefault("results", []).append(payload)
    return payload

def loop_node(name, *, body_route, enumerate_items=False):
    setting = {"body_route": {"type": "string", "value": body_route}}
    if enumerate_items:
        setting["enumerate_items"] = {"type": "bool", "value": True}
    return LoopNode(config=NodeConfig(name=name, setting=setting))


def fn_node(name, func_path):
    setting = {"callable": {"type": "string", "value": func_path}}
    return FunctionNode(config=NodeConfig(name=name, setting=setting))


nodes = {
    "loop": loop_node(name="loop", body_route="worker", enumerate_items=True),
    "worker": fn_node(name="worker", func_path=f"{MODULE}.collect"),
}

flow = Flow.from_dsl(nodes=nodes, entry="loop", edges=["loop >> worker", "loop >> loop"])
ctx = {}
flow.run(ctx, user_input=["a", "b", "c"])
```

- `loop` は `user_input` から要素を取り出し、`worker` に `{"item": 値, "index": i}` を渡します。
- `worker` はコンテキストへ収集結果を追記し、ループが完了すると `ctx['results']` に処理済み一覧が残ります。

## 設計・実装・動作検証ポイントまとめ
- **分岐計画**: 判断基準とターゲット名、後続ノードを先に整理し、監査で必要なメタデータを決める。
- **ルーティング検証**: 実行後に `context['routing'][node_id]` を確認し、選択されたターゲットと `confidence` / `reason` が期待どおりかをチェックする。
- **早期停止**: ガード条件で停止したい場合は `[]` を返し、後続ノードが動作しないことを確認する。
- **ループ設計**: 入力コレクションのスキーマや `enumerate_items` の有無を決め、ボディノードを冪等に実装する。
- **ループ検証**: `context` の蓄積結果や `steps` を確認し、期待回数だけループしたか、出力が整合しているかを検証する。
