# Phase 2 Update Requests

## 0. 背景
- フェーズ1では Agent / Tracer / Policy の基本実装およびチュートリアル刷新を完了した。
- 次フェーズは運用品質の底上げ（CLI 検証、追加テスト、監視連携強化）と、ユーザー導線の拡充を目的とする。

## 1. 必須対応 (Must)
- [ ] CLI フローの手動検証（Tracer 切替・Policy 指定）を実施し、`docs/test_checklist*.md` に結果を反映する。
- [ ] `illumo run` 実行ログをもとに、ConsoleTracer / SQLiteTracer のサンプル出力をチュートリアルへ追記する。
- [ ] Policy 設定変更の動作確認手順を README とチュートリアル双方に追加し、環境切替時のガイドラインを整備する。

## 1.1 最優先トラック
- [ ] コーディング補助エージェントのマルチエージェント事例を `examples/multi_agent/coding_assistant/` に追加し、必要な Node 機能（例: ファイル編集、テスト実行ノード）を洗い出す。→ 詳細要件は「設計付録 A」を参照（サンプルプロジェクトに Python ファイルを用意し、バグ修正シナリオを想定）。
- [ ] TracerDB インターフェースを設計し、SQLite 用・Tempo 用の TracerDB 派生クラスを実装（既存トレーサーとの連携を確認）する。→ 詳細要件は「設計付録 B」を参照。

## 2. 優先対応 (Should)
- [ ] チャットボット事例を `examples/multi_agent/chat_bot/` に追加し、既存ノードで不足する機能を整理する。→ 詳細要件は「設計付録 C」を参照。
- [ ] Tutorial チャプターに対応するサンプル YAML / Python ファイルを `examples/` 配下へ整理し、実行手順を README にリンクする。
- [ ] Tracer ごとのベンチマーク（起動時間、ログ書き込み量）を作成し、docs/ 以下に記録する。
- [ ] Policy リトライ設定のベストプラクティス（開発／ステージング／本番）をまとめ、`docs/update_requirement.md` に追記する。

## 3. 検討事項 (Could)
- [ ] LM Studio / Ollama 向けにストリーミング対応を調査し、実装可否と必要な追加要件を整理する。
- [ ] エージェント用の拡張サンプル（評価結果による分岐+再試行）のコード化を検討する。
- [ ] OpenAI 以外のプロバイダでの評価テストを自動化するためのツールチェーン（例: 事前にダミー応答を用意）を調査する。

## 4. 調整メモ
- 追加要望や優先順位変更が発生した場合、本ファイルを更新し、対応リストと紐付くタスクチケットを作成する。
- フェーズ2完了時には、チェック済み項目の証跡（実行ログ・テスト結果・ドキュメント差分）をまとめ、docs/update_plan.md と整合させる。

---

## 設計付録 A: コーディング補助エージェント
### 開発者が実現したいこと
- PR レビュー、リファクタ提案、テスト実行などを自動化するマルチエージェント「開発支援フロー」を `illumo run` で再現したい。
- チームの開発者が「入力: 変更概要」「出力: 修正済みファイル＋テスト結果＋レビュー要約」を受け取れるようにする。

### 全体アーキテクチャ
1. **サンプルプロジェクト構成**: `examples/multi_agent/coding_assistant/sample_app/` に複数の Python ファイル（バグ混入版）と `tests/` ディレクトリを配置。CLI からはこのサンプルのみを対象にする。
2. **WorkspaceInspectorNode (新規)**: サンプルプロジェクト内のファイル一覧・プレビューを収集し、DraftAgent のプロンプトに埋め込む材料を用意。
3. **DraftAgent**: 変更概要と対象ファイルをもとに修正案を差分形式で生成。
4. **PatchNode (新規)**: 差分を仮想適用し、`ctx.workspace.files` にパッチ後の内容を保存（実ファイルは変更しない）。sandbox 設定で許可外パスを拒否。
5. **TestExecutorNode (新規)**: `pytest` コマンドを受け取り、`sample_app/` 配下でサブプロセス実行。stdout/stderr を `ctx.tests.results` に保存。
6. **ReviewAgent**: DraftAgent の提案とテスト結果を要約し、リスク評価（OK/NG）を返す。
7. **RouterAgent**: ReviewAgent の判定に基づきフロー分岐（OK → 完了、NG → DraftAgent に差し戻し）。

### 主要コンテキスト設計
- `ctx.request` … ユーザーが CLI で渡すリクエスト（変更概要、対象ファイルリスト、テストコマンド）。
- `ctx.workspace.structure` … [{"path": str, "size": int, "preview": str, "selected": bool}]（WorkspaceInspectorNode が生成）。
- `ctx.workspace.structure_excluded` … [{"path": str, "reason": str}]。
- `ctx.workspace.files` … [{"path": str, "original_content": str, "patched_content": str, "status": "original"|"patched"}]。
- `ctx.diff.proposed` … DraftAgent が生成する unified diff。
- `ctx.tests.command` / `ctx.tests.results` … テスト実行コマンドと結果ログ。
- `ctx.review.summary` / `ctx.review.status` … ReviewAgent が返す評価。

### Node API（新規）
1. **WorkspaceInspectorNode**
   - 入力: `ctx.request.target_root`, `ctx.request.target_files`（省略時はプロジェクト全体を走査）。
   - 処理: 許可拡張子（既定: `.py`, `.txt`, `.md`）のみを対象にファイル一覧を生成。各ファイルの先頭/末尾 N 行を `preview` として抽出し、ファイルサイズ（バイト）とともに `ctx.workspace.structure` に格納。`target_files` が指定されている場合は該当ファイルを `selected=True` とし、その他は参照候補として保持。
   - 出力: `ctx.workspace.structure` に JSON 配列を保存し、DraftAgent のプロンプトに `{{ $ctx.workspace.structure }}` として注入。併せて、バイナリやサイズ上限超過のファイルは `ctx.workspace.structure_excluded` に理由付きで格納。
   - エラー処理: 読み込み不可のファイルは `permission_denied` として記録し、処理を継続。
2. **PatchNode**
   - 入力: `ctx.diff.proposed`, `ctx.request.target_files`。
   - 処理: `patch` ライブラリで仮想適用し、結果を `ctx.workspace.files` に格納（`original_content` / `patched_content` を保持）。実ファイルへは書き込まない。
   - 出力: `ctx.diff.applied` にパッチ成功状況、拒否されたファイルを記録。
   - エラー処理: diff 適用失敗時は例外を投げ、Policy のリトライ対象とする。
3. **TestExecutorNode**
   - 入力: `ctx.tests.command`（例: `pytest tests/unit -q`）。
   - 処理: `subprocess.run` で実行。タイムアウトは Policy に従う（既定 120s）。
   - 出力: `ctx.tests.results`（stdout/stderr/returncode）を JSON 形式で保存。
- 既存 Agent には `metadata_path` でトークン消費や推論根拠を保存する。

### 開発者操作フロー
1. `examples/multi_agent/coding_assistant/` に用意する YAML を編集し、`allowed_paths` やテストコマンド、WorkspaceInspectorNode の `allowed_extensions` / `preview_lines` を設定。
2. `illumo run coding_assistant.yaml --context '{"request": {...}}'` を実行。
3. 出力: `ctx.workspace.files` の更新内容を CLI に表示。`--write` オプションを用意し、ユーザーが同意した場合のみサンプルプロジェクトへ適用（デフォルトは dry-run）。
4. 失敗時は ReviewAgent の結果を受けて再実行（差し戻しループ）。

### セキュリティ/ガード
- WorkspaceInspectorNode で読み取るファイルは `allowed_extensions` とサイズ上限（例: 128 KB）を強制。超過時はプレビューを省略し、警告を記録。
- `PatchNode` で `../` が含まれるパスは拒否。
- テスト実行は `shell=False` で実行し、許可コマンドのリストを設定。
- エラー時は ConsoleTracer/SQLiteTracer でログ確認できるよう Span に詳細情報を添付。

### テスト戦略
- 単体テスト: PatchNode のパス制限、TestExecutorNode のタイムアウト動作を pytest で検証。
- 統合テスト: サンプルリポジトリを fixtures に準備し、実際に diff → patch → pytest → review の流れを実行。

## 設計付録 B: TracerDB インターフェース
### 目的と背景
- ConsoleTracer のみで完結しない運用向けに、永続化ストア（SQLite / Tempo）とトレーサーの橋渡しをする共通レイヤーを提供。
- トレーサー実装者が DB/API の違いを意識せずに Span を記録できるようにする。

### インターフェース仕様
```python
class TracerDB(Protocol):
    def connect(self) -> None: ...
    def record_span(self, span: SpanData) -> None: ...
    def record_event(self, span_id: str, event: EventData) -> None: ...
    def flush(self) -> None: ...
    def close(self) -> None: ...
```
- `SpanData` / `EventData`: 既存トレーサーが扱う辞書形式を dataclass 化して共通化。
- 実装は同期 I/O を前提。将来的な非同期化を見越し、`flush` を明示。

### SQLiteTracerDB
- 依存: `sqlite3`（標準ライブラリ）。
- テーブル設計
  - `spans(span_id TEXT PRIMARY KEY, trace_id TEXT, parent_id TEXT, name TEXT, start TIMESTAMP, end TIMESTAMP, status TEXT, attributes JSON)`
  - `events(id INTEGER PRIMARY KEY AUTOINCREMENT, span_id TEXT, name TEXT, timestamp TIMESTAMP, attributes JSON)`
- 実装ポイント
  - `connect()` で DB ファイルを生成、PRAGMA `journal_mode=WAL` を設定。
  - `record_span()` はトランザクションにバッチング（コンテキストマネージャで制御）。
  - `flush()` で `conn.commit()`、`close()` でリソース解放。
- 開発者操作
  - `FlowRuntime.configure(tracer=SQLiteTracer(db_path="...", db=SQLiteTracerDB(db_path="...")))`
  - CLI: `illumo run flow.yaml --tracer sqlite --tracer-arg db_path=./trace.db`
  - 分析: `sqlite3 trace.db 'SELECT * FROM spans ORDER BY start DESC LIMIT 10'`

### TempoTracerDB
- 依存: OTLP gRPC エクスポーター（`opentelemetry-exporter-otlp`）。
- `record_span()` で SpanData を OTEL span に変換し、Exporter へ送信。
- リトライ戦略: `grpc.RpcError` を捕捉し、指数バックオフ（3 回）で再送。
- `flush()` は Exporter の `force_flush()` を呼ぶ。
- 設定例
  - `FlowRuntime.configure(tracer=OtelTracer(db=TempoTracerDB(endpoint="http://tempo:4317")))`
  - CLI: `illumo run flow.yaml --tracer otel --tracer-arg exporter_endpoint=http://tempo:4317`

### システム統合
- 既存の `SQLiteTracer` / `OtelTracer` を改修し、内部で TracerDB を注入する構造に変更。
- ConsoleTracer は DB を使用しないが、インターフェースに適合させることで将来拡張可能にする。
- テスト: SQLiteTracerDB のファイル作成、TempoTracerDB のモックエクスポーター送信を pytest でカバー。

## 設計付録 C: チャットボット事例
### 目的
- FAQ 応答から必要に応じて人へのエスカレーションまで行う “サポートチャットボット” を実装し、マルチエージェント構成と Policy 活用例を提供する。

### フロー概要
1. **GreetingAgent**: 最初の挨拶と問い合わせ分類。
2. **FAQAgent**: FAQ 知識ベース（例: JSON / ベクターストア）から回答。
3. **EscalationRouter**: FAQAgent の信頼スコアを確認し、閾値未満ならサポート窓口へ転送。
4. **HandoffNode (新規)**: エスカレーション時にチケットを生成し、外部 API へ接続（例: Slack webhook）。
5. **AuditNode (新規)**: すべての会話ログを `ctx.support.history` に蓄積し、SQLiteTracer と連携。

### コンテキスト構造
- `ctx.user.session_id`, `ctx.user.profile` … ユーザー情報。
- `ctx.chat.history` … 発話履歴配列。
- `ctx.chat.answer` … FAQAgent の回答。
- `ctx.chat.confidence` … 信頼度スコア。
- `ctx.escalation.ticket` … HandoffNode が作成するチケット ID。

### Policy 設計
- 開発環境: `fail_fast=False`, `retry(max_attempts=2, delay=0.2)`, `on_error=continue`。
- 本番環境: `fail_fast=True`, `timeout="5s"`, 信頼度が低い場合は `goto: human_support` ノードへ。

### 開発者操作
- `examples/multi_agent/chat_bot/faq_flow.yaml` を編集し、FAQ データソースまたは API エンドポイントを指定。
- CLI: `illumo run faq_flow.yaml --context '@examples/multi_agent/chat_bot/context.json'`
- 監視: SQLiteTracerDB を参照してセッション単位の span を確認。

### 不足機能の洗い出し
- HandoffNode: 汎用 HTTP POST ノード（リトライ含む）が必要か検討。
- FAQAgent: ベクターストア連携が必要な場合は別途アダプタを追加。
- 会話メモリ: 履歴を一定長でトリミングするユーティリティの検討。
- `PatchNode` が保持する `patched_content` をディスクへ書き出す処理は、ユーザーが `--write` を明示した場合のみ実行。

## 設計付録 D: SummaryAgent（変更要約担当）
### 目的
- マルチエージェントフローの実行結果（修正内容、テスト結果、レビュー判定など）を定型フォーマットのレポートにまとめ、開発者へ提示する。

### 要件
- Agent ベースで実装し、入力として `ctx.workspace.files`, `ctx.tests.results`, `ctx.review.summary` などを参照。
- レポートフォーマット例:
  - `summary.title`（変更概要）
  - `summary.changes`（箇条書きで修正点）
  - `summary.tests`（テスト実行結果の概要）
  - `summary.next_actions`（未対応項目や注意事項）
- 出力先: `ctx.summary.report`（テキスト）、`ctx.summary.json`（構造化レポート）。必要に応じてファイル保存ノードへ引き渡す。
- Policy: 失敗時は `continue` とし、レポート生成に失敗してもフローが完了するようにする。

### 開発者操作
- コーディング補助エージェントやチャットボットの最終段階に SummaryAgent を配置し、CLI 実行後にレポートを標準出力へ表示。
- レポートを PR コメントや Slack 通知に流すユースケースを想定し、連携ノードの追加を検討。

### テスト
- モックコンテキストを使い、SummaryAgent が定型フォーマットで要約を返すかを検証。
- ネガティブケース（必要情報が無い場合）でも graceful に fallback メッセージを返すことを確認。
- [ ] SummaryAgent（変更要約担当）を設計・実装し、フロー全体の実行結果を定型フォーマットで報告できるノードを追加する。→ 詳細要件は「設計付録 D」を参照。
