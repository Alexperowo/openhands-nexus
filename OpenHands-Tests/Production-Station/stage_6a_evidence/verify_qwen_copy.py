import hashlib
import json
import time
from pathlib import Path

files = [
    {
        'name': 'Qwen3.8-27B-Opus-Distill-v2-Q4_K_M.gguf',
        'src': r'D:\Project\models\Qwen3.8-27B-Opus-Distill-v2-Q4_K_M.gguf',
        'dst': r'K:\Project\Models\Qwen3.8\Qwen3.8-27B-Opus-Distill-v2-Q4_K_M.gguf'
    },
    {
        'name': 'Qwen3.8-27B-Opus-Distill-v2-mmproj-f16.gguf',
        'src': r'D:\Project\models\Qwen3.8-27B-Opus-Distill-v2-mmproj-f16.gguf',
        'dst': r'K:\Project\Models\Qwen3.8\Qwen3.8-27B-Opus-Distill-v2-mmproj-f16.gguf'
    }
]

def hash_file(path_str):
    h = hashlib.sha256()
    p = Path(path_str)
    size = p.stat().st_size
    t0 = time.time()
    with open(p, 'rb') as f:
        while True:
            chunk = f.read(64 * 1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    elapsed = round(time.time() - t0, 2)
    return h.hexdigest(), size, elapsed

manifest = []
all_matched = True

for item in files:
    src_path = item['src']
    dst_path = item['dst']
    file_name = item['name']
    print(f'Hashing source: {src_path}...')
    src_hash, src_size, src_time = hash_file(src_path)
    print(f'Source SHA256: {src_hash} ({src_size} bytes in {src_time}s)')

    print(f'Hashing destination: {dst_path}...')
    dst_hash, dst_size, dst_time = hash_file(dst_path)
    print(f'Dest SHA256: {dst_hash} ({dst_size} bytes in {dst_time}s)')

    size_match = (src_size == dst_size)
    hash_match = (src_hash == dst_hash)
    matched = size_match and hash_match
    if not matched:
        all_matched = False

    manifest.append({
        'file_name': file_name,
        'source_path': src_path,
        'destination_path': dst_path,
        'source_size': src_size,
        'destination_size': dst_size,
        'size_match': size_match,
        'sha256_source': src_hash,
        'sha256_destination': dst_hash,
        'hash_match': 'YES' if hash_match else 'NO',
        'verified': matched
    })

report = {
    'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ'),
    'all_verified': all_matched,
    'qwen38_copy_complete': all_matched,
    'source_preserved': Path(r'D:\Project\models\Qwen3.8-27B-Opus-Distill-v2-Q4_K_M.gguf').exists(),
    'manifest': manifest
}

out_path = Path(r'K:\Project\OpenHands-Tests\Production-Station\stage_6a_evidence\qwen38_copy_manifest.json')
out_path.write_text(json.dumps(report, indent=2), encoding='utf-8')
print('Manifest written to:', out_path)
print('ALL_VERIFIED:', all_matched)
