# 5. EvaluationAgent – スコアで品質チェック

## やりたいこと
LLM の出力に点数と理由を付け、その結果をフローの意思決定に活かしたい。

### `EvaluationAgent` を使う理由
- `target` の内容を評価し、JSON `{score, reasons}` を解析して自動でコンテキストに保存します。
- FunctionNode で毎回パース処理を書く手間を省けます。

## 手順
1. FlowRuntime を設定。
2. `EvaluationAgent` に `prompt` / `target` / 出力先を指定。
3. `bind`・`_execute` し、`ctx.metrics.*` を確認。

```python
from illumo_flow import EvaluationAgent, NodeConfig

evaluator = EvaluationAgent(
    config=NodeConfig(
        name="Reviewer",
        setting={
            "prompt": {
                "type": "string",
                "value": "{{ $ctx.messages.greeting }} を0-100点で評価し、JSON {'score':...,'reasons':...} を返してください",
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
print(ctx["metrics"]["score"], ctx["metrics"]["reason"], ctx["metrics"]["details"])
```

## YAML 版
```yaml
flow:
  entry: review
  nodes:
    review:
      type: illumo_flow.nodes.EvaluationAgent
      context:
        inputs:
          prompt: "{{ $ctx.messages.greeting }} を0-100点で評価し、JSON {'score':...,'reasons':...} を返してください"
          target: $ctx.messages.greeting
        outputs: $ctx.metrics.score
        metadata_path: $ctx.metrics.reason
        structured_path: $ctx.metrics.details
```
```bash
illumo run evaluate_greeting.yaml --context '{"messages": {"greeting": "Hello world"}}'
```
- 自動パイプラインに組み込むなら Python 例を、CLI で素早く採点したいときは YAML フローを使いましょう。

## 評価ノードの強み
- `target` には任意のコンテキストパスを指定できるため、ドラフト文章だけでなくツール出力や会話全体も採点できます。
- JSON 解析はロバストで、素のテキストが返ってきても数値スコアを抽出し、残りをメタデータとして保存します。
- ConsoleTracer 上では評価ノードがマゼンタで表示され、ドラフト生成との区別が一目瞭然です。
- Policy のリトライと組み合わせれば、自動修正後に再採点するワークフローが簡単に組めます。

## チャレンジ
- モデルに `{"score":0-100,"reasons":[],"action_items":[]}` のようなフォーマットを要求し、`structured_path` に `action_items` を格納して RouterAgent から活用してみましょう。
- `output_path` を `$ctx.metrics.history[-1].score` にすると、過去スコアの履歴リストを維持できます。
- ユーザー満足度バージョンとコンプライアンスチェック版というようにプロンプトを変えて 2 回評価し、`ctx.metrics.details` の違いを比較してみてください。
- 低スコアの場合はフォローアップ用 Agent にルーティングし、書き直した結果を再度 EvaluationAgent に通して改善サイクルを完成させましょう。

## この章で学んだこと
- `EvaluationAgent` はスコアと理由を自動的に解析・保存してくれる評価ノードです。
- JSON 形式が得られれば構造化情報を `ctx.metrics` に蓄積できます。
- 第6章でマルチエージェントアプリに組み込む準備が整いました。
