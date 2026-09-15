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
        // Multi-agent team chains
        "Team-Flagship": "Связка: Архитектор (122B) + Исполнитель (35B)",
        "Team-Full": "Связка: Трио (Планнер 27B + Кодер 35B + Дебаггер 80B)",
        "Team-Qwen-Ornith": "Связка: Планнер (27B) + Исполнитель (35B)",
        "Team-Qwen-Next": "Связка: Планнер (27B) + Дебаггер (80B)",
        "Team-Next-Ornith": "Связка: Аналитик (80B) + Исполнитель (35B)",

        // Solo autonomous engineers
        "Qwen-122B-ChatGPT-5.6-SOL": "Соло: Флагман Qwen 122B (Все роли)",
        "Qwen122-Standalone": "Соло: Qwen 122B Турбо (Все роли)",
        "Ornith-Standalone": "Соло: Кодер Ornith 35B (Все роли)",
        "Qwen-Standalone": "Соло: Быстрый Qwen 27B (Все роли)",
        "Next-Normal-Standalone": "Соло: Отладчик Next 80B (Все роли)",
        "Next-Deep-Standalone": "Соло: Глубокий Next 80B (Все роли)",
        "default": "Базовый инженер OpenHands",

        // Reasoning levels & modes
        "Qwen3.8-Opus-Direct": "Qwen3.8-Opus (Без рассуждения)",
        "Qwen3.8-Opus-Low": "Qwen3.8-Opus (Низкая)",
        "Qwen3.8-Opus-Medium": "Qwen3.8-Opus (Средняя)",
        "Qwen3.8-Opus-XHigh": "Qwen3.8-Opus (Максимальная)",
        "Direct": "Без рассуждения",
        "Low": "Низкая",
        "Medium": "Средняя",
        "XHigh": "Максимальная",

        // Automation titles
        "GitHub Code Review Agent": "Агент ревью кода GitHub",
        "GitHub Repo Monitor": "Мониторинг репозиториев GitHub",
        "Slack Bot": "Бот для Slack",
        "Automate": "Автоматизация",
        "Automations": "Автоматизации"
    };

    // Safe targeted text node replacer for specific dropdown / label selectors
    function localizeProfileNodes() {
        // Target dropdown options, profile selector badges, and context menu items
        const targetElements = document.querySelectorAll(
            'span.truncate, div[role="option"], li[role="option"], [role="menuitem"] span, [data-slot="item"] span, button[aria-haspopup="listbox"] span, [data-testid*="profile-selector"] span, [data-testid*="model-selector"] span, [data-testid*="chat-input-agent-profile-option-"] span, [data-testid="agent-profile-submenu"] span, [data-testid="agent-profile-submenu"] button, [data-testid="agent-profile-submenu"] li, [data-testid="sidebar-automations-link"], [data-testid="sidebar-automations-link"] span'
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

            if (el.hasAttribute('title')) {
                const titleVal = el.getAttribute('title').trim();
                if (PROFILE_DISPLAY_ALIASES[titleVal]) {
                    el.setAttribute('title', PROFILE_DISPLAY_ALIASES[titleVal]);
                }
            }
        });

        // Direct deterministic replacement for agent profile submenu buttons
        document.querySelectorAll('[data-testid*="chat-input-agent-profile-option-"]').forEach(btn => {
            const testId = btn.getAttribute('data-testid') || '';
            const profileName = testId.replace('chat-input-agent-profile-option-', '').trim();
            if (PROFILE_DISPLAY_ALIASES[profileName]) {
                const alias = PROFILE_DISPLAY_ALIASES[profileName];
                const span = btn.querySelector('span');
                if (span && span.textContent !== alias) {
                    span.textContent = alias;
                    span.setAttribute('title', alias);
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