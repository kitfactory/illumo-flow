# 6. マルチエージェントミニアプリを作る

## やりたいこと
複数のエージェントが協力してリリース可否を判断する “ローンチアドバイザー” を構築したい。

### この構成を使う理由
- `Agent` が文章を作り、`EvaluationAgent` が採点し、`RouterAgent` が Ship/Refine を決めます。
- `ctx.notes`、`ctx.metrics`、`ctx.route` といった共有コンテキストによりステップ間で情報が受け渡されます。

## フロー概要
1. `AuthorAgent` がリリースノート案を作成。
2. `EvaluationAgent` がスコア付け。
3. `RouterAgent` が「Ship or Refine」を判断。
4. スコアが低ければ再度 `AuthorAgent` へループ。

## Python 実装例
```python
from illumo_flow import Flow, Agent, EvaluationAgent, RouterAgent, NodeConfig

author = Agent(
    config=NodeConfig(
        name="AuthorAgent",
        setting={
            "prompt": {"type": "string", "value": "{{ $ctx.feature.name }} のリリースノートを作成してください"},
            "output_path": {"type": "string", "value": "$ctx.notes.draft"},
        },
    )
)

review = EvaluationAgent(
    config=NodeConfig(
        name="ReviewAgent",
        setting={
            "prompt": {
                "type": "string",
                "value": "{'score':0-100,'reasons':...} の JSON を返してください",
            },
            "target": {"type": "string", "value": "$ctx.notes.draft"},
            "output_path": {"type": "string", "value": "$ctx.metrics.score"},
            "metadata_path": {"type": "string", "value": "$ctx.metrics.reason"},
            "structured_path": {"type": "string", "value": "$ctx.metrics.details"},
        },
    )
)

decide = RouterAgent(
    config=NodeConfig(
        name="RouterAgent",
        setting={
            "prompt": {
                "type": "string",
                "value": "スコア {{ $ctx.metrics.score }} / 理由 {{ $ctx.metrics.reason }}\nShip か Refine を選択してください。",
            },
            "choices": {"type": "sequence", "value": ["Ship", "Refine"]},
            "output_path": {"type": "string", "value": "$ctx.route.decision"},
            "metadata_path": {"type": "string", "value": "$ctx.route.reason"},
        },
    )
)

flow = Flow.from_dsl(
    nodes={"author": author, "review": review, "decide": decide},
    entry="author",
    edges=["author >> review", "review >> decide"],
)

context = {"feature": {"name": "Smart Summary"}}
flow.run(context)
print(context["route"]["decision"], context["route"]["reason"])
```

## YAML 例
```yaml
flow:
  entry: author
  nodes:
    author:
      type: illumo_flow.nodes.Agent
      context:
        inputs:
          prompt: "{{ $ctx.feature.name }} のリリースノートを作成してください"
        outputs: $ctx.notes.draft
    review:
      type: illumo_flow.nodes.EvaluationAgent
      context:
        inputs:
          prompt: "{'score':0-100,'reasons':...} の JSON を返してください"
          target: $ctx.notes.draft
        outputs: $ctx.metrics.score
        metadata_path: $ctx.metrics.reason
        structured_path: $ctx.metrics.details
    decide:
      type: illumo_flow.nodes.RouterAgent
      context:
        inputs:
          prompt: |
            スコア {{ $ctx.metrics.score }} / 理由 {{ $ctx.metrics.reason }}
            Ship か Refine を選択してください。
        choices: [Ship, Refine]
        output_path: $ctx.route.decision
        metadata_path: $ctx.route.reason
  edges:
    - author >> review
    - review >> decide
```
```bash
illumo run flow_launch.yaml --context '{"feature": {"name": "Smart Summary"}}'
```
- サービスに組み込む際は Python 実装を、チームでリプレイする際は YAML フローを共有しましょう。

## 任意のループ
`decide >> author` を追加し、Refine のときだけドラフト作成に戻す条件を用意します。

## ナラティブの工夫
- `ctx.notes.versions` のようにリストを用意し、ドラフトの各バージョンを保存しておくと EvaluationAgent が過去との比較をしやすくなります。
- `ctx.metrics.reason` を著者エージェントのプロンプトに差し込み、レビュアーのフィードバックを即座に反映させましょう。
- RouterAgent に `metadata_path` を指定して「Ship を選んだ理由」を記録すると、後で Policy のフォールバック条件に活用できます。
- ConsoleTracer では各エージェントの instruction / input / response が色分けされ、漫画のコマのようにフローの物語を追えます。

## ストレッチ課題
- コンプライアンス特化の EvaluationAgent を追加し、スコアを平均してからルーティングする構成を試してください。
- 著者ノードに Policy のリトライ設定（例: 最大2回の指数バックオフ）を加え、プロバイダの揺らぎに備えましょう。
- 実行ごとに `json.dump(ctx, open("launch_snapshot.json"))` のようにコンテキストを保存して、意思決定のタイムラプスを作ってみましょう。

## この章で学んだこと
- 複数のエージェントを連携させることで「チーム」のようなフローを構築できる。
- `ctx.notes`、`ctx.metrics`、`ctx.route` を通じてドラフト→採点→判断のストーリーが繋がる。
- RouterAgent を活用すれば採点結果に応じたループや分岐を簡単に設計可能。

第7章ではトレーサーを切り替えてフローの裏側を観察します。
