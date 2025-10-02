# Chat Bot Demo

このサンプルは FAQ 応答とエスカレーションを行うマルチエージェント構成の例です。`illumo run` を使って CLI から確認できます。

## ディレクトリ構成

```
examples/multi_agent/chat_bot/
├─ chatbot_flow.yaml          # フロー定義
├─ data/
│   └─ faqs.json              # FAQ データベース
└─ handoff.py                 # エスカレーション/監査用のユーティリティ
```

## 実行方法

```bash
illumo run examples/multi_agent/chat_bot/chatbot_flow.yaml \
  --context '{
    "chat": {
      "history": [
        {"role": "user", "message": "返品したいのですが"}
      ]
    },
    "request": {
      "profile": {"tier": "standard"}
    }
  }'
```

- `chat.history` にユーザー発話を入れると、RouterAgent が FAQ 応答をするかエスカレーションするかを判断します。
- `handoff.py` の `handoff_to_human` 関数は擬似的にサポートチケットを作成し、`data/handoff_log.jsonl` に記録します。
- `audit_conversation` は会話履歴を `data/audit_log.jsonl` に追加します。

## ノード構成

- `Agent (greet)` : 開始メッセージと要約。
- `RouterAgent (faq_router)` : FAQ → エスカレーションの判定。
- `Agent (faq)` : FAQ の回答生成。
- `FunctionNode (handoff)` : `handoff_to_human` を呼び出してサポートチケット作成を模擬。
- `FunctionNode (audit)` : 会話履歴を記録。

## 注意事項

- FAQ の選択ロジックは RouterAgent のプロンプトで簡単に条件分岐します。実運用では Agent / SummaryAgent でより詳細な判定やログ記録を組み合わせてください。
- エスカレーションや監査用のログは JSON Lines 形式で `data/` 配下に追記されます。
- LLM プロンプトには日本語で指示していますが、用途に応じてカスタマイズ可能です。
