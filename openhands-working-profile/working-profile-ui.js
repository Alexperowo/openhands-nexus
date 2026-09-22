/**
 * OpenHands Nexus - Minimalist Remote Control UI Layer
 * Claude Code / ChatGPT Codex / Google Antigravity Architecture
 *
 * Provides:
 * 1. 4 Models + 3 Chains canonical selection (7 items strictly).
 * 2. Orthogonal Reasoning Control (Выкл, Низкое, Среднее, Глубокое).
 * 3. Live Station Telemetry Pill (speed, prefill %, tokens, active tool).
 * 4. Universal mount for BOTH Landing Page (/) and Conversation Page (/conversations/*).
 * 5. Complete immunity to MutationObserver recursion and layout freezing.
 * 6. Minimum 48px touch targets for Samsung Galaxy Tab S9 Ultra (WCAG 2.5.5 AAA).
 */

(function () {
    "use strict";

    console.log("[NexusRemoteControl] Initializing Minimalist Remote Control Layer...");

    const API_PROFILES_URL = "/api/working-profiles";
    let availableProfiles = [];
    let activeState = null;
    let isSubmitting = false;
    let isMutatingDOM = false;
    let telemetryInterval = null;
    let lastTelemetryMilestone = -1;
    let observer = null;

    // Helper: Escape HTML
    function escapeHtml(str) {
        if (!str) return "";
        return String(str)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    // Helper: Kind badge formatting (COMPACT DIGITS as requested)
    function getKindBadge(kind) {
        if (kind === "flagship_chain" || kind === "two_model_flagship") {
            return { text: "СВЯЗКА", class: "badge-flagship-chain" };
        } else if (kind === "flagship_single" || kind === "flagship") {
            return { text: "ФЛАГМАН", class: "badge-flagship" };
        } else if (kind === "three_model_chain") {
            return { text: "3", class: "badge-3-models" };
        } else if (kind === "two_model_chain") {
            return { text: "2", class: "badge-2-models" };
        } else {
            return { text: "1", class: "badge-1-models" };
        }
    }

    // Safe execution wrapper preventing MutationObserver loops
    function withDOMUpdate(fn) {
        isMutatingDOM = true;
        try {
            fn();
        } finally {
            // Reset flag after all synchronous DOM events have flushed
            Promise.resolve().then(() => {
                isMutatingDOM = false;
            });
        }
    }

    // Screen reader announcements (WCAG 4.1.3)
    function announceStatus(message) {
        let announcer = document.getElementById("oh-nexus-announcer");
        if (!announcer) {
            announcer = document.createElement("div");
            announcer.id = "oh-nexus-announcer";
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

    // Task running detection
    function isTaskRunning() {
        const stopCandidates = document.querySelectorAll(
            '[data-testid="stop-button"], [data-testid="chat-input-stop"], button[aria-label*="Stop" i], button[aria-label*="Остановить" i], button[title*="Stop" i]'
        );
        for (const btn of stopCandidates) {
            if (btn.id === "oh-composer-mic-btn" || btn.closest("#oh-voice-pill, .oh-voice-popover, .oh-voice-container")) {
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

    // Load working profiles from backend
    async function loadWorkingProfiles(silent = false) {
        try {
            const resp = await fetch(`${API_PROFILES_URL}?_ts=${Date.now()}`);
            if (!resp.ok) throw new Error("HTTP " + resp.status);
            const data = await resp.json();

            const profilesChanged = JSON.stringify(availableProfiles) !== JSON.stringify(data.profiles);
            const stateChanged = !activeState ||
                activeState.active_working_profile_id !== data.state.active_working_profile_id ||
                activeState.active_reasoning_mode_id !== data.state.active_reasoning_mode_id;

            availableProfiles = data.profiles || [];
            activeState = data.state || null;

            if (profilesChanged || stateChanged || !silent) {
                withDOMUpdate(() => {
                    mountOrUpdateNexusBar();
                });
            }
        } catch (err) {
            if (!silent) {
                console.warn("[NexusRemoteControl] Failed to load profiles:", err.message);
            }
        }
    }

    // Switch profile / reasoning mode
    async function switchProfile(wpId, rmId) {
        if (isSubmitting || isTaskRunning()) return;
        isSubmitting = true;

        const modelBtn = document.getElementById("oh-nexus-model-btn");
        if (modelBtn) modelBtn.classList.add("is-loading");

        try {
            const resp = await fetch(API_PROFILES_URL, {
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

            const targetWp = availableProfiles.find(p => p.id === wpId);
            const targetMode = targetWp?.reasoning?.modes?.find(m => m.id === rmId)?.label || rmId || "Direct";
            announceStatus(`Модель: ${targetWp ? targetWp.name : wpId}, Режим: ${targetMode}`);

            withDOMUpdate(() => {
                mountOrUpdateNexusBar();
            });

            // Sync with upstream LLM profile button if present in conversation page
            if (activeState && activeState.resolved_llm_profile_name) {
                syncNativeComposerProfile(activeState.resolved_llm_profile_name);
            }
        } catch (err) {
            console.error("[NexusRemoteControl] Error switching profile:", err);
        } finally {
            isSubmitting = false;
            if (modelBtn) modelBtn.classList.remove("is-loading");
        }
    }

    // Sync upstream OpenHands profile if button exists
    function syncNativeComposerProfile(targetProfileName) {
        if (!targetProfileName || isTaskRunning()) return;
        const nativeBtn = document.querySelector('[data-testid="chat-input-llm-profile"]');
        if (!nativeBtn || nativeBtn.disabled) return;

        const currentAttr = nativeBtn.getAttribute("data-resolved-profile") || "";
        if (currentAttr === targetProfileName) return;

        let popover = document.querySelector('[data-testid="chat-input-llm-profile-popover"]');
        if (!popover) {
            nativeBtn.click();
        }

        setTimeout(() => {
            const option = document.querySelector(`[data-testid="chat-input-llm-profile-option-${targetProfileName}"]`);
            if (option) {
                option.click();
                nativeBtn.setAttribute("data-resolved-profile", targetProfileName);
            } else {
                const stillOpen = document.querySelector('[data-testid="chat-input-llm-profile-popover"]');
                if (stillOpen) nativeBtn.click();
            }
        }, 60);
    }

    // Agent Profile to Working Profile mapping for bidirectional synchronization
    const PROFILE_TO_WP = {
        "Team-Flagship": { wpId: "team-flagship", rmId: "medium" },
        "Team-Full": { wpId: "team-full", rmId: "medium" },
        "Team-Qwen-Ornith": { wpId: "team-qwen-ornith", rmId: "medium" },
        "Team-Qwen-Next": { wpId: "team-qwen-ornith", rmId: "medium" },
        "Team-Next-Ornith": { wpId: "team-flagship", rmId: "medium" },
        "Qwen-122B-ChatGPT-5.6-SOL": { wpId: "qwen122-solo", rmId: "high" },
        "Qwen122-Standalone": { wpId: "qwen122-solo", rmId: "direct" },
        "Ornith-Standalone": { wpId: "ornith-solo", rmId: "medium" },
        "Qwen-Standalone": { wpId: "qwen38-solo", rmId: "medium" },
        "Next-Normal-Standalone": { wpId: "next-solo", rmId: "medium" },
        "Next-Deep-Standalone": { wpId: "next-solo", rmId: "high" }
    };

    // Auto-sync Working Profile when user selects native agent profile in '+' menu
    document.addEventListener("click", (e) => {
        const optionBtn = e.target && e.target.closest && e.target.closest('[data-testid*="chat-input-agent-profile-option-"]');
        if (!optionBtn) return;
        const testId = optionBtn.getAttribute("data-testid") || "";
        const profileName = testId.replace("chat-input-agent-profile-option-", "").trim();
        if (PROFILE_TO_WP[profileName]) {
            const target = PROFILE_TO_WP[profileName];
            console.log(`[NexusRemoteControl] Native agent profile selected: "${profileName}" -> Auto-syncing working profile: "${target.wpId}" (mode: ${target.rmId})`);
            switchProfile(target.wpId, target.rmId);
        }
    }, true);

    // Telemetry logic
    function getTelemetryUrl() {
        const isSec = (window.location.protocol === "https:" || window.location.port === "8443");
        return isSec ? (window.location.origin + "/api/station-telemetry") : "http://127.0.0.1:18002/api/station-telemetry";
    }

    function formatTokenCount(num) {
        if (!num || isNaN(num)) return "0";
        if (num >= 1000) return (num / 1000).toFixed(1) + "k";
        return String(num);
    }

    async function pollTelemetry() {
        if (document.hidden) return;
        try {
            const url = getTelemetryUrl();
            const sep = url.includes("?") ? "&" : "?";
            const resp = await fetch(`${url}${sep}_ts=${Date.now()}`);
            if (!resp.ok) return;
            const data = await resp.json();
            withDOMUpdate(() => {
                updateTelemetryPill(data);
            });
        } catch (e) {}
    }

    function updateTelemetryPill(data) {
        cleanNativeExecutionButton();
        const pill = document.getElementById("oh-nexus-telemetry-pill");
        if (!pill) return;

        if (!data || data.state === "idle" || !data.is_active) {
            if (pill.dataset.state !== "idle") {
                pill.dataset.state = "idle";
                pill.className = "oh-nexus-telemetry-pill idle";
                pill.innerHTML = `
                    <span class="oh-telemetry-dot idle"></span>
                    <span class="oh-telemetry-text">Готов</span>
                `;
                let idleTitle = `Станция готова к работе · ${activeState?.active_working_profile_id || 'OpenHands'}`;
                if (data && data.last_gen_speed > 0) {
                    idleTitle += ` · Посл. генерация: ${data.last_gen_speed} т/с`;
                    if (data.last_prefill_speed > 0) {
                        idleTitle += ` (чтение: ${Math.round(data.last_prefill_speed)} т/с)`;
                    }
                }
                pill.setAttribute("title", idleTitle);
                pill.setAttribute("aria-label", idleTitle);
                lastTelemetryMilestone = -1;
            }
            return;
        }

        if (data.state === "loading") {
            pill.dataset.state = "loading";
            pill.className = "oh-nexus-telemetry-pill loading";
            pill.innerHTML = `
                <span class="oh-telemetry-dot loading"></span>
                <span class="oh-telemetry-text">Загрузка...</span>
            `;
            pill.setAttribute("title", "Загрузка весов модели в VRAM");
            pill.setAttribute("aria-label", "Загрузка модели в память");
        } else if (data.state === "prefill") {
            const pct = Math.min(100, Math.max(0, Math.round(data.progress_pct || 0)));
            const currentTokens = formatTokenCount(data.tokens);
            const totalTokens = formatTokenCount(data.total_tokens);
            const speed = data.speed_tok_s ? data.speed_tok_s.toFixed(0) : "0";
            const metaParts = [`${speed} т/с`];
            if (data.eta_str) {
                metaParts.push(`~${data.eta_str}`);
            }
            const metaDisplay = metaParts.join(" · ");

            pill.dataset.state = "prefill";
            pill.className = "oh-nexus-telemetry-pill prefill";
            pill.innerHTML = `
                <span class="oh-telemetry-dot prefill"></span>
                <span class="oh-telemetry-text">${pct}%</span>
                <span class="oh-telemetry-meta">${metaDisplay}</span>
            `;
            const etaAria = data.eta_str ? `, осталось ~${data.eta_str}` : '';
            const ariaText = `Загрузка контекста: ${pct}%, ${currentTokens} из ${totalTokens} токенов, скорость ${speed} т/с${etaAria}`;
            pill.setAttribute("title", ariaText);
            pill.setAttribute("aria-label", ariaText);

            const milestone = Math.floor(pct / 25) * 25;
            if (milestone > lastTelemetryMilestone && milestone > 0) {
                lastTelemetryMilestone = milestone;
                announceStatus(`Контекст ${milestone}%`);
            }
        } else if (data.state === "thinking") {
            pill.dataset.state = "thinking";
            pill.className = "oh-nexus-telemetry-pill thinking";
            pill.innerHTML = `
                <span class="oh-telemetry-dot thinking"></span>
                <span class="oh-telemetry-text">Мыслит...</span>
            `;
            pill.setAttribute("title", "Модель формирует цепочку рассуждений (reasoning)");
            pill.setAttribute("aria-label", "Размышление модели");
        } else if (data.state === "generating") {
            const speed = data.speed_tok_s ? data.speed_tok_s.toFixed(1) : "0";
            pill.dataset.state = "generating";
            pill.className = "oh-nexus-telemetry-pill generating";
            pill.innerHTML = `
                <span class="oh-telemetry-dot active"></span>
                <span class="oh-telemetry-text">${speed} т/с</span>
            `;
            pill.setAttribute("title", `Модель генерирует ответ со скоростью ${speed} токенов/сек`);
            pill.setAttribute("aria-label", `Генерация ответа: ${speed} токенов в секунду`);
        } else if (data.state === "tool") {
            const toolName = escapeHtml(data.active_tool || "инструмент");
            pill.dataset.state = "tool";
            pill.className = "oh-nexus-telemetry-pill tool";
            pill.innerHTML = `
                <span class="oh-telemetry-dot tool"></span>
                <span class="oh-telemetry-text">${toolName}</span>
            `;
            pill.setAttribute("title", `Выполнение инструмента: ${toolName}`);
            pill.setAttribute("aria-label", `Выполнение инструмента: ${toolName}`);
        }
    }

    let visibilityHandlerAttached = false;

    function startTelemetry() {
        stopTelemetry();
        pollTelemetry();
        telemetryInterval = setInterval(pollTelemetry, 1500);

        if (!visibilityHandlerAttached) {
            visibilityHandlerAttached = true;
            document.addEventListener("visibilitychange", () => {
                if (!document.hidden) {
                    pollTelemetry();
                }
            });
        }
    }

    function stopTelemetry() {
        if (telemetryInterval) {
            clearInterval(telemetryInterval);
            telemetryInterval = null;
        }
    }

    // Popover Management
    function closePopovers() {
        const p1 = document.getElementById("oh-nexus-model-popover");
        if (p1) p1.remove();
        const p2 = document.getElementById("oh-nexus-reasoning-popover");
        if (p2) p2.remove();

        const b1 = document.getElementById("oh-nexus-model-btn");
        if (b1) b1.setAttribute("aria-expanded", "false");
        const b2 = document.getElementById("oh-nexus-reasoning-btn");
        if (b2) b2.setAttribute("aria-expanded", "false");
    }

    function toggleModelPopover() {
        const existing = document.getElementById("oh-nexus-model-popover");
        if (existing) {
            closePopovers();
            return;
        }
        closePopovers();

        const btn = document.getElementById("oh-nexus-model-btn");
        if (!btn || btn.disabled || isTaskRunning()) return;

        const popover = document.createElement("div");
        popover.id = "oh-nexus-model-popover";
        popover.className = "oh-nexus-popover";
        popover.setAttribute("role", "listbox");
        popover.setAttribute("aria-label", "Выбор модели станции");

        const singleModels = availableProfiles.filter(p => p.kind === "single_model" || !p.kind.includes("chain"));
        const chainModels = availableProfiles.filter(p => p.kind.includes("chain"));

        function renderGroup(title, list) {
            let html = `<div class="oh-nexus-popover-section">
                <div class="oh-nexus-popover-section-title">${title} (${list.length})</div>`;
            for (const p of list) {
                const b = getKindBadge(p.kind);
                const isActive = p.id === activeState?.active_working_profile_id;
                const activeClass = isActive ? " active" : "";
                const checkHtml = isActive ? '<span class="oh-nexus-check">✓</span>' : '';

                html += `
                    <div class="oh-nexus-popover-item${activeClass}" data-wp-id="${escapeHtml(p.id)}" role="option" aria-selected="${isActive ? 'true' : 'false'}" tabindex="0">
                        <div class="oh-nexus-popover-row">
                            <span class="oh-nexus-popover-name">
                                <span>${escapeHtml(p.name)}</span>
                            </span>
                            <div class="flex items-center gap-1.5">
                                <span class="oh-nexus-badge ${b.class}">${b.text}</span>
                                ${checkHtml}
                            </div>
                        </div>
                        <div class="oh-nexus-popover-desc">${escapeHtml(p.description || "")}</div>
                    </div>
                `;
            }
            html += `</div>`;
            return html;
        }

        popover.innerHTML = `
            <div class="oh-nexus-popover-header">
                <span>Модели и связки станции</span>
                <span class="text-[11px] text-[var(--oh-text-muted,#71717a)]">4 Модели · 3 Связки</span>
            </div>
            <div class="oh-nexus-popover-list">
                ${renderGroup("МОДЕЛИ", singleModels)}
                ${renderGroup("СВЯЗКИ АГЕНТОВ", chainModels)}
            </div>
        `;

        document.body.appendChild(popover);
        btn.setAttribute("aria-expanded", "true");

        // Position popover
        positionPopover(popover, btn, 320);

        popover.querySelectorAll(".oh-nexus-popover-item").forEach(item => {
            item.addEventListener("click", (e) => {
                e.preventDefault();
                e.stopPropagation();
                const wpId = item.getAttribute("data-wp-id");
                const targetWp = availableProfiles.find(p => p.id === wpId);
                if (!targetWp) return;

                const defaultRmId = targetWp.reasoning?.default_mode_id || targetWp.reasoning?.modes?.[0]?.id || null;
                switchProfile(targetWp.id, defaultRmId);
                closePopovers();
            });
        });

        setTimeout(() => {
            document.addEventListener("click", handleOutsideClick, true);
        }, 50);
    }

    function toggleReasoningPopover() {
        const existing = document.getElementById("oh-nexus-reasoning-popover");
        if (existing) {
            closePopovers();
            return;
        }
        closePopovers();

        const btn = document.getElementById("oh-nexus-reasoning-btn");
        if (!btn || btn.disabled || isTaskRunning()) return;

        const currentWp = availableProfiles.find(p => p.id === activeState?.active_working_profile_id);
        if (!currentWp || !currentWp.reasoning?.supported) return;

        const modes = currentWp.reasoning.modes || [];
        const activeModeId = activeState?.active_reasoning_mode_id;

        const popover = document.createElement("div");
        popover.id = "oh-nexus-reasoning-popover";
        popover.className = "oh-nexus-popover";
        popover.setAttribute("role", "listbox");
        popover.setAttribute("aria-label", "Степень рассуждений");

        let itemsHtml = "";
        for (const m of modes) {
            const isSelected = m.id === activeModeId;
            const activeClass = isSelected ? " active" : "";
            const checkHtml = isSelected ? '<span class="oh-nexus-check">✓</span>' : '';
            itemsHtml += `
                <div class="oh-nexus-popover-item${activeClass}" data-mode-id="${escapeHtml(m.id)}" role="option" aria-selected="${isSelected ? 'true' : 'false'}" tabindex="0">
                    <div class="oh-nexus-popover-row">
                        <span class="oh-nexus-popover-name">${escapeHtml(m.label)}</span>
                        ${checkHtml}
                    </div>
                    <div class="oh-nexus-popover-desc">${escapeHtml(m.description || "")}</div>
                </div>
            `;
        }

        popover.innerHTML = `
            <div class="oh-nexus-popover-header">
                <span>Степень рассуждений (Thinking)</span>
            </div>
            <div class="oh-nexus-popover-list">
                ${itemsHtml}
            </div>
        `;

        document.body.appendChild(popover);
        btn.setAttribute("aria-expanded", "true");

        // Position popover
        positionPopover(popover, btn, 280);

        popover.querySelectorAll(".oh-nexus-popover-item").forEach(opt => {
            opt.addEventListener("click", (e) => {
                e.preventDefault();
                e.stopPropagation();
                const modeId = opt.getAttribute("data-mode-id");
                if (modeId && modeId !== activeState?.active_reasoning_mode_id) {
                    switchProfile(currentWp.id, modeId);
                }
                closePopovers();
            });
        });

        setTimeout(() => {
            document.addEventListener("click", handleOutsideClick, true);
        }, 50);
    }

    function positionPopover(popover, anchorBtn, widthPx) {
        const rect = anchorBtn.getBoundingClientRect();
        const vh = window.innerHeight || document.documentElement.clientHeight;
        const vw = window.innerWidth || document.documentElement.clientWidth;

        const spaceAbove = Math.max(0, rect.top - 16);
        const spaceBelow = Math.max(0, vh - rect.bottom - 16);

        // Desired content height (scroll height of popover content)
        const scrollH = popover.scrollHeight || 480;

        let top = 0;
        let maxHeight = 0;

        // If placed below, check if spaceBelow has enough room or more room than above
        if (spaceBelow >= 360 || spaceBelow >= spaceAbove) {
            top = rect.bottom + 8;
            maxHeight = spaceBelow - 8;
        } else {
            maxHeight = spaceAbove - 8;
            const actualH = Math.min(scrollH, maxHeight);
            top = rect.top - actualH - 8;
        }

        let left = rect.left;
        if (left + widthPx > vw - 10) {
            left = vw - widthPx - 10;
        }

        popover.style.top = `${Math.max(10, Math.round(top))}px`;
        popover.style.left = `${Math.max(10, Math.round(left))}px`;
        popover.style.width = `${widthPx}px`;
        popover.style.maxHeight = `${Math.max(160, Math.round(maxHeight))}px`;
    }

    function handleOutsideClick(e) {
        const p1 = document.getElementById("oh-nexus-model-popover");
        const p2 = document.getElementById("oh-nexus-reasoning-popover");
        const b1 = document.getElementById("oh-nexus-model-btn");
        const b2 = document.getElementById("oh-nexus-reasoning-btn");

        const clickedInside =
            (p1 && p1.contains(e.target)) ||
            (p2 && p2.contains(e.target)) ||
            (b1 && b1.contains(e.target)) ||
            (b2 && b2.contains(e.target));

        if (!clickedInside) {
            closePopovers();
            document.removeEventListener("click", handleOutsideClick, true);
        }
    }

    // Escape key closes popovers
    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape") {
            closePopovers();
        }
    });

    // Mount or update the unified Nexus Composer Bar
    function mountOrUpdateNexusBar() {
        if (!availableProfiles.length || !activeState) return;

        const chatInput = document.querySelector(".chat-input, [contenteditable='true'], textarea");
        if (!chatInput) return;

        const currentWp = availableProfiles.find(p => p.id === activeState.active_working_profile_id) || availableProfiles[0];
        const badgeInfo = getKindBadge(currentWp.kind);

        const reasoning = currentWp.reasoning || {};
        const isReasoningSupported = reasoning.supported && reasoning.modes && reasoning.modes.length > 0;
        const modes = isReasoningSupported ? reasoning.modes : [];
        const activeModeId = activeState.active_reasoning_mode_id || (modes[0] ? modes[0].id : "");
        const activeModeObj = modes.find(m => m.id === activeModeId) || modes[0];
        const running = isTaskRunning();

        // 1. Locate the best mount container in the composer
        let composerCard = chatInput.closest("form, [class*='rounded-[15px]'], [class*='rounded-xl'], [class*='border-t']");
        if (!composerCard) composerCard = chatInput.parentElement;

        let actionsRow = composerCard.querySelector('[data-testid="chat-input-actions"]');
        if (!actionsRow) {
            actionsRow = composerCard.querySelector('div.flex.items-center.justify-between, div.flex.w-full.items-center');
        }

        // 2. Ensure #oh-nexus-bar exists
        let bar = document.getElementById("oh-nexus-bar");
        if (!bar) {
            bar = document.createElement("div");
            bar.id = "oh-nexus-bar";
            bar.className = "oh-nexus-bar";
            bar.innerHTML = `
                <button id="oh-nexus-model-btn" class="oh-nexus-btn" type="button" aria-haspopup="listbox" aria-expanded="false" title="Нажмите для выбора модели станции">
                    <span class="oh-nexus-model-name"></span>
                    <span class="oh-nexus-badge" style="display: none;"></span>
                    <svg class="oh-nexus-chevron" viewBox="0 0 20 20" width="14" height="14" fill="currentColor">
                        <path fill-rule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clip-rule="evenodd"/>
                    </svg>
                </button>
                <button id="oh-nexus-reasoning-btn" class="oh-nexus-btn" type="button" aria-haspopup="listbox" aria-expanded="false">
                    <span class="oh-nexus-reasoning-label"></span>
                    <svg class="oh-nexus-chevron" viewBox="0 0 20 20" width="14" height="14" fill="currentColor">
                        <path fill-rule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clip-rule="evenodd"/>
                    </svg>
                </button>
                <div id="oh-nexus-telemetry-pill" class="oh-nexus-telemetry-pill idle" role="status" aria-live="polite">
                    <span class="oh-telemetry-dot idle"></span>
                    <span class="oh-telemetry-text">Готов</span>
                </div>
            `;

            // Attach click handlers
            const mBtn = bar.querySelector("#oh-nexus-model-btn");
            mBtn.addEventListener("click", (e) => {
                e.preventDefault();
                e.stopPropagation();
                toggleModelPopover();
            });

            const rBtn = bar.querySelector("#oh-nexus-reasoning-btn");
            rBtn.addEventListener("click", (e) => {
                e.preventDefault();
                e.stopPropagation();
                toggleReasoningPopover();
            });
        }

        // Enforce strict inline styles so it can never wrap or distort
        bar.style.display = "inline-flex";
        bar.style.alignItems = "center";
        bar.style.flexWrap = "nowrap";
        bar.style.whiteSpace = "nowrap";
        bar.style.gap = "5px";
        bar.style.flexShrink = "0";
        bar.style.margin = "0";
        bar.style.overflow = "visible";

        // 3. Mount into DOM: Place next to plus button inside left container
        if (actionsRow) {
            const plusBtn = composerCard.querySelector('[data-testid="chat-plus-button"]');
            let placed = false;

            if (plusBtn) {
                let leftCol = plusBtn;
                while (leftCol && leftCol.parentElement && leftCol.parentElement !== actionsRow) {
                    leftCol = leftCol.parentElement;
                }

                if (leftCol && leftCol.parentElement === actionsRow) {
                    leftCol.style.flexShrink = "0";
                    leftCol.style.minWidth = "0";
                    leftCol.style.display = "flex";
                    leftCol.style.alignItems = "center";
                    leftCol.style.gap = "6px";

                    const plusParent = plusBtn.parentElement;
                    const plusBox = plusParent ? plusParent.parentElement : null;
                    const innerFlex = plusBox ? plusBox.parentElement : null;

                    if (plusParent) plusParent.style.flexShrink = "0";
                    plusBtn.style.flexShrink = "0";
                    plusBtn.style.margin = "0";

                    if (innerFlex && innerFlex.contains(plusBox)) {
                        innerFlex.style.display = "flex";
                        innerFlex.style.alignItems = "center";
                        innerFlex.style.flexWrap = "nowrap";
                        innerFlex.style.flexShrink = "0";
                        innerFlex.style.minWidth = "0";
                        innerFlex.style.overflow = "visible";
                        innerFlex.style.gap = "5px";

                        if (plusBox && plusBox.parentElement === innerFlex) {
                            if (bar.parentElement !== innerFlex || bar.previousElementSibling !== plusBox) {
                                plusBox.after(bar);
                            }
                            placed = true;
                        }
                    }

                    if (!placed) {
                        if (bar.parentElement !== leftCol) {
                            leftCol.appendChild(bar);
                        }
                        placed = true;
                    }
                }
            }

            if (!placed) {
                const rightContainer = actionsRow.lastElementChild;
                if (bar.parentElement !== actionsRow) {
                    if (rightContainer && rightContainer !== bar) {
                        actionsRow.insertBefore(bar, rightContainer);
                    } else {
                        actionsRow.appendChild(bar);
                    }
                }
            }
        } else {
            if (bar.parentElement !== composerCard) {
                chatInput.after(bar);
            }
        }

        // 4. Update Model button state
        const modelBtn = document.getElementById("oh-nexus-model-btn");
        if (modelBtn) {
            const nameEl = modelBtn.querySelector(".oh-nexus-model-name");
            if (nameEl && nameEl.textContent !== currentWp.name) {
                nameEl.textContent = currentWp.name;
            }
            const badgeEl = modelBtn.querySelector(".oh-nexus-badge");
            if (badgeEl) {
                const isChain = currentWp.kind && currentWp.kind.includes("chain");
                if (isChain) {
                    if (badgeEl.textContent !== badgeInfo.text) badgeEl.textContent = badgeInfo.text;
                    badgeEl.className = `oh-nexus-badge ${badgeInfo.class}`;
                    badgeEl.style.display = "";
                } else {
                    badgeEl.style.display = "none";
                }
            }
            modelBtn.disabled = running;
            modelBtn.setAttribute("aria-disabled", running ? "true" : "false");
            modelBtn.setAttribute("title", `Модель станции: ${currentWp.name}${currentWp.kind.includes("chain") ? ' (' + badgeInfo.text + ')' : ''}`);
        }

        // 5. Update Reasoning button state
        const reasoningBtn = document.getElementById("oh-nexus-reasoning-btn");
        if (reasoningBtn) {
            const rLabel = reasoningBtn.querySelector(".oh-nexus-reasoning-label");
            const rChevron = reasoningBtn.querySelector(".oh-nexus-chevron");

            if (isReasoningSupported && activeModeObj) {
                const shortLabel = activeModeObj.label.split(" ")[0] || activeModeObj.label;
                if (rLabel && rLabel.textContent !== shortLabel) rLabel.textContent = shortLabel;
                if (rChevron) rChevron.style.display = "";

                reasoningBtn.disabled = running;
                reasoningBtn.classList.remove("disabled");
                reasoningBtn.setAttribute("aria-disabled", running ? "true" : "false");
                reasoningBtn.setAttribute("title", `Степень рассуждения: ${activeModeObj.label} (${activeModeObj.description || ""})`);
                reasoningBtn.setAttribute("aria-label", `Степень рассуждения: ${activeModeObj.label}`);
            } else {
                if (rLabel && rLabel.textContent !== "Direct") rLabel.textContent = "Direct";
                if (rChevron) rChevron.style.display = "none";

                reasoningBtn.disabled = true;
                reasoningBtn.classList.add("disabled");
                reasoningBtn.setAttribute("aria-disabled", "true");
                reasoningBtn.setAttribute("title", "Данная модель работает напрямую без скрытых рассуждений (Direct Mode)");
                reasoningBtn.setAttribute("aria-label", "Рассуждения не поддерживаются моделью (Direct Mode)");
            }
        }

        // Hide redundant native LLM profile button to avoid UI clutter and confusion
        const nativeLlmBtn = document.querySelector('[data-testid="chat-input-llm-profile"]');
        if (nativeLlmBtn && nativeLlmBtn.style.display !== "none") {
            nativeLlmBtn.style.display = "none";
        }

        // Clean native execution state controller: hide text label ('Выполняется' / 'Остановлено'), keeping only pause/play icon
        cleanNativeExecutionButton();
    }

    function cleanNativeExecutionButton() {
        const execBtn = document.querySelector('button[data-testid="stop-button"], button[data-testid="play-button"]');
        if (execBtn) {
            const container = execBtn.closest('.flex.items-center.gap-1') || (execBtn.parentElement ? execBtn.parentElement.parentElement : null);
            if (container) {
                container.style.gap = '0px';
                container.style.minWidth = '28px';
                container.style.width = '28px';
                container.style.flexShrink = '0';
                const spans = container.querySelectorAll('span');
                spans.forEach(s => {
                    if (s.style.display !== 'none') s.style.display = 'none';
                });
            }
        }
    }

    // Set up throttled MutationObserver with strict reentrancy protection
    function setupObserver() {
        if (observer) {
            try { observer.disconnect(); } catch (e) {}
        }

        let debounceTimer = null;

        observer = new MutationObserver((mutations) => {
            if (isMutatingDOM) return;

            let shouldUpdate = false;
            for (const m of mutations) {
                // Ignore mutations occurring inside our own custom elements
                const target = m.target;
                if (target && target.closest && (
                    target.closest("#oh-nexus-bar") ||
                    target.closest("#oh-nexus-model-popover") ||
                    target.closest("#oh-nexus-reasoning-popover") ||
                    target.closest("#oh-nexus-announcer")
                )) {
                    continue;
                }

                // If nodes were added or removed, or chat input appeared
                if (m.type === "childList") {
                    shouldUpdate = true;
                    break;
                }
            }

            if (!shouldUpdate) return;

            if (debounceTimer) clearTimeout(debounceTimer);
            debounceTimer = setTimeout(() => {
                withDOMUpdate(() => {
                    mountOrUpdateNexusBar();
                });
            }, 120);
        });

        observer.observe(document.body, { childList: true, subtree: true });

        window.addEventListener("beforeunload", () => {
            try { observer.disconnect(); } catch (e) {}
            stopTelemetry();
        });
    }

    // Visibility API support (battery saver for tablets & mobile)
    let syncInterval = null;

    function startSyncPolling() {
        stopSyncPolling();
        syncInterval = setInterval(() => {
            if (document.hidden) return;
            loadWorkingProfiles(true);
        }, 3000);
    }

    function stopSyncPolling() {
        if (syncInterval) {
            clearInterval(syncInterval);
            syncInterval = null;
        }
    }

    document.addEventListener("visibilitychange", () => {
        if (document.hidden) {
            stopSyncPolling();
            stopTelemetry();
        } else {
            startSyncPolling();
            startTelemetry();
            loadWorkingProfiles(true);
        }
    });

    window.addEventListener("focus", () => {
        if (!document.hidden) {
            startSyncPolling();
            startTelemetry();
            loadWorkingProfiles(true);
        }
    });

    // Startup initialization
    async function init() {
        await loadWorkingProfiles(false);
        setupObserver();
        startTelemetry();
        startSyncPolling();
        withDOMUpdate(() => {
            mountOrUpdateNexusBar();
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();