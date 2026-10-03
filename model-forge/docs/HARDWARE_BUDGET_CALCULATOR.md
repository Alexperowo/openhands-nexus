# Hardware Budget & VRAM Calculator for OpenHands Nexus

## 1. Physical Hardware Ceilings

```text
+-----------------------------------------------------------------------------------+
| Host System RAM: 48 GB (Physical visible: 47.92 GB)                               |
+-------------------------------------------------+---------------------------------+
| GPU 0: NVIDIA GeForce RTX 5060 Ti               | GPU 1: NVIDIA GeForce RTX 2080 Ti|
| Dedicated VRAM: 16.00 GB (GDDR7, 448-512 GB/s)  | Dedicated VRAM: 22.00 GB (GDDR6)|
| Primary Role: Secondary Model / Isolation       | Primary Role: Heavy Model / SFT |
+-------------------------------------------------+---------------------------------+
| Combined Dual-GPU Physical VRAM Ceiling: Strictly 37.9 GB                         |
+-----------------------------------------------------------------------------------+
```

---

## 2. Universal VRAM Footprint Formula

The total physical VRAM required to run any model on the station is given by:

$$V_{\text{total}} = V_{\text{weights}} + V_{\text{KV\_cache}} + V_{\text{recurrent\_states}} + V_{\text{runtime\_overhead}}$$

Where:
- $V_{\text{weights}}$: Size of model weights in VRAM (dependent on parameter count $P$ and bits-per-weight $bpw$):
  $$V_{\text{weights}} \approx P \times \frac{bpw}{8} \times 1.02\quad (\text{accounting for header/padding})$$
- $V_{\text{KV\_cache}}$: Physical size of KV cache:
  $$V_{\text{KV\_cache}} = 2 \times L_{\text{attn}} \times N_{\text{kv\_heads}} \times D_{\text{head}} \times C \times \frac{B_{\text{kv}}}{8}$$
  - $L_{\text{attn}}$: Number of **quadratic attention layers** (for pure Transformers $L_{\text{attn}} = L_{\text{total}}$; for Qwen 3.8 hybrid $L_{\text{attn}} = 16$).
  - $N_{\text{kv\_heads}}$: Number of key-value heads.
  - $D_{\text{head}}$: Head dimension (typically 128).
  - $C$: Context window token count (e.g. 32,768, 65,536, 131,072).
  - $B_{\text{kv}}$: Average bits per KV entry ($16$ for F16, $6.5$ for `q8_0/q5_0`, $5.5$ for `q6_0/q4_0`, $4.0$ for `q4_0/q4_0`).
- $V_{\text{recurrent\_states}}$: Memory for state-space or DeltaNet recurrent states:
  $$V_{\text{recurrent\_states}} = L_{\text{ssm}} \times S_{\text{state}} \times \text{sizeof(FP32)}$$
  *(Note: this is $O(1)$ constant, strictly independent of context length $C$!)*
- $V_{\text{runtime\_overhead}}$: CUDA context, cuBLAS scratchpads, FlashAttention work buffers:
  $$\approx 0.70\text{–}1.10\text{ GB}\quad (\text{scale with batch size and context window}).$$

---

## 3. GPU 0 (RTX 5060 Ti 16 GB) Allocation Matrix

Max physical VRAM budget: **16.00 GB**. Recommended safe runtime ceiling: **14.80 GB** (leaving 1.20 GB OS/WDDM buffer).

### 27B Hybrid Architecture (16 Attn Layers + 48 DeltaNet Layers)

| Target Context | KV Cache (`q6_0/q4_0`) | DeltaNet + CUDA Overhead | Max Allowable Weight Size | Feasible Quantization Schemes |
| :--- | :--- | :--- | :--- | :--- |
| **32K (32,768)** | 0.74 GB | 0.85 GB | **13.21 GB** | `Q4_K_M` (15.65 GB exceeds, needs Q3_K_L ~12.8 GB) |
| **64K (65,536)** | 1.48 GB | 0.90 GB | **12.42 GB** | RCO `IQ3_S-mtp` (12.12 GB) |
| **128K (131,072)** | 2.95 GB | 1.02 GB | **10.83 GB** | RCO `IQ3_XXS-mtp` (10.44 GB) ✅ |

---

## 4. GPU 1 (RTX 2080 Ti 22 GB) Allocation Matrix

Max physical VRAM budget: **22.00 GB**. Recommended safe runtime ceiling: **20.50 GB**.

### 35B Architecture (e.g. Ornith 1.5-35B Full Attention, 40 Layers)

| Target Context | KV Cache (`q8_0/q5_0`) | Overhead | Max Allowable Weight Size | Feasible Quantization Schemes |
| :--- | :--- | :--- | :--- | :--- |
| **16K (16,384)** | 1.09 GB | 0.85 GB | **18.56 GB** | `MTP-19G-ICE` (17.53 GB) ✅ |
| **32K (32,768)** | 2.18 GB | 0.95 GB | **17.37 GB** | `Q3_K_M` (16.8 GB) ✅ |
| **64K (65,536)** | 4.36 GB | 1.10 GB | **15.04 GB** | `IQ3_XXS` (14.2 GB) |

---

## 5. Dual-GPU Concurrent Orchestration Pattern

```text
[ Incoming Agent Task Request ]
           │
           ├──> GPU 0 (RTX 5060 Ti 16 GB)
           │     Model: Qwen3.8-27B-Opus-Distill-v2-RCO-IQ3_XXS-mtp
           │     Weights: 10.44 GB | KV Cache (128K): 2.95 GB | Total: 14.41 GB
           │     Role: Deep Context Inspection, Log Analysis, AST Dumps, Code Diffing
           │
           └──> GPU 1 (RTX 2080 Ti 22 GB)
                 Model: Ornith-1.5-35B-MTP-19G-ICE
                 Weights: 17.53 GB | KV Cache (32K): 2.18 GB | Total: 20.66 GB
                 Role: Code Generation, Execution Supervisor, System Tool Calling
```
Both models run physically resident inside their respective GPUs concurrently with **zero memory bus contention** and **zero VRAM swapping**.
