import os
import struct
import json
import shutil

def unpack_asar(asar_path, dest_dir):
    with open(asar_path, 'rb') as f:
        f.seek(4)
        header_size = struct.unpack('<I', f.read(4))[0]
        f.seek(16)
        header_json = f.read(header_size - 8).decode('utf-8')
        header = json.loads(header_json)
        base_offset = 16 + header_size
        
        def extract(d, curr_path):
            for k, v in d.get('files', {}).items():
                target = os.path.join(curr_path, k)
                if 'files' in v:
                    os.makedirs(target, exist_ok=True)
                    extract(v, target)
                elif not v.get('unpacked', False):
                    f.seek(base_offset + int(v['offset']))
                    data = f.read(int(v['size']))
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    with open(target, 'wb') as out_f:
                        out_f.write(data)
                        
        extract(header, dest_dir)
    return header

def pack_asar(src_dir, output_asar, original_header=None):
    # Walk directory to collect all files in canonical order
    files_tree = {}
    files_order = []
    
    for root, dirs, files in os.walk(src_dir):
        rel_root = os.path.relpath(root, src_dir).replace('\\', '/')
        if rel_root == '.':
            curr_dict = files_tree
        else:
            curr_dict = files_tree
            for part in rel_root.split('/'):
                curr_dict = curr_dict.setdefault('files', {}).setdefault(part, {})
        
        for file in files:
            full_path = os.path.join(root, file)
            rel_file = os.path.relpath(full_path, src_dir).replace('\\', '/')
            files_order.append((rel_file, full_path))

    # Check original header for unpacked files
    unpacked_set = set()
    if original_header:
        def find_unpacked(d, prefix=''):
            for k, v in d.get('files', {}).items():
                p = f"{prefix}/{k}" if prefix else k
                if 'files' in v:
                    find_unpacked(v, p)
                elif v.get('unpacked', False):
                    unpacked_set.add(p)
        find_unpacked(original_header)

    # Build header metadata and offsets
    curr_offset = 0
    header_files = {}
    
    for rel_file, full_path in files_order:
        size = os.path.getsize(full_path)
        is_unpacked = rel_file in unpacked_set
        
        parts = rel_file.split('/')
        curr = header_files
        for part in parts[:-1]:
            curr = curr.setdefault('files', {}).setdefault(part, {})
        
        entry = {'size': size}
        if is_unpacked:
            entry['unpacked'] = True
        else:
            entry['offset'] = str(curr_offset)
            curr_offset += size
            
        curr.setdefault('files', {})[parts[-1]] = entry

    header_dict = header_files
    header_json_bytes = json.dumps(header_dict, separators=(',', ':')).encode('utf-8')
    
    # 4-byte align the header
    align = 4 - (len(header_json_bytes) % 4)
    if align < 4:
        header_json_bytes += b'\x00' * align
        
    header_json_size = len(header_json_bytes)
    header_size = header_json_size + 8
    total_header_size = header_size + 4

    with open(output_asar, 'wb') as f:
        # Write ASAR 16-byte prefix
        f.write(struct.pack('<I', 4))
        f.write(struct.pack('<I', total_header_size))
        f.write(struct.pack('<I', header_size))
        f.write(struct.pack('<I', header_json_size))
        f.write(header_json_bytes)
        
        # Write packed file bodies
        for rel_file, full_path in files_order:
            if rel_file not in unpacked_set:
                with open(full_path, 'rb') as in_f:
                    shutil.copyfileobj(in_f, f)

if __name__ == '__main__':
    src_asar = r'C:\Users\User\AppData\Local\Programs\antigravity\resources\app.asar'
    temp_dir = r'K:\Project\Temp\asar_unpack_test'
    test_out = r'K:\Project\Temp\app_repacked.asar'
    
    if os.path.exists(temp_dir): shutil.rmtree(temp_dir)
    os.makedirs(temp_dir, exist_ok=True)
    
    orig_header = unpack_asar(src_asar, temp_dir)
    print('Unpacked successfully. Packing back...')
    pack_asar(temp_dir, test_out, orig_header)
    print(f'Repacked: orig={os.path.getsize(src_asar)} new={os.path.getsize(test_out)}')
