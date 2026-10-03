"""
Model Forge: Upstream Checkpoint & Calibration Downloader
Downloads pristine BF16 weights and importance matrices with resuming and disk-space checks.
"""

import os
import sys
import shutil
import argparse
import requests
from tqdm import tqdm

TARGETS = {
    'imatrix-qwen38': {
        'url': 'https://huggingface.co/ISTA-DASLab/Qwen3.8-27B-GSQ-RCO-GGUF/resolve/main/imatrix-qwen3.8-27b.gguf',
        'default_dest': r'K:\Project\model-forge\calibration\imatrix-qwen3.8-27b.gguf',
        'min_free_gb': 0.1,
    },
    'bf16-opus-distill-v2': {
        'url': 'https://huggingface.co/barozp/Qwen3.8-27B-Opus-Distill-v2-GGUF/resolve/main/Qwen3.8-27B-Opus-Distill-v2-BF16.gguf',
        'default_dest': r'D:\Staging\Qwen3.8-27B-Opus-Distill-v2-BF16.gguf',
        'min_free_gb': 56.0,
    }
}

def check_disk_space(target_path: str, required_gb: float) -> bool:
    drive = os.path.splitdrive(os.path.abspath(target_path))[0]
    if not drive:
        drive = '.'
    usage = shutil.disk_usage(drive)
    free_gb = usage.free / (1024 ** 3)
    print(f"Target drive: {drive} | Free space: {free_gb:.2f} GB | Required: {required_gb:.2f} GB")
    return free_gb >= required_gb

def download_file(url: str, dest_path: str, min_free_gb: float):
    os.makedirs(os.path.dirname(os.path.abspath(dest_path)), exist_ok=True)

    if not check_disk_space(dest_path, min_free_gb):
        print(f"ERROR: Insufficient disk space on {dest_path}. Need at least {min_free_gb:.2f} GB.")
        sys.exit(1)

    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    temp_file = dest_path + '.part'
    resume_byte_pos = 0

    if os.path.exists(temp_file):
        resume_byte_pos = os.path.getsize(temp_file)
        headers['Range'] = f'bytes={resume_byte_pos}-'
        print(f"Resuming download from byte offset: {resume_byte_pos:,} ({resume_byte_pos / (1024**3):.2f} GiB)")

    response = requests.get(url, headers=headers, stream=True, timeout=30)
    response.raise_for_status()

    total_size = int(response.headers.get('content-length', 0)) + resume_byte_pos
    mode = 'ab' if resume_byte_pos > 0 else 'wb'

    print(f"Downloading from: {url}")
    print(f"Saving to: {dest_path}")
    print(f"Total file size: {total_size / (1024**3):.2f} GiB")

    chunk_size = 16 * 1024 * 1024  # 16 MB chunks for maximum NVMe throughput
    with open(temp_file, mode) as f, tqdm(
        total=total_size,
        initial=resume_byte_pos,
        unit='B',
        unit_scale=True,
        unit_divisor=1024,
        desc=os.path.basename(dest_path)
    ) as pbar:
        for chunk in response.iter_content(chunk_size=chunk_size):
            if chunk:
                f.write(chunk)
                pbar.update(len(chunk))

    if os.path.exists(dest_path):
        os.remove(dest_path)
    os.rename(temp_file, dest_path)
    print(f"\nDownload completed successfully: {dest_path}")

def main():
    parser = argparse.ArgumentParser(description='Download models and imatrix files for Model Forge')
    parser.add_argument('--target', choices=list(TARGETS.keys()), required=True, help='Target file alias')
    parser.add_argument('--dest', type=str, default='', help='Optional custom destination path')
    args = parser.parse_args()

    cfg = TARGETS[args.target]
    dest = args.dest if args.dest else cfg['default_dest']
    download_file(cfg['url'], dest, cfg['min_free_gb'])

if __name__ == '__main__':
    main()
