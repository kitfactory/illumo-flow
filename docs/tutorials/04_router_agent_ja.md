# 4. RouterAgent – 分岐の決め手

## やりたいこと
フローを “Ship” か “Refine” に分岐させ、その理由も追跡したい。

### `RouterAgent` を使う理由
- `choices` によって応答を明確に分岐へマッピングできる。
- `output_path` / `metadata_path` で結果と理由を自動保存。
- `ctx.routing.<id>` が意思決定履歴を時系列で残す。

## 手順
1. FlowRuntime を設定（第1章参照）。
2. `RouterAgent` に `choices` とプロンプトを指定。
3. `bind`・`_execute` して `ctx.route` / `ctx.routing` を確認。

```python
from illumo_flow import RouterAgent, NodeConfig

router = RouterAgent(
    config=NodeConfig(
        name="Decision",
        setting={
            "prompt": {"type": "string", "value": "Context: {{ $ctx.review }}\nChoose Ship or Refine."},
            "choices": {"type": "sequence", "value": ["Ship", "Refine"]},
            "output_path": {"type": "string", "value": "$ctx.route.decision"},
            "metadata_path": {"type": "string", "value": "$ctx.route.reason"},
        },
    )
)

router.bind("decision")
ctx = {"review": "Tests are green and stakeholders approved."}
routing = router._execute({}, ctx)

print(routing.target, routing.reason)
print(ctx["route"]["decision"], ctx["route"]["reason"])
print(ctx["routing"]["decision"])
```

## YAML 版
```yaml
flow:
  entry: decision
  nodes:
    decision:
      type: illumo_flow.nodes.RouterAgent
      context:
        inputs:
          prompt: |
            Context: {{ $ctx.review }}
            Choose Ship or Refine.
          choices:
            - Ship
            - Refine
        output_path: $ctx.route.decision
        metadata_path: $ctx.route.reason
```
```bash
illumo run router_decision.yaml --context '{"review": "Tests are green and stakeholders approved."}'
```
- オーケストレーションをカスタム実装するときは Python 版を、CLI で分岐ロジックを共有したいときは YAML 版を活用しましょう。

## 捜査メモ
- `choices` は大文字小文字を無視して突き合わせるため、`ship` や `REFINE` と返ってきても正しくマッピングされます。
- 実行結果オブジェクトには `target` / `reason` / `metadata` が含まれ、特に `metadata` にはツール呼び出しや reasoning が保持されます。
- `ctx.routing.decision` には `timestamp` / `target` / `reason` が追加され、意思決定の時系列ログとして後からエクスポート可能です。
- ConsoleTracer の色付き表示と組み合わせれば、分岐理由（既定ではシアン）がハイライトされ、レビューが楽しくなります。

## ミニクエスト
- 第8章の Policy と組み合わせ、`Defer` という 3 つ目の選択肢を追加して評価スコアが閾値ぎりぎりの時にリトライさせるシナリオを試してみましょう。
- Router の結果を FunctionNode に渡し、Webhook 経由でダッシュボードを更新。レスポンスを `ctx.audit.router_push` に保存するとトレーサーとの突合せができます。
- プロバイダを LMStudio や Ollama に切り替えても `/v1` 自動追加のおかげで正しく分岐する様子を観察してみてください。

## この章で学んだこと
- `RouterAgent` は LLM 応答を `choices` の候補にマッピングして分岐できる。
- `output_path` / `metadata_path` で決定と理由が自動的に保存される。
- `ctx.routing` を見れば過去の意思決定を時系列で追跡できる。

第5章では EvaluationAgent でスコア付けを行い、フローをさらにリッチにします。
