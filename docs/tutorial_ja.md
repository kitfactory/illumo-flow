# Flow チュートリアル

## 1. クイックスタート
- 仮想環境を作成 (`uv venv --seed`)、`.venv` を有効化。
- 開発インストール: `pip install -e .`
- 最小フローを実行:

```bash
python -m examples linear_etl
```

最終ペイロード (`persisted`) と `steps`・`payloads` の内容が表示されれば成功です。

## 2. 最初のフローを作る（線形 ETL）
1. `examples/ops.py` の `extract` / `transform` / `load` を確認。いずれも `(context, payload)` を受け取り、`context["outputs"]` と `context["payloads"]` に保存します。
2. ノードを組み立ててフローを作成:

```python
from illumo_flow import Flow, FunctionNode
from examples import ops

nodes = {
    "extract": FunctionNode(ops.extract),
    "transform": FunctionNode(ops.transform).requires("extract"),
    "load": FunctionNode(ops.load).requires("transform"),
}

flow = Flow.from_dsl(
    nodes=nodes,
    entry="extract",
    edges=["extract >> transform", "transform >> load"],
)

context = {}
result = flow.run(context)
```

3. `context["payloads"]` がノードID→出力の辞書、`context["steps"]` が実行順を示します。
4. `transform` 内で例外を投げ、Fail-Fast で停止し `failed_node_id` が記録されることを確認。

## 3. ルーティング分岐
1. ルーター例を実行:

```bash
python -m examples confidence_router
```

2. `classify` ノードは `Routing(next, confidence, reason)` を `context["routing"]["classify"]` に書き込みます。Flow は後続候補を検証し、`default_route` をフォールバックに使用します。
3. `examples/ops.classify` を編集して手動レビューを強制し、`steps`/`payloads` の変化を観察。

## 4. 並列エンリッチとジョイン
1. ファンアウト/ファンイン例を実行:

```bash
python -m examples parallel_enrichment
```

2. `seed` から `geo` と `risk` に分岐し、`merge` が `.requires("geo", "risk")` で合流します。
3. `context["joins"]["merge"]` を確認すると、両親の結果が揃うまでバッファされ、揃った時点で `{ "geo": ..., "risk": ... }` が `merge` に渡されます。

## 5. ノード内タイムアウトと早期停止
### ノードがタイムアウトを管理
- `python -m examples node_managed_timeout`
- `call_api_with_timeout` が内部でタイムアウト/リトライを行い、Flow は例外を受け取って Fail-Fast で停止します (`steps` に履歴が残ります)。

### 早期停止
- `python -m examples early_stop_watchdog`
- `guard` が `Routing(next=None, reason=...)` を書き込み、下流ノードを実行せずに正常終了します。

## 6. 独自フローの作成手順
1. `(context, payload)` 形式のノード関数を作成し、`context["payloads"][node_id]` に出力を保存します。必要に応じて `describe()` に `context_inputs` / `context_outputs` を記述。
2. ノード辞書を用意し `.requires(...)` で依存関係を宣言。
3. `Flow.from_dsl` でエッジを定義（文字列 DSL または `(src, dst)` タプル）。
4. Flow を実行し、`context["routing"]` や `context["joins"]`、`context["errors"]` をチェックして挙動を確認。

## 7. 次のステップ
- `tests/test_flow_examples.py` を参考に、フロー単位の pytest を整備する。
- `context["steps"]` を用いてログ/トレースの収集を行う。
- 詳細設計 (`docs/flow.md` / `docs/flow_ja.md`) を参照し、コンテキスト命名規約やライフサイクルを把握する。
