# 変更要件書（Change Requirements)

**対象**: illumo-flow
**目的**: OpenAI Agents SDK の段階的取り込みと、Agent → Tracer → Policy の実行順序に基づく観測性／運用性の拡張。AIエディタ（自動改変エージェント）が誤解なく実装できるよう、意図・IF・受け入れ条件を明示する。

---

## 0. 背景と到達目標

* 現状: `Flow` + `Node`（FunctionNode など）を DSL / YAML で簡潔に構築できる。
* 目標:

  1. **OpenAI Agents SDK** を取り込み、**Agent系ノード**（Agent / RouterAgent / EvaluationAgent）を一級市民として提供。
  2. **観測性**を **Console → SQLite → OTel** の三段で**ワンライン切替**できるよう統一。
  3. **実行ポリシー**（fail-fast、retry/backoff、timeout、on_error など）を **宣言的に統合**。
  4. 実行順序は **Agent → Tracer → Policy** の合成で安定化（詳細は §2）。
  5. **ユーザー操作性優先**: Flow と Agent の組み合わせは `flow.run()` だけで即動作し、Tracer/Policy などの高度設定は必要になった段階で `FlowRuntime.configure(...)` により段階的に有効化できるよう保つ。

> **進捗段階**: 本ドキュメントは Agent → Tracer → Policy の順に段階的な実装を進める前提で記載している。初期リリースでは Agent 機能とコンソールトレーサ（色分けログ）、fail-fast ポリシーを既定とし、後続フェーズで Tracer/Policy の選択肢を拡張する。
* 成果物: ライブラリ実装、YAML/DSL、CLI、スキーマ、テスト、ドキュメント。

---

## 変更点の要旨

* **Agent 機能**: LLM を用いた 3 種の Agent (`Agent` / `RouterAgent` / `EvaluationAgent`) を追加。OpenAI Agents SDK を利用し、OpenAI 互換 API を使用する。
* **Tracer 機能**: Tracer を追加。既定は色分け Console。SQLite や OTel(Tempo) の Tracer に切り替え可能。SQL と OTel には TracerDB クライアントクラスも提供する。
* **Policy 機能**: Flow 制御に Policy を加え、エラー処理やリトライを簡単に設定可能に。デフォルトは Fast-Fail。

---

## 1. 用語と基本設計方針

* **Agent**: OpenAI Agents SDK を利用し、LLM による処理（生成/評価/ルーティング）を行うノード実装の総称。
* **Tracer**: **OpenAI Agents SDK の Tracer インターフェース準拠**で提供する。Console/SQLite/OTel は **SDK Tracer へのアダプタ実装**としてぶら下げる（独自 I/F は作らない）。
* **Policy**: timeout、retry/backoff、on_error（stop/goto/continue）、fail_fast（デフォルト true）等の実行ポリシー。
* **Context**: フロー実行中の共有辞書。ノード入出力や評価結果、メタ情報を格納。YAML では `output_path` で保存先を指定。
* **Agent 出力コンテキスト**: LLM ノードでは会話履歴や構造化データ、補助情報を分離して保存する。`output_path` はメイン応答の保存先であり、 追加で `history_path`（会話履歴の一覧）や `metadata_path`（思考過程・ツール利用ログ）、`structured_path`（JSON などの構造化出力）をオプションで受け付ける。 生成系ノードは既定で Python 実行時の `ctx["agents"][node.id]`（YAML/DSL では `$ctx.agents.<node_id>`）配下にサブキー（`response` / `history` / `metadata` / `structured`）を利用し、`output_path` が指定された場合は優先する。
* **会話継続**: 後続ノードは Python 側では `ctx["agents"][<node_id>]["history"]`、YAML/DSL では `$ctx.agents.<node_id>.history` を参照するだけで直前のトランスクリプトを取得でき、`payload` に渡して会話を継続できる。`history_path` を指定した場合はそのパス（例: `$ctx.history.refine`）経由で同様にアクセスする。
* **構造化参照**: `structured_path` や `metadata_path` に保存された値は YAML テンプレートでは `{{ $ctx.metrics.prd_review_details }}`、Python コードでは `ctx["metrics"]["prd_review_details"]` のように参照でき、後段 LLM が特定データのみを使う設計が容易になる。
* **優先順位**: CLI > YAML（設定の上書き規則／環境変数は使用しない）。

---

## 2. 実行順序の厳密定義（Agent → Tracer → Policy）

**クラス階層ポリシー**: `Agent` は `Node` を継承、`RouterAgent` は `RouterNode` を継承する。実装上は既存の `Node`/`RouterNode` と完全に同一の実行境界・ライフサイクルで動作させる。

````
for node in topologically_sorted(flow):
    payload = resolve_inputs(context)

    # (1) Agent レイヤ（任意）: illumo の get_llm() でプロバイダ非依存にモデル取得
    agent = node.get_agent()  # None の場合もある

    # (2) Tracer レイヤ（**OpenAI Agents SDK Tracer I/F**）
    tracer.on_span_start({
        "kind": "node",
        "name": node.id,
        "attrs": node.meta,
        "trace_id": current_trace_id(),
        "parent_span_id": current_span_id(),
    })

    # (3) Policy レイヤ: timeout → retry/backoff → on_error を順に合成
    try:
        result = apply_policy(node, agent, payload, context)
        tracer.on_event({"level": "debug", "node": node.id, "msg": "ok"})
        tracer.on_span_end({"status": "OK"})
    except Exception as e:
        tracer.on_event({"level": "error", "node": node.id, "error": str(e)})
        tracer.on_span_end({"status": "ERROR", "error": str(e)})
        handle_error_with_policy(node, e)
        continue

    # 各 Agent ノードは response/history/metadata/structured をマッピングし、競合しないキーへ格納
    write_outputs(context, node, result)
```

* **例外発生**時:

  * ノード個別 `on_error` があればそれに従う（`stop` / `goto: <node>` / `continue`）。
  * なければフローの既定 `policy` に従う。`fail_fast: true` なら即停止。
  * span は `status="ERROR"` で close し、エラー情報を属性として残す。

---

## 3. 新規/変更 API 仕様

### 3.1 Tracer 抽象（**OpenAI Agents SDK の Tracer I/F 準拠**）

> ここでは **OpenAI Agents SDK の Tracer** プロトコル/インターフェースに準拠する。illumo-flow 独自のメソッドは追加しない。Console/SQLite/OTel は **アダプタ**としてこの I/F を実装する。

```python
# 例: openai_agents.tracing.Tracer に準拠する想定
# 実際の I/F 名・引数は SDK に合わせて厳密に一致させること（追加/省略禁止）
from typing import Any, Dict, Optional, Protocol

class TracerProtocol(Protocol):
    def on_span_start(self, span: Dict[str, Any]) -> None: ...
    def on_span_end(self, span: Dict[str, Any]) -> None: ...
    def on_event(self, event: Dict[str, Any]) -> None: ...
```

**方針**

* `on_span_start`/`on_span_end` で **flow/node/tool/llm** などの span 種別を `span["kind"]` に格納。
* `on_event` はログ/チェックポイント/中間出力などを受け取り、宛先（Console/SQLite/OTel）へフォワード。
* **相関 ID**: `trace_id`, `span_id`, `parent_span_id` を SDK 準拠で扱い、ContextVars 等で暗黙伝播可能にする。

```python
# illumo_flow/tracing/base.py
from typing import Protocol, Optional, Dict, Any

class Tracer(Protocol):
    def start_flow(self, name: str, attrs: Optional[Dict[str, Any]] = None): ...
    def end_flow(self, status: str = "OK", error: Optional[Exception] = None): ...
    def start_span(self, name: str, attrs: Optional[Dict[str, Any]] = None): ...
    def end_span(self, status: str = "OK", error: Optional[Exception] = None): ...
    def log(self, msg: str, **kwargs): ...
```

### 3.2 Tracer 注入と `SpanTracker`

* `FlowRuntime.configure(tracer=...)` によりプロセス全体の既定トレーサーを切り替える。指定が無い場合は `ConsoleTracer`。
* `SpanTracker` が flow/node span を自動生成し、`TracerProtocol` の `on_span_start` / `on_span_end` を呼び出す。`emit_event()` で任意のイベントを送出できる。
* 既定のアダプタ
  * `ConsoleTracer` — 標準出力へ色分けログを出力
  * `SQLiteTracer` — span / event を SQLite DB へ永続化
  * `OtelTracer` — span をバッファリングしてカスタムエクスポーターへ渡す

```python
from illumo_flow import FlowRuntime, ConsoleTracer, SQLiteTracer, OtelTracer

# Console
FlowRuntime.configure(tracer=ConsoleTracer())

# SQLite (TracerDB 経由)
FlowRuntime.configure(tracer=SQLiteTracer(db_path="./trace.db"))

# OTEL (TempoTracerDB 経由)
FlowRuntime.configure(
    tracer=OtelTracer(exporter=my_exporter),
)
```

CLI オプション例:
```bash
illumo run flow.yaml --tracer sqlite --tracer-arg db_path=./trace.db
illumo run flow.yaml --tracer otel --tracer-arg exporter_endpoint=http://localhost:4317
```

### 3.3 Policy インターフェース

```python
# illumo_flow/policy/types.py
from dataclasses import dataclass

@dataclass
class Retry:
    max_attempts: int = 0      # 0 => retry disabled
    delay: float = 0.0         # 初回待機秒数（exponential の場合は初期値）
    mode: str = "fixed"        # fixed | exponential

@dataclass
class OnError:
    action: str = "stop"        # stop | goto | continue
    target: str | None = None

@dataclass
class Policy:
    fail_fast: bool = True
    timeout: str = "0s"          # 0 => 無制限
    retry: Retry = Retry()
    on_error: OnError = OnError()
```

```python
# illumo_flow/policy/runtime.py
# timeout → retry (fixed/exponential) → on_error を順に合成
```

**既定挙動と優先順位**

* `FlowRuntime.configure()` を呼ばない初期状態では `Policy(fail_fast=True)` がグローバル既定として適用される（コンソールトレーサーと組み合わせて Fail-Fast で動作）。
* `FlowRuntime.configure(policy=Policy(...))` を実行すると、その時点以降のフロー全体に対する既定ポリシーが置き換わる。CLI > YAML > FlowRuntime の優先順位で解決し、後段が先に適用されていれば前段で上書きできる。
* ノード個別ポリシー（YAML の `nodes.<id>.policy` や Python 構築時の `NodeConfig`) は常に最優先で適用され、グローバル設定では上書きされない。
* 想定外の分岐や評価結果はポリシーで `on_error`／`goto` を指定して制御し、なお許容できない場合は例外を送出して Fail-Fast で停止させる。

#### グローバル設定の例

```python
from illumo_flow import FlowRuntime
from illumo_flow.core import Policy, Retry, OnError

FlowRuntime.configure(
    tracer=...,  # 任意
    policy=Policy(
        fail_fast=False,
        timeout="30s",
        retry=Retry(max_attempts=3, delay=0.5, mode="exponential"),
        on_error=OnError(action="continue"),
    ),
)
```

#### 推奨プロファイル

| 環境 | 推奨設定 | 意図 |
| --- | --- | --- |
| 開発 | `Policy(fail_fast=False, retry=Retry(max_attempts=2, delay=0.2), on_error=OnError(action="continue"))` | 手元での試行錯誤を優先し、失敗してもフローを止めない |
| ステージング | `Policy(fail_fast=False, retry=Retry(max_attempts=3, delay=0.5, mode="exponential"), timeout="10s", on_error=OnError(action="goto", target="notify"))` | 自動復旧を試しつつ、繰り返し失敗は運用チームへ通知 |
| 本番 | `Policy(fail_fast=True, retry=Retry(max_attempts=1), timeout="5s", on_error=OnError(action="goto", target="support"))` | 影響範囲を最小にし、即座に人または代替フローへ切り替える |

#### Node 個別設定の例（YAML）

```yaml
flow:
  entry: Intake
  nodes:
    Intake:
      type: illumo_flow.core.FunctionNode
      callable: examples.ops.load_ticket
    Review:
      type: illumo_flow.nodes.agent.Agent
      policy:
        fail_fast: true
        timeout: 15s
        retry:
          max_attempts: 2
          delay: 1.0
          mode: fixed
        on_error:
          action: goto
          target: Escalate
    Escalate:
      type: illumo_flow.core.FunctionNode
      callable: examples.ops.escalate
```

この例では FlowRuntime の設定よりも `Review` ノードのポリシーが優先され、`timeout` や `retry`、`on_error=goto Escalate` が強制される。

#### `on_error` 特殊ケース

| action     | 挙動概要 |
|------------|-----------|
| `stop`     | 例外発生時に即座にフローを終了（`fail_fast=True` と同義）。|
| `continue` | 現在ノードのエラーを記録したうえで次ノードへ進む（retry が尽きた後に評価）。|
| `goto`     | 指定した `target` ノードを ready キューに追加し、制御フローを転送。ターゲットは同一フロー内の有効なノード ID であること。|

`goto` を利用する場合は、ターゲットノードが複数回実行され得る点に留意し、無限ループやハングを避けるための最大リトライ数・制御フラグを併用する。

### 3.4 Agent 系ノードのインターフェース

> **継承関係の厳守**: `Agent` は `Node` を継承、`RouterAgent` は `RouterNode` を継承する。内部処理は **OpenAI Agents SDK の `Agent` オブジェクト**を用いて実行する（自前の推論実装は持たない）。

```python
# illumo_flow/nodes/agent.py（概略）
from openai import OpenAI
from openai.agents import Agent as OpenAIAgent  # SDK の Agent を使用

class Agent(Node):
    provider: str | None = "openai"
    model: str | None = "gpt-4.1-mini"
    base_url: str | None = None
    system: str | None = None
    prompt: str | None = None
    tools: list[ToolSpec] | None = None
    output_path: str | None = None      # メイン応答
    history_path: str | None = None     # 会話履歴（messages log）
    metadata_path: str | None = None    # reasoning/tool logs
    structured_path: str | None = None  # JSON などの構造化出力

    # SDK Agent のインスタンスを内部に compose
    _sdk_agent: OpenAIAgent | None = None

    def _ensure_sdk_agent(self):
        if self._sdk_agent is None:
            client = OpenAI(base_url=self.base_url)
            # get_llm() はクライアント/モデルの解決に利用するが、**実行は SDK Agent** に委譲
            # LLM モデル指定や tools, tracer は SDK Agent に渡す
            self._sdk_agent = OpenAIAgent(
                client=client,
                model=self.model,
                system_prompt=self.system,
                tools=self.tools or [],
                tracer=self.runtime.tracer   # §3.1/3.2 の SDK Tracer を注入
            )
        return self._sdk_agent

    def run(self, ctx, payload):
        agent = self._ensure_sdk_agent()
        # 入力は prompt か messages を構成して SDK Agent に渡す
        # 返り値（responses/messages）は **SDK の戻り**を正規化し、出力スロットごとに分割する
        resp = agent.run(input=self._render_prompt(ctx, payload))
        normalized = self._normalize_agent_result(resp)
        return {
            "response": normalized.response,
            "history": normalized.history,
            "metadata": normalized.metadata,
            "structured": normalized.structured,
        }
```

```python
class RouterAgent(RouterNode, Agent):
    choices: list[str]
    output_path: str                   # 選択結果の保存先
    metadata_path: str | None = None   # ルーティング理由やスコアを格納
    def run(self, ctx, payload):
        agent = self._ensure_sdk_agent()
        resp = agent.run(input=self._render_prompt(ctx, payload, choices=self.choices))
        decision, rationale = self._extract_choice(resp, self.choices)
        return {
            "decision": decision,
            "metadata": rationale,
        }
```

```python
class EvaluationAgent(Agent):
    rubric: str
    target: str
    output_path: str                   # スコア数値
    structured_path: str | None = None # スコアと評価根拠を JSON 化したもの
    metadata_path: str | None = None   # ローブレベルの評価ログ
    def run(self, ctx, payload):
        agent = self._ensure_sdk_agent()
        text = self._render_eval_prompt(ctx, rubric=self.rubric, target_path=self.target)
        resp = agent.run(input=text)
        score, reasons, details = self._parse_eval(resp)
        return {
            "response": score,
            "metadata": reasons,
            "structured": details,
        }
```

**設計要点**

* LLM/モデル選択は `get_llm()` を用いた解決を踏襲しつつ、**最終実行は SDK Agent に委譲**（自作 generate/chat 呼び出しはしない）。
* `tracer` は **OpenAI Agents SDK Tracer I/F** をそのまま Agent に注入（Console/SQLite/OTel アダプタ）。
* tools/MCP は `tools:` 配列を **SDK Agent の引数**へ渡す。
* `write_outputs()` は `output_path` 群が未指定の場合、`context["agents"][node.id]` 配下に `response`/`history`/`metadata`/`structured` を自動配置し、既存値がある場合は timestamp 付きで追記する。

#### 3.4.1 サンプル実装（Agent 系ノードの使用例）

```python
from illumo_flow.flow import Flow
from illumo_flow.nodes.agent import Agent, RouterAgent, EvaluationAgent
from illumo_flow import FlowRuntime
from illumo_flow.tracing.console_adapter import ConsoleTracer

nodes = [
    Agent(
        id="Refine",
        model="gpt-4.1-mini",
        prompt="Rewrite PRD shorter: {{$ctx.data.prd}}",
        output_path="data.prd_short",
        history_path="history.refine",
        metadata_path="traces.refine",
    ),
    RouterAgent(
        id="Decide",
        prompt="Should we ship or refine?",
        choices=["Ship", "Refine"],
        output_path="route.decision",
        metadata_path="route.rationale",
    ),
    EvaluationAgent(
        id="Review",
        rubric="Score clarity 0-100 and list reasons as JSON",
        target="data.prd_short",
        output_path="metrics.prd_review",
        structured_path="metrics.prd_review_details",
    ),
]

flow = Flow(nodes=nodes, edges=[
    {"from": "Refine", "to": "Decide"},
    {"from": "Decide", "to": "Review"},
])

ctx = {"data": {"prd": "Long product document"}}
FlowRuntime.configure(tracer=ConsoleTracer())
flow.run(ctx)

# DSL では `$ctx.history.refine` と書ける会話履歴を、Python では次のように参照
refine_history = ctx["history"]["refine"]
review_json = ctx["metrics"]["prd_review_details"]
```
##### 単体呼び出し例

```python
from illumo_flow.nodes.agent import Agent, RouterAgent, EvaluationAgent

# Agent: 会話生成
ctx = {"agents": {}, "data": {"prd": "Long product document"}}
refine = Agent(
    id="Refine",
    model="gpt-4.1-mini",
    prompt="Rewrite PRD shorter: {{$ctx.data.prd}}",
    output_path="data.prd_short",
    history_path="history.refine",
)
result = refine.run(ctx, payload={})
ctx.setdefault("agents", {}).setdefault("Refine", {}).update(result)
print(ctx["data"]["prd_short"])            # main response
print(ctx["history"]["refine"])             # conversation log

# RouterAgent: 次ノードを分岐
router = RouterAgent(
    id="Decide",
    prompt="Ship or refine?",
    choices=["Ship", "Refine"],
    output_path="route.decision",
)
route = router.run(ctx, payload={"score": 82})
ctx.setdefault("route", {}).update(route)
print(ctx["route"]["decision"])          # -> "Ship" など

# EvaluationAgent: 採点
reviewer = EvaluationAgent(
    id="Review",
    rubric="Score 0-100 and list reasons",
    target="data.prd_short",
    output_path="metrics.prd_review",
    structured_path="metrics.prd_review_details",
)
score_payload = reviewer.run(ctx, payload={})
ctx.setdefault("metrics", {}).update(score_payload)
print(ctx["metrics"]["prd_review"])       # numeric score
print(ctx["metrics"]["prd_review_details"])
```

*上記の単体呼び出し例では `ctx` 更新を手動で行っているが、実運用では FlowRuntime が `write_outputs()` を通じて同じ構造で書き込む。*



---

#### 3.4.2 連携シナリオ（RouterAgent → 会話継続 Agent → EvaluationAgent）

```yaml
flow:
  entry: RouteSelector
  nodes:
    RouteSelector:
      type: illumo_flow.nodes.agent.RouterAgent
      prompt: |
        Inspect the intake ticket. Choose `Refine` if a quick polish helps, otherwise `Escalate`.
      choices: [Refine, Escalate]
      output_path: route.selected
      metadata_path: route.reason

    Refine:
      type: illumo_flow.nodes.agent.Agent
      model: gpt-4.1-mini
      prompt: |
        Continue the intake conversation and polish the proposal:
        {{ $ctx.history.intake }}
      history_path: history.refine
      output_path: draft.refined

    EvaluateDraft:
      type: illumo_flow.nodes.agent.EvaluationAgent
      rubric: |
        Score 0-100. Pass if the draft is concise, actionable, and risk-aware.
        Return JSON {"score": number, "verdict": "pass" | "fail", "reasons": [str]}.
      target: draft.refined
      output_path: metrics.refine_score
      structured_path: metrics.refine_details

    FinalGate:
      type: illumo_flow.core.FunctionNode
      handler: pkg.nodes.final_gate  # Summarise verdict/reasons / 合否と理由をまとめる
      context:
        inputs:
          verdict: $ctx.metrics.refine_details.verdict
          reasons: $ctx.metrics.refine_details.reasons
        outputs:
          result: decisions.final

  edges:
    - "RouteSelector >> (Refine | FinalGate)"
    - "Refine >> EvaluateDraft"
    - "EvaluateDraft >> FinalGate"
```

```python
from illumo_flow import Flow, FlowRuntime

flow_config = {
    "flow": {
        "entry": "RouteSelector",
        "nodes": {
            "RouteSelector": {
                "type": "illumo_flow.nodes.agent.RouterAgent",
                "prompt": (
                    "Inspect the intake ticket. Choose `Refine` if a quick polish helps, "
                    "otherwise `Escalate`."
                ),
                "choices": ["Refine", "Escalate"],
                "output_path": "route.selected",
                "metadata_path": "route.reason",
            },
            "Refine": {
                "type": "illumo_flow.nodes.agent.Agent",
                "model": "gpt-4.1-mini",
                "prompt": (
                    "Continue the intake conversation and polish the proposal:\n"
                    "{{ $ctx.history.intake }}"
                ),
                "history_path": "history.refine",
                "output_path": "draft.refined",
            },
            "EvaluateDraft": {
                "type": "illumo_flow.nodes.agent.EvaluationAgent",
                "rubric": (
                    "Score 0-100. Pass if the draft is concise, actionable, and risk-aware.\n"
                    "Return JSON {\\"score\\": number, \\"verdict\\": \\"pass\\" | \\"fail\\", "
                    "\\"reasons\\": [str]}.")
                ,
                "target": "draft.refined",
                "output_path": "metrics.refine_score",
                "structured_path": "metrics.refine_details",
            },
            "FinalGate": {
                "type": "illumo_flow.core.FunctionNode",
                "handler": "pkg.nodes.final_gate",
                "context": {
                    "inputs": {
                        "verdict": "$ctx.metrics.refine_details.verdict",
                        "reasons": "$ctx.metrics.refine_details.reasons",
                    },
                    "outputs": {
                        "result": "decisions.final",
                    },
                },
            },
        },
        "edges": [
            "RouteSelector >> (Refine | FinalGate)",
            "Refine >> EvaluateDraft",
            "EvaluateDraft >> FinalGate",
        ],
    }
}

FlowRuntime.configure()  # Configure tracer/policy when needed / tracer/policy は必要時に設定
flow = Flow.from_config(flow_config)

context = {
    "history": {
        "intake": ["User: Draft request", "Agent: Understood."],
    },
}

flow.run(context)

print(context["route"]["selected"])          # Selected branch/選択された分岐
print(context["draft"]["refined"])          # Refined draft/更新ドラフト
print(context["metrics"]["refine_details"])  # Evaluation JSON/評価詳細
print(context["decisions"]["final"])         # Final verdict/最終判定

# pkg/nodes/final_gate.py の例/Example implementation
def final_gate(verdict: str, reasons: list[str] | None) -> dict[str, str | list[str] | None]:
    """Return final decision payload./最終合否ペイロード"""
    return {
        "status": verdict,
        "note": "; ".join(reasons) if reasons else None,
        "reasons": reasons,
    }
```

- RouterAgent が `route.selected` に分岐結果、`route.reason` に根拠を格納する。
- `Refine` Agent は `history.intake` を継続して `draft.refined` に改稿案を保存し、会話ログは `history.refine` に追記される。
- EvaluationAgent は JSON 詳細を `metrics.refine_details` に書き込み、`FinalGate` 関数ノードが verdict と理由から最終判定を `decisions.final` に集約する。
- Flow 全体を Flow 定義として組み、Tracer/Policy は必要に応じて `FlowRuntime.configure(...)` で後付けできる。

---

### 3.5 LLM 取得インターフェース：`get_llm()`

* **目的**: プロバイダ非依存で LLM クライアントを取得する。ただし **独自型は定義しない**。最小指定（モデル名など）で OpenAI のチャット／レスポンス クライアント、Anthropic や Google、LMStudio/Ollama/OpenRouter などの OSS 連携クライアントを推測して返せる。
* **方針**: `get_llm()` はモデル名・CLI/YAML 指定・環境変数からプロバイダを推測し、優先順位 OpenAI → Anthropic → Google → LMStudio → Ollama → OpenRouter で解決する。基になっている設計は `src/illumo/get_llm.py` に準じ、**Agent 実行自体は SDK の `Agent`** が行う。

```python
# illumo_flow/llm/registry.py（抜粋の再掲）
from typing import Any, Optional
from openai import OpenAI

# Responses / ChatCompletions の選択は保持するが、**実行は SDK Agent 側**で行う

def get_llm(provider: Optional[str], model: str, base_url: Optional[str] = None, **opts) -> Any:
    client = OpenAI(base_url=base_url, **opts)
    # 返却は SDK が扱うクライアント実体（Any）でよい。Agent 側で受け取り、OpenAIAgent 生成に使用。
    return client
```

---：`get_llm()`

* **目的**: プロバイダ非依存で LLM クライアントを取得する。ただし **独自型を定義しない**。**OpenAI のチャット／レスポンスのクライアント**（OpenAI SDK）が返る前提で実装する。
* **方針**: `get_llm()` は **OpenAI SDK のクライアント/モデル実装**をそのまま返す（`Any` で受ける）。利用側（Agent/Routing/Evaluation）は OpenAI SDK の I/F を直接呼び出す。

```python
# illumo_flow/llm/registry.py
from typing import Any, Optional
from openai import OpenAI  # OpenAI公式SDK

# 例: illumo と同様の切替。Responses API優先、無ければChat Completions。

def _use_responses_api(provider: Optional[str], base_url: Optional[str]) -> bool:
    # 実装例: provider/base_url/feature-flag で判断。必要なら YAML/CLI で明示指定も可。
    return True if provider == "openai" else False

class OpenAIResponsesModel:
    def __init__(self, openai_client: OpenAI, model: str):
        self.client = openai_client
        self.model = model
    # 呼び出し側は OpenAI SDK の responses エンドポイントを直接使用
    # 例: self.client.responses.create(...)

class OpenAIChatCompletionsModel:
    def __init__(self, openai_client: OpenAI, model: str):
        self.client = openai_client
        self.model = model
    # 呼び出し側は chat.completions を直接使用
    # 例: self.client.chat.completions.create(...)


def get_llm(provider: Optional[str], model: str, base_url: Optional[str] = None, **opts) -> Any:
    # ここでは **独自型を導入せず**、OpenAI SDK のクライアント実体をベースにした
    # レスポンス/チャットクライアントを返す。資格情報や接続先は YAML/CLI 由来の引数で渡す（新規ENVは導入しない）。
    # provider が None の場合はモデル名から OpenAI/Anthropic/Google/LMStudio/Ollama/OpenRouter を推測
    client = OpenAI(base_url=base_url, **opts)

    model_inst: Any
    if _use_responses_api(provider, base_url):
        model_inst = OpenAIResponsesModel(openai_client=client, model=model)
    else:
        model_inst = OpenAIChatCompletionsModel(openai_client=client, model=model)
    return model_inst
```

* **利用例（Agent 内）**

```python
class Agent(Node):
    provider: str | None = "openai"
    model: str | None = "gpt-4.1-mini"
    base_url: str | None = None

    def run(self, ctx, payload):
        llm = get_llm(self.provider, self.model, base_url=self.base_url)
        # 以降は OpenAI SDK の I/F を**直接**呼ぶ実装にする
        # Responses API の例:
        # resp = llm.client.responses.create(model=self.model, input=self._render_prompt(ctx))
        # Chat Completions の例:
        # resp = llm.client.chat.completions.create(model=self.model, messages=[...])
        # 戻り値整形は Agent 側で実施
        return self._post(resp)
```

**重要**

* 本ライブラリとして **新規環境変数は導入しない**。APIキー等の資格情報は **CLI/YAML から明示**で渡すか、または各 SDK の既定解決（SDK側ENVなど）に委譲する。
* 将来、Ollama/LmStudio などを拡張する場合も **独自プロトコル型は作らず**、該当クライアントの I/F を直接呼ぶ薄いアダプタに留める。

---

## 4. YAML スキーマ（簡易）と例

### 4.1 YAML ルート

```yaml
flow:
  name: demo
  policy:
    fail_fast: true
    retry: { max: 0 }

observability:
  tracer: sqlite          # console | sqlite | otel
  args:
    db_path: ./trace.db

nodes:
  - id: Fetch
    type: Function
    handler: pkg.nodes.fetch
    timeout: "3s"

  - id: Enrich
    type: Function
    handler: pkg.nodes.enrich
    retry: { max: 2, backoff: "fixed:0.5" }

  - id: Decide
    type: RouterAgent
    prompt: "If sum>3 then Ship else Refine"
    choices: ["Ship", "Refine"]
    output_path: route.decision
    metadata_path: route.rationale

  - id: Aggregate
    type: Function
    handler: pkg.nodes.aggregate

  - id: Refine
    type: Agent
    model: gpt-4.1-mini
    prompt: "Rewrite PRD shorter: {{context.prd}}"
    output_path: prd_short
    history_path: history.refine
    metadata_path: traces.refine

  - id: Review
    type: EvaluationAgent
    rubric: |
      Score 0-100 for clarity, feasibility, risks. Return JSON {score, reasons[]}
    target: prd_short
    output_path: metrics.prd_review
    structured_path: metrics.prd_review_details
    metadata_path: traces.review

edges:
  - { from: Fetch, to: Enrich }
  - { from: Enrich, to: Aggregate }
  - { from: Aggregate, to: Decide }
  - { from: Decide, when: '{{context.sum > 3}}', to: Ship }
  - { from: Decide, when: '{{context.sum <= 3}}', to: Refine }
  - { from: Refine, to: Review }
```

### 4.2 JSON Schema（サマリ）

* `flow.name` (string)
* `flow.policy` (fail_fast/timeout/retry/on_error)
* `observability.tracer` ∈ {console, sqlite, otel}
* `nodes[].type` ∈ {Function, Agent, RouterAgent, EvaluationAgent}
* すべての `edges[].from/to/when` を検証。未定義ノードや循環を検出して**ロード時に失敗**。

---

## 5. CLI（環境変数は使用しない）

* `illumo run flow.yaml --tracer otel --tracer-arg exporter_endpoint=http://localhost:4317 --fail-fast=false --policy.retry.max=2`
* LLM プロバイダ/モデル指定（例）:

  * `illumo run flow.yaml --set nodes.Refine.provider=openai --set nodes.Refine.model=gpt-4.1-mini`
* **優先順位**: CLI > YAML

---

## 7. 受け入れ条件（Acceptance Criteria）

* [ ] **継承関係**: `Agent` は `Node` 継承、`RouterAgent` は `RouterNode` 継承で動作し、既存 Node/RouterNode と同一の実行境界でトレースが貼られる。
* [ ] **Tracer I/F**: すべてのトレースは **OpenAI Agents SDK の Tracer インターフェース**で発火する。Console/SQLite/OTel はこの I/F の**純粋なアダプタ**。
* [ ] **観測性切替**: `console`/`sqlite`/`otel` を **クラス差し替え（DI）**で切替可能。span が各ノード実行境界に 1:1 で作成される。
* [ ] **Policy 準拠**: `fail_fast` 既定で、`retry/timeout/on_error` がノード上書きで期待通りに動作する。
* [ ] **Agent ノード**: `Agent`/`RouterAgent`/`EvaluationAgent` が YAML のみで動作し、`output_path`/`history_path`/`metadata_path`/`structured_path` を使い分けて応答・会話履歴・構造化データを競合なく保存できる。
* [ ] **get_llm()**: YAML/CLI で指定した `provider`/`model` に基づき LLM を取得し、OpenAI/他プロバイダを差し替えても挙動が変わらない（I/F 互換）。
* [ ] **YAML 検証**: 不正な `edges`、未定義 `nodes`、循環がロード時に検知され、明確なエラーメッセージが出る。
* [ ] **優先順位**: 設定の適用順は **CLI > YAML**。**新規環境変数は導入しない**。

受け入れ条件（Acceptance Criteria）

* [ ] **継承関係**: `Agent` は `Node` 継承、`RouterAgent` は `RouterNode` 継承で動作し、既存 Node/RouterNode と同一の実行境界でトレースが貼られる。
* [ ] **Tracer I/F**: すべてのトレースは **OpenAI Agents SDK の Tracer インターフェース**で発火する。Console/SQLite/OTel はこの I/F の**純粋なアダプタ**。
* [ ] **観測性切替**: `console`/`sqlite`/`otel` を CLI 1コマンドで切替可能。span が各ノード実行境界に 1:1 で作成される。
* [ ] **Policy 準拠**: `fail_fast` 既定で、`retry/timeout/on_error` がノード上書きで期待通りに動作する。
* [ ] **Agent ノード**: `Agent`/`RouterAgent`/`EvaluationAgent` が YAML のみで動作し、`output_path`/`history_path`/`metadata_path`/`structured_path` を使い分けて応答・会話履歴・構造化データを競合なく保存できる。
* [ ] **get_llm()**: YAML/CLI で指定した `provider`/`model` に基づき LLM を取得し、OpenAI/他プロバイダを差し替えても挙動が変わらない（I/F 互換）。
* [ ] **YAML 検証**: 不正な `edges`、未定義 `nodes`、循環がロード時に検知され、明確なエラーメッセージが出る。
* [ ] **優先順位**: 設定の適用順は CLI > YAML。**新規環境変数は導入しない**。

---

## 8. 使用体験（UX）— 開発→PoC→本番

**方針**: 引数フラグではなく、**クラス差し替え**（DI）で Tracer を切り替える。初期段階では `Flow` が `FlowRuntime.default()` を内部生成するため、利用者は `flow = Flow.from_config("./flow.yaml")` と `flow.run()` だけで最小構成を即時起動できる。運用段階の切替が必要になったら `FlowRuntime.configure(...)` でグローバル設定を差し替えるだけで移行できる。

### A) 開発（Console）

```python
from illumo_flow import FlowRuntime
from illumo_flow.tracing.console_adapter import ConsoleTracer

flow = Flow.from_config("./flow.yaml")
flow.run(initial_context={})  # デフォルトランタイムで即実行

# 観測性などを増やしたい場合はグローバル設定を切り替える
FlowRuntime.configure(tracer=ConsoleTracer())
flow.run(initial_context={})
```

* 目的: 色付きログで高速に失敗箇所を特定。`fail_fast=true` 既定。

### B) PoC（SQLite 永続）

```python
from illumo_flow.tracing.sqlite_adapter import SQLiteTracer

FlowRuntime.configure(tracer=SQLiteTracer(db_path="./trace.db"))
flow.run(initial_context={})
```

* 目的: ローカルで履歴を確認・比較可能に。

### C) 本番（OTel / Tempo）

```python
from illumo_flow.tracing.otel_adapter import OtelTracer

FlowRuntime.configure(
    tracer=OtelTracer(
        service_name="illumo-flow",
        exporter_endpoint="http://localhost:4317",
    )
)
flow.run(initial_context={})
```

* 目的: 分散トレースを Tempo/Grafana で可視化。**SDK Tracer I/F 準拠**のため相関IDが継続。

### D) YAML による最小指定（任意）

```yaml
observability:
  tracer: otel            # console | sqlite | otel
  args:
    exporter_endpoint: http://localhost:4317
    service_name: illumo-flow
```

* ローダが `tracer` を見て内部で **対応する Tracer クラスを生成**。明示的にクラスを差し替えるコードと**等価**の挙動。

---

## 11. 付録：バックオフ文字列の文法（BNF）

付録：バックオフ文字列の文法（BNF）

```
<backoff> ::= "fixed:" <seconds>
            | "exponential:" <start> ".." <cap> [" + jitter"]
<seconds> ::= float
<start>   ::= float
<cap>     ::= float
```

* 例: `fixed:0.5` / `exponential:0.5..8.0` / `exponential:1..32 + jitter`

---

### 本要件書の意図

* AIエディタが**改変順序と責務分離**（Agent→Tracer→Policy）を誤認しないこと。
* 開発者が**運用面の最小構成**（Fast-Fail 既定、SQLite での PoC、OTel での本番）を**直感的に切替**できること。
* 既存ユーザの破壊を避け、**軽量コア×宣言的運用**の体験を損なわないこと。
