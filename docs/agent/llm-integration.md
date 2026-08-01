# LLM Integration

How Atlas talks to models. Authoritative detail:
[PROJECT.md §5.1 / §5.1a](../PROJECT.md#51-ai-provider-abstraction-atlasai),
[§7 (AI task contracts)](../PROJECT.md#7-ai-task-contracts),
[Appendix A (CLI invocations)](../PROJECT.md#appendix-a--coding-cli-adapter-reference).

## One interface, two families of backend

All AI goes through the `LLMProvider` interface. There are two implementations:

1. **CLI adapters** (`ai/cli/`) — **default**. Drive locally installed coding CLIs headlessly
   via `subprocess`: `claude -p`, `codex exec`, `agy -p`. All three support
   `--output-format json` + a JSON-schema flag, so structured output is uniform. Per-tool
   quirks (auth, sandboxing, neutralizing file edits) are in Appendix A — **read it before
   touching an adapter.**
2. **LiteLLM adapter** (`ai/api/`) — one `LiteLLMProvider` for **all** API providers
   (OpenRouter, Bedrock, Anthropic, Gemini, DeepSeek, Groq, Ollama, OpenAI-compat). Kept
   **behind** `LLMProvider` so it's swappable.

> CLI backends are **not** LiteLLM. LiteLLM cannot drive the coding CLIs. Don't try to route
> them through it.

## Rules (from the reference review, PROJECT.md §19)

- **Two retry layers, kept separate:**
  - *Transport retries* (network/5xx/rate-limit) live in the **LiteLLM `Router` +
    `RetryPolicy`**. Do **not** re-retry transport in callers.
  - *Content retries* (bad/truncated JSON) live in **`complete_json()`**.
- **Model capabilities from a registry, not hardcoded** — JSON-mode support, max tokens,
  temperature limits are queried per model; request JSON mode only where supported.
- **Key handling:** one `resolve_api_key()`; keys come from the keyring and pass to LiteLLM
  **directly, never via `os.environ`**. **Local providers skip the env-key fallback** so a
  paid key can't leak to a local endpoint.
- **Capability probing:** `atlas doctor` detects each backend, runs a tiny JSON round-trip,
  and records JSON/schema/streaming/system-prompt/model-override support.
- **Failover:** ordered backend chain; on hard error/auth/quota, try the next.

## Structured output: `complete_json()`

Every structured call goes through the shared helper, which recovers in layers before
failing (full detail in PROJECT.md §5.1):

1. Read native structured field (CLI `structured_output` / LiteLLM JSON mode) → validate.
2. Brace-balancing extraction from prose/code-fence → re-validate.
3. Content-quality retry (bounded), escalating temperature slightly.
4. JSON-mode → prompt-only fallback ("return only JSON between delimiters").
5. Clear error, then optional backend failover.

## Prompts

- **Jinja2 templates** under `ai/prompts/`, **versioned**, each paired with a JSON schema
  (Pydantic-derived) for its task. Not plain Python string constants.
- Every generative prompt supports an output-language variable for future i18n.
- User-editable prompts (if any) validate required variables before save.

## Accounting

Record per-call usage/cost (`usage`, `total_cost_usd` where available) to the `ai_call`
table. Respect the per-day spend cap for API backends. Cache by (prompt version, model,
inputs) so re-opening a posting doesn't re-spend.

## Testing AI code

Never hit a real CLI or API in the default suite. Use the **fake `LLMProvider`** and
**`respx`** for transport. Real-LLM checks go in the `eval` marker, excluded by default. See
[testing-strategy.md](./testing-strategy.md).
