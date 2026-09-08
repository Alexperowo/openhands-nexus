OBJECTIVE:      OpenHands Local Stage 4: Voice UI & Mobile Accessibility (Full Audit & Real Hardware Verification)
PHASE:          Stage 4 of 4 (Real Device Hardware Verification & UX Audit COMPLETE)
STATE:          Verified directly on physical Samsung Galaxy Tab S9 Ultra (1848x2960) via Wi-Fi ADB + Chrome DevTools. Input field restored to comfortable 52px height across virtual keyboard open/closed states. Native composer model picker ([data-testid="chat-input-llm-profile"]) verified intact and visible next to the "+" button across all profile states. Complete profile renaming performed: removed confusing legacy names ("Qwen38_Opus_96K", "-Opus-") across working-profiles and agent-profiles; replaced with clean, professional standards (Qwen 3.8 (Автономный), Qwen3.8-Direct, Qwen3.8-Low, Qwen3.8-Medium, Qwen3.8-High). Backwards compatibility 100% preserved (all legacy profile files retained). Verified live on physical tablet.
DONE:
  - Conducted full audit of model and profile naming across OpenHands, llama-swap, Working Profiles, and Agent Profiles.
  - Eliminated "Qwen38_Opus_96K" and "-Opus-" from all user-facing working profiles, agent profiles, and default configurations.
  - Added clean, standardized Qwen 3.8 LLM profiles: Qwen3.8-Direct, Qwen3.8-Low, Qwen3.8-Medium, Qwen3.8-High while retaining legacy aliases for 100% backwards compatibility.
  - Updated Working Profile display names: "Qwen 3.8 (Автономный)", "Team-Full: Три Модели", "Qwen 3.8 + Ornith (Кодинг-тандем)", "Qwen 3.8 + Next (Анализ-тандем)".
  - Verified live on physical Samsung Galaxy Tab S9 Ultra: composer displays clean "+ Qwen3.8-Medium ▾" without truncation; top banner displays clean "Qwen 3.8 (Автономный)".
EVIDENCE:
  - Physical Screenshots:
    * scratch/s9ultra_clean_qwen_naming.png (Qwen 3.8 Solo with clean "+ Qwen3.8-Medium ▾" picker and banner).
    * scratch/s9ultra_clean_teamfull_naming.png (Qwen 3.8 High with "+ Qwen3.8-High ▾").
    * scratch/s9ultra_teamfull_verified.png (Clean synchronization verified live on hardware).
  - Validation: JSON syntax and integrity validated across all 7 working profiles, 9 agent profiles, and 17 LLM profiles.
OPEN_ISSUES:    None.
NEXT_ACTION:    Present findings and clean naming report to user.
