"""
Model Forge: RCO Allocation to llama-quantize --custom-q Converter
Parses ISTA-DASLab GSQ-RCO allocation maps and converts them into
validated, compact regex arguments for ik_llama\\bin\\llama-quantize.exe.
"""

import sys
import os
import re
import urllib.request
import argparse

# Exact casing rules enforced by ik_llama / GGML
TYPE_MAPPING = {
    'F32': 'f32',
    'BF16': 'bf16',
    'F16': 'f16',
    'IQ1_S': 'iq1_s',
    'IQ1_M': 'iq1_m',
    'IQ2_XXS': 'iq2_xxs',
    'IQ2_XS': 'iq2_xs',
    'IQ2_S': 'iq2_s',
    'IQ2_M': 'iq2_m',
    'IQ3_XXS': 'iq3_xxs',
    'IQ3_XS': 'iq3_xs',
    'IQ3_S': 'iq3_s',
    'IQ3_M': 'iq3_m',
    'IQ4_XS': 'iq4_xs',
    'IQ4_NL': 'iq4_nl',
    'Q2_K': 'q2_K',
    'Q3_K': 'q3_K',
    'Q3_K_S': 'q3_K',
    'Q3_K_M': 'q3_K',
    'Q3_K_L': 'q3_K',
    'Q4_K': 'q4_K',
    'Q4_K_S': 'q4_K',
    'Q4_K_M': 'q4_K',
    'Q5_K': 'q5_K',
    'Q5_K_S': 'q5_K',
    'Q5_K_M': 'q5_K',
    'Q6_K': 'q6_K',
    'Q8_0': 'q8_0',
}

def load_allocation(file_or_url: str) -> dict:
    if file_or_url.startswith('http://') or file_or_url.startswith('https://'):
        req = urllib.request.Request(file_or_url, headers={'User-Agent': 'Mozilla/5.0'})
        content = urllib.request.urlopen(req).read().decode('utf-8')
        lines = content.splitlines()
    else:
        with open(file_or_url, 'r', encoding='utf-8') as f:
            lines = f.readlines()

    allocations = {}
    for line in lines:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        parts = line.split(':')
        if len(parts) == 2:
            t_name = parts[0].strip()
            raw_type = parts[1].strip()
            mapped_type = TYPE_MAPPING.get(raw_type, raw_type.lower())
            allocations[t_name] = mapped_type
    return allocations

def build_grouped_regex_rules(allocations: dict, preserve_critical: bool = False) -> list:
    grouped = {}
    special = []

    for tensor_name, qtype in allocations.items():
        # F32 and BF16 norms/biases are naturally preserved by llama-quantize
        if qtype in ('f32', 'bf16'):
            continue

        # Optional preservation: elevate critical tensors
        if preserve_critical:
            if tensor_name == 'output.weight':
                qtype = 'q6_K'
            elif tensor_name == 'token_embd.weight':
                qtype = 'q4_K'
            elif 'nextn' in tensor_name:
                qtype = 'q6_K'

        m = re.match(r'blk\.(\d+)\.(.+)', tensor_name)
        if m:
            l_num, suffix = int(m.group(1)), m.group(2)
            grouped.setdefault((suffix, qtype), []).append(l_num)
        else:
            special.append(f'{tensor_name}={qtype}')

    rules = []
    for (suffix, qtype), layers in sorted(grouped.items()):
        layers_sorted = sorted(layers)
        if len(layers_sorted) == 65:
            rules.append(f'blk\\..*\\.{suffix}={qtype}')
        else:
            layers_str = '|'.join(str(l) for l in layers_sorted)
            rules.append(f'blk\\.({layers_str})\\.{suffix}={qtype}')

    rules.extend(special)
    return rules

def main():
    parser = argparse.ArgumentParser(description='Convert RCO map to custom-q regexes')
    parser.add_argument('--input', type=str, required=True, help='Path or URL to rco-allocation.txt')
    parser.add_argument('--preserve-critical', action='store_true', help='Elevate output.weight to Q6_K and token_embd to Q4_K')
    parser.add_argument('--output-rules', type=str, default='', help='Path to save raw custom-q string')
    args = parser.parse_args()

    allocations = load_allocation(args.input)
    print(f'Loaded {len(allocations)} tensor allocations.')

    rules = build_grouped_regex_rules(allocations, preserve_critical=args.preserve_critical)
    arg_string = ','.join(rules)

    print(f'Generated {len(rules)} grouped regex rules.')
    print(f'Total command-line string length: {len(arg_string)} characters (Windows limit is 32,767).')

    if args.output_rules:
        os.makedirs(os.path.dirname(os.path.abspath(args.output_rules)), exist_ok=True)
        with open(args.output_rules, 'w', encoding='utf-8') as f:
            f.write(arg_string)
        print(f'Rules saved to: {args.output_rules}')

    print('\nSample rules:')
    for r in rules[:5]:
        print(' ', r)

if __name__ == '__main__':
    main()
