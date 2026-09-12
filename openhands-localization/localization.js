/**
 * OpenHands Local - Runtime Localization Layer
 * Supplements official i18next runtime with profile aliases & language defaults
 */

(function () {
    console.log("[Localization] Initializing OpenHands Russian Localization Layer...");

    // 1. Default to Russian ONLY if no user choice has been saved yet
    // Ensure OpenHands knows onboarding is completed for local platform
    if (!localStorage.getItem('openhands-onboarded')) {
        localStorage.setItem('openhands-onboarded', '1');
    }

    const currentLang = localStorage.getItem("i18nextLng");
    if (!currentLang) {
        localStorage.setItem("i18nextLng", "ru");
    }

    // 2. Profile aliases for UI display (preserves internal IDs for LLM API)
    const PROFILE_DISPLAY_ALIASES = {
        "Qwen3.8-Opus-Direct": "Qwen3.8-Opus (Без рассуждения)",
        "Qwen3.8-Opus-Low": "Qwen3.8-Opus (Низкая)",
        "Qwen3.8-Opus-Medium": "Qwen3.8-Opus (Средняя)",
        "Qwen3.8-Opus-XHigh": "Qwen3.8-Opus (Максимальная)",
        "Direct": "Без рассуждения",
        "Low": "Низкая",
        "Medium": "Средняя",
        "XHigh": "Максимальная"
    };

    // Safe targeted text node replacer for specific dropdown / label selectors
    function localizeProfileNodes() {
        // Only target dropdown options and profile selector badges
        const targetElements = document.querySelectorAll(
            'span.truncate, div[role="option"], li[role="option"], [role="menuitem"] span, [data-slot="item"] span, button[aria-haspopup="listbox"] span, [data-testid*="profile-selector"] span, [data-testid*="model-selector"] span'
        );

        targetElements.forEach(el => {
            // NEVER touch input, textarea, code, pre, or message content
            if (el.closest('pre, code, textarea, input, [data-message-author], [data-role="assistant"], [data-role="user"]')) {
                return;
            }

            for (const child of el.childNodes) {
                if (child.nodeType === Node.TEXT_NODE) {
                    const text = child.nodeValue.trim();
                    if (PROFILE_DISPLAY_ALIASES[text]) {
                        child.nodeValue = child.nodeValue.replace(text, PROFILE_DISPLAY_ALIASES[text]);
                    }
                }
            }
        });
    }

    // Observe dropdown openings safely
    const observer = new MutationObserver((mutations) => {
        let shouldCheck = false;
        for (const m of mutations) {
            if (m.addedNodes.length > 0) {
                shouldCheck = true;
                break;
            }
        }
        if (shouldCheck) {
            localizeProfileNodes();
        }
    });

    function setup() {
        if (window.__ohLocObserver) {
            try { window.__ohLocObserver.disconnect(); } catch (e) {}
        }
        localizeProfileNodes();
        observer.observe(document.body, { childList: true, subtree: true });
        window.__ohLocObserver = observer;
        window.addEventListener("beforeunload", () => {
            try { observer.disconnect(); } catch (e) {}
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", setup);
    } else {
        setup();
    }
})();