# チュートリアル要件 (Draft)

## 目的
- illumo-flow を使うことで「LLM を組み合わせたフローが直感的に構築できる」「既存の DSL / CLI / Python API を活用して柔軟に運用できる」というメリットを最初に伝える。
- Agent / Router / Evaluation といった LLM ノードを束ねたマルチエージェントアプリケーションを素早く作れるワクワク感を演出する。
- Tracer（Console / SQLite / OTEL）と Policy（fail-fast / retry / timeout / on_error）を組み合わせ、観測性と堅牢性を両立できる楽しさを体験できるようにする。
- CLI／YAML／Python API の使い分けを実例で示し、「何を作りたい時にどの構成を選べばよいか」が段階的に理解できるようにする。
- チュートリアルを通じて `docs/update_requirement.md` に定義された設計思想（Agent → Tracer → Policy）に沿った開発手順を自然に学べるようにする。

## 全体構成（章立て）
1. **イントロダクションとセットアップ**
   - illumo-flow の概要（フロー指向 / LLM ノード / 宣言的設定）
   - リポジトリの取得・依存関係・環境変数の準備
   - `FlowRuntime.configure()` の初期設定（ConsoleTracer + fail-fast Policy）

2. **Agent 基本編**
   - `Agent` ノードの役割と設定キー（provider/model/prompt/paths）
   - シンプルなチャット応答・コンテキストへの書き込み例
   - LMStudio など OpenAI 互換 API を使う際の `base_url` と `/v1` 補完

3. **Flow と DSL の基礎**
   - ノード定義 / `Flow.from_dsl` / `flow.run()` の実行フロー
   - `inputs` / `outputs` / `$ctx` 式の活用方法
   - YAML 構成からの読み込みと CLI (`illumo run`) の使い分け

4. **RouterAgent での分岐制御**
   - `choices` と `metadata_path` の指定
   - 分岐ごとに異なる Agent/Function へ遷移するパターン
   - `ctx.routing.<id>` / `ctx.route` への記録内容を検証

5. **EvaluationAgent での採点・判定**
   - スコアや理由を構造化データとして保存する方法
   - JSON 出力のパースロジックと `structured_path`
   - RouterAgent と組み合わせて「採点 → 分岐」フローを構築

6. **マルチエージェント的アプリケーション組み立て**
   - Agent / RouterAgent / EvaluationAgent を連携させた実践例
   - 共有コンテキスト (`ctx.agents.*` / `ctx.metrics.*`) を跨いだデータフロー
   - CLI 実行と Python API での再利用方法

7. **Tracer の活用**
   - ConsoleTracer / SQLiteTracer / OtelTracer への切り替えと出力確認
   - `SpanTracker` による flow/node span の見方
   - CLI オプション例とトラブルシュート（ログ確認 / SQLite の参照例）

8. **Policy 設定とエラーハンドリング**
   - グローバル Policy（fail_fast / retry / timeout / on_error）の解説
   - ノード個別の Policy 上書き方法
   - 失敗時の挙動比較（fail-fast vs non fail-fast、goto 分岐など）

9. **次のステップと参考情報**
   - CLI/チュートリアルの handoff（更なるドキュメント・API リファレンス）
   - マルチエージェント拡張、Tracer と監視ツール連携、Policy の高度な構成案
   - サンプルコード／チェックリスト／用語集の参照先

## 章ごとの記載ポイント
- **イントロダクション**: illumo-flow の設計思想、必要な前提知識、環境セットアップ手順。
- **Agent 基本編**: `NodeConfig` の `setting`、`output_path` 群、`ctx.agents.<id>` の構造、OpenAI/LMStudio 統合のベストプラクティス。
- **Flow 基礎**: DSL 記法、`inputs`/`outputs` の式、`payload` vs `context` の使い分け、CLI 操作。
- **RouterAgent**: `choices` の選定、理由保存、分岐後のノード接続、`ctx.routing` の読み方。
- **EvaluationAgent**: JSON 解析、スコア・理由の記録、評価結果に基づく自動処理例。
- **マルチエージェント**: 実践的なユースケース（例: PRD 改稿フロー）、エージェント間のデータ授受、ワークフロー全体図。
- **Tracer**: TracerProtocol の基礎、各アダプタの特徴、SpanTracker で確認できる情報、CLI での切り替え方。
- **Policy**: Retry/Timeout/OnError の挙動、ノード上書きの優先順位、失敗時ケーススタディ。
- **次のステップ**: ドキュメントマップ、テストチェックリスト、運用ヒント。
