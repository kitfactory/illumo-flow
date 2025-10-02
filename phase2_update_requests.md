# Phase 2 Update Requests

## 0. 背景
- フェーズ1では Agent / Tracer / Policy の基本実装およびチュートリアル刷新を完了した。
- 次フェーズは運用品質の底上げ（CLI 検証、追加テスト、監視連携強化）と、ユーザー導線の拡充を目的とする。

## 1. 必須対応 (Must)
- [ ] CLI フローの手動検証（Tracer 切替・Policy 指定）を実施し、`docs/test_checklist*.md` に結果を反映する。
- [ ] `illumo run` 実行ログをもとに、ConsoleTracer / SQLiteTracer のサンプル出力をチュートリアルへ追記する。
- [ ] Policy 設定変更の動作確認手順を README とチュートリアル双方に追加し、環境切替時のガイドラインを整備する。

## 1.1 最優先トラック
- [x] コーディング補助エージェントのマルチエージェント事例を `examples/multi_agent/coding_assistant/` に追加し、必要な Node 機能（例: ファイル編集、テスト実行ノード）を洗い出す。→ 詳細要件は「設計付録 A」を参照（サンプルプロジェクトに Python ファイルを用意し、バグ修正シナリオを想定）。
- [x] TracerDB インターフェースを設計し、SQLite 用・Tempo 用の TracerDB 派生クラスを実装（既存トレーサーとの連携を確認）する。→ 詳細要件は「設計付録 B」を参照。

## 2. 優先対応 (Should)
- [x] チャットボット事例を `examples/multi_agent/chat_bot/` に追加し、既存ノードで不足する機能を整理する。→ 詳細要件は「設計付録 C」を参照。
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

### CLI / 実行メモ
- 現状 `illumo` CLI エントリーポイントは配布していないため、以下いずれかでフローを実行する。
  1. **python ワンライナー**
     ```bash
     python - <<'PY'
     from pathlib import Path
     from illumo_flow.core import Flow

     flow = Flow.from_config('examples/multi_agent/coding_assistant/coding_assistant.yaml')
     context = {
         'request': {
             'description': 'Fix add implementation',
             'target_root': 'examples/multi_agent/coding_assistant',
             'tests': 'pytest -q',
             'write': True,
         },
         'diff': {
             'proposed': Path('examples/multi_agent/coding_assistant/example_diff.patch').read_text()
         }
     }
     flow.run(context)
     PY
     ```
  2. **uv 経由で venv を整備し editable install**
     ```bash
     uv run -- python -m pip install --editable .
     uv run -- python - <<'PY'
     from pathlib import Path
     from illumo_flow.core import Flow

     flow = Flow.from_config('examples/multi_agent/chat_bot/chatbot_flow.yaml')
     context = {
         'chat': {
             'history': [
                 {'role': 'user', 'message': '返品したいのですが'}
             ]
         }
     }
     flow.run(context)
     PY
     ```
- 上記コンテキストは JSON で管理すると便利。サンプル:
  ```json
  {
    "request": {
      "description": "Fix add implementation",
      "target_root": "examples/multi_agent/coding_assistant",
      "tests": "pytest -q",
      "write": true
    },
    "diff": {
      "proposed": "$(cat examples/multi_agent/coding_assistant/example_diff.patch | python -c 'import json,sys; print(json.dumps(sys.stdin.read()))')"
    }
  }
  ```
  ```json
  {
    "chat": {
      "history": [
        {"role": "user", "message": "返品したいのですが"}
      ]
    }
  }
  ```
- CLI 化が必要になった場合は `python -m illumo_flow.cli` のようなエントリーポイントを導入予定。現段階では上記スクリプトで代替する。

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

## 設計付録 B: TracerDB（トレース検索クライアント）
### 目的と背景
- トレーサーが書き出した SQLite ベースのトレースを後から参照・検索するための読み取り用クラスを提供する。
- 永続化自体はトレーサー（Console / SQLite / OTEL）が担い、TracerDB は分析者やツールが既存データを絞り込むために利用する。

### SQLiteTraceReader
- 依存: `sqlite3`（標準ライブラリ）。
- 主な API:
  - `trace_ids(limit=None)` … 保存済みトレースIDの一覧を取得。
  - `spans(trace_id=None, span_id=None, name=None, kind=None, status=None, limit=None)` … 条件指定で span レコードを取得。
  - `events(trace_id=None, span_id=None, event_type=None, level=None, limit=None)` … span に紐付くイベントを取得。
- `attributes` を文字列として保存しているテーブルに対しては `ast.literal_eval` で辞書に戻して返却する。
- 使用例:
  ```python
  from illumo_flow.tracing_db import SQLiteTraceReader

  reader = SQLiteTraceReader('trace.db')
  spans = reader.spans(trace_id='abc123')
  events = reader.events(span_id=spans[0].span_id)
  ```

### CLI / ツール統合
- SQL で直接操作する場合は `SELECT * FROM spans` / `events` テーブルを利用。
- 将来的に CLI を導入する場合は `illumo trace --list` などのサブコマンドで Reader を呼び出す形を想定。
- OTEL/Tempo など外部監視システムでは既存 exporter を利用し、TracerDB の検索機能は SQLite ベースの運用・分析用途に限定する。


### CLI 実装方針
- `illumo` コマンドを `python -m illumo_flow.cli` で提供。インストール時に `illumo` エントリーポイントを生成する。
- サブコマンド案:
  - `illumo run FLOW_PATH --context '@context.json' --tracer sqlite --trace-db trace.db`
  - `illumo trace list` / `illumo trace show TRACE_ID` で `SQLiteTraceReader` を利用。
  - `illumo policy lint FLOW_PATH` で YAML 内の Policy 設定を検査。
- 実装 TODO:
  1. `illumo_flow/cli/__init__.py` に Typer または argparse ベースの CLI を追加。
  2. `run` サブコマンドは現行 `Flow.from_config` 実行ロジックをラップし、`--context` に JSON 文字列またはファイル (`@path`) を受け付ける。
  3. `trace` サブコマンドは `SQLiteTraceReader` を呼び出して絞り込み (`--trace-id`, `--name`, `--kind`, `--limit`) をサポート。
  4. 既存チュートリアルの CLI 例は `illumo run` に統一した形で更新する。
- 実装前提: CLI から tracer/policy/環境変数を上書きできるオプションを `--tracer`・`--set policy.fail_fast=false` のように追加する。
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
- 監視: SQLiteTraceReader を参照してセッション単位の span を確認。

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
