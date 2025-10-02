# 5. EvaluationAgent – スコアで品質チェック

## 目標
LLM 出力を採点し、そのスコアや理由を構造化データとして保存します。

## 面白い点
- 「合格ライン 80 点以上なら Ship」のようなガードレールを簡単に導入できます。
- JSON 出力を解析しやすく保存でき、後続処理がはかどります。

## キー概念
- `target` で評価対象を指定。
- JSON 応答の解析とフォールバック（プレーンテキストの場合）。
- `structured_path` で詳細情報を保持。

## ハンズオン
```python
from illumo_flow import EvaluationAgent, NodeConfig

evaluator = EvaluationAgent(
    config=NodeConfig(
        name="Reviewer",
        setting={
            "prompt": {
                "type": "string",
                "value": "{{ $ctx.messages.greeting }} に対して JSON {'score':0-100,'reasons':...} を返してください",
            },
            "target": {"type": "string", "value": "$ctx.messages.greeting"},
            "output_path": {"type": "string", "value": "$ctx.metrics.score"},
            "metadata_path": {"type": "string", "value": "$ctx.metrics.reason"},
            "structured_path": {"type": "string", "value": "$ctx.metrics.details"},
        },
    )
)

evaluator.bind("review")
ctx = {"messages": {"greeting": "Hello world"}}
score = evaluator._execute({}, ctx)

print("score=", score)
print(ctx["metrics"])
```

## チェックリスト
- [ ] スコアが戻り値と `ctx.metrics.score` に保存される。
- [ ] 理由 (`reasons`) や構造化 JSON が対応パスに書き込まれる。
- [ ] `ctx.metrics.review` 系統が連続実行でも情報を積み上げる。

いよいよ第 6 章では複数エージェントを束ねた “ミニアプリ” づくりに挑戦します。
