# 8. ポリシーで失敗をコントロールする

## やりたいこと
例外が出てもフロー全体を止めず、最小限の設定でリトライやフォールバックを実現したい。

### `Policy` を使う理由
- `fail_fast` / `retry` / `timeout` / `on_error` を宣言的に組み合わせるだけで、n8n や Prefect でも使われる典型パターンを再現できます。
- 実装側に try/except を増やさず、ノード単位で挙動を切り替えられます。

## 主な設定
- `fail_fast`: True なら即停止、False なら続行（既定は True）。
- `retry`: `{max_attempts, delay, mode}` で固定 / 指数バックオフを指定。
- `timeout`: 文字列（例 `"15s"`）。
- `on_error`: `stop` / `continue` / `goto: <node_id>`。

## 手順
```python
from illumo_flow import FlowRuntime, Policy, Retry, OnError

FlowRuntime.configure(
    policy=Policy(
        fail_fast=False,
        retry=Retry(max_attempts=2, delay=0.5, mode="fixed"),
        timeout="10s",
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

## YAML 版（全体 + ノード）
```yaml
flow:
  entry: risky
  policy:
    fail_fast: false
    timeout: 10s
    retry:
      max_attempts: 2
      delay: 0.5
      mode: fixed
    on_error:
      action: goto
      target: fallback
  nodes:
    risky:
      type: illumo_flow.core.FunctionNode
      policy:
        fail_fast: true
        retry:
          max_attempts: 1
          delay: 0
    fallback:
      type: illumo_flow.nodes.Agent
      context:
        inputs:
          prompt: "{{ $ctx.input }} の処理でフォールバックを実行したことをオペレーターに知らせてください"
        outputs: $ctx.messages.fallback
```
```bash
illumo run policy_demo.yaml --context '{"input": "payload"}'
```
- コード側で制御したい場合は Python 例を、CLI で運用チームがリトライ設定を切り替えたい場合は YAML 例を活用してください。

### 観察ポイント
- `fail_fast=False` にすると Flow は継続し、`ctx.errors` に失敗情報が蓄積されます。
- リトライが発生すると ConsoleTracer に `node.retry` イベントが出力されます。
- `goto` 指定でフォールバックノードがキューに積まれ、滑らかに回復できます。

### 推奨プロファイル
- **開発**: `Policy(fail_fast=False, retry=Retry(max_attempts=2, delay=0.2), on_error=OnError(action="continue"))` — エラーがあっても継続し、ログを見ながら改善。
- **ステージング**: `Policy(fail_fast=False, retry=Retry(max_attempts=3, delay=0.5, mode="exponential"), timeout="10s", on_error=OnError(action="goto", target="notify"))` — 自動回復を試しつつ、繰り返し失敗は通知。
- **本番**: `Policy(fail_fast=True, retry=Retry(max_attempts=1), timeout="5s", on_error=OnError(action="goto", target="support"))` — 失敗は即座に人や代替経路へ切り替え、影響を最小化。

## Policy レシピ集
- **実験モード**: `fail_fast=False`、`retry=Retry(max_attempts=3, delay=0.2, mode="exponential")`、`on_error=OnError(action="continue")` で止めずに挙動を観察。
- **本番ローンチ**: `fail_fast=True` に設定し、`on_error` で `support_escalation` ノードへ `goto` させると即座に通知に回せます。
- **安全ネット**: `timeout="5s"` と RouterAgent のフォールバックを組み合わせ、評価が長引くと人間レビューへ誘導する仕立てに。

## さらに深掘り
- Policy は「グローバル設定 → フロー/CLI の上書き → ノード個別設定」の順にマージされ、最後に来た値が優先されます。
- `timeout` は `illumo_flow.policy.duration.parse_duration` で解析され、`s` や `ms` のサフィックスに対応。無効な文字列は即例外になるため設定ミスを早期に発見できます。
- リトライ履歴は `ctx.errors[ノードID]['retries']` に保存され、監査やモニタリングで活用できます。
- Tracer には `flow.policy.apply` や `node.retry` といったイベントが流れるので、OTEL ダッシュボードに表示して挙動を可視化しましょう。

## この章で学んだこと
- グローバル Policy は `FlowRuntime.configure` でまとめて設定し、ノード内 `policy` で個別に上書きできます。
- 再試行・タイムアウト・フォールバックを設定だけで表現でき、コードを複雑にしません。
- 準備が整ったところで、第9章では次のアクションを整理します。
