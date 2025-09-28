# illumo-flow

宣言的 DSL と Fail-Fast 実行モデルを備えたワークフローオーケストレーション基盤です。

## インストール
```bash
pip install illumo-flow
```

## クイックスタート
```python
from illumo_flow import Flow, FunctionNode

# まずはペイロードだけを扱う関数を定義（共有コンテキストは必要時のみアクセス）

def extract(payload):
    return {"customer_id": 42, "source": "demo"}

def transform(payload):
    return {**payload, "normalized": True}

def load(payload):
    return f"stored:{payload['customer_id']}"

nodes = {
    "extract": FunctionNode(extract, name="extract", outputs="$ctx.data.raw"),
    "transform": FunctionNode(
        transform,
        name="transform",
        inputs="$ctx.data.raw",
        outputs="$ctx.data.normalized",
    ),
    "load": FunctionNode(
        load,
        name="load",
        inputs="$ctx.data.normalized",
        outputs="$ctx.data.persisted",
    ),
}

flow = Flow.from_dsl(
    nodes=nodes,
    entry="extract",
    edges=["extract >> transform", "transform >> load"],
)

context = {}
flow.run(context)
print(context["data"]["persisted"])  # stored:42

# Flow.run は加工後のコンテキストを返します。各ノードの出力も
# `context["payloads"]` に保持されます。
```

## サンプル / CLI
GitHub リポジトリには CLI（例: `python -m examples linear_etl`）とサンプル DSL が同梱されています。利用する場合はリポジトリを取得してください。
```bash
git clone https://github.com/kitfactory/illumo-flow.git
cd illumo-flow
python -m examples linear_etl
```

## YAML 設定からの構築
設定ファイルだけでフローを定義することも可能です:

```yaml
flow:
  entry: extract
  nodes:
    extract:
      type: illumo_flow.core.FunctionNode
      name: extract
      context:
        inputs:
          callable: examples.ops.extract
        outputs: $ctx.data.raw
    transform:
      type: illumo_flow.core.FunctionNode
      name: transform
      context:
        inputs:
          callable: examples.ops.transform
          payload: $ctx.data.raw
        outputs: $ctx.data.normalized
    load:
      type: illumo_flow.core.FunctionNode
      name: load
      context:
        inputs:
          callable: examples.ops.load
          payload: $ctx.data.normalized
        outputs: $ctx.data.persisted
  edges:
    - extract >> transform
    - transform >> load
```

各ノードの Python 関数は `context.inputs.callable` で指定します。文字列リテラルはビルド時にインポートされ、`$ctx.registry.func` のような式は実行時に解決されます。

```python
from illumo_flow import Flow

flow = Flow.from_config("./flow.yaml")
context = {}
flow.run(context)
print(context["data"]["persisted"])
```

### ペイロードとコンテキストの違い
- `inputs` に従って Flow が各ノードの `payload` を算出します。
- ノードは次の `payload` を返却し、Flow が `context["payloads"][node_id]` および `outputs` へ書き込みます。
- 基本方針はペイロード重視です。共有コンテキストへアクセスできるのは `allow_context_access=True` を有効にしたノードだけで、その場合でも `context.setdefault("metrics", {})` など予約・明示的な領域に限定して更新します。

### ブランチング
- 動的に分岐させたい場合は、`{"successor_id": payload}` 形式の辞書を戻り値として返します。そのキーに対応する後続ノードだけが実行されます。
- 空の辞書 `{}` を返すと後続が停止し、複数キーを返すと複数の後続へペイロードをブロードキャストできます。


### 式の書き方
- `$ctx.*`: 共有コンテキストを参照 (例: `$ctx.data.raw`)。`ctx.*` や短縮記法 `$.foo` と書いても内部的に同じく `$ctx.*` へ正規化されます。
- `$payload.*`: `context["payloads"]` を参照
- `$joins.*`: `context["joins"]` を参照
- `$env.VAR`: 環境変数を取得
- テンプレート構文 `"こんにちは {{ $ctx.user.name }}"` は `inputs` などで利用可能

## テスト（リポジトリ利用時）
テストは常に 1 件ずつ実行し、ハングを防ぎながら確実に確認します。

- テストコードは `tests/test_flow_examples.py` に追記・更新します。
- 各ケースは `pytest tests/test_flow_examples.py::TEST_NAME` で個別実行し、ループ検証時は `FLOW_DEBUG_MAX_STEPS=200` を設定してハングを防ぎます。
- 進捗管理は `docs/test_checklist_ja.md` で行い、回帰前には全項目を未チェックへ戻します。

最新のチェックリストは `docs/test_checklist_ja.md` を参照してください。

## ドキュメント
- 英語版アーキテクチャ: [docs/flow.md](docs/flow.md)
- 日本語版アーキテクチャ: [docs/flow_ja.md](docs/flow_ja.md)
- コンセプト概説: [docs/concept.md](docs/concept.md) / [docs/concept_ja.md](docs/concept_ja.md)
- チュートリアル（クイックリファレンス）: [docs/tutorial.md](docs/tutorial.md) / [docs/tutorial_ja.md](docs/tutorial_ja.md)
- 章立てチュートリアル（設計思想とサンプル）: [docs/tutorials/README.md](docs/tutorials/README.md) / [docs/tutorials/README_ja.md](docs/tutorials/README_ja.md)

## ハイライト
- DSL エッジ (`A >> B`, `(A & B) >> C`)
- `inputs` / `outputs` 宣言でコンテキスト上の読取・書込パスを明示
- ペイロード優先（`allow_context_access=True` を指定したノードのみ共有コンテキストへ明示アクセス）
- LoopNode での逐次ループ処理（例: `loop >> loop`, `loop >> worker` のように body ルートを指定）
- `{successor: payload}` を戻り値とする動的ブランチング
- 複数親ノードは自動的にジョイン処理
- ETL / 分岐 / 並列ジョイン / タイムアウト / 早期停止サンプル
