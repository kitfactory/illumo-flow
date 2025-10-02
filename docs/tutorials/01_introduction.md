# 1. Introduction & Setup

## What you will build
- Understand why illumo-flow helps you orchestrate LLM-driven flows faster and safer.
- Prepare your environment so that you can immediately run Agents, route decisions, and capture telemetry.

## Why it matters (and why it’s fun)
- Instead of wiring ad-hoc scripts, you get a deliberate pipeline where every LLM step, retry, and branch is explicit.
- The tutorial treats each capability as a building block for a playful multi-agent “mini app”.

## Prerequisites
- Python 3.10+
- Access to at least one OpenAI-compatible endpoint (OpenAI `gpt-4.1-nano` and/or LMStudio `openai/gpt-oss-20b` at `http://192.168.11.16:1234`).
- Git and `uv` (optional but recommended).

## Steps
1. **Clone / install**
   ```bash
   git clone https://github.com/kitfactory/illumo-flow.git
   cd illumo-flow
   uv pip install -e .  # or pip install -e .
   ```
2. **Configure environment**
   - Ensure your LLM endpoint credentials are available (OpenAI key or LMStudio without auth).
   - Optional `.env` for convenience, but the tutorial primarily passes credentials at runtime.
3. **Sanity check**
   ```bash
   pytest tests/test_flow_examples.py::test_examples_run_without_error -q
   ```
   If it passes, you’re ready to create flows.

## Look ahead
- Chapter 2 introduces the `Agent` node and shows how a single prompt interacts with `ctx`.
- By Chapter 6 you’ll combine multiple agents into an application-like workflow.
- Chapters 7-8 reveal how Tracers and Policy framing give you production-grade observability and control.

Grab your favorite beverage—the journey blends hands-on coding with the fun of taming multiple LLM personalities.
