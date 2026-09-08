import json
from pathlib import Path

model_inventory = {
    'canonical_model_root': r'K:\Project\Models',
    'production_models': {
        'Qwen3.8': {
            'model_name': 'Qwen3.8-27B-Opus-Distill-v2-Q4_K_M',
            'current_path': r'D:\Project\models\Qwen3.8-27B-Opus-Distill-v2-Q4_K_M.gguf',
            'disk': 'D:',
            'canonical_k_path': r'K:\Project\Models\Qwen3.8\Qwen3.8-27B-Opus-Distill-v2-Q4_K_M.gguf',
            'files': [
                {
                    'file_name': 'Qwen3.8-27B-Opus-Distill-v2-Q4_K_M.gguf',
                    'role': 'main_gguf',
                    'size_bytes': 16810714688,
                    'sha256': '424b98a8f5add2fb66b92902d98ee9288badc82f4b986e70ade5f8d5ca615991'
                },
                {
                    'file_name': 'Qwen3.8-27B-Opus-Distill-v2-mmproj-f16.gguf',
                    'role': 'vision_projector_companion',
                    'size_bytes': 927607296,
                    'sha256': 'de0d58cea206add6ff82392027785ff294ad9cca22b74fc949f4eb15add35512'
                }
            ],
            'total_size_bytes': 17738321984,
            'referenced_by': r'K:\Project\llama-swap\config.yaml (models.qwen)',
            'backend': r'K:\Project\ik_llama\bin\llama-server.exe',
            'runtime_package': {
                'main_gguf': 'Qwen3.8-27B-Opus-Distill-v2-Q4_K_M.gguf',
                'split_shards': None,
                'mtp_draft': 'Embedded MTP layers (spec-type mtp:n_max=3,p_min=0.0)',
                'sidecars': ['Qwen3.8-27B-Opus-Distill-v2-mmproj-f16.gguf']
            },
            'llm_profile_references': [
                'default.json',
                'Qwen38_Opus_96K.json',
                'Qwen3.8-Opus-Medium.json',
                'Qwen3.8-Opus-Direct.json',
                'Qwen3.8-Opus-Low.json',
                'Qwen3.8-Opus-XHigh.json'
            ]
        },
        'Ornith': {
            'model_name': 'Ornith-1.5-35B-MTP-19G-ICE',
            'current_path': r'K:\Project\Models\Ornith-1.5-35B-MTP-19G-ICE.gguf',
            'disk': 'K:',
            'canonical_k_path': r'K:\Project\Models\Ornith-1.5-35B-MTP-19G-ICE.gguf',
            'files': [
                {
                    'file_name': 'Ornith-1.5-35B-MTP-19G-ICE.gguf',
                    'role': 'main_gguf',
                    'size_bytes': 18822546944
                },
                {
                    'file_name': 'mmproj-Ornith-1.5-35B-BF16.gguf',
                    'role': 'vision_projector_companion',
                    'size_bytes': 902822240
                }
            ],
            'total_size_bytes': 19725369184,
            'referenced_by': r'K:\Project\llama-swap\config.yaml (models.ornith)',
            'backend': r'K:\Project\ik_llama\bin\llama-server.exe',
            'runtime_package': {
                'main_gguf': 'Ornith-1.5-35B-MTP-19G-ICE.gguf',
                'split_shards': None,
                'mtp_draft': 'Embedded MTP layers (spec-type mtp:n_max=1,p_min=0.75)',
                'sidecars': ['mmproj-Ornith-1.5-35B-BF16.gguf']
            },
            'llm_profile_references': [
                'Ornith-Coding.json',
                'Ornith-Direct.json'
            ]
        },
        'Qwen3-Next': {
            'model_name': 'Qwen3-Next-80B-A3B-Thinking-UD-Q3_K_XL',
            'current_path': r'K:\Project\Models\Qwen3-Next-80B-A3B-Thinking-UD-Q3_K_XL.gguf',
            'disk': 'K:',
            'canonical_k_path': r'K:\Project\Models\Qwen3-Next-80B-A3B-Thinking-UD-Q3_K_XL.gguf',
            'files': [
                {
                    'file_name': 'Qwen3-Next-80B-A3B-Thinking-UD-Q3_K_XL.gguf',
                    'role': 'main_gguf',
                    'size_bytes': 35494473888
                },
                {
                    'file_name': 'Qwen3-Next-80B-A3B-Thinking-MTP-ONLY-Q4_K_M.gguf',
                    'role': 'mtp_draft_model',
                    'size_bytes': 1507217408
                }
            ],
            'total_size_bytes': 37001691296,
            'referenced_by': r'K:\Project\llama-swap\config.yaml (models.next)',
            'backend': r'K:\Project\llama-mainline\b10816\llama-server.exe',
            'runtime_package': {
                'main_gguf': 'Qwen3-Next-80B-A3B-Thinking-UD-Q3_K_XL.gguf',
                'split_shards': None,
                'mtp_draft': 'Qwen3-Next-80B-A3B-Thinking-MTP-ONLY-Q4_K_M.gguf (-md)',
                'sidecars': None
            },
            'llm_profile_references': [
                'Next-Normal.json',
                'Next-Deep.json'
            ]
        }
    },
    'inactive_models_in_models_dir': [
        {
            'file_name': 'Qwen3.5-122B-A10B-44GB-GPT5.6Sol-SFT-LynnStyle-GGUF.gguf',
            'path': r'K:\Project\Models\Qwen3.5-122B-A10B-44GB-GPT5.6Sol-SFT-LynnStyle-GGUF.gguf',
            'size_bytes': 44612547968,
            'status': 'INACTIVE_BENCHMARK_MODEL'
        },
        {
            'file_name': 'Qwen3.5-122B-A10B-44GB-GPT5.6Sol-SFT-LynnStyle-GGUF-mmproj-Q8_0.gguf',
            'path': r'K:\Project\Models\Qwen3.5-122B-A10B-44GB-GPT5.6Sol-SFT-LynnStyle-GGUF-mmproj-Q8_0.gguf',
            'size_bytes': 619212000,
            'status': 'INACTIVE_BENCHMARK_MODEL'
        },
        {
            'file_name': 'Qwen3-Next-80B-A3B-Thinking-MTP-ONLY-Q6_K.gguf',
            'path': r'K:\Project\Models\Qwen3-Next-80B-A3B-Thinking-MTP-ONLY-Q6_K.gguf',
            'size_bytes': 1873725440,
            'status': 'ALTERNATIVE_DRAFT_QUANT_INACTIVE'
        }
    ]
}

out_path = Path(r'K:\Project\OpenHands-Tests\Production-Station\stage_6a_evidence\model_inventory.json')
out_path.write_text(json.dumps(model_inventory, indent=2), encoding='utf-8')
print('Written to:', out_path)
