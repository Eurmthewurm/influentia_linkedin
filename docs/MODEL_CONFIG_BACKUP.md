# Hermes Model Config - Working backup (2026-05-12)
# Default: openrouter/qwen/qwen3-coder:free
# Ring model was returning HTTP 400 so switched to Qwen3-Coder as primary

model:
  default: openrouter/qwen/qwen3-coder:free
  provider: openrouter

# Full fallback chain (all free, no ollama):
# 1. openrouter/inclusionai/ring-2.6-1t:free     - if it comes back
# 2. openrouter/qwen/qwen3-coder:free              - same as primary (retry)
# 3. openrouter/nvidia/nemotron-3-super-120b-a12b:free
# 4. openrouter/google/gemma-4-31b-it:free
# 5. openrouter/openai/gpt-oss-120b:free
# 6. openrouter/minimax/minimax-m2.5:free
# 7. openrouter/arcee-ai/trinity-large-thinking:free
# 8. openrouter/owl-alpha                           - last resort, rate limited

# To restore: copy relevant sections to ~/.hermes/config.yaml
