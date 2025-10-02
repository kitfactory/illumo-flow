# 6. マルチエージェントミニアプリを作る

## 目標
Agent → RouterAgent → EvaluationAgent を組み合わせ、「リリース判定アプリ」を構築します。

## 楽しいポイント
- 複数の LLM エージェントが役割分担して協力する様子が見えます。
- コンテキストにストーリーが蓄積され、後から分析しやすくなります。

## ワークフロー概要
1. `AuthorAgent` がリリースノート案を生成。
2. `EvaluationAgent` がスコア付け。
3. `RouterAgent` が Ship/Refine を決定。
4. 必要なら再度 `AuthorAgent` に戻るループ。

## DSL 例
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
            Draft score: {{ $ctx.metrics.score }}
            Reasons: {{ $ctx.metrics.reason }}
            Choose Ship or Refine.
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

## ループ拡張（任意）
- `decide >> author` のエッジを追加し、`RouterAgent` が Refine を返したときのみ再トライ。
- `ctx.history.author` を参照し、過剰ループを防ぐロジックを仕込む。

## チェックリスト
- [ ] ドラフト／スコア／意思決定が一連のフローで得られる。
- [ ] 理由 (`ctx.route.reason`) が記録され、後からレビューできる。
- [ ] ループが必要なときだけ発動する。

次章ではトレーサーを切り替え、フローの裏側を覗き見します。
