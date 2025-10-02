# 8. ポリシーで失敗をコントロールする

## 目標
`Policy(fail_fast, retry, timeout, on_error)` を使ってエラー発生時の挙動を制御します。

## 楽しい理由
- ハプニングが起きても自動リトライや代替ルートでリカバリーできます。
- 設定を変えるだけで実験モード ↔ 本番モードの切り替えが自由自在。

## キー設定
- `fail_fast`: True なら即停止、False なら続行。
- `retry`: `{max_attempts, delay, mode}` で再試行を制御。
- `timeout`: 文字列で秒指定 (`"15s"` など)。
- `on_error`: `stop` / `continue` / `goto: <node_id>`。

## ハンズオン
```python
from illumo_flow import FlowRuntime, Policy, Retry, OnError

FlowRuntime.configure(
    policy=Policy(
        fail_fast=False,
        timeout="10s",
        retry=Retry(max_attempts=2, delay="0.5s", mode="exponential"),
        on_error=OnError(action="goto", target="fallback"),
    )
)
```

### ノードごとの上書き
```yaml
nodes:
  risky:
    type: illumo_flow.core.FunctionNode
    policy:
      fail_fast: true
      retry:
        max_attempts: 1
        delay: 0
```

### 観察ポイント
- `fail_fast=False` のときは Flow が止まらず `ctx.errors` に記録される。
- リトライ時には Tracer に `node.retry` イベントが出力される。
- `goto` で代替ノードへ移行する場合、Queue にターゲットが追加される。

## チェックリスト
- [ ] グローバル Policy を変えると挙動が変わる。
- [ ] ノードごとの `policy` がグローバル設定より優先される。
- [ ] 失敗履歴が `ctx.errors` に残る。

これでエラーハンドリングも万全。最終章で今後の応用方法をチェックしましょう。
