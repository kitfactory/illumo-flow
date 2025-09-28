# Chapter 5 · Configuration, Testing, and Operations

The final chapter covers maintainability topics: configuration sources, testing discipline, and operational guard rails.

## 5.1 Managing Configuration
- Store flow definitions in YAML or JSON for auditability.
- Keep the Python DSL in sync with configuration to ensure parity between environments.
- Use import strings (`examples.ops.extract`) for callables so configuration stays declarative.

```yaml
flow:
  entry: ingest
  nodes:
    ingest:
      type: illumo_flow.core.FunctionNode
      name: ingest
      context:
        inputs:
          callable: my_project.nodes.ingest
        outputs: $ctx.data.ingested
    normalize:
      type: illumo_flow.core.FunctionNode
      name: normalize
      context:
        inputs:
          callable: my_project.nodes.normalize
          payload: $ctx.data.ingested
        outputs: $ctx.data.normalized
  edges:
    - ingest >> normalize
```

## 5.2 Testing Strategy
- Use the checklist in `docs/test_checklist.md` to run pytest targets one at a time.
- Prefer real payloads over mocks; flows are deterministic.
- For integration tests, seed the context with fixtures and assert both payloads and routing metadata.

## 5.3 Operational Considerations
- Use `FLOW_DEBUG_MAX_STEPS` to cap loop iterations during live debugging.
- Record routing metadata (`confidence`, `reason`) so decisions are auditable.
- Keep context mutations minimal; rely on payload transformations whenever possible.
- When integrating external services, handle retries inside the node and surface failures clearly.

## 5.4 Next Steps
- Read the API reference in `docs/flow.md` for advanced hooks.
- Explore `examples/` for end-to-end compositions.
- Extend the checklist as new tests are added to the suite.
