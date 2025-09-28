# 第2章 · 直列フローの構築

最小構成の ETL フロー（extract → transform → load）を題材に、どのように設計し、DSL で配線し、コンテキストとやり取りするかを順を追って確認します。

## 2.1 フローのゴール
- 入力ペイロードとして任意のユーザー入力を受け取り、`extract` でソース情報を構築する。
- `transform` で抽出結果を正規化し、下流がそのまま扱える形へ整える。
- `load` で最終的な処理結果（ここでは永続化済み ID）を返し、コンテキストへ監査用情報を残す。

この直列フローは単一のエントリーポイントから順にノードを流すだけですが、実運用ではこの形を土台に分岐やファンアウトを追加していきます。

## 2.2 接続 DSL とデータの流れ
- ノード間の配線は文字列 DSL で表し、`"extract >> transform"` のように `>>` を使って順序を記述します。複数ノードを並べる場合は配列で列挙し、`Flow.from_dsl(nodes, entry, edges)` でグラフへ展開されます。
- ノードはペイロードを入力として受け取り、戻り値を次ノードに引き渡します。同時に `outputs` に宣言したパス（例: `$ctx.data.normalized`）へ値がコピーされ、共有コンテキストから監査できます。
- コンテキストに保存された値は次ノードの `inputs="$ctx.data.raw"` のような記法で参照でき、DSL と組み合わせることでデータフローを明示的に表現します。

## 2.3 設計プロセス
1. ノードの役割と順序を言語化する（extract → transform → load）。
2. 各ステップ間で受け渡すペイロードのスキーマを整理し、必要なキー・構造を決める。
3. 結果を書き込む共有コンテキスト上の場所（例: `$ctx.data.persisted`）を定義しておく。

事前にこれらを固めると、後からノードを差し替える場合でも影響範囲を把握しやすくなります。

## 2.4 ノード実装例
```python
from illumo_flow import Flow, FunctionNode

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

flow = Flow.from_dsl(nodes=nodes, entry="extract", edges=["extract >> transform", "transform >> load"])
ctx = {}
flow.run(ctx)
print(ctx["data"]["persisted"])  # stored:42
```

ペイロードのみでノード間を接続しつつ、`outputs` によって監査用データが共有コンテキストへ残ります。

## 2.5 安全な拡張
- ノード追加時はエッジを宣言的に増やす（例: `"load >> publish"`）。
- YAML/辞書設定も同時に更新し、設定とコードを同期させる。
- ビジネスロジックは関数へ閉じ込め、フロー層は配線に専念させる。

## 設計・実装・動作検証ポイントまとめ
- **フロー計画**: 必要ステップとペイロードスキーマを先に整理し、コンテキストの書き込み先（例: `$ctx.data.persisted`）を決めておく。
- **ノード実装**: ペイロードのみを引数にし、`outputs` で監査用の値を宣言的に記録しながら副作用を最小化する。
- **結果確認**: 実行後に `ctx["payloads"]["load"]` や `ctx["data"]["persisted"]` を確認し、業務上の期待値と合致するかをチェックする。
- **フェイルファスト検証**: 試験的に `transform` で例外を発生させ、アプリケーションが想定どおりに異常停止・ロールバックするかを確認する。
- **設定同期**: DSL で追加したノード・エッジは YAML/辞書設定にも反映し、運用チームが参照する設定資料とずれないように保つ。
