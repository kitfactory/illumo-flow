
# Illumo Flow チュートリアル

全9章構成のチュートリアルを案内します。ユーザーのやりたいこと → 使うクラス → ハンズオン → 学んだこと、という流れで進み、英語版と日本語版が１章ずつ対応しています。

各章には Python と YAML の例を併載しています。アプリに組み込むときは Python、CLI で共有したいときは `illumo run` で呼び出せる YAML を活用してください。

### 開発者にとってのメリット
- プロンプトの配線やコンテキスト保存、分岐や採点まで一揃いで提供されるため、面倒なグルーコードを減らせます。
- 観測手段がワンアクションで切り替えられ、色付きコンソール表示・SQLite 永続化・OTEL 連携を状況に応じて選べます。
- リトライやフォールバックといった失敗時の振る舞いを宣言的に制御でき、実験モード ↔ 本番モードの移行も設定変更のみです。
- CLI・YAML・Python が同じ発想で扱えるので、プロトタイプから運用までの橋渡しがスムーズです。
- プロバイダ固有の違いは吸収され、同じ設定感覚で OpenAI や LMStudio などを切り替えられます。
- コンテキストが実行ログを兼ねるため、開発チームと運用チームが同じ情報で議論できます。

## 日本語版の章
- [01 · 導入とセットアップ](01_introduction_ja.md) — `pip install illumo-flow` から FlowRuntime の初期化まで。
- [02 · Agent 基礎](02_agent_basics_ja.md) — 会話エージェントと履歴管理。
- [03 · Flow 基礎](03_flow_basics_ja.md) — Agent と FunctionNode をつないで CLI でも動かす。
- [04 · RouterAgent](04_router_agent_ja.md) — 分岐と意思決定の理由を記録。
- [05 · EvaluationAgent](05_evaluation_agent_ja.md) — スコアリングと JSON 結果の保存。
- [06 · マルチエージェントアプリ](06_multi_agent_app_ja.md) — 自動ドラフト / 採点 / 判断ループ。
- [07 · トレーサー道場](07_tracer_playground_ja.md) — Console/SQLite/OTEL を切り替えて観察。
- [08 · Policy で制御](08_policy_mastery_ja.md) — Fail-Fast・リトライ・フォールバックの設定。
- [09 · 次のステップ](09_next_steps_ja.md) — 応用とリファレンスの道しるべ。

## 英語版の章
- [01 · Introduction & Setup](01_introduction.md)
- [02 · Agent Basics](02_agent_basics.md)
- [03 · Flow Fundamentals](03_flow_basics.md)
- [04 · RouterAgent](04_router_agent.md)
- [05 · EvaluationAgent](05_evaluation_agent.md)
- [06 · Multi-Agent Mini App](06_multi_agent_app.md)
- [07 · Tracer Playground](07_tracer_playground.md)
- [08 · Policy Mastery](08_policy_mastery.md)
- [09 · Next Steps](09_next_steps.md)

## チュートリアルの進め方
1. 第1章から順番に読み、コードを実際に動かしてみてください。
2. 重要な設定や CLI コマンドはメモしておき、プロジェクトに合わせて書き換えましょう。
3. 第7章・第8章のトレーサー／ポリシー設定で動作を観察しながら、安心して第9章の応用に踏み出してください。
4. 進むにつれて `ctx.messages` / `ctx.metrics` / `ctx.route` / `ctx.errors` などのキーがどのように変化するかを追い、ミッションログのように読める感覚を身につけましょう。
5. OpenAI と LMStudio などプロバイダを切り替えながら読み返すと、`/v1` 自動補完や Policy のリトライ挙動の違いが体験できます。

## マスターできること
- 会話系 Agent / Router / EvaluationAgent がコンテキストを共有しながら協調する設計。
- Console / SQLite / OTEL トレーサーによる観測と、色付き Agent span の読み解き方。
- リトライ・タイムアウト・フォールバックを宣言的に扱う Policy パターン。
- マルチエージェントの物語をプロダクション品質のフローとして仕上げる手順。
