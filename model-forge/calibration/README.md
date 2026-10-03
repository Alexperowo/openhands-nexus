# Importance Matrix (imatrix) Calibration Repository

This directory stores `.gguf` importance matrices used by `llama-quantize.exe` during model quantization.

## 1. Upstream Base Matrices
- `imatrix-qwen3.8-27b.gguf` (13.6 MB)
  - Origin: `ISTA-DASLab/Qwen3.8-27B-GSQ-RCO-GGUF`
  - URL: `https://huggingface.co/ISTA-DASLab/Qwen3.8-27B-GSQ-RCO-GGUF/resolve/main/imatrix-qwen3.8-27b.gguf`
  - Calibrated on: Standard Riemann Curvature Optimization general dataset.

## 2. Generating Station-Specific Agentic Matrices (Candidate C)
To calibrate directly on OpenHands Nexus workloads (CodeAct loops, Russian dialogues, tool execution):

```powershell
K:\Project\ik_llama\bin\llama-imatrix.exe `
  -m "K:\Project\Models\Qwen3.8\staging\Qwen3.8-27B-Opus-Distill-v2-BF16.gguf" `
  -f "K:\Project\model-forge\recipes\calibration_prompts\nexus_calibration_corpus.txt" `
  -o "K:\Project\model-forge\calibration\imatrix-qwen3.8-27b-nexus-agentic.gguf" `
  -c 4096 `
  -b 512 `
  --chunks 64 `
  -dev CUDA1 `
  --process-output
```
*Note: Run on GPU 1 (RTX 2080 Ti 22 GB) with `-dev CUDA1` to avoid interrupting GPU 0.*
