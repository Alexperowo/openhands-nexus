/**
 * OpenHands Local - Working Profile & Remote Control UI
 * Accessible, High-Contrast Control Layer for Desktop & Mobile
 * Stage 3: Dynamic Reasoning / Thinking UX
 */

(function () {
    console.log("[WorkingProfileUI] Initializing Stage 3 Working Profile & Reasoning Control Layer...");

    const API_URL = "/api/working-profiles";
    let availableProfiles = [];
    let activeState = null;
    let isSubmitting = false;
    let lastRenderedRoute = null;

    // Helper: translate kind to human-readable Russian badge
    function getKindBadge(kind) {
        if (kind === "three_model_chain") {
            return { text: "3 МОДЕЛИ", class: "badge-3-models" };
        } else if (kind === "two_model_chain") {
            return { text: "2 МОДЕЛИ", class: "badge-2-models" };
        } else {
            return { text: "1 МОДЕЛЬ", class: "badge-1-models" };
        }
    }

    // Load state from server
    async function loadWorkingProfiles(silent = false) {
        try {
            const resp = await fetch(API_URL, {
                headers: { "Cache-Control": "no-cache" }
            });
            if (!resp.ok) throw new Error("HTTP " + resp.status);
            const data = await resp.json();

            const profilesChanged = JSON.stringify(availableProfiles) !== JSON.stringify(data.profiles);
            const stateChanged = !activeState || 
                activeState.active_working_profile_id !== data.state.active_working_profile_id ||
                activeState.active_reasoning_mode_id !== data.state.active_reasoning_mode_id;

            availableProfiles = data.profiles || [];
            activeState = data.state || null;

            if (profilesChanged || stateChanged || !silent) {
                renderUI();
            }
        } catch (err) {
            if (!silent) {
                console.warn("[WorkingProfileUI] Failed to load working profiles:", err.message);
            }
        }
    }

    function announceStatus(message) {
        let announcer = document.getElementById("oh-wp-status-announcer");
        if (!announcer) {
            announcer = document.createElement("div");
            announcer.id = "oh-wp-status-announcer";
            announcer.setAttribute("aria-live", "polite");
            announcer.setAttribute("aria-atomic", "true");
            announcer.className = "sr-only";
            document.body.appendChild(announcer);
        }
        announcer.textContent = message;
        setTimeout(() => {
            if (announcer) announcer.textContent = "";
        }, 1500);
    }

    // Switch profile / reasoning mode on server
    async function switchProfile(wpId, rmId) {
        if (isSubmitting) return;
        isSubmitting = true;

        const card = document.getElementById("oh-wp-card") || document.querySelector(".oh-wp-card");
        if (card) {
            card.classList.add("is-changing");
            setTimeout(() => card.classList.remove("is-changing"), 350);
        }

        const syncEl = document.getElementById("oh-wp-sync");
        if (syncEl) {
            syncEl.textContent = "Сохранение...";
            syncEl.className = "oh-wp-sync-indicator syncing";
        }

        try {
            const resp = await fetch(API_URL, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    working_profile_id: wpId,
                    reasoning_mode_id: rmId
                })
            });

            if (!resp.ok) {
                const errData = await resp.json().catch(() => ({}));
                throw new Error(errData.error || ("HTTP " + resp.status));
            }

            const res = await resp.json();
            activeState = res.state;

            if (syncEl) {
                syncEl.textContent = "✓ Активно";
                syncEl.className = "oh-wp-sync-indicator";
            }

            const targetWp = availableProfiles.find(p => p.id === wpId);
            const targetMode = targetWp?.reasoning?.modes?.find(m => m.id === rmId)?.label || rmId;
            announceStatus(`Выбран профиль: ${targetWp ? targetWp.name : wpId}, режим: ${targetMode}`);

            renderUI();
        } catch (err) {
            console.error("[WorkingProfileUI] Error switching profile/reasoning:", err);
            if (syncEl) {
                syncEl.textContent = "Ошибка сохранения";
                syncEl.className = "oh-wp-sync-indicator syncing";
            }
        } finally {
            isSubmitting = false;
        }
    }

    function isConversationPage() {
        return window.location.pathname.includes("/conversations/");
    }

    // Find the best mount target in the DOM
    function findMountTarget() {
        const chatInput = document.querySelector(".chat-input, [contenteditable='true'], textarea");
        if (!chatInput) return null;

        // In both root and conversation pages, target the composer card wrapper inside the chat column.
        // This ensures the container is stacked vertically and never creates an unwanted horizontal column.
        let card = chatInput.closest("[class*='rounded-[15px]'], [class*='rounded-xl'], form");
        if (!card) card = chatInput.parentElement;
        while (card && card.parentElement && card.parentElement.className.includes("relative w-full")) {
            card = card.parentElement;
        }
        return card;
    }

    // Render or update the UI
    function renderUI() {
        if (!availableProfiles.length || !activeState) return;

        const isConv = isConversationPage();
        const currentWp = availableProfiles.find(p => p.id === activeState.active_working_profile_id) || availableProfiles[0];
        const badgeInfo = getKindBadge(currentWp.kind);

        const target = findMountTarget();
        if (!target) return;

        let rootContainer = document.getElementById("oh-working-profile-container");

        // If route changed or container is missing, create/re-mount
        if (!rootContainer || rootContainer.parentElement !== target.parentElement || lastRenderedRoute !== isConv) {
            if (rootContainer) rootContainer.remove();

            rootContainer = document.createElement("div");
            rootContainer.id = "oh-working-profile-container";
            rootContainer.className = "oh-wp-container";

            // Insert directly before the prompt input card
            target.parentElement.insertBefore(rootContainer, target);
            lastRenderedRoute = isConv;
        }

        const reasoning = currentWp.reasoning || {};
        const isReasoningSupported = reasoning.supported && reasoning.modes && reasoning.modes.length > 0;
        const modes = isReasoningSupported ? reasoning.modes : [];
        const activeModeId = activeState.active_reasoning_mode_id || (modes[0] ? modes[0].id : "");
        const activeModeObj = modes.find(m => m.id === activeModeId) || modes[0];

        // 1. In-flight active conversation page
        if (isConv) {
            function getConversationModelInfo() {
                let raw = "";
                const modelBtn = document.querySelector('[data-testid="chat-input-llm-profile"]') ||
                                 document.querySelector('[data-testid*="llm-profile"]') ||
                                 document.querySelector('button[aria-label*="model" i]') ||
                                 document.querySelector('.chat-input [role="button"]');
                if (modelBtn) {
                    raw = (modelBtn.getAttribute('title') || modelBtn.getAttribute('aria-label') || modelBtn.innerText || "").trim();
                }

                if (!raw) return null;

                let name = raw;
                let kindBadge = { text: "1 МОДЕЛЬ", class: "badge-1-models" };

                // Match with available profiles
                const matched = availableProfiles.find(p =>
                    p.default_llm_profile_name === raw ||
                    (p.reasoning && p.reasoning.modes && p.reasoning.modes.some(m => m.target_llm_profile_name === raw))
                );

                if (matched) {
                    name = matched.name;
                    kindBadge = getKindBadge(matched.kind);
                } else if (raw.includes("Qwen3.8") || raw.includes("qwen") || raw.includes("Qwen")) {
                    name = "Qwen 3.8 Opus";
                    if (raw.includes("Medium")) name += " (Medium)";
                    else if (raw.includes("Low")) name += " (Low)";
                    else if (raw.includes("High")) name += " (High)";
                    else if (raw.includes("Direct")) name += " (Direct)";
                    kindBadge = { text: "1 МОДЕЛЬ", class: "badge-1-models" };
                } else if (raw.includes("Ornith")) {
                    name = "Ornith 1.5 Coder";
                    kindBadge = { text: "1 МОДЕЛЬ", class: "badge-1-models" };
                } else if (raw.includes("Next")) {
                    name = "Qwen3-Next";
                    kindBadge = { text: "1 МОДЕЛЬ", class: "badge-1-models" };
                }

                return { raw, name, kindBadge };
            }

            const modelInfo = getConversationModelInfo();
            const displayName = modelInfo ? modelInfo.name : currentWp.name;
            const kindBadge = modelInfo ? modelInfo.kindBadge : badgeInfo;

            // Check if already rendered
            const isAlreadyRendered = rootContainer.querySelector("#oh-wp-conv-toggle");
            if (isAlreadyRendered) {
                if (modelInfo) {
                    const titleEl = rootContainer.querySelector(".oh-wp-conv-collapsed-title strong");
                    if (titleEl && titleEl.textContent !== modelInfo.name) {
                        titleEl.textContent = modelInfo.name;
                    }
                    const badgeEl = rootContainer.querySelector(".oh-wp-badge");
                    if (badgeEl && modelInfo.kindBadge) {
                        badgeEl.className = "oh-wp-badge " + modelInfo.kindBadge.class;
                        badgeEl.textContent = modelInfo.kindBadge.text;
                    }
                }
                return;
            }

            const badgeHtml = kindBadge ? `<span class="oh-wp-badge ${kindBadge.class}" style="padding: 2px 8px; font-size: 10px; margin-left: 4px;">${kindBadge.text}</span>` : "";

            rootContainer.innerHTML = [
                '<div class="oh-wp-conv-container" id="oh-wp-conv-container">',
                '    <div class="oh-wp-conv-collapsed" id="oh-wp-conv-toggle" role="button" tabindex="0" aria-expanded="false" title="Нажмите, чтобы развернуть информацию о профиле диалога">',
                '        <div class="oh-wp-conv-collapsed-left">',
                '            <span class="oh-wp-locked-icon">🔒</span>',
                '            <span class="oh-wp-conv-collapsed-title">Диалог зафиксирован: <strong>' + displayName + '</strong></span>',
                '            ' + badgeHtml,
                '        </div>',
                '        <div class="oh-wp-conv-collapsed-right">',
                '            <span class="oh-wp-toggle-arrow">▾</span>',
                '        </div>',
                '    </div>',
                '    <div class="oh-wp-conv-drawer" id="oh-wp-conv-drawer" style="display: none;">',
                '        <div class="oh-wp-conv-drawer-inner">',
                '            <div class="oh-wp-conv-drawer-desc">',
                '                Этот диалог привязан к данной модели. Изменение профиля на главной странице применяется к новым диалогам.',
                '            </div>',
                '            <a href="/" class="oh-wp-new-chat-btn" title="Создать новый диалог с другим профилем">',
                '                <span>+ Новый диалог</span>',
                '            </a>',
                '        </div>',
                '    </div>',
                '</div>'
            ].join('\n');

            const toggleBtn = rootContainer.querySelector("#oh-wp-conv-toggle");
            const drawer = rootContainer.querySelector("#oh-wp-conv-drawer");
            if (toggleBtn && drawer) {
                toggleBtn.addEventListener("click", () => {
                    const isExpanded = drawer.style.display !== "none";
                    drawer.style.display = isExpanded ? "none" : "block";
                    toggleBtn.classList.toggle("expanded", !isExpanded);
                    toggleBtn.setAttribute("aria-expanded", isExpanded ? "false" : "true");
                });
            }

            // Continuous sync for conversation model in case modelBtn mounts slightly later
            const convSyncInterval = setInterval(() => {
                if (!isConversationPage()) {
                    clearInterval(convSyncInterval);
                    return;
                }
                const info = getConversationModelInfo();
                if (info) {
                    const titleEl = rootContainer.querySelector(".oh-wp-conv-collapsed-title strong");
                    if (titleEl && titleEl.textContent !== info.name) {
                        titleEl.textContent = info.name;
                    }
                    const badgeEl = rootContainer.querySelector(".oh-wp-badge");
                    if (badgeEl && info.kindBadge) {
                        badgeEl.className = "oh-wp-badge " + info.kindBadge.class;
                        badgeEl.textContent = info.kindBadge.text;
                    }
                }
            }, 500);

            return;
        }

        // 2. Main root / new chat page
        let profileOptionsHtml = "";
        for (const p of availableProfiles) {
            const b = getKindBadge(p.kind);
            const isSelected = p.id === currentWp.id ? "selected" : "";
            profileOptionsHtml += '<option value="' + p.id + '" ' + isSelected + '>' + p.name + ' (' + b.text + ')</option>';
        }

        // Reasoning field representation
        let reasoningFieldHtml = "";
        if (isReasoningSupported) {
            let reasoningOptionsHtml = "";
            for (const m of modes) {
                const isSelected = m.id === activeModeId ? "selected" : "";
                reasoningOptionsHtml += '<option value="' + m.id + '" ' + isSelected + '>' + m.label + '</option>';
            }

            reasoningFieldHtml = [
                '<div class="oh-wp-field">',
                '    <label class="oh-wp-label" for="oh-wp-select-reasoning">',
                '        <span>Режим рассуждения (Thinking):</span>',
                '    </label>',
                '    <div class="oh-wp-select-wrapper">',
                '        <select id="oh-wp-select-reasoning" class="oh-wp-select" aria-label="Выберите режим рассуждения">',
                '            ' + reasoningOptionsHtml,
                '        </select>',
                '        <svg class="oh-wp-select-arrow" viewBox="0 0 20 20"><path d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z"/></svg>',
                '    </div>',
                '</div>'
            ].join('\n');
        } else {
            // Requirement 4: Ornith / non-reasoning models: NO reasoning selector, fixed mode display
            reasoningFieldHtml = [
                '<div class="oh-wp-field">',
                '    <label class="oh-wp-label">',
                '        <span>Режим рассуждения (Thinking):</span>',
                '    </label>',
                '    <div class="oh-wp-fixed-mode-box" id="oh-wp-fixed-mode">',
                '        <span class="oh-wp-fixed-icon">⚡</span>',
                '        <span class="oh-wp-fixed-text">Фиксированный режим (без Thinking)</span>',
                '    </div>',
                '</div>'
            ].join('\n');
        }

        // Mode description text
        let modeDescHtml = "";
        if (isReasoningSupported && activeModeObj && activeModeObj.description) {
            modeDescHtml = '<div class="oh-wp-desc-mode" id="oh-wp-desc-mode"><span class="oh-wp-highlight">Рассуждение:</span> ' + activeModeObj.description + '</div>';
        } else if (!isReasoningSupported) {
            modeDescHtml = '<div class="oh-wp-desc-mode" id="oh-wp-desc-mode"><span class="oh-wp-highlight">Рассуждение:</span> Прямой синтез кода без скрытых токенов рассуждений (Fixed Direct Mode)</div>';
        }

        rootContainer.innerHTML = [
            '<div class="oh-wp-card" role="region" aria-label="Выбор рабочего профиля и режима рассуждения">',
            '    <div class="oh-wp-header">',
            '        <div class="oh-wp-title-group">',
            '            <span class="oh-wp-icon">⚡</span>',
            '            <span class="oh-wp-title">Рабочий профиль OpenHands</span>',
            '        </div>',
            '        <div class="oh-wp-header-badges">',
            '            <span class="oh-wp-badge ' + badgeInfo.class + '" id="oh-wp-badge">' + badgeInfo.text + '</span>',
            '            <span class="oh-wp-sync-indicator" id="oh-wp-sync">✓ Активно</span>',
            '        </div>',
            '    </div>',
            '    <div class="oh-wp-controls-grid">',
            '        <div class="oh-wp-field">',
            '            <label class="oh-wp-label" for="oh-wp-select-profile">',
            '                <span>Команда агентов:</span>',
            '            </label>',
            '            <div class="oh-wp-select-wrapper">',
            '                <select id="oh-wp-select-profile" class="oh-wp-select" aria-label="Выберите команду агентов">',
            '                    ' + profileOptionsHtml,
            '                </select>',
            '                <svg class="oh-wp-select-arrow" viewBox="0 0 20 20"><path d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z"/></svg>',
            '            </div>',
            '        </div>',
            '        ' + reasoningFieldHtml,
            '    </div>',
            '    <div class="oh-wp-info-box">',
            '        <div class="oh-wp-desc-arch">',
            '            <span class="oh-wp-highlight">Архитектура:</span> ' + (currentWp.description || "Локальный автономный профиль"),
            '        </div>',
            '        ' + modeDescHtml,
            '    </div>',
            '</div>'
        ].join('\n');

        // Attach change events
        const profileSelect = document.getElementById("oh-wp-select-profile");
        if (profileSelect) {
            profileSelect.addEventListener("change", (e) => {
                const newWpId = e.target.value;
                const newWp = availableProfiles.find(p => p.id === newWpId);
                let newRmId = null;
                if (newWp && newWp.reasoning && newWp.reasoning.supported && newWp.reasoning.modes && newWp.reasoning.modes.length) {
                    newRmId = newWp.reasoning.default_mode_id || newWp.reasoning.modes[0].id;
                }
                switchProfile(newWpId, newRmId);
            });
        }

        const reasoningSelect = document.getElementById("oh-wp-select-reasoning");
        if (reasoningSelect && isReasoningSupported) {
            reasoningSelect.addEventListener("change", (e) => {
                const newRmId = e.target.value;
                switchProfile(currentWp.id, newRmId);
            });
        }

        if (!isConversationPage() && activeState && activeState.resolved_llm_profile_name) {
            syncComposerLlmProfile(activeState.resolved_llm_profile_name);
        }
    }

    // Sync bottom composer picker on root page to match active working profile
    function syncComposerLlmProfile(targetProfileName) {
        if (isConversationPage() || !targetProfileName) return;

        const btn = document.querySelector('[data-testid="chat-input-llm-profile"]');
        if (!btn) return;

        const currentText = (btn.getAttribute('title') || btn.innerText || "").trim();
        if (currentText === targetProfileName) return;

        let popover = document.querySelector('[data-testid="chat-input-llm-profile-popover"]');
        if (!popover) {
            btn.click();
        }

        setTimeout(() => {
            const option = document.querySelector(`[data-testid="chat-input-llm-profile-option-${targetProfileName}"]`);
            if (option) {
                option.click();
            } else {
                const stillOpen = document.querySelector('[data-testid="chat-input-llm-profile-popover"]');
                if (stillOpen) btn.click();
            }
        }, 60);
    }

    // Watch for user selecting a profile via the bottom composer picker on root page
    function setupComposerPickerWatcher() {
        document.addEventListener("click", (e) => {
            if (isConversationPage()) return;
            const opt = e.target.closest('[data-testid*="chat-input-llm-profile-option-"]');
            if (opt) {
                const testId = opt.getAttribute("data-testid") || "";
                const profileName = testId.replace("chat-input-llm-profile-option-", "").trim();
                if (profileName) {
                    const matchedWp = availableProfiles.find(p =>
                        p.default_llm_profile_name === profileName ||
                        (p.reasoning && p.reasoning.modes && p.reasoning.modes.some(m => m.target_llm_profile_name === profileName))
                    );
                    if (matchedWp && matchedWp.id !== activeState?.active_working_profile_id) {
                        let rmId = null;
                        if (matchedWp.reasoning && matchedWp.reasoning.modes) {
                            const matchedMode = matchedWp.reasoning.modes.find(m => m.target_llm_profile_name === profileName);
                            rmId = matchedMode ? matchedMode.id : matchedWp.reasoning.default_mode_id;
                        }
                        switchProfile(matchedWp.id, rmId);
                    }
                }
            }
        }, true);
    }

    // Set up DOM observer to survive SPA re-renders and page navigation (debounced to avoid over-firing)
    function setupObserver() {
        let debounceTimer = null;

        const observer = new MutationObserver(() => {
            if (debounceTimer) clearTimeout(debounceTimer);
            debounceTimer = setTimeout(() => {
                const hasInput = document.querySelector(".chat-input");
                const existingPanel = document.getElementById("oh-working-profile-container");
                const routeChanged = lastRenderedRoute !== isConversationPage();

                if (hasInput && (!existingPanel || routeChanged)) {
                    renderUI();
                } else if (existingPanel && isConversationPage()) {
                    renderUI();
                }
            }, 150);
        });

        observer.observe(document.body, { childList: true, subtree: true });
    }

    // Periodic sync poll every 3 seconds with Visibility API pause to save mobile battery
    let syncIntervalId = null;

    function startSyncPolling() {
        stopSyncPolling();
        syncIntervalId = setInterval(() => {
            if (document.hidden) return;
            loadWorkingProfiles(true);
        }, 3000);
    }

    function stopSyncPolling() {
        if (syncIntervalId) {
            clearInterval(syncIntervalId);
            syncIntervalId = null;
        }
    }

    // Pause polling when tab is hidden or backgrounded, resume immediately on focus/visibility
    document.addEventListener("visibilitychange", () => {
        if (document.hidden) {
            stopSyncPolling();
        } else {
            startSyncPolling();
            loadWorkingProfiles(true);
        }
    });

    window.addEventListener("focus", () => {
        if (!document.hidden) {
            startSyncPolling();
            loadWorkingProfiles(true);
        }
    });

    window.addEventListener("blur", () => {
        if (document.hidden) {
            stopSyncPolling();
        }
    });

    startSyncPolling();

    // Startup initialization
    async function init() {
        await loadWorkingProfiles(false);
        setupObserver();
        setupComposerPickerWatcher();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
