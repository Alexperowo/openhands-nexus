import os
import sys
import json
import glob
import re

HEAD_DIR = r"K:\Project\LLM-tests\Heavy-Model-Comparison\head-to-head"
OUT_HEAD_MD = r"K:\Project\LLM-tests\Heavy-Model-Comparison\HEAD-TO-HEAD.md"
OUT_DECISION_MD = r"K:\Project\LLM-tests\Heavy-Model-Comparison\FINAL-HEAVY-DECISION.md"

MODELS = [
    {"key": "laguna_2_1", "name": "Laguna-S-2.1", "arch": "Dense 40L (poolside)", "offload": "18/40 (44%)", "ctx": "16K-96K"},
    {"key": "qwen_122b", "name": "Qwen3.5-122B-LynnStyle", "arch": "MoE 48L (ik_llama)", "offload": "18/48 (43%)", "ctx": "16K-96K"},
    {"key": "qwen3_next_80b", "name": "Qwen3-Next-80B-Thinking", "arch": "MoE 48L (ik_llama)", "offload": "26/48 (62%)", "ctx": "16K-96K"},
    {"key": "qwen_27b_opus", "name": "Qwen3.8-27B-Opus (Baseline)", "arch": "Dense 65L (ik_llama)", "offload": "65/65 (100%)", "ctx": "16K-96K"}
]

TASKS = [
    {"id": 1, "name": "Task 1: Distributed Architecture Plan"},
    {"id": 2, "name": "Task 2: Code Audit (Seeded Concurrency Bugs)"},
    {"id": 3, "name": "Task 3: Bad Architecture Review"},
    {"id": 4, "name": "Task 4: Difficult Debugging (Pool Exhaustion)"},
    {"id": 5, "name": "Task 5: Final PR Review (Senior Staff)"}
]

def load_all_data():
    data = {}
    for m in MODELS:
        m_key = m["key"]
        data[m_key] = {}
        for t in TASKS:
            t_id = t["id"]
            p = os.path.join(HEAD_DIR, f"{m_key}_task_{t_id}.json")
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8") as f:
                    data[m_key][t_id] = json.load(f)
            else:
                data[m_key][t_id] = None
    return data

def main():
    data = load_all_data()
    print("Loaded tournament data for models:", list(data.keys()))
    for m_key, tasks in data.items():
        done_count = sum(1 for v in tasks.values() if v is not None)
        print(f"  {m_key}: {done_count}/5 tasks complete")

if __name__ == "__main__":
    main()
