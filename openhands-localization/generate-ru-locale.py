import json
import os
import re
import sys
import time

import requests

sys.stdout.reconfigure(encoding='utf-8')

appdata = os.environ.get("APPDATA") or os.path.expanduser(r"~\AppData\Roaming")
EN_FILE = os.path.join(appdata, r"npm\node_modules\@openhands\agent-canvas\build\locales\en\openhands.json")
RU_FILE = os.path.join(os.path.dirname(__file__), "ru.json")
LLM_URL = "http://127.0.0.1:8080/v1/chat/completions"

def load_json(path):
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_ru(ru_dict):
    with open(RU_FILE, 'w', encoding='utf-8') as f:
        json.dump(ru_dict, f, ensure_ascii=False, indent=2)

def translate_batch(items):
    input_list = [{'i': i, 't': t} for i, k, t in items]
    prompt = f"""Translate the 't' field of each JSON item from English to Russian for OpenHands desktop UI.
Keep 'i' unchanged.
Terminology: Conversation->Диалог, Settings->Настройки, Workspace->Рабочая область, Terminal->Терминал, Cancel->Отмена, Save->Сохранить, Reasoning Effort->Глубина рассуждения.
Preserve {{{{var}}}}, <cmd>...</cmd>, <punct>...</punct>, <example>...</example> exactly.
Return a valid JSON array of objects with 'i' and 't'.
Input:
{json.dumps(input_list, ensure_ascii=False)}
"""

    for attempt in range(3):
        try:
            resp = requests.post(LLM_URL, json={
                'model': 'Qwen3.8-27B-Opus-Distill-v2-Q4_K_M.gguf',
                'messages': [{'role': 'user', 'content': prompt}],
                'chat_template_kwargs': {'reasoning_effort': 'low'},
                'max_tokens': 2048,
                'temperature': 0.1
            }, timeout=60)
            data = resp.json()
            raw = data['choices'][0]['message']['content'].strip()

            cleaned = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL).strip()
            if '```' in cleaned:
                m = re.search(r'```(?:json)?\s*(\[.*?\])\s*```', cleaned, re.DOTALL)
                if m:
                    cleaned = m.group(1).strip()
                else:
                    cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
                    cleaned = re.sub(r'\s*```$', '', cleaned)

            if not cleaned.startswith('['):
                b_start = cleaned.find('[')
                b_end = cleaned.rfind(']')
                if b_start != -1 and b_end != -1 and b_end > b_start:
                    cleaned = cleaned[b_start:b_end+1]

            parsed = json.loads(cleaned)
            res_dict = {entry['i']: entry['t'] for entry in parsed if isinstance(entry, dict) and 'i' in entry and 't' in entry}
            if len(res_dict) > 0:
                return res_dict
        except Exception as e:
            print(f" [Att {attempt+1}: {e}]", end="", flush=True)
            time.sleep(1)
    return {}

def main():
    en = load_json(EN_FILE)
    ru = load_json(RU_FILE)

    # 1. On-the-fly text mapping from existing translations
    text_map = {en[k]: ru[k] for k in ru if k in en}
    instant_count = 0
    for k, v in en.items():
        if k not in ru:
            if v in text_map:
                ru[k] = text_map[v]
                instant_count += 1
            elif v.strip() in text_map:
                ru[k] = text_map[v.strip()]
                instant_count += 1
    if instant_count > 0:
        save_ru(ru)
        print(f"Instantly resolved {instant_count} keys via text mapping.")

    keys = list(en.keys())
    total = len(keys)
    print(f"Total keys in EN: {total}")
    print(f"Already in RU:    {len(ru)}")

    missing_items = []
    for idx, k in enumerate(keys):
        if k not in ru or not ru[k]:
            missing_items.append((idx, k, en[k]))

    print(f"Remaining to translate: {len(missing_items)}")
    if not missing_items:
        print("All keys are already translated!")
        return

    BATCH_SIZE = 10
    for b_start in range(0, len(missing_items), BATCH_SIZE):
        batch = missing_items[b_start : b_start + BATCH_SIZE]
        b_num = (b_start // BATCH_SIZE) + 1
        total_batches = (len(missing_items) + BATCH_SIZE - 1) // BATCH_SIZE
        print(f"[{b_num}/{total_batches}] Translating {len(batch)} items...", end="", flush=True)
        t0 = time.time()

        translated = translate_batch(batch)
        dt = time.time() - t0

        saved = 0
        for i, k, orig_text in batch:
            if i in translated and translated[i]:
                ru[k] = translated[i]
                text_map[orig_text] = translated[i]
                saved += 1
            else:
                ru[k] = orig_text

        save_ru(ru)
        print(f" OK ({dt:.1f}s, {saved}/{len(batch)}). Total: {len(ru)}/{total}")

    print(f"Final check: {len(ru)}/{total} keys translated.")
    save_ru(ru)

if __name__ == '__main__':
    main()
