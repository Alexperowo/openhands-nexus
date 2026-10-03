"""
Model Forge: GGUF to Binary imatrix.dat Converter
Extracts importance matrices from GGUF containers and writes the native binary
format required by ik_llama and mainline llama.cpp llama-quantize.exe.
"""

import os
import sys
import struct
import argparse
import numpy as np

def convert_gguf_to_dat(gguf_path: str, dat_path: str):
    if not os.path.exists(gguf_path):
        print(f"ERROR: File not found: {gguf_path}")
        sys.exit(1)

    with open(gguf_path, 'rb') as f:
        magic = f.read(4)
        if magic != b'GGUF':
            print(f"ERROR: {gguf_path} is not a valid GGUF file (magic={magic})")
            sys.exit(1)

        version = struct.unpack('<I', f.read(4))[0]
        n_tensors = struct.unpack('<Q', f.read(8))[0]
        n_kv = struct.unpack('<Q', f.read(8))[0]

        meta = {}
        alignment = 32
        for _ in range(n_kv):
            k_len = struct.unpack('<Q', f.read(8))[0]
            k = f.read(k_len).decode('utf-8')
            v_type = struct.unpack('<I', f.read(4))[0]
            if v_type == 8:
                s_len = struct.unpack('<Q', f.read(8))[0]
                val = f.read(s_len).decode('utf-8')
            elif v_type == 4:
                val = struct.unpack('<I', f.read(4))[0]
            elif v_type == 9:
                arr_type = struct.unpack('<I', f.read(4))[0]
                arr_len = struct.unpack('<Q', f.read(8))[0]
                val = []
                for _ in range(arr_len):
                    if arr_type == 8:
                        slen = struct.unpack('<Q', f.read(8))[0]
                        val.append(f.read(slen).decode('utf-8'))
            else:
                val = None
            meta[k] = val
            if k == 'general.alignment':
                alignment = val

        tensors = {}
        for i in range(n_tensors):
            name_len = struct.unpack('<Q', f.read(8))[0]
            t_name = f.read(name_len).decode('utf-8')
            n_dims = struct.unpack('<I', f.read(4))[0]
            dims = [struct.unpack('<Q', f.read(8))[0] for _ in range(n_dims)]
            t_type = struct.unpack('<I', f.read(4))[0]
            offset = struct.unpack('<Q', f.read(8))[0]
            tensors[t_name] = {'dims': dims, 'type': t_type, 'offset': offset}

        cur = f.tell()
        pad = (alignment - (cur % alignment)) % alignment
        data_start = cur + pad

        # Collect paired tensors: (base_name, in_sum2_meta, counts_meta)
        pairs = {}
        for name in tensors:
            if name.endswith('.in_sum2'):
                base = name[:-8]
                counts_name = base + '.counts'
                if counts_name in tensors:
                    pairs[base] = (tensors[name], tensors[counts_name])

        print(f"GGUF parsed: {len(tensors)} tensors total, {len(pairs)} base imatrix tensors identified.")
        chunk_count = meta.get('imatrix.chunk_count', 1000)
        datasets = meta.get('imatrix.datasets', ['imatrix_dataset'])
        dataset_name = datasets[0] if isinstance(datasets, list) and datasets else 'imatrix_dataset'

        os.makedirs(os.path.dirname(os.path.abspath(dat_path)), exist_ok=True)
        with open(dat_path, 'wb') as out:
            # 1. Number of entries
            n_entries = len(pairs)
            out.write(struct.pack('<i', n_entries))

            # 2. For each entry
            for base_name, (in_sum2_meta, counts_meta) in pairs.items():
                name_bytes = base_name.encode('utf-8')
                name_len = len(name_bytes)
                out.write(struct.pack('<i', name_len))
                out.write(name_bytes)

                # ncall = 1 (we write normalized mean squared activation directly)
                ncall = 1
                out.write(struct.pack('<i', ncall))

                nval = in_sum2_meta['dims'][0]
                out.write(struct.pack('<i', nval))

                # Read counts
                f.seek(data_start + counts_meta['offset'])
                counts_val = struct.unpack('<f', f.read(4))[0]
                if counts_val <= 0:
                    counts_val = 1.0

                # Read in_sum2
                f.seek(data_start + in_sum2_meta['offset'])
                floats = np.frombuffer(f.read(nval * 4), dtype=np.float32)

                # Normalize by count
                norm_floats = (floats / counts_val).astype(np.float32)
                out.write(norm_floats.tobytes())

            # 3. Footer
            out.write(struct.pack('<i', chunk_count))
            dataset_bytes = dataset_name.encode('utf-8')
            out.write(struct.pack('<i', len(dataset_bytes)))
            out.write(dataset_bytes)

        out_size = os.path.getsize(dat_path)
        print(f"[SUCCESS] Converted {len(pairs)} entries to native binary: {dat_path}")
        print(f"File size: {out_size:,} bytes ({out_size / (1024*1024):.2f} MB)")

def main():
    parser = argparse.ArgumentParser(description='Convert GGUF imatrix to binary dat format')
    parser.add_argument('--gguf', type=str, required=True, help='Source GGUF imatrix file')
    parser.add_argument('--dat', type=str, required=True, help='Destination dat file')
    args = parser.parse_args()

    convert_gguf_to_dat(args.gguf, args.dat)

if __name__ == '__main__':
    main()
