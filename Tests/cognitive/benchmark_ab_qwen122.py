#!/usr/bin/env python3
"""
Tests/cognitive/benchmark_ab_qwen122.py
Head-to-head cognitive audit comparing:
- Baseline 256E: Qwen3.5-122B-A10B (original unpruned brain)
- Pruned 208E:   Qwen3.5-122B-A10B-208E (pruned brain)
"""

import os
import sys
import time
import json
import requests

API_URL = "http://127.0.0.1:8080/v1/chat/completions"
RESULTS_DIR = r"K:\Project\Tests\cognitive"

BENCHMARK_PROMPTS = [
    {
        "id": "vector1_concurrency_rust",
        "domain": "Algorithmics & Concurrency Hazards (Rust/C++)",
        "prompt": (
            "Ты ведущий системный инженер и эксперт по низкоуровневой многопоточности в Rust.\n"
            "Реализуй потокобезопасную неблокирующую очередь типа Single-Producer Single-Consumer (SPSC) "
            "с кольцевым буфером фиксированного размера на базе AtomicUsize.\n\n"
            "Требования:\n"
            "1. Используй корректные атомарные барьеры памяти (Ordering::Acquire, Ordering::Release, Ordering::Relaxed). "
            "Подробно обоснуй в рассуждениях, почему в каждом месте выбран именно этот порядок памяти, и к какому аппаратному "
            "поведению кэша процессора и переупорядочиванию компилятора это приводит.\n"
            "2. Исключи явление false sharing между указателями головы и хвоста (используй cache-line alignment padding).\n"
            "3. Продемонстрируй корректную обработку условий опустошения и переполнения буфера без блокировок.\n"
            "4. Напиши синтаксически корректный, компилируемый код с исчерпывающими комментариями."
        )
    },
    {
        "id": "vector2_logic_deduction",
        "domain": "Hard Multi-Step Logical CoT Deduction",
        "prompt": (
            "Проведи глубокий пошаговый логический и математический вывод следующей задачи. "
            "Подробно зафиксируй все этапы в цепочке размышлений.\n\n"
            "Задача о распределении ресурсов в распределенной системе:\n"
            "Имеется кластер из 5 узлов (N1, N2, N3, N4, N5), на которых размещаются 4 реплики критического сервиса "
            "(R1, R2, R3, R4) и 3 фоновых воркера (W1, W2, W3).\n"
            "Ограничения:\n"
            "1. На любом одном узле не может быть больше 2 задач (реплик или воркеров суммарно).\n"
            "2. Реплика R1 и воркер W1 никогда не могут находиться на одном узле из-за конфликта сетевых портов.\n"
            "3. Если узел содержит хотя бы одну реплику R_k, он должен иметь прямое подключение к кворумному координатору. "
            "Координатор физически размещен ТОЛЬКО на узлах N2 и N4. Следовательно, реплики могут размещаться только "
            "на узлах из множества {N1, N2, N4}, так как только N1 имеет выделенный оптический линк к N2 и N4. "
            "Узлы N3 и N5 не имеют связности с координатором.\n"
            "4. Воркер W2 требует 80% RAM узла, поэтому на том узле, где запущен W2, не может находиться никакая другая "
            "задача (ни реплика, ни другой воркер).\n"
            "5. Воркер W3 должен быть размещен строго на узле с наибольшим номером среди всех узлов, занятых воркерами.\n"
            "6. На узле N4 суммарно должно быть ровно 2 задачи.\n\n"
            "Вопрос:\n"
            "Существует ли валидное размещение всех 7 задач по 5 узлам, удовлетворяющее ВСЕМ ограничениям одновременно?\n"
            "Если существует — найди ВСЕ возможные варианты размещения и строго докажи их полноту.\n"
            "Если не существует — укажи минимальное подмножество ограничений, которое приводит к строгому математическому "
            "противоречию, и докажи невозможность размещения."
        )
    },
    {
        "id": "vector3_security_audit",
        "domain": "Security Vulnerability Audit (C Memory Safety)",
        "prompt": (
            "Проведи глубокий аудит безопасности следующего фрагмента кода десериализатора сетевого протокола на языке C:\n"
            "```c\n"
            "#include <stdint.h>\n"
            "#include <stdlib.h>\n"
            "#include <string.h>\n\n"
            "typedef struct {\n"
            "    uint16_t num_elements;\n"
            "    uint16_t element_size;\n"
            "    uint8_t  flags;\n"
            "    uint8_t  payload[];\n"
            "} __attribute__((packed)) packet_header_t;\n\n"
            "int parse_network_packet(const uint8_t *raw_buf, size_t raw_len, uint8_t **out_data, size_t *out_size) {\n"
            "    if (!raw_buf || raw_len < sizeof(packet_header_t)) {\n"
            "        return -1;\n"
            "    }\n"
            "    const packet_header_t *hdr = (const packet_header_t *)raw_buf;\n"
            "    size_t payload_len = raw_len - sizeof(packet_header_t);\n"
            "    \n"
            "    uint16_t count = hdr->num_elements;\n"
            "    uint16_t el_sz = hdr->element_size;\n"
            "    \n"
            "    // Check total allocation required\n"
            "    uint32_t total_alloc = (uint32_t)count * (uint32_t)el_sz;\n"
            "    if (total_alloc > 65536) {\n"
            "        return -2; // Exceeds safety threshold\n"
            "    }\n"
            "    \n"
            "    if (total_alloc > payload_len) {\n"
            "        return -3; // Malformed payload\n"
            "    }\n"
            "    \n"
            "    uint8_t *buf = (uint8_t *)malloc(total_alloc ? total_alloc : 1);\n"
            "    if (!buf) {\n"
            "        return -4;\n"
            "    }\n"
            "    \n"
            "    // Copy elements\n"
            "    for (uint16_t i = 0; i < count; i++) {\n"
            "        uint16_t offset = i * el_sz;\n"
            "        memcpy(buf + offset, hdr->payload + offset, el_sz);\n"
            "    }\n"
            "    \n"
            "    *out_data = buf;\n"
            "    *out_size = total_alloc;\n"
            "    return 0;\n"
            "}\n"
            "```\n"
            "Твоя задача:\n"
            "1. Найти скрытые уязвимости в этой функции (обрати внимание на переполнения типов, выравнивание, "
            "условия в циклах, знаковость и граничные случаи).\n"
            "2. Описать точный сценарий эксплуатации (Proof of Concept) и последствия (RCE, Out-of-Bounds Write, DoS).\n"
            "3. Предоставить безопасный исправленный вариант функции с учётом стандартов MISRA C и CERT C."
        )
    },
    {
        "id": "vector4_strict_constraints_json",
        "domain": "Instruction Invariants & Strict JSON Format",
        "prompt": (
            "Ты главный архитектор высоконагруженных систем. Спроектируй архитектуру глобально-распределённой системы биллинга финтех-платформы.\n"
            "СТРОЖАЙШИЕ ОГРАНИЧЕНИЯ (нарушение хотя бы одного означает провал теста):\n"
            "1. Выведи ТОЛЬКО валидный JSON-объект. Запрещено использовать любые символы, разметку ```json или пояснения до и после JSON. "
            "Ответ должен парситься функцией json.loads() напрямую.\n"
            "2. Схема JSON должна содержать ключи: 'system_name', 'regions', 'consensus_mechanism', 'storage_layers', "
            "'disaster_recovery', 'negative_invariants_verification'.\n"
            "3. НЕГАТИВНОЕ ОГРАНИЧЕНИЕ 1: Никаких двухфазных коммитов (2PC / XA) между датацентрами.\n"
            "4. НЕГАТИВНОЕ ОГРАНИЧЕНИЕ 2: Запрещено использовать синхронные REST/gRPC вызовы в критическом пути списания средств.\n"
            "5. НЕГАТИВНОЕ ОГРАНИЧЕНИЕ 3: База данных балансов НЕ может быть реляционной с единой точкой отказа (Single Primary RDBMS запрещена).\n"
            "6. В ключе 'negative_invariants_verification' для каждого из трёх запретов явно опиши, какой механизм предотвращает их появление."
        )
    },
    {
        "id": "vector5_russian_linguistics",
        "domain": "Russian Technical Linguistics & Architectural Synthesis",
        "prompt": (
            "Проведи глубокий сравнительный инженерный разбор алгоритмов консенсуса Raft и Paxos в условиях частичного сетевого "
            "разбиения (asymmetric network partition) и византийского поведения сетевого оборудования (пакеты искажаются или избирательно отбрасываются).\n"
            "Требования:\n"
            "1. Используй богатый, грамотный русский инженерный язык с академической строгостью. Избегай вульгарных англицизмов и корявой "
            "дословной кальки (вместо 'лидер электится' используй 'выборы координатора/лидера', вместо 'аппенд ентрис' — 'репликация записей журнала').\n"
            "2. Детально разбери сценарий, при котором старый лидер оказывается изолирован от кворума, но продолжает отвечать клиентам на чтение (stale read), "
            "и как эта проблема решается с помощью Lease Read / Read Index.\n"
            "3. Опиши математический инвариант безопасности журнала (Log Matching Property) и почему в Raft он гарантируется конструктивно."
        )
    }
]

def run_test(model_name, prompt_item):
    p_id = prompt_item["id"]
    domain = prompt_item["domain"]
    prompt = prompt_item["prompt"]
    
    print(f"\n{'='*70}", flush=True)
    print(f"[{model_name}] >>> Running test: {p_id} ({domain})", flush=True)
    print(f"{'='*70}", flush=True)
    t0 = time.time()
    
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.6,
        "top_p": 0.95,
        "max_tokens": 12288,
        "stream": True
    }
    
    ttft = None
    reasoning_chunks = []
    content_chunks = []
    token_count = 0
    last_report_tok = 0
    last_report_t = t0
    
    try:
        with requests.post(API_URL, json=payload, stream=True, timeout=1800) as resp:
            if resp.status_code != 200:
                print(f"[{model_name}] [ERROR] Status {resp.status_code}: {resp.text}", flush=True)
                return {"error": f"HTTP {resp.status_code}: {resp.text}", "duration": time.time() - t0}
            
            for line in resp.iter_lines():
                if not line:
                    continue
                line_str = line.decode('utf-8', errors='ignore')
                if line_str.startswith("data: "):
                    data_str = line_str[6:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        delta = chunk["choices"][0].get("delta", {})
                        
                        r_part = delta.get("reasoning_content") or ""
                        c_part = delta.get("content") or ""
                        
                        if r_part:
                            reasoning_chunks.append(r_part)
                        if c_part:
                            content_chunks.append(c_part)
                            
                        if r_part or c_part:
                            now = time.time()
                            if ttft is None:
                                ttft = now - t0
                                print(f"[{model_name}] TTFT: {ttft:.2f}s", flush=True)
                                last_report_t = now
                            token_count += 1
                            
                            if token_count - last_report_tok >= 200:
                                dt = now - last_report_t
                                speed = (token_count - last_report_tok) / dt if dt > 0 else 0
                                cum_speed = token_count / (now - (t0 + ttft)) if (now - (t0 + ttft)) > 0 else 0
                                in_think = "THINKING" if len(content_chunks) == 0 else "ANSWERING"
                                print(f"[{model_name}] Token {token_count:5d} [{in_think}] | Current: {speed:5.1f} t/s | Avg: {cum_speed:5.1f} t/s", flush=True)
                                last_report_tok = token_count
                                last_report_t = now
                    except Exception:
                        pass
                        
        t_elapsed = time.time() - t0
        gen_time = t_elapsed - (ttft or 0)
        final_speed = token_count / gen_time if gen_time > 0 else 0
        
        full_reasoning = "".join(reasoning_chunks)
        full_content = "".join(content_chunks)
        
        print(f"\n[{model_name}] [OK] Finished: {token_count} tokens in {gen_time:.1f}s ({final_speed:.2f} tok/s)", flush=True)
        print(f"[{model_name}] Thinking: {len(full_reasoning)} chars | Answer: {len(full_content)} chars", flush=True)
        
        return {
            "id": p_id,
            "domain": domain,
            "duration_sec": round(t_elapsed, 2),
            "ttft_sec": round(ttft or 0, 2),
            "tokens_generated": token_count,
            "tok_per_sec": round(final_speed, 2),
            "reasoning_content": full_reasoning,
            "content": full_content
        }
    except Exception as e:
        print(f"[{model_name}] [EXCEPTION]: {e}", flush=True)
        return {"error": str(e), "duration": time.time() - t0}

def main():
    if len(sys.argv) < 2:
        print("Usage: python benchmark_ab_qwen122.py <model_name>")
        sys.exit(1)
        
    model_name = sys.argv[1]
    out_file = os.path.join(RESULTS_DIR, f"results_{model_name.replace(':', '_')}.json")
    
    print("=" * 70)
    print(f"  COGNITIVE BENCHMARK RUNNER: {model_name}")
    print(f"  Target File: {out_file}")
    print("=" * 70)
    
    results = []
    for item in BENCHMARK_PROMPTS:
        res = run_test(model_name, item)
        results.append(res)
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"[{model_name}] [SAVED] Progress saved ({len(results)}/{len(BENCHMARK_PROMPTS)}) to {out_file}", flush=True)
        time.sleep(2)
        
    print(f"\n[ALL DONE] Saved {len(results)} test outputs to {out_file}")

if __name__ == "__main__":
    main()
