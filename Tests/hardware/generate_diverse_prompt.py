#!/usr/bin/env python3
"""
Tests/hardware/generate_diverse_prompt.py
Generates non-repeating diverse engineering text from actual files in the repository
to test sparse PLE row lookups without synthetic token repetition.
"""

import os
import sys

def build_diverse_prompt(target_chars: int, output_path: str):
    sources = [
        r"K:\Project\AUDIT_BUNDLE.md",
        r"K:\Project\PERFORMANCE_OPTIMIZATION_REPORT.md",
        r"K:\Project\AGENTS.md",
        r"K:\Project\llama-direct-read\src\llama-context.cpp",
        r"K:\Project\llama-direct-read\src\llama-model.cpp",
        r"K:\Project\llama-direct-read\src\llama-graph.cpp",
        r"K:\Project\llama-direct-read\src\llama-lazy-reader.cpp",
        r"K:\Project\llama-direct-read\ggml\src\ggml.c",
        r"K:\Project\llama-swap\config.yaml",
        r"K:\Project\README.md"
    ]
    
    collected = []
    total_len = 0
    
    for src in sources:
        if os.path.exists(src):
            try:
                with open(src, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                    collected.append(content)
                    total_len += len(content)
                    if total_len >= target_chars:
                        break
            except Exception as e:
                print(f"Error reading {src}: {e}", file=sys.stderr)
                
    full_text = "\n\n".join(collected)
    if len(full_text) > target_chars:
        full_text = full_text[:target_chars]
        
    with open(output_path, "w", encoding="utf-8") as out:
        out.write(full_text)
        
    print(f"Generated {len(full_text)} characters of diverse text to {output_path}")

if __name__ == "__main__":
    chars = int(sys.argv[1]) if len(sys.argv) > 1 else 250000
    out = sys.argv[2] if len(sys.argv) > 2 else r"K:\Project\Tests\hardware\diverse_prompt.txt"
    build_diverse_prompt(chars, out)
