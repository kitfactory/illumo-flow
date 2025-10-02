# 2. Agent 基礎 – 会話するノードを作る

## 目標
`Agent` ノードで挨拶メッセージを生成し、結果をコンテキスト (`ctx`) に保存できるようにします。

## 楽しいポイント
- `output_path` を設定するだけで、LLM の応答が好きな場所に保存されます。
- プロバイダ切り替え（OpenAI ⇔ LMStudio）が驚くほど簡単です。

## 学ぶこと
- `NodeConfig` で `Agent` を宣言する方法。
- テンプレート式 (`{{ $ctx.user.name }}`) でコンテキスト値を prompts に埋め込む。
- `ctx.agents.<node_id>` に履歴やメタデータが蓄積される仕組み。

## ハンズオン
```python
from illumo_flow import FlowRuntime, Agent, NodeConfig

FlowRuntime.configure()  # ConsoleTracer + デフォルト Policy

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

## さらに遊ぶ
- LMStudio を試す:
  ```python
  greeter = Agent(
      config=NodeConfig(
          name="LM",
          setting={
              "provider": {"type": "string", "value": "lmstudio"},
              "model": {"type": "string", "value": "openai/gpt-oss-20b"},
              "base_url": {"type": "string", "value": "http://192.168.11.16:1234"},
              "prompt": {"type": "string", "value": "{{ $ctx.topic }} の概要を書いてください"},
          },
      )
  )
  ```
- `metadata_path` を追加して LLM の reasoning や tool 使用ログを保存してみる。

## チェックリスト
- [ ] 個別の挨拶が生成される。
- [ ] `ctx.messages.greeting` に最新応答が入る。
- [ ] `ctx.agents.greeter` に履歴 / メタデータが残る。

準備完了！次はフロー全体を組み立てる第 3 章へ進みましょう。
