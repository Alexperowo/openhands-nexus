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

    // Collapsed / Expanded state with localStorage persistence
    function getInitialCollapsedState() {
        try {
            const saved = localStorage.getItem("oh_wp_collapsed");
            if (saved === "false") return false;
        } catch (e) {}
        return true; // Default to ultra-compact collapsed bar
    }
    let isCollapsed = getInitialCollapsedState();

    function setCollapsed(collapsed, save = true) {
        isCollapsed = collapsed;
        if (save) {
            try {
                localStorage.setItem("oh_wp_collapsed", collapsed ? "true" : "false");
            } catch (e) {}
        }
        const card = document.getElementById("oh-wp-card");
        if (card) {
            if (isCollapsed) {
                card.classList.add("is-collapsed");
            } else {
                card.classList.remove("is-collapsed");
            }
        }
        const header = document.getElementById("oh-wp-header");
        if (header) {
            header.setAttribute("aria-expanded", isCollapsed ? "false" : "true");
        }
        const toggleBtn = document.getElementById("oh-wp-toggle-btn");
        if (toggleBtn) {
            toggleBtn.setAttribute("aria-label", (isCollapsed ? "Настроить" : "Свернуть") + " панель профиля");
            const label = toggleBtn.querySelector(".oh-wp-toggle-label");
            if (label) {
                label.textContent = isCollapsed ? "Настроить" : "Свернуть";
            }
        }
    }
    window.setWorkingProfileCollapsed = setCollapsed;

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

    let lastTaskRunningState = false;

    // Detect if agent is actively running a task
    function isTaskRunning() {
        const stopCandidates = document.querySelectorAll('[data-testid="stop-button"], [data-testid="chat-input-stop"], button[aria-label*="Stop" i], button[aria-label*="Остановить" i], button[title*="Stop" i]');
        for (const btn of stopCandidates) {
            if (btn.id === "oh-composer-mic-btn" || btn.closest("#oh-voice-pill, .oh-voice-popover, .oh-voice-container, .oh-tts-speak-btn")) {
                continue;
            }
            if (btn.offsetParent !== null) return true;
        }

        const loadingEl = document.querySelector('.loading-spinner, [data-streaming="true"], .typing-cursor, [data-testid="chat-input-loading"]');
        if (loadingEl && loadingEl.offsetParent !== null) return true;

        const chatInput = document.querySelector(".chat-input, [contenteditable='true'], textarea");
        if (chatInput && (chatInput.hasAttribute("disabled") || chatInput.getAttribute("aria-disabled") === "true")) {
            return true;
        }

        return false;
    }

    // Switch profile / reasoning mode on server
    async function switchProfile(wpId, rmId) {
        if (isSubmitting || isTaskRunning()) return;
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

            if (activeState && activeState.resolved_llm_profile_name) {
                syncComposerLlmProfile(activeState.resolved_llm_profile_name);
            }
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

        const running = isTaskRunning();
        lastTaskRunningState = running;

        const disabledAttr = running ? 'disabled="disabled"' : '';
        const cardRunningClass = running ? ' is-running' : '';
        const syncStatusHtml = running
            ? '<span class="oh-wp-sync-indicator running" id="oh-wp-sync" title="Агент выполняет задачу. Переключение моделей заблокировано до завершения шага.">⏳ Выполняется...</span>'
            : '<span class="oh-wp-sync-indicator" id="oh-wp-sync">✓ Активно</span>';

        // Profile options
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
                '        <select id="oh-wp-select-reasoning" class="oh-wp-select" aria-label="Выберите режим рассуждения" ' + disabledAttr + '>',
                '            ' + reasoningOptionsHtml,
                '        </select>',
                '        <svg class="oh-wp-select-arrow" viewBox="0 0 20 20"><path d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z"/></svg>',
                '    </div>',
                '</div>'
            ].join('\n');
        } else {
            // Non-reasoning models: NO reasoning selector, fixed mode display
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

        const summaryMode = isReasoningSupported && activeModeObj 
            ? (activeModeObj.label.split(" ")[0] || activeModeObj.label)
            : "Direct";
        const summaryFull = currentWp.name + " · " + (isReasoningSupported && activeModeObj ? activeModeObj.label : "Direct");
        const summaryShort = currentWp.name + " · " + summaryMode;

        const collapsedClass = isCollapsed ? " is-collapsed" : "";
        const toggleLabel = isCollapsed ? "Настроить" : "Свернуть";
        const ariaExpanded = isCollapsed ? "false" : "true";

        rootContainer.innerHTML = [
            '<div class="oh-wp-card' + cardRunningClass + collapsedClass + '" id="oh-wp-card" role="region" aria-label="Выбор рабочего профиля и режима рассуждения">',
            '    <div class="oh-wp-header" id="oh-wp-header" role="button" tabindex="0" aria-expanded="' + ariaExpanded + '" aria-controls="oh-wp-body" title="Нажмите, чтобы свернуть или развернуть настройки профиля">',
            '        <div class="oh-wp-header-left">',
            '            <span class="oh-wp-icon">⚡</span>',
            '            <span class="oh-wp-title">Рабочий профиль</span>',
            '            <span class="oh-wp-badge ' + badgeInfo.class + '" id="oh-wp-badge">' + badgeInfo.text + '</span>',
            '            <span class="oh-wp-summary-pill" id="oh-wp-summary-pill" title="' + summaryFull + '">' + summaryShort + '</span>',
            '        </div>',
            '        <div class="oh-wp-header-right">',
            '            ' + syncStatusHtml,
            '            <button class="oh-wp-toggle-btn" id="oh-wp-toggle-btn" type="button" aria-label="' + toggleLabel + ' панель профиля" tabindex="-1">',
            '                <span class="oh-wp-toggle-label">' + toggleLabel + '</span>',
            '                <svg class="oh-wp-chevron" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clip-rule="evenodd"/></svg>',
            '            </button>',
            '        </div>',
            '    </div>',
            '    <div class="oh-wp-body" id="oh-wp-body" role="group" aria-label="Настройки профиля и рассуждений">',
            '        <div class="oh-wp-controls-grid">',
            '            <div class="oh-wp-field">',
            '                <label class="oh-wp-label" for="oh-wp-select-profile">',
            '                    <span>Команда агентов:</span>',
            '                </label>',
            '                <div class="oh-wp-select-wrapper">',
            '                    <select id="oh-wp-select-profile" class="oh-wp-select" aria-label="Выберите команду агентов" ' + disabledAttr + '>',
            '                        ' + profileOptionsHtml,
            '                    </select>',
            '                    <svg class="oh-wp-select-arrow" viewBox="0 0 20 20"><path d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z"/></svg>',
            '                </div>',
            '            </div>',
            '            ' + reasoningFieldHtml,
            '        </div>',
            '        <div class="oh-wp-info-box">',
            '            <div class="oh-wp-desc-arch">',
            '                <span class="oh-wp-highlight">Архитектура:</span> ' + (currentWp.description || "Локальный автономный профиль"),
            '            </div>',
            '            ' + modeDescHtml,
            '        </div>',
            '    </div>',
            '</div>'
        ].join('\n');

        // Attach header collapse toggle events
        const header = document.getElementById("oh-wp-header");
        if (header) {
            header.addEventListener("click", () => {
                setCollapsed(!isCollapsed, true);
            });
            header.addEventListener("keydown", (e) => {
                if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    setCollapsed(!isCollapsed, true);
                }
            });
        }

        // Attach change events if not running
        const profileSelect = document.getElementById("oh-wp-select-profile");
        if (profileSelect && !running) {
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
        if (reasoningSelect && isReasoningSupported && !running) {
            reasoningSelect.addEventListener("change", (e) => {
                const newRmId = e.target.value;
                const modeObj = modes.find(m => m.id === newRmId);
                announceStatus(`Режим мышления: ${modeObj ? modeObj.label : newRmId}`);
                switchProfile(currentWp.id, newRmId);
            });
        }

        // Keep composer profile in sync when idle
        if (!running && activeState && activeState.resolved_llm_profile_name) {
            syncComposerLlmProfile(activeState.resolved_llm_profile_name);
        }
    }

    // Sync bottom composer picker to match active working profile
    function syncComposerLlmProfile(targetProfileName) {
        if (!targetProfileName || isTaskRunning()) return;

        const btn = document.querySelector('[data-testid="chat-input-llm-profile"]');
        if (!btn || btn.hasAttribute("disabled") || btn.getAttribute("aria-disabled") === "true") return;

        const currentText = (btn.getAttribute('title') || btn.innerText || "").trim();
        if (currentText === targetProfileName || currentText.includes(targetProfileName)) return;

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

    // Watch for user selecting a profile via the bottom composer picker
    function setupComposerPickerWatcher() {
        document.addEventListener("click", (e) => {
            if (isTaskRunning()) return;
            const opt = e.target.closest('[data-testid*="chat-input-llm-profile-option-"]');
            if (opt) {
                const testId = opt.getAttribute("data-testid") || "";
                const profileName = testId.replace("chat-input-llm-profile-option-", "").trim();
                if (profileName) {
                    const matchedWp = availableProfiles.find(p =>
                        p.default_llm_profile_name === profileName ||
                        (p.reasoning && p.reasoning.modes && p.reasoning.modes.some(m => m.target_llm_profile_name === profileName))
                    );
                    if (matchedWp) {
                        let rmId = null;
                        if (matchedWp.reasoning && matchedWp.reasoning.modes) {
                            const matchedMode = matchedWp.reasoning.modes.find(m => m.target_llm_profile_name === profileName);
                            rmId = matchedMode ? matchedMode.id : matchedWp.reasoning.default_mode_id;
                        }
                        const isProfileDiff = matchedWp.id !== activeState?.active_working_profile_id;
                        const isModeDiff = rmId && rmId !== activeState?.active_reasoning_mode_id;
                        if (isProfileDiff || isModeDiff) {
                            switchProfile(matchedWp.id, rmId);
                        }
                    }
                }
            }
        }, true);
    }

    // Set up DOM observer to survive SPA re-renders, route changes, and task running state changes
    function setupObserver() {
        let debounceTimer = null;

        const observer = new MutationObserver(() => {
            if (debounceTimer) clearTimeout(debounceTimer);
            debounceTimer = setTimeout(() => {
                const hasInput = document.querySelector(".chat-input, [contenteditable='true'], textarea");
                const existingPanel = document.getElementById("oh-working-profile-container");
                const isConv = isConversationPage();
                const routeChanged = lastRenderedRoute !== isConv;
                const running = isTaskRunning();
                const taskRunningChanged = running !== lastTaskRunningState;

                if (hasInput && (!existingPanel || routeChanged || taskRunningChanged)) {
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
            const running = isTaskRunning();
            if (running !== lastTaskRunningState) {
                renderUI();
            }
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

    // Auto-collapse panel when composer prompt input receives focus (frees screen for mobile virtual keyboard)
    function setupFocusAutoCollapse() {
        document.addEventListener("focusin", (e) => {
            const target = e.target;
            if (target && (target.matches(".chat-input, [contenteditable='true'], textarea") || target.closest(".chat-input"))) {
                if (!isCollapsed) {
                    setCollapsed(true, false);
                }
            }
        }, true);
    }

    // Startup initialization
    async function init() {
        await loadWorkingProfiles(false);
        setupObserver();
        setupComposerPickerWatcher();
        setupFocusAutoCollapse();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
