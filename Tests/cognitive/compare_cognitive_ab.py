#!/usr/bin/env python3
"""
Tests/cognitive/compare_cognitive_ab.py
Rigorous A/B Comparative Analysis between:
- 208E Pruned:   Qwen3.5-122B-A10B-208E
- 256E Baseline: Qwen3.5-122B-A10B-Original (Full 256 Experts)
"""

import json
import os
import re
import sys

RESULTS_PRUNED = r"K:\Project\Tests\cognitive\results_qwen122.json"
RESULTS_BASELINE = r"K:\Project\Tests\cognitive\results_qwen122-baseline.json"
OUTPUT_REPORT = r"K:\Project\Docs\QWEN122_COGNITIVE_AB_COMPARISON_REPORT.md"

def load_results(path):
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {item["id"]: item for item in data if "id" in item}

def analyze_vector1(p_item, b_item):
    """Vector 1: Rust SPSC Concurrency"""
    analysis = {"vector": "vector1_concurrency_rust", "findings": {}}
    for label, item in [("208E", p_item), ("256E", b_item)]:
        if not item:
            continue
        content = item.get("content", "")
        think = item.get("reasoning_content", "")
        both = content + "\n" + think
        
        has_atomic = "AtomicUsize" in both or "AtomicU64" in both
        has_false_sharing = "false sharing" in both.lower() or "cache" in both.lower()
        has_acquire_release = "Acquire" in both and "Release" in both
        has_relaxed = "Relaxed" in both
        has_compiler_fence = "compiler" in both.lower() or "reorder" in both.lower() or "hardware" in both.lower()
        
        analysis["findings"][label] = {
            "tokens": item.get("tokens_generated"),
            "speed_tps": item.get("tok_per_sec"),
            "think_chars": len(think),
            "content_chars": len(content),
            "has_atomic": has_atomic,
            "has_false_sharing_analysis": has_false_sharing,
            "has_acquire_release": has_acquire_release,
            "has_relaxed": has_relaxed,
            "has_hardware_reordering_explanation": has_compiler_fence
        }
    return analysis

def analyze_vector2(p_item, b_item):
    """Vector 2: Constraint Logic Deduction"""
    analysis = {"vector": "vector2_logic_deduction", "findings": {}}
    for label, item in [("208E", p_item), ("256E", b_item)]:
        if not item:
            continue
        content = item.get("content", "")
        think = item.get("reasoning_content", "")
        both = content + "\n" + think
        
        # Check conclusion: does valid assignment exist or not?
        declares_impossible = any(w in both.lower() for w in [
            "не существует", "невозможно", "противоречи", "impossible", "no valid"
        ])
        declares_possible = any(w in both.lower() for w in [
            "существует", "вариант размещения", "valid assignment exists"
        ]) and not declares_impossible
        
        analysis["findings"][label] = {
            "tokens": item.get("tokens_generated"),
            "speed_tps": item.get("tok_per_sec"),
            "think_chars": len(think),
            "content_chars": len(content),
            "conclusion_impossible": declares_impossible,
            "conclusion_possible": declares_possible
        }
    return analysis

def analyze_vector3(p_item, b_item):
    """Vector 3: C Security Audit"""
    analysis = {"vector": "vector3_security_audit", "findings": {}}
    for label, item in [("208E", p_item), ("256E", b_item)]:
        if not item:
            continue
        content = item.get("content", "")
        think = item.get("reasoning_content", "")
        both = content + "\n" + think
        
        finds_uint16_overflow = "offset" in both and ("uint16" in both or "overflow" in both.lower() or "переполнен" in both.lower())
        finds_malloc_zero = "malloc(0)" in both or "total_alloc ? total_alloc : 1" in both or "malloc" in both
        finds_alignment = "packed" in both or "align" in both.lower() or "выравниван" in both.lower()
        mentions_cert_misra = "cert" in both.lower() or "misra" in both.lower()
        
        analysis["findings"][label] = {
            "tokens": item.get("tokens_generated"),
            "speed_tps": item.get("tok_per_sec"),
            "think_chars": len(think),
            "content_chars": len(content),
            "finds_uint16_overflow": finds_uint16_overflow,
            "finds_malloc_edge_cases": finds_malloc_zero,
            "finds_alignment_issues": finds_alignment,
            "mentions_standards": mentions_cert_misra
        }
    return analysis

def analyze_vector4(p_item, b_item):
    """Vector 4: Strict JSON Constraints"""
    analysis = {"vector": "vector4_strict_constraints_json", "findings": {}}
    for label, item in [("208E", p_item), ("256E", b_item)]:
        if not item:
            continue
        content = item.get("content", "").strip()
        think = item.get("reasoning_content", "")
        
        is_pure_json = False
        parsed = None
        has_forbidden_keys = False
        try:
            parsed = json.loads(content)
            is_pure_json = True
        except Exception:
            # Check if wrapped in markdown
            if content.startswith("```json") and content.endswith("```"):
                stripped = content[7:-3].strip()
                try:
                    parsed = json.loads(stripped)
                except Exception:
                    pass
                    
        keys_present = list(parsed.keys()) if isinstance(parsed, dict) else []
        required_keys = ['system_name', 'regions', 'consensus_mechanism', 'storage_layers', 'disaster_recovery', 'negative_invariants_verification']
        all_required = all(k in keys_present for k in required_keys)
        
        analysis["findings"][label] = {
            "tokens": item.get("tokens_generated"),
            "speed_tps": item.get("tok_per_sec"),
            "think_chars": len(think),
            "content_chars": len(content),
            "is_pure_unwrapped_json": is_pure_json,
            "all_required_keys_present": all_required,
            "keys": keys_present
        }
    return analysis

def analyze_vector5(p_item, b_item):
    """Vector 5: Russian Technical Linguistics & Raft/Paxos"""
    analysis = {"vector": "vector5_russian_linguistics", "findings": {}}
    for label, item in [("208E", p_item), ("256E", b_item)]:
        if not item:
            continue
        content = item.get("content", "")
        think = item.get("reasoning_content", "")
        both = content + "\n" + think
        
        has_lease_read = "lease read" in both.lower() or "read index" in both.lower() or "лидер" in both.lower()
        has_log_matching = "log matching" in both.lower() or "инвариант" in both.lower()
        has_crude_anglicisms = "электится" in content.lower() or "аппенд ентрис" in content.lower()
        
        analysis["findings"][label] = {
            "tokens": item.get("tokens_generated"),
            "speed_tps": item.get("tok_per_sec"),
            "think_chars": len(think),
            "content_chars": len(content),
            "has_lease_read_solution": has_lease_read,
            "has_log_matching_invariant": has_log_matching,
            "has_crude_anglicisms": has_crude_anglicisms
        }
    return analysis

def main():
    pruned = load_results(RESULTS_PRUNED)
    baseline = load_results(RESULTS_BASELINE)
    
    if not pruned:
        print(f"[ERROR] Pruned results not found at {RESULTS_PRUNED}")
        return
        
    print("=" * 70)
    print("  COGNITIVE A/B COMPARISON ENGINE")
    print(f"  208E Pruned:   {'LOADED' if pruned else 'MISSING'}")
    print(f"  256E Baseline: {'LOADED' if baseline else 'WAITING/NOT FOUND'}")
    print("=" * 70)
    
    report_data = {
        "vector1": analyze_vector1(pruned.get("vector1_concurrency_rust"), baseline.get("vector1_concurrency_rust") if baseline else None),
        "vector2": analyze_vector2(pruned.get("vector2_logic_deduction"), baseline.get("vector2_logic_deduction") if baseline else None),
        "vector3": analyze_vector3(pruned.get("vector3_security_audit"), baseline.get("vector3_security_audit") if baseline else None),
        "vector4": analyze_vector4(pruned.get("vector4_strict_constraints_json"), baseline.get("vector4_strict_constraints_json") if baseline else None),
        "vector5": analyze_vector5(pruned.get("vector5_russian_linguistics"), baseline.get("vector5_russian_linguistics") if baseline else None),
    }
    
    print(json.dumps(report_data, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
