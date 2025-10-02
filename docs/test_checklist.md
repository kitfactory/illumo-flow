# Test Checklist

Maintain deterministic runs by executing one test at a time and logging completion status here.

## Usage Guidelines
- Extend scenarios only inside `tests/test_flow_examples.py`; keep this repository in edit-only mode.
- Before running, list every target case in the checklist below.
- Execute each test via `pytest tests/test_flow_examples.py::TEST_NAME`. Set `FLOW_DEBUG_MAX_STEPS=200` when exercising looping flows to avoid hangs.
- Tick the checkbox after the test passes. For regression sweeps, reset all boxes to unchecked state and run sequentially.
- Add new checklist entries whenever you introduce a test and remove entries when tests are deleted.

## Checklist (reset before regression passes)
- [x] tests/test_flow_examples.py::test_examples_run_without_error — Smoke run for the bundled DSL scenarios
- [x] tests/test_flow_examples.py::test_join_node_receives_parent_dictionary — Validates fan-in nodes aggregate parent payloads
- [x] tests/test_flow_examples.py::test_context_paths_are_honored — Confirms `inputs`/`outputs` mappings reach the shared context paths
- [x] tests/test_flow_examples.py::test_multiple_outputs_configuration — Ensures a single node can write to multiple targets
- [x] tests/test_flow_examples.py::test_flow_from_yaml_config — Builds and runs flows from YAML and dict-based configs
- [x] tests/test_flow_examples.py::test_expression_inputs_and_env — Covers template expressions and environment variable resolution
- [x] tests/test_flow_examples.py::test_callable_resolved_from_context_expression — Exercises dynamic callable lookup from context
- [x] tests/test_flow_examples.py::test_function_node_returning_routing_is_rejected — Asserts FunctionNode rejects Routing return values
- [x] tests/test_flow_examples.py::test_loop_node_iterates_over_sequence — Verifies loop nodes advance through iterable payloads
- [x] tests/test_flow_examples.py::test_get_llm_appends_v1_suffix_when_missing — Ensures OpenAI-compatible hosts gain the `/v1` suffix automatically
- [x] tests/test_flow_examples.py::test_get_llm_keeps_existing_v1_suffix — Confirms existing `/v1`-suffixed base URLs remain unchanged
- [x] tests/test_flow_examples.py::test_get_llm_defaults_to_openai_when_unspecified — Verifies provider inference defaults to OpenAI when no hints are given
- [x] tests/test_flow_examples.py::test_get_llm_respects_explicit_provider_priority — Confirms explicit provider arguments override heuristic ordering
- [x] tests/test_flow_examples.py::test_agent_openai_writes_to_configured_paths — Ensures OpenAI-backed Agents write responses to configured context paths
- [x] tests/test_flow_examples.py::test_agent_lmstudio_writes_to_agents_bucket — Confirms LMStudio-backed Agents store outputs under `ctx.agents.<id>` when paths are omitted
- [x] tests/test_flow_examples.py::test_router_agent_selects_route_with_reason — Validates RouterAgent records the chosen branch and rationale
- [x] tests/test_flow_examples.py::test_evaluation_agent_records_score_and_metadata — Ensures EvaluationAgent stores scores, reasons, and structured payloads
- [x] tests/test_flow_examples.py::test_console_tracer_emits_flow_and_node_spans — Verifies console tracer outputs span lifecycle messages
- [x] tests/test_flow_examples.py::test_sqlite_tracer_persists_spans — Confirms SQLite tracer records span rows for flow/node execution
- [x] tests/test_flow_examples.py::test_otel_tracer_exports_spans — Ensures Otel tracer forwards span payloads to the configured exporter
- [ ] CLI manual check — Run `illumo run` with `--tracer` / Policy overrides and confirm spans & policy behaviour interactively
- [x] tests/test_workspace_nodes.py::test_workspace_inspector_collects_selected_files — Verifies WorkspaceInspectorNode records previews for selected files
- [x] tests/test_workspace_nodes.py::test_workspace_inspector_filters_by_extension — Ensures disallowed extensions are excluded with reasons
- [x] tests/test_workspace_nodes.py::test_workspace_inspector_respects_max_bytes — Confirms oversized files omit previews and record exclusion reasons
- [x] tests/test_workspace_nodes.py::test_workspace_inspector_rejects_missing_root — Raises FlowError when the target root is absent
- [x] tests/test_workspace_nodes.py::test_patch_node_applies_diff_without_writing — Applies unified diffs to context data without touching disk
- [x] tests/test_workspace_nodes.py::test_patch_node_respects_allowed_paths — Rejects patches targeting disallowed paths
- [x] tests/test_workspace_nodes.py::test_patch_node_write_option — Writes patched content to disk only when requested
- [x] tests/test_workspace_nodes.py::test_test_executor_runs_pytest — Executes pytest in the target workspace and captures results
- [x] tests/test_workspace_nodes.py::test_test_executor_records_failures — Captures non-zero exit codes without raising
