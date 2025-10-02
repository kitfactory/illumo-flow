# Roadmap

## Prioritization Approach
- **Evaluation criteria**: user impact, development effort, quality risk, ecosystem leverage, and strategic differentiation.
- **Resulting order**: 4. Flow Runtime Hardening → 2. Tracing & Observability Enhancements → 6. Context / RAG Infrastructure → 1. GUI / Visual Builder → 5. Ecosystem Connectors → 3. Agent & LLM Abstractions.
- **Rationale**: solidifying reliability and tracing first protects downstream UX work, while RAG and connectors build on that foundation before deeper agent abstractions; provider-specific optimizations remain deferred until feature parity is secured.

## 1. GUI / Visual Builder
- **Goal**: Provide an interactive view for flow DSL and tracing data to improve discoverability and authoring.
- **Key Deliverables**: CLI-powered static viewer, optional browser-based editor, TraceQL overlay for spans, and export back to DSL.
- **Dependencies**: Existing CLI runtime, tracing database API, documentation for user workflows.
- **Open Questions**: Hosting model (local vs. bundled server), authentication needs, alignment with design guidelines.

## 2. Tracing & Observability Enhancements
- **Goal**: Elevate debugging and monitoring through richer query options and exporter support.
- **Key Deliverables**: Python API for TraceQL-like filters, additional OTEL exporter adapters, formatted CLI outputs, alert-friendly summaries.
- **Dependencies**: Current tracing_db module, CLI command structure, pytest coverage to guard regressions.
- **Open Questions**: Target backends to prioritize, performance impact of complex queries, test data generation policy.

## 3. Agent & LLM Abstractions
- **Goal**: Normalize external model integrations via ABC/Protocol layers while keeping API surface minimal.
- **Key Deliverables**: Unified connector interfaces, evaluation agent templates, documentation for adapter contributions, strict publish window.
- **Dependencies**: Existing agent nodes, design guide constraints, adapter injection points.
- **Open Questions**: Versioning of third-party SDKs, local model support guarantees, telemetry boundaries.

## 4. Flow Runtime Hardening
- **Goal**: Improve reliability and recoverability for production-like workloads.
- **Key Deliverables**: Enhanced policy validation (fail-fast/retry/timeout), richer error surfaces, resumable execution diary, CLI formatting options.
- **Dependencies**: Core runtime modules, policy definitions, tracing hooks.
- **Open Questions**: Required persistence guarantees, feature flags vs. configuration, performance budgets.

## 5. Ecosystem Connectors
- **Goal**: Offer minimal yet composable entry/exit points for external systems.
- **Key Deliverables**: Webhook/MQ/DB adapters, examples showcasing real business flows, contributor-facing adapter guide.
- **Dependencies**: Existing examples directory, adapter injection abstractions, docs pipeline.
- **Open Questions**: Prioritization rubric for connectors, backwards compatibility policy, security review checklist.

## 6. Context / RAG Infrastructure
- **Goal**: Enable retrieval-augmented flows with a consistent context management layer.
- **Key Deliverables**: ContextStore abstraction, vector/full-text backend adapters, CLI/SDK commands for ingest & query, bilingual setup docs.
- **Dependencies**: Flow runtime context handling, tracing metadata, design constraints on configuration.
- **Open Questions**: Default storage backend, cost/performance guardrails, data governance requirements.
