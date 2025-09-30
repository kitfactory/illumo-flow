# Flow 設計ガイド

## スコープ
- `Flow` インスタンスがグラフ実行・ルーティング・コンテキスト管理をどのように調停するかを定義する。
- `Node` 実装と共有 `context` 辞書に課される契約を明文化する。
- 直列・動的分岐・ファンイン/ファンアウト・リトライなど、ランタイムが扱うべきシナリオを列挙し、それぞれのモデリング方法を示す。

## 用語
- **Flow**: グラフ、実行キュー、ランタイムポリシーを保持するスケジューラ兼オーケストレータ。
- **Node**: 入力を変換し、共有コンテキストへ情報を追加する実行単位。
- **Edge**: DSL/設定で宣言された後続ノード候補を示す接続。
- **ルーティング結果**: `Routing` オブジェクト。行き先となるノード ID (`target`) と確信度・理由などを保持し、実行時の分岐を表現する。必要に応じてペイロード上書きは `(Routing, payload)` の形で別途返す。
- **Context**: 各ノードがペイロード、メタデータ、診断結果を共有する可変辞書。
- **Join Target**: 複数の上流結果を待つノード（複数の親エッジを持つノードが自動的に該当）。

## API リファレンス概要
### Flow
**主なメソッド**
- `__init__(*, nodes, entry, edges)` — ノードをバインドし、エントリ検証と隣接/依存マップを構築する。
- `from_dsl(*, nodes, entry, edges)` — DSL エッジ表現を展開して `Flow` を生成する。
- `from_config(source)` — YAML/JSON/辞書を DSL 形式に正規化して `Flow` をインスタンス化する。
- `run(context=None, user_input=None)` — グラフを実行し、ルーティングやジョインを処理しつつコンテキストを更新して返却する。

**主な属性**
- `nodes`: `node_id -> Node` のマッピング。
- `entry_id`: エントリノード ID。
- `adjacency` / `reverse`: 後続・前続ノード集合を保持する辞書。
- `parent_counts`: 各ノードが待つべき親ノード数。
- `parent_order`: ジョイン時に利用する親ノードの決定的順序。
- `dependency_counts`: 実行中に消費する依存カウンタ。

### Node
**主なメソッド**
- `__init__(config: NodeConfig) -> None` — 正規化済みの設定オブジェクト（`name` / `setting` / `inputs` / `outputs`）を受け取り、宣言的入出力やメタデータを初期化する。
- `bind(node_id: str) -> None` — Flow が割り当てた ID を関連付ける。
- `node_id` (property) -> str — 関連付け済みのノード ID を取得する。
- `run(payload: Any) -> Any` — サブクラスが実装する本処理。
- `describe() -> Dict[str, Any]` — モジュール/クラス/入出力などのメタデータを返す。
- `request_context() -> MutableMapping[str, Any]` — 実行中の共有コンテキストへアクセスする。

**主な属性**
- `name`: 診断で利用する名称。
- `_inputs` / `_outputs`: 正規化済みの入出力式リスト。
- `_active_context`: 実行中に参照するコンテキスト（内部利用）。

### Routing
**主なメソッド**
- `to_context() -> Dict[str, Any]` — `{target, payload?, confidence?, reason?}` を `context['routing']` 向けにシリアライズする。

**主な属性**
- `target`: 次に実行するノード ID。
- `payload`: 後続へ渡すペイロード（任意）。
- `confidence`: 判断の確信度（任意）。
- `reason`: 判断理由（任意）。

## 中核の責務
### Flow
- ビルド時にグラフを検証し、孤立ノード・欠落依存・サイクルを拒否する。
- 隣接リストを整備する: `outgoing[node_id] -> set[edge]`, `incoming[node_id] -> set[parent_id]`。
- 単一の `ready` キューと依存カウンタでスケジューリングし、親ノードが揃った順に実行する。
- ノード結果を受け取り、`Routing` があれば分岐情報を抽出しつつ、結果オブジェクト自体は `context["payloads"]` に保持する。
- ジョイン対象では上流ノードごとのペイロードを `context["joins"][join_id][parent_id]` に溜め、必要数が揃ったら順序付きで集約する。
- Fail-Fast を維持し、リトライやグローバルタイムアウトは提供せず、失敗時は診断情報を記録して実行を中断する。

### Node
- サブクラスは `run(payload) -> payload` を実装する。`payload` は `inputs` で解決され、Flow が戻り値を `context["payloads"]` および宣言済み `outputs` に書き込む。
- ツールやバリデーションのために `describe()` でメタデータを公開し、参照/書き込みするコンテキストキーを列挙する。
- 単一責務を守り、1ノード=1処理または1つの判断境界とする。
- 静的な遷移は DSL のエッジ定義で固定し、動的分岐が必要な場合は `RoutingNode` を用いて `Routing(target=..., confidence=..., reason=...)` もしくは `(Routing(...), payload)` を返す。
- `inputs` / `outputs`（DSL の `context.inputs` / `context.outputs`）を使って、コンテキスト上の特定のパスから読み書きする。ノードは戻り値として payload を返すだけで、Flow が書き込みを代行する。

### Routing の構造
- `target`: 次に実行するノード ID。
- `confidence` / `reason`: 判断の確信度や理由（任意）。
- ファンアウトは `Routing` を複数件返すか、`(Routing, payload)` のタプルを並べることで表現します。ペイロードを渡さない場合は入力ペイロードが次ノードへ送られます。空のリストを返すと安全に停止できます。
Flow は `{target, confidence, reason}` の配列として `context["routing"][node_id]` に判断結果を保存し、実行後の監査に利用できます。

### Context
- 以下の安定したネームスペースを提供する:
  - `context["steps"]`: `{timestamp, node_id, status, info}` 形式の実行ログ。
  - `context["joins"]`: `join_id -> parent_id -> payload` を格納する多重マップ。
  - `context["errors"]`: ノード例外発生時のエラーレコード。
- `context["routing"]`: `node_id -> List[{target, confidence, reason}]` 形式の決定情報。
- 上記以外は利用者が任意のキーを追加できるが、予約キーは保護されるべき。
- Flow は実行前に `context["joins"]` などの予約ネームスペースを初期化し、ノードは式を通じて参照する。
- `describe()` で宣言された `context_inputs` / `context_outputs` などを参照し、Flow が追加キーを事前確保・検証できる。
- `context["payloads"]`: 各ノードが最後に生成したペイロード。エントリノードは Flow が初期化し、ノード実装は自分のスロットを更新する。
- `context.output` に指定したパスへノードの出力を格納したり、`context.input` で指定したパスから入力を取得したりできる。
- 共有状態の更新は Flow が定めた場所（例: `context.setdefault("metrics", {})` など）に限定し、n8n / Dify と同様にコンテキストアクセスを最小限にする。
  必要時は `self.request_context()` を使用し、操作するキーやスキーマを事前に取り決める。
- `$` で始まる文字列は式として評価されます（例: `$ctx.data.raw`, `$env.API_KEY`）。
- 文字列内の `{{ ... }}` も式を受け付け、テンプレートとして展開されます。
- ノードに渡される `payload` は `inputs` から解決された値であり、共有 `context` とは分離しています。ノードは戻り値として `payload` を返し、Flow が `context["payloads"]` と `outputs` へ書き込みます。共有状態が必要な場合も、`context.setdefault(...)` など明示的な操作に限定します。
- `ctx.*` / `payload.*` / `joins.*` といった `$` 省略形は自動的に `$ctx.*` 等へ正規化されます。`$.foo` のような短縮記法も `$ctx.foo` として扱われます。それ以外の文字列はリテラルのままです。

## 分岐設計
### 静的分岐
- `A >> B` や `A >> (B | C)` のような DSL エッジから直接導出される。
- Flow は後続集合を事前計算し、実行時に分岐不要なノードは自動的にその集合を利用する。
- エントリノードから到達可能であることを検証し、存在しない後続は構築段階で拒否する。

### 動的分岐
- 実行時に分岐が必要なノードは `Routing(target=..., confidence=..., reason=...)` を返し、必要に応じて `(Routing(...), payload)` の形で後続用ペイロードを上書きします。
- 複数の後続を同時に起動したい場合は、これらの要素をシーケンスとして返します。空のリスト（`[]`）を返すと後続を停止できます。
- Flow は `target` が DSL で宣言済みの後続に含まれるか検証し、存在しないノードが指定された場合は `FlowError` を送出します。

## 設定ファイルからのロード
- `Flow.from_config(source)` は YAML/JSON ファイル、または辞書オブジェクトからフローを構築します。
- ノード定義では `type`、`callable`、`context.input` / `context.output`、`describe` などを指定できます。
- 設定例:

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
        output: $ctx.data.raw
    transform:
      type: illumo_flow.core.FunctionNode
      name: transform
      context:
        inputs:
          callable: examples.ops.transform
          payload: $ctx.data.raw
        output: $ctx.data.normalized
    load:
      type: illumo_flow.core.FunctionNode
      name: load
      context:
        inputs:
          callable: examples.ops.load
          payload: $ctx.data.normalized
        output: $ctx.data.persisted
  edges:
    - extract >> transform
    - transform >> load
```

- 利用例:

```python
from illumo_flow import Flow

flow = Flow.from_config("flow.yaml")
context = {}
flow.run(context)

`Flow.run` は更新後の `context` を返し、各ノードの結果は `context["payloads"]` に保持されます。
```

`FunctionNode` は `context.inputs.callable` に実装パスを指定します。リテラル文字列は実行時にオンデマンドで解決され、`$.registry.transform` のような式はコンテキストから評価されます。`CustomRoutingNode` でも同様に `context.inputs.routing_rule`（またはトップレベルの `routing_rule`）を使ってルーティングロジックを解決します。

### ファンアウト / ブロードキャスト
- `A | B` の両エッジを発火させるケースでは、Flow が単一の戻り値を各ターゲットへ共有し、追加のメタデータは付与しません。
- `RoutingNode` は複数の `Routing` や `(Routing, payload)` を返すことで、DSL が選択集合であっても各分岐へ個別ペイロードや確信度を配布できます。

### ルーティング実装ガイドライン
1. **静的ルート指定**: `FunctionNode` など通常ノードはペイロードのみを返し、DSL で宣言された全後続が順番に実行されます。固定ルートは DSL の配線で表現します。
2. **動的分岐**: 後続を実行時に選択する場合は `RoutingNode`（例: `CustomRoutingNode`）を利用し、`Routing(target=..., confidence=..., reason=...)` か `(Routing(...), payload)` を 1 件または複数件返します。
   - Flow は `context["routing"][node_id]` に判断結果（`target`, `confidence`, `reason`）を保存し、宣言済みエッジのうち指定された後続だけを起動します。未知の後続 ID が含まれている場合は `FlowError` を送出して Fail-Fast で停止します。
3. **早期停止**: 後続を実行させたくない場合は空のリスト（`[]`）を返します。Flow は分岐なしと判断し、残りのノードをキューに追加しません。
4. **ジョインとの併用**: ジョイン対象ノードは各親から受け取ったペイロードを `context["joins"][join_id][parent_id]` に蓄積します。RoutingNode から渡されたペイロード上書きも同様に記録され、下流は `$joins.join_id.parent_id` で参照できます。

### ファンイン / ジョイン
- 複数の親エッジを持つノードは自動的にジョイン対象となる。
- Flow は `pending[(join_id)] -> remaining_count` のカウンタで残タスクを追跡する。
- 各上流完了時に `context["joins"][join_id][parent_id]` へペイロードを保存する。
- カウンタが0になったら、集約入力を添えてジョインノードを ready キューへ移す。

### デフォルト・終端ルート
- DSL の配線のみで後続ノードが決まり、動的に切り替える場合は `Routing(target=...)`（必要なら `(Routing(...), payload)`）を返して分岐先を指定します。
- 空のリスト（`[]`）を返すと Flow に正常停止を指示できます。

## 実行ライフサイクル
1. DSL/設定を内部グラフ表現へコンパイルする。
2. 実行状態を初期化し（コンテキスト予約キー、ready キューにエントリノードを投入）、ループを開始する。
3. ディスパッチループ:
   - 並列上限を守りつつキューからノードを取得。
  - `inputs` からペイロードを解決し、`Node.run(payload)` を呼び出す（必要に応じて Flow が実行中のコンテキストをアタッチする）。
   - 成功時: ステップを記録し、戻り値を `outputs` へ保存し、戻り値の辞書から後続を決定して投入する。
   - 失敗時: 診断情報を収集し、失敗キーを設定し、ループを中断。
4. 終了処理: 実行後の `context` 全体を `Flow.run` の戻り値として返し、最終ペイロードは `context["payloads"]` に保持される。

## 状態管理構造
- 隣接リストと逆辺マップは辞書で保持し、依存カウンタと `ready` キューで進捗を追跡する。
- ジョインバッファはターゲットごとの辞書で管理し、必要数が揃った時点で集約する。
- 追加の専用クラスは持たず、Flow 内部で完結するユーティリティ関数で構成する。

## 並列性と順序保証
- 依存カウントが 0 になったノードを単一キューから順次取り出して実行し、同時並列実行は行わない。
- 単一分岐内の順序は保持され、マージはジョインで構築された順序付きペイロードに依存する。
- タイムアウト管理はノード実装側の責務であり、Flow は発生した例外をそのまま扱う。

## エラーハンドリング戦略
- デフォルトは Fail-Fast: 最初の例外で実行を中断するが、診断用に部分的なコンテキストを保持する。
- 例外送出前に `context["failed_node_id"]`, `context["failed_exception_type"]`, `context["failed_message"]` を必ず設定する。
- 回復可能なケースでは空のリスト（`[]`）を返すことで正常停止できる。
- リトライやタイムアウト管理はアプリケーション側（各ノード）で実装し、Flow は結果を受け取って記録する。

## 可観測性要件
- ノード開始・成功・失敗時に `context["steps"]` へ `{node_id, status, message?}` 形式のレコードを追加する。
- Flow は追加のトレーシングコールバックやメトリクスフックをまだ提供していない。

## 将来拡張の検討ポイント
- **拡張フック**: `Node.describe()` から構造化メタデータを公開し、Flow 実行の前後フックを用意してロギング／トレーシング／メトリクスを注入しやすくする。
- **エラー／リトライ方針**: Fail-Fast を基本に保ちながら、任意でリトライやバックオフ、失敗通知を差し込めるプラグイン構造を検討する。
- **可観測性ツール**: 実行トレースやステップ時間を外部ダッシュボードへ送れるエクスポータを整備する。
- **設定バリデーション**: `context.inputs` / `context.outputs`、式、callable 指定の静的検証を強化し、実行前に誤りを検出する。
- **UI 連携準備**: `Flow.to_config()` のようなシリアライズ機構、ノードカタログの機械可読化、式・バリデーション規約の明文化によりワークフロー編集 UI への展開を容易にする。

### ロードマップ
**これまでの歩み**: バージョン 0.1.3 でノードの契約をペイロード中心に固定しつつ、YAML / DSL の互換性を維持しました。その後の更新で `request_context()` による共有コンテキスト操作を簡素化し、拡張フック・検証・可観測性・UI 連携へ繋げる基盤を整備しています。

**短期（0.1.x）**
- `Flow.run` がコンテキストを返す仕様を周知し、ノードが共有コンテキストを更新する際のベストプラクティス（`context.setdefault` など）を明示。
- `Node.describe()` からの構造化メタデータ拡充と、Flow 実行前後フックの追加設計。
- `context.inputs` / `context.outputs` / callable 指定の静的バリデーションを強化し、エラーを実行前に検出。
- 共有コンテキストに触れる際のベストプラクティス（予約キーの利用など）をサンプルとドキュメントに追加。

**中期（0.2.x）**
- Fail-Fast を維持しつつ、任意でリトライ・バックオフ・失敗通知を差し込めるポリシーをプラグイン化。
- OpenTelemetry や JSON エクスポータなど、トレース／メトリクスの標準アダプタを提供。
- ノードカタログの JSON スキーマを公開し、外部ツールから入出力メタデータを取得可能に。
- `Flow.to_config()` / `Flow.diff_config()` を整備し、UI とコードの往復編集を支援。

**長期（0.3.x 以降）**
- 必要に応じて分散実行・バックプレッシャ制御を検討しつつ、単一プロセス実装との互換性を保持。
- カタログとバリデーションスキーマを活用したリファレンス UI（または設計キット）を提供。
- イベントストリームや永続的な監査ログなど、ポリシー駆動の可観測性パイプラインを提供。
- コミュニティ貢献ノード／統合を管理する `FlowPlugin` レジストリを正式化し、エコシステム拡大を支援。
## 対応すべきシナリオチェックリスト
- 直列パイプライン (`A >> B >> C`)。
- 静的ファンアウト (`A >> (B | C)` が両方発火)。
- ランタイムの選択分岐（ルーターノードが後続を選択）。
- ファンインを伴う並列処理 (`(B & C) >> join`)。
- `LoopNode` を利用した逐次ループ処理（`loop >> loop`, `loop >> worker`）。
- 早期終了（ルーティングノードが `[]` を返して後続ノードを停止する）。
- （ノード側で実装される）タイムアウトによるキャンセル。
- 外部イベント待機をノード内で完結させる（Flow は同期実行のまま例外を受け取る）。

## テスト用フロー例
- **線形 ETL チェーン**: `extract >> transform >> load`。順序の決定性、コンテキストの蓄積、`transform` 例外時のフェイルファスト挙動を確認。
- **信頼度付きブランチング**: `classify` ノードが `Routing(target="approve", confidence=0.82, reason="score > 0.8")` を返す。動的ブランチとメトリクス記録の扱いを検証。
- **並列エンリッチ + ジョイン**: `start >> (geo | risk)` から `merge` へ。並列スケジューリング、`context["joins"]` のバッファ処理、決定的な結合をテスト。
- **ノード内タイムアウト管理**: `call_api` が独自にタイムアウト/リトライを実装し、最終的に例外を投げる。Flow が Fail-Fast を維持しつつ、ノードが外部信頼性をカプセル化する例。
- **早期停止ウォッチドッグ**: しきい値超過で `guard` が `[]` を返す。正常停止、実行ログの完備性、停止後の余剰タスクが無いことを検証。

## Node 実装チェックリスト
- [ ] 可読な `name` と `describe()` メタデータを宣言する。
- [ ] 動的分岐が必要な場合は `RoutingNode` を継承し、`Routing(target, confidence, reason)` または `(Routing(...), payload)` を返す。
- [ ] 衝突を避けるユニークなキーでペイロードを返す。
- [ ] `context["payloads"][node_id]` へ生成したペイロードを格納し、下流ノードへの入力を整える。
- [ ] 例外は握りつぶさずに送出し、Flow がログと Fail-Fast を担う（自動リトライはしない）。
- [ ] 非同期処理ではノード内でタイムアウト/キャンセルを管理し、即座に例外を伝播させる。
- [ ] 必須コンテキストキーを `describe()` メタデータに記載し、バリデーションツールが検証可能にする。

## Flow 実装チェックリスト
- [ ] グラフ構築時に到達不能ノードや重複IDを検証する。
- [ ] 実行開始時に予約ネームスペースを初期化する。
- [ ] 並列上限を強制しつつ、タイムアウト管理はノード実装に委ねる。
- [ ] `RoutingNode` の決定を検証し、`context["routing"]` に記録した上で後続をスケジュールする。
- [ ] ジョイン集約をアトミックかつ決定的に保つ。
- [ ] 例外送出前に十分な診断情報をコンテキストへ格納する。
- [ ] 計測・カスタムスケジューラ用の拡張フックを公開しつつ、内部表現を漏洩させない。
