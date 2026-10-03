"""
Model Forge: Quantization Pipeline Orchestrator
Automates invocation of ik_llama\\bin\\llama-quantize.exe with custom RCO/UD maps,
imatrix validation, dry-run safety gates, and physical artifact verification.
"""

import os
import sys
import time
import shutil
import argparse
import subprocess

DEFAULT_BINARY = r'K:\Project\ik_llama\bin\llama-quantize.exe'

def format_bytes(n: int) -> str:
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if n < 1024.0:
            return f"{n:.2f} {unit}"
        n /= 1024.0
    return f"{n:.2f} PB"

def run_quantization(
    binary: str,
    src_path: str,
    dst_path: str,
    imatrix_path: str,
    rules_file_or_string: str,
    dry_run: bool = False,
    allow_requantize: bool = False,
    ignore_imatrix_rules: bool = True,
    ftype: str = 'IQ3_XXS'
) -> bool:
    if not os.path.exists(binary):
        print(f"ERROR: llama-quantize binary not found: {binary}")
        return False

    if not os.path.exists(src_path):
        print(f"ERROR: Source model not found: {src_path}")
        return False

    if imatrix_path and not os.path.exists(imatrix_path):
        print(f"ERROR: Importance matrix file not found: {imatrix_path}")
        return False

    # Resolve rules string
    if os.path.exists(rules_file_or_string):
        with open(rules_file_or_string, 'r', encoding='utf-8') as f:
            rules_str = f.read().strip()
    else:
        rules_str = rules_file_or_string.strip()

    if not rules_str:
        print("ERROR: Quantization rules cannot be empty.")
        return False

    if len(rules_str) > 32000:
        print(f"WARNING: Rules string length ({len(rules_str)}) approaches Windows 32,767 CLI ceiling!")

    # Check disk space if not dry-run
    if not dry_run:
        dst_dir = os.path.dirname(os.path.abspath(dst_path))
        os.makedirs(dst_dir, exist_ok=True)
        drive = os.path.splitdrive(dst_dir)[0]
        usage = shutil.disk_usage(drive if drive else '.')
        free_gb = usage.free / (1024 ** 3)
        # We need at least ~14 GB free for a 27B model
        if free_gb < 12.0:
            print(f"ERROR: Target disk {drive} has only {free_gb:.2f} GB free. At least 12.0 GB required.")
            return False

    cmd = [binary]

    if dry_run:
        cmd.append('--dry-run')
    if allow_requantize:
        cmd.append('--allow-requantize')
    if ignore_imatrix_rules:
        cmd.append('--ignore-imatrix-rules')
    if imatrix_path:
        cmd.extend(['--imatrix', imatrix_path])

    cmd.extend(['--custom-q', rules_str])
    cmd.extend([src_path, dst_path, ftype])

    print("=" * 70)
    print("MODEL FORGE QUANTIZATION EXECUTION")
    print(f"Mode: {'DRY RUN' if dry_run else 'PHYSICAL QUANTIZATION'}")
    print(f"Source: {src_path} ({format_bytes(os.path.getsize(src_path))})")
    print(f"Destination: {dst_path}")
    if imatrix_path:
        print(f"Imatrix: {imatrix_path} ({format_bytes(os.path.getsize(imatrix_path))})")
    print(f"Rules length: {len(rules_str)} chars")
    print("=" * 70)

    start_time = time.time()
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            encoding='utf-8',
            errors='replace'
        )

        for line in proc.stdout:
            try:
                sys.stdout.write(line)
                sys.stdout.flush()
            except UnicodeEncodeError:
                sys.stdout.write(line.encode('ascii', errors='replace').decode('ascii'))
                sys.stdout.flush()

        proc.wait()
        elapsed = time.time() - start_time

        if proc.returncode != 0:
            print(f"\n[FAIL] llama-quantize exited with return code: {proc.returncode}")
            return False

        print("\n" + "=" * 70)
        print(f"[SUCCESS] Quantization finished in {elapsed:.1f}s (Return code: 0).")
        if not dry_run and os.path.exists(dst_path):
            final_size = os.path.getsize(dst_path)
            print(f"Generated artifact: {dst_path}")
            print(f"Physical file size: {format_bytes(final_size)} ({final_size / (1024**3):.2f} GiB)")
        print("=" * 70)
        return True

    except Exception as e:
        print(f"Exception during quantization: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description='Model Forge Quantization Runner')
    parser.add_argument('--src', type=str, required=True, help='Path to source GGUF')
    parser.add_argument('--dst', type=str, required=True, help='Path to output GGUF')
    parser.add_argument('--imatrix', type=str, default='', help='Path to imatrix GGUF')
    parser.add_argument('--rules', type=str, required=True, help='Path to rules txt file or raw string')
    parser.add_argument('--binary', type=str, default=DEFAULT_BINARY, help='Path to llama-quantize.exe')
    parser.add_argument('--dry-run', action='store_true', help='Run dry-run without writing output')
    parser.add_argument('--allow-requantize', action='store_true', help='Allow quantizing an already quantized model')
    parser.add_argument('--no-ignore-imatrix-rules', action='store_true', help='Do not pass --ignore-imatrix-rules')
    parser.add_argument('--ftype', type=str, default='IQ3_XXS', help='Fallback base quantization type (default: IQ3_XXS)')
    args = parser.parse_args()

    success = run_quantization(
        binary=args.binary,
        src_path=args.src,
        dst_path=args.dst,
        imatrix_path=args.imatrix,
        rules_file_or_string=args.rules,
        dry_run=args.dry_run,
        allow_requantize=args.allow_requantize,
        ignore_imatrix_rules=not args.no_ignore_imatrix_rules,
        ftype=args.ftype
    )

    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()
