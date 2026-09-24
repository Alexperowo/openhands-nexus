# TODO: Recalibrate Qwen 122B Expert Pruning with Russian Dataset

**Priority:** Medium (non-blocking, quality improvement)
**Created:** 2026-09-24
**Status:** Open

## Problem

The current Qwen3-235B → 122B expert pruning (256 → 208 experts) was performed
using an English-only calibration dataset. This resulted in Russian language
generation being severely degraded:

- Model **understands** Russian input correctly (comprehension is intact)
- Model **generates** broken Russian output: mixed scripts, garbled words
  ("Хороо", "саво", "ИOpenHands"), defaulting to English mid-sentence
- English coding and reasoning capabilities are fully preserved (tests pass)

## Root Cause

MoE expert routing specializes different experts for different languages.
The English-only calibration dataset marked Russian-specialized experts as
"low activity" → they were pruned.

## Solution

Re-run the pruning pipeline with a **multilingual calibration dataset** that
includes Russian text. This will preserve Russian language experts and instead
prune less-needed ones (e.g., Japanese, Arabic, Thai — languages we don't use).

### Calibration Dataset Requirements

- Include a mix of:
  - Russian conversational text
  - Russian technical documentation
  - English code and reasoning (to preserve coding ability)
- Ratio suggestion: ~40% English code, ~30% Russian text, ~30% English prose
- Minimum 1000 calibration samples

### Steps

1. Prepare multilingual calibration dataset (Russian + English)
2. Re-run expert importance scoring with the new dataset
3. Prune to the same 208-expert target (or find the new sweet spot)
4. Verify Russian generation quality
5. Verify English coding/reasoning quality hasn't regressed
6. Replace the GGUF in `Models/Qwen122/`

## Workaround (Tested)

- System prompt "Всегда отвечай на русском языке" — **does NOT help**
  - Model thinks in English, attempts Russian, falls back to Chinese (Mandarin)
  - Reasoning trace: "Я是一个人工智能助手，旨在帮助用户完成各种任务"
  - Content field comes back empty (all budget consumed by broken thinking)
- **Conclusion:** This is a generation-level defect, not a prompt-level issue
- For Russian-heavy tasks, use Qwen 27B (full, unpruned model)

## Reference

- Pruning report: `QWEN122_MOE_PRUNING_ENGINEERING_REPORT.md`
- Original model: Qwen3-235B-A22B (256 experts)
- Current pruned model: Qwen3-Next-122B (208 experts)
