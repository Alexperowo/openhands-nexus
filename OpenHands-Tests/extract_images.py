import json, base64, os

with open(r"K:\Project\OpenHands-Tests\Android-Smoke-01\agent-transcript.md", "r", encoding="utf-8") as f:
    text = f.read()

import re
OUTPUT_DIR = r"K:\Project\OpenHands-Tests\Android-Smoke-01"

# Find all JSON event blocks
json_blocks = re.findall(r'```json\n([\s\S]*?)\n```', text)

extracted = []
for i, block in enumerate(json_blocks):
    try:
        ev = json.loads(block)
        obs = ev.get("observation", {})
        content = obs.get("content", [])
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "image":
                    urls = part.get("image_urls", [])
                    if isinstance(urls, str):
                        urls = [urls]
                    for url in urls:
                        if "base64," in url:
                            b64_str = url.split("base64,")[1]
                            img_data = base64.b64decode(b64_str)
                            img_name = f"step_{i+1}_screenshot.png"
                            img_path = os.path.join(OUTPUT_DIR, img_name)
                            with open(img_path, "wb") as f_img:
                                f_img.write(img_data)
                            extracted.append((i+1, img_path))
    except Exception as e:
        pass

print(f"Successfully extracted {len(extracted)} screenshots from conversation trace!")
if len(extracted) > 0:
    import shutil
    shutil.copyfile(extracted[0][1], os.path.join(OUTPUT_DIR, "initial-screen.png"))
    print(f"Saved initial-screen.png from {extracted[0][1]}")

if os.path.exists(r"K:\Project\final_about_tablet.png"):
    import shutil
    shutil.copyfile(r"K:\Project\final_about_tablet.png", os.path.join(OUTPUT_DIR, "final-about-tablet.png"))
    print("Saved final-about-tablet.png from K:\\Project\\final_about_tablet.png")
elif len(extracted) > 0:
    import shutil
    shutil.copyfile(extracted[-1][1], os.path.join(OUTPUT_DIR, "final-about-tablet.png"))
    print(f"Saved final-about-tablet.png from {extracted[-1][1]}")