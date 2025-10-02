# 2. Agent 基礎 – 会話するノードを作る

## やりたいこと
LLM に挨拶文を生成させ、その結果や履歴をコンテキストに保存したい。

### `Agent` を使う理由
- `illumo_flow.nodes.Agent` はプロンプト・応答・履歴・メタデータを自動で管理します。
- FunctionNode でも可能ですが、コンテキスト書き込みを自分で実装する必要があります。

## 手順
1. FlowRuntime を設定して ConsoleTracer + デフォルト Policy を有効化。
2. `NodeConfig` で `prompt` / `output_path` などを指定して `Agent` を生成。
3. `bind` して `_execute`、`ctx.messages` や `ctx.agents.<id>` を確認。

```python
from illumo_flow import FlowRuntime, Agent, NodeConfig

FlowRuntime.configure()

greeter = Agent(
    config=NodeConfig(
        name="Greeter",
        setting={
            "model": {"type": "string", "value": "gpt-4.1-nano"},
            "prompt": {"type": "string", "value": "こんにちは、{{ $ctx.user.name }}さん！"},
            "output_path": {"type": "string", "value": "$ctx.messages.greeting"},
            "history_path": {"type": "string", "value": "$ctx.history.greeter"},
        },
    )
)

greeter.bind("greeter")
ctx = {"user": {"name": "葵"}}
response = greeter._execute({}, ctx)

print(response)
print(ctx["messages"]["greeting"])
print(ctx["history"]["greeter"])
```

## YAML 版
```yaml
flow:
  entry: greet
  nodes:
    greet:
      type: illumo_flow.nodes.Agent
      context:
        inputs:
          model: gpt-4.1-nano
          prompt: "こんにちは、{{ $ctx.user.name }}さん！"
        outputs: $ctx.messages.greeting
        history_path: $ctx.history.greeter
        metadata_path: $ctx.history.greeter_metadata
```
```bash
illumo run agent_greet.yaml --context '{"user": {"name": "葵"}}'
```
- アプリケーションコードに組み込むときは Python 例を、チームで CLI 共有したいときは YAML フローを使い分けてください。

## バリエーション
- LMStudio に切り替えるには `provider`, `model`, `base_url` を設定するだけ。
- `metadata_path` を指定すれば reasoning やツール出力も記録できます。
- JSON を返す場合は `structured_path` を使っておくと、後続ノードが構造化データとして安全に参照できます。

## 仕組みを覗く
- Agent は `provider` / `model` / `base_url` を統合して `get_llm()` に渡し、LMStudio や Ollama のような OpenAI 互換エンドポイントには自動で `/v1` を補完します。
- 応答は指定した `history_path` に加えて、既定の `ctx["agents"]["greeter"]` 配下 (`history` / `response` / `metadata`) にも記録され、どちらからでも参照できます。
- Tracer は毎回 `instruction` / `input` / `response` の 3 イベントを色付きで吐き出すため、複数エージェントの会話でも視覚的に追いやすくなっています。
- `output_path` を省略した場合でも `ctx.agents.greeter.response` に値が入るため、明示的な保存先はデータをコピーまたは移動する役割になります。

## 挑戦してみよう
- プロンプト文字列を `prompt_path`（例: `$ctx.prompts.greeting`）に切り替え、実行時にコンテキストで差し込む仕組みを試してみましょう。
- JSON で挨拶文と豆知識を返し、`structured_path` に保存して Chapter 5 の EvaluationAgent で採点させてみると構造化連携のメリットが分かります。
- `ctx.agents.greeter.metadata` を表示し、プロバイダのレイテンシやトークン使用量がどのように記録されているか観察してみてください。

## この章で学んだこと
- `Agent` クラスを使えば LLM 応答と履歴管理まで含めた会話ノードを簡単に作れる。
- テンプレート式 (`{{ $ctx.* }}`) でコンテキスト値をプロンプトに埋め込める。
- プロバイダの切り替えが軽量で、実験しやすい。
