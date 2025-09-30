# 第4章 · ファンアウト / ジョイン / 構造化入力

複数のノードへ処理を分岐させ、後で結果を統合するフローの組み立て方を解説します。まず仕組みと設計ポイントを整理し、そのあとで具体例とコードを確認します。

## 4.1 ファンアウトのメカニズム
- **実行モデル**: DSL で `A >> (B | C)` と宣言すると、ランタイムは同じペイロードを `B` と `C` に送ります。追加のルーティング指定は不要で、エッジが静的ファンアウトを表現します。
- **ジョインバッファ**: 複数の親エッジを持つノードは自動的にジョイン対象となり、親ノードごとのペイロードが `context["joins"][対象ノードID][親ノードID]` に蓄積されます。
- **親ノード順序**: Flow は `Flow.parent_order` に決定的な親順序を保持し、親の完了順が前後してもジョイン結果が安定するようにします。
- **共有コンテキスト**: 各枝の出力は `$ctx.data.geo` など別々のキーに書き込むのが一般的で、最終的なマージ処理も宣言的に表現できます。

## 4.2 設計チェックリスト
1. 複製すべきシードペイロードを特定する。
2. 各枝が出力するデータ構造と保存先（コンテキストパスやフォーマット）を決める。
3. ジョインノードの契約を明確化し、`context["joins"][join_id]` をどのように解釈して最終結果へ変換するか定義する。
4. 監査・デバッグの観点で必要なメタデータ（例: `$ctx.data.profile` など）を書き出すポイントを設計に組み込む。

## 4.3 サンプルフロー: Geo / Risk マージ
シードデータを `geo` と `risk` に並列配信し、`merge` で統合する例です。コードを読む前にデータフローを把握しておくと理解がスムーズです。

- `seed` で顧客 ID を生成し、 `$ctx.data.customer` に保存。
- `geo` と `risk` がそれぞれ地理情報・リスクスコアを計算し、 `$ctx.data.geo` / `$ctx.data.risk` に出力。
- `merge` ノードは `context["joins"]["merge"]` に集まった親ノードの結果を受け取り、統合済みプロフィールを `$ctx.data.profile` へ書き出します。

```python
from illumo_flow import Flow, FunctionNode, NodeConfig

def seed(payload):
    return {"id": 1}

def geo(payload):
    return {"country": "JP"}

def risk(payload):
    return {"score": 0.2}

def merge(inputs):
    return {"geo": inputs["geo"], "risk": inputs["risk"]}

MODULE = __name__

def fn_node(name, func_path, *, inputs=None, outputs=None):
    return FunctionNode(
        config=NodeConfig(
            name=name,
            setting={"callable": {"type": "string", "value": func_path}},
            inputs=inputs,
            outputs=outputs,
        )
    )


nodes = {
    "seed": fn_node(
        "seed",
        f"{MODULE}.seed",
        outputs={"customer": {"type": "expression", "value": "$ctx.data.customer"}},
    ),
    "geo": fn_node(
        "geo",
        f"{MODULE}.geo",
        inputs={"payload": {"type": "expression", "value": "$ctx.data.customer"}},
    ),
    "risk": fn_node(
        "risk",
        f"{MODULE}.risk",
        inputs={"payload": {"type": "expression", "value": "$ctx.data.customer"}},
    ),
    "merge": fn_node(
        "merge",
        f"{MODULE}.merge",
        inputs={"joined": {"type": "expression", "value": "$joins.merge"}},
        outputs={"profile": {"type": "expression", "value": "$ctx.data.profile"}},
    ),
}

flow = Flow.from_dsl(
    nodes=nodes,
    entry="seed",
    edges=["seed >> (geo | risk)", "(geo & risk) >> merge"],
)

ctx = {}
flow.run(ctx)
```

実行後のポイント:
- `context["joins"]["merge"]` は `{ "geo": {"country": "JP"}, "risk": {"score": 0.2} }` となり、ジョイン入力が確認できます。
- `context["data"]["profile"]` にマージ結果が保存されます。

## 4.4 構造化入力と複数出力
- `inputs` に辞書を指定すると、エイリアス付きで複数のコンテキスト値を取得できます。
- `outputs` も辞書にすると、1 ノードで複数パスへ書き込めるため、明示的に `context` を更新する必要がありません。

```python
def split_ranges(payload):
    return {"left": payload[::2], "right": payload[1::2]}

split_config = FunctionNode(
    config=NodeConfig(
        name="split",
        setting={
            "callable": {
                "type": "string",
                "value": f"{MODULE}.split_ranges",
            }
        },
        inputs={"source": {"type": "expression", "value": "$ctx.data.source"}},
        outputs={
            "left": {"type": "expression", "value": "$ctx.data.left"},
            "right": {"type": "expression", "value": "$ctx.data.right"},
        },
    )
)
```

## 4.5 テストの着眼点
- `context["joins"][join_id]` が期待した辞書になっているか確認する。
- 最終的なコンテキスト書き込み（例: `$ctx.data.profile`）をアサートする。
- 親ノードの順序が重要な場合は `Flow.parent_order[join_id]` を活用し、テストで順序を固定する。
- 予測しやすい小さな入力データを使い、リグレッションテストでも同じ結果が得られるようにする。
