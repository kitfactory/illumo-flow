# コンセプト

## ライブラリの意図
- `pip` で導入できる軽量なワークフローランナー
- 短時間で完結する自動化を素早く始めて素早く終える体験を重視
- 設定ファイルや DSL 断片を含めた辞書でフローを記述

## 実行モデル
- `Flow` が受け取ったワークフロー辞書を基に処理をオーケストレーション
- ワークフローは制御やデータの流れを表す `Node` サブクラスを連結して構成
- ノードは結果を返すほか、失敗時には即座に処理を打ち切って終了

## Node のライフサイクル
- 抽象 `Node` は実行とコンテキスト処理に必要な最小限の契約を定義
- 同期 API は `run(user_input: str, context: dict) -> dict` で、更新済みコンテキストを下流ノードへ引き渡す
- `run_async` は `run` を委譲する非同期版で、イベントループ上のワークフローを支援
- 具象ノードはサブクラス検出で起動時に登録され、環境に応じた拡張が可能
- ノードは単一責務と合成しやすさを保ち、肥大化を避ける
- 各ノードは `describe() -> dict` を実装し、モジュール名・説明・引数メタデータ・返り値ヒントを返してツールやローダーが参照できるようにする

## エラーポリシー
- Fail-fast 方針: 原因が分かる情報を添えて即座に例外を送出
- ワークフローで明示されない限り、黙示のリカバリや再試行は実施しない
- ログは失敗箇所の特定に必要な最小限へ絞る

## DSL クイックスタート
```python
from illumo import Flow, FunctionNode

start = FunctionNode(lambda ctx, x: x, name="start", output_path="data.start")
A     = FunctionNode(lambda ctx, x: f"A:{x}", name="A", input_path="data.start", output_path="data.A")
B     = FunctionNode(lambda ctx, x: f"B:{x}", name="B", input_path="data.start", output_path="data.B")
join  = FunctionNode(lambda ctx, inp: f"JOIN:{inp['A']},{inp['B']}", name="join", input_path="joins.join", output_path="data.join")

flow = Flow.from_dsl(
    nodes={"start": start, "A": A, "B": B, "join": join},
    entry=start,
    edges=[
        start >> (A | B),     # fan-out
        (A & B) >> join,      # fan-in
    ],
)

ctx = {}
result = flow.run(ctx, 42)
print(result)         # "JOIN:A:42,B:42"
print(ctx["steps"])  # 実行ログ
```
- シュガー演算子で宣言的な DSL を維持しつつ、命令的ロジックはノード内部に閉じ込める
- 起動時にサブクラスが揃っていれば追加ノードを自動で利用可能

## DSL 演算子
- `A >> B` — 直列。`A` の後に `B` を実行
- `A | B` — OR 候補集合。ルーターは選択分岐へ、通常ノードは両方へ fan-out
- `A & B` — AND 必須集合。両方へ送信し、`(A & B) >> join` のように fan-in を表現

## 設定ファイルでのフロー定義
- `Flow.from_config(path_or_dict, loader=...)` を使うと YAML/TOML/JSON などの定義からグラフを生成できる
- 設定ファイルでも演算子 DSL をそのまま利用してエッジを記述できる例:

```yaml
flow:
  entry: start
  nodes:
    start:
      type: illumo.nodes.FunctionNode
      callable: start_func
      context:
        output: data.start
    A:
      type: illumo.nodes.FunctionNode
      callable: node_a
      context:
        input: data.start
        output: data.A
    B:
      type: illumo.nodes.FunctionNode
      callable: node_b
      context:
        input: data.start
        output: data.B
    join:
      type: illumo.nodes.FunctionNode
      callable: join_func
      context:
        input: joins.join
        output: data.join
  edges:
    - start >> (A | B)
    - (A & B) >> join
```
- ローダーは `start_func` のようなシンボル名を import 文字列やレジストリを通じて実際の Python オブジェクトへ解決する
- パースされた設定は `Flow` が期待する内部辞書形式に正規化され、コード定義フローとの共存が可能
- ノード定義には `summary` や `inputs`、`returns` といったメタデータを含め、`node.describe()` に反映してドキュメント生成や検証に活用できる
- カスタムローダーを用いれば、許可モジュールやサンドボックス方針など環境制約を実行前に検証できる
- 追加で `context.input` / `context.output` を指定すると、共有コンテキストのどこから読み書きするかを制御できる

## 実行時のふるまい
- 並列実行: 依存が揃ったノードは遅延なく起動
- ルーター分岐: `|` はルーター決定に従い、`&` は強制的に全ノードへ送信
- 暗黙の JOIN: 複数の親エッジを持つノードは `{"A": ..., "B": ...}` のように親ノードの出力を辞書で受け取る
- エラー処理: フェイルファスト。`Flow.run` は最初の失敗で例外を送出し、診断情報を `ctx` に保存

```python
try:
    flow.run(ctx, 99)
except Exception as exc:
    print("例外:", exc)

print(ctx["failed_node_id"])
print(ctx["failed_exception_type"])
print(ctx["failed_message"])
print(ctx["errors"])
```

### ルーティング実装ガイドライン
1. DSL 配線で次ノードが一意に決まる場合（例: `A >> B`）は `self.next_routing = "B"` を設定
2. 実行時に分岐が決まる場合は `next_routing` を設定せず、`context["routing"]`（または設定したキー）へ `RoutingInfo` を書き込む
3. 複数の親を持つ合流ノードは、結合結果を `context["joins"]["join_id"]` のような名前空間に保存し後続ノードが参照できるようにする
4. `next_routing` もルーティング情報も無い場合は `Flow` がルーティングエラーを送出（あるいは `default_route` へ退避）し、未定義の遷移を検知する

## バックステージ機能
- Pydantic などによる型バリデーション
- ノード単位のタイムアウト制御
- 並列実行上限
- トレース統合（OpenTelemetry や Langfuse など）

## Flow を選ぶ理由
| 観点 | Flow | LangGraph | Mastra |
| --- | --- | --- | --- |
| 記法 | 演算子 DSL (`| & >>`) | Builder 関数 | Builder 関数 |
| 可読性 | 高（ASCII 演算子で配線が見える） | 中 | 中 |
| 直列/分岐/合流 | 2〜3 行 | 5〜7 行 | 5〜7 行 |
| Router 表現 | `router >> (A | B)` | ルータ関数 + マッピング | ルータ + マッピング |
| JOIN 入力整形 | 辞書を自動生成 | 自前 | 自前 |
| 型/運用 | 裏側で吸収 | 表層に露出 | 表層に露出 |

特徴サマリ
- 短く書ける: 他フレームワークの半分以下の行数になることが多い
- 見やすい: `|`/`&`/`>>` が視覚的に配線を表現
- 運用安心: バリデーションや制御が自動適用
- API 明確: エントリポイントは `Flow.from_dsl` に統一
