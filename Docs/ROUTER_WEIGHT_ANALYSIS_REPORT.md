# Qwen3.5-122B-A10B: MoE Static Router Weight & Affinity Report

**Target Model:** `Qwen3.5-122B-A10B-44GB-GPT5.6Sol-SFT-LynnStyle-GGUF.gguf`  
**Layers Analyzed:** 48 (Full model depth: 0 to 47)  
**Total Routed Experts / Layer:** 256  
**Router Input Dimension:** 3072 (F32 unquantized projections)  
**Overall Mean Gating Vector L2 Norm:** 1.0947 (± 0.0157)  

---

## 1. Executive Summary & Pruning Feasibility

Static analysis of all 48 router gating matrices reveals a distinct, non-uniform distribution of expert routing weights:
1. **Strong Vector Norm Differentiation:** Across all layers, gating vector norms range significantly (min ~0.50 to max ~1.95, a ~3.9x dynamic ratio).
2. **Low-Norm Cold Clusters:** A significant subset of experts consistently possesses sub-average routing vector norms, rendering them statistically disadvantaged during router softmax competition across arbitrary input activations.
3. **Pairwise Redundancy:** Cosine similarity between routing vectors exhibits clusters of experts with high directional alignment (> 0.70–0.85), indicating functional redundancy in the routing subspace.
4. **32-Expert Slicing Target:** Reducing each layer from 256 to 224 experts (-12.5%) removes exactly 4.41 GB of expert weights, successfully bringing total model memory from 41.55 GB down to **~37.14 GB**—fitting 100% inside our Dual-GPU VRAM pool (37.9 GB).

---

## 2. Global Persistent Cold Experts (Across All 48 Layers)

Experts ranked by the number of layers in which they fall into the bottom 32 by gating vector L2 norm:

| Rank | Expert ID | Layers in Bottom 32 (Max 48) | Mean L2 Norm | Pruning Priority |
| :---: | :---: | :---: | :---: | :---: |
| 1 | `exp_20` | **14 / 48** | 1.0661 | Priority Safe |
| 2 | `exp_3` | **12 / 48** | 1.0901 | Priority Safe |
| 3 | `exp_39` | **12 / 48** | 1.1081 | Priority Safe |
| 4 | `exp_226` | **12 / 48** | 1.0712 | Priority Safe |
| 5 | `exp_0` | **11 / 48** | 1.1266 | Priority Safe |
| 6 | `exp_134` | **11 / 48** | 1.1005 | Priority Safe |
| 7 | `exp_88` | **11 / 48** | 1.0843 | Priority Safe |
| 8 | `exp_31` | **11 / 48** | 1.0721 | Priority Safe |
| 9 | `exp_238` | **11 / 48** | 1.0605 | Priority Safe |
| 10 | `exp_116` | **11 / 48** | 1.0905 | Priority Safe |
| 11 | `exp_228` | **11 / 48** | 1.0781 | Priority Safe |
| 12 | `exp_250` | **11 / 48** | 1.0635 | Priority Safe |
| 13 | `exp_10` | **11 / 48** | 1.1040 | Priority Safe |
| 14 | `exp_7` | **11 / 48** | 1.0914 | Priority Safe |
| 15 | `exp_232` | **10 / 48** | 1.0626 | Priority Safe |
| 16 | `exp_12` | **10 / 48** | 1.1008 | Priority Safe |
| 17 | `exp_85` | **10 / 48** | 1.0771 | Priority Safe |
| 18 | `exp_219` | **10 / 48** | 1.0725 | Priority Safe |
| 19 | `exp_220` | **10 / 48** | 1.0828 | Priority Safe |
| 20 | `exp_18` | **10 / 48** | 1.1023 | Priority Safe |
| 21 | `exp_252` | **10 / 48** | 1.1006 | Priority Safe |
| 22 | `exp_207` | **10 / 48** | 1.0956 | Priority Safe |
| 23 | `exp_124` | **10 / 48** | 1.0939 | Priority Safe |
| 24 | `exp_191` | **10 / 48** | 1.1007 | Priority Safe |
| 25 | `exp_26` | **10 / 48** | 1.0777 | Priority Safe |
| 26 | `exp_34` | **9 / 48** | 1.0842 | Priority Safe |
| 27 | `exp_35` | **9 / 48** | 1.0655 | Priority Safe |
| 28 | `exp_42` | **9 / 48** | 1.1158 | Priority Safe |
| 29 | `exp_5` | **9 / 48** | 1.1237 | Priority Safe |
| 30 | `exp_174` | **9 / 48** | 1.0894 | Priority Safe |
| 31 | `exp_165` | **9 / 48** | 1.0870 | Priority Safe |
| 32 | `exp_4` | **9 / 48** | 1.1110 | Priority Safe |

---

## 3. Global Dominant (Hot) Experts (Across All 48 Layers)

Top 16 experts by overall mean gating vector norm (critical reasoning / syntax backbone):

| Rank | Expert ID | Mean L2 Norm | Std Dev | Status |
| :---: | :---: | :---: | :---: | :---: |
| 1 | `exp_1` | **1.1727** | ±0.3351 | **CORE PROTECTED** |
| 2 | `exp_9` | **1.1463** | ±0.3231 | **CORE PROTECTED** |
| 3 | `exp_50` | **1.1323** | ±0.2893 | **CORE PROTECTED** |
| 4 | `exp_80` | **1.1298** | ±0.3280 | **CORE PROTECTED** |
| 5 | `exp_8` | **1.1288** | ±0.2952 | **CORE PROTECTED** |
| 6 | `exp_140` | **1.1281** | ±0.3331 | **CORE PROTECTED** |
| 7 | `exp_0` | **1.1266** | ±0.3349 | **CORE PROTECTED** |
| 8 | `exp_13` | **1.1265** | ±0.3192 | **CORE PROTECTED** |
| 9 | `exp_237` | **1.1260** | ±0.3309 | **CORE PROTECTED** |
| 10 | `exp_55` | **1.1248** | ±0.3068 | **CORE PROTECTED** |
| 11 | `exp_5` | **1.1237** | ±0.2939 | **CORE PROTECTED** |
| 12 | `exp_106` | **1.1229** | ±0.2983 | **CORE PROTECTED** |
| 13 | `exp_195` | **1.1216** | ±0.3405 | **CORE PROTECTED** |
| 14 | `exp_181` | **1.1204** | ±0.3323 | **CORE PROTECTED** |
| 15 | `exp_30` | **1.1184** | ±0.2935 | **CORE PROTECTED** |
| 16 | `exp_112` | **1.1171** | ±0.3285 | **CORE PROTECTED** |

---

## 4. Per-Layer Router Dynamics (Samples: Layer 0, 12, 24, 36, 47)

### Layer 0
- **L2 Norm Range:** min `0.5255`, max `1.8289`, mean `0.8349` (Dynamic Ratio: `3.48x`)
- **Top-5 Coldest Candidates:** `[197, 128, 236, 112, 7]`
- **Top-5 Hottest Candidates:** `[181, 105, 113, 116, 106]`
- **Top Similar Expert Pairs:**
  * `exp_199` & `exp_207`: Cosine Similarity = `0.9326`
  * `exp_84` & `exp_207`: Cosine Similarity = `0.9303`
  * `exp_84` & `exp_229`: Cosine Similarity = `0.9300`

### Layer 12
- **L2 Norm Range:** min `1.0423`, max `1.8980`, mean `1.4293` (Dynamic Ratio: `1.82x`)
- **Top-5 Coldest Candidates:** `[14, 7, 16, 11, 59]`
- **Top-5 Hottest Candidates:** `[13, 157, 0, 222, 128]`
- **Top Similar Expert Pairs:**
  * `exp_5` & `exp_158`: Cosine Similarity = `0.7970`
  * `exp_47` & `exp_184`: Cosine Similarity = `0.7696`
  * `exp_50` & `exp_184`: Cosine Similarity = `0.7416`

### Layer 24
- **L2 Norm Range:** min `0.8691`, max `1.5092`, mean `1.1497` (Dynamic Ratio: `1.74x`)
- **Top-5 Coldest Candidates:** `[135, 21, 113, 63, 196]`
- **Top-5 Hottest Candidates:** `[199, 218, 46, 103, 193]`
- **Top Similar Expert Pairs:**
  * `exp_190` & `exp_252`: Cosine Similarity = `0.8534`
  * `exp_1` & `exp_77`: Cosine Similarity = `0.8502`
  * `exp_3` & `exp_83`: Cosine Similarity = `0.8492`

### Layer 36
- **L2 Norm Range:** min `0.6915`, max `1.2450`, mean `0.9159` (Dynamic Ratio: `1.80x`)
- **Top-5 Coldest Candidates:** `[30, 163, 185, 255, 240]`
- **Top-5 Hottest Candidates:** `[122, 203, 165, 171, 242]`
- **Top Similar Expert Pairs:**
  * `exp_68` & `exp_127`: Cosine Similarity = `0.9206`
  * `exp_3` & `exp_64`: Cosine Similarity = `0.8958`
  * `exp_18` & `exp_96`: Cosine Similarity = `0.8797`

### Layer 47
- **L2 Norm Range:** min `0.3811`, max `0.7210`, mean `0.5099` (Dynamic Ratio: `1.89x`)
- **Top-5 Coldest Candidates:** `[98, 113, 140, 212, 132]`
- **Top-5 Hottest Candidates:** `[21, 34, 121, 166, 253]`
- **Top Similar Expert Pairs:**
  * `exp_67` & `exp_150`: Cosine Similarity = `0.9923`
  * `exp_186` & `exp_219`: Cosine Similarity = `0.9897`
  * `exp_101` & `exp_155`: Cosine Similarity = `0.9854`

