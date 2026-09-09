/**
 * OpenHands Local Voice Bridge - Client Extension
 * Stage 4.1: Seamless Composer-Integrated Voice & Dual-Engine TTS
 * 
 * Location: K:\Project\local-voice\voice-bridge.js
 * 100% offline & local. Non-blocking UI layout.
 */

(function () {
    console.log("[VoiceBridge] Initializing Stage 4.1 Composer Voice UI & Dual TTS...");

    const VOICE_API = (window.location.protocol === "https:" || window.location.port === "8443")
        ? `${window.location.origin}/voice-api`
        : "http://127.0.0.1:18002";

    let mediaRecorder = null;
    let audioChunks = [];
    let isRecording = false;
    let currentAudio = null;
    let currentTtsAbortController = null;
    let lastSpokenMessageId = null;
    let availableVoices = [];
    let isPopoverOpen = false;
    let activeMediaStream = null;

    const isMobileDevice = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent) ||
        (window.innerWidth <= 768 && ("ontouchstart" in window || navigator.maxTouchPoints > 0));

    const savedTtsMode = localStorage.getItem("oh_voice_tts_mode");
    const defaultTtsMode = isMobileDevice ? "native" : "supertonic";

    const config = {
        autoSend: localStorage.getItem("oh_voice_auto_send") === "true",
        ttsMode: savedTtsMode || defaultTtsMode,
        voiceStyle: localStorage.getItem("oh_voice_style") || "M1",
        speechRate: parseFloat(localStorage.getItem("oh_voice_rate") || "1.0")
    };

    function saveConfig() {
        localStorage.setItem("oh_voice_auto_send", config.autoSend);
        localStorage.setItem("oh_voice_tts_mode", config.ttsMode);
        localStorage.setItem("oh_voice_style", config.voiceStyle);
        localStorage.setItem("oh_voice_rate", config.speechRate);
    }

    function triggerHaptic(pattern) {
        if ("vibrate" in navigator) {
            try { navigator.vibrate(pattern); } catch (e) {}
        }
    }

    function updatePillStatus(text, state = "idle") {
        const pill = document.getElementById("oh-voice-pill");
        const statusText = document.getElementById("oh-voice-pill-text");
        if (pill && statusText) {
            statusText.textContent = text;
            pill.className = `oh-voice-pill ${state}`;
        }
    }

    function cleanTextForSpeech(text) {
        if (!text) return "";
        let clean = text;
        clean = clean.replace(/<think>[\s\S]*?<\/think>/gi, "");
        clean = clean.replace(/```[\s\S]*?```/g, " Код опущен. ");
        clean = clean.replace(/`([^`]+)`/g, "$1");
        clean = clean.replace(/\[([^\]]+)\]\([^)]+\)/g, "$1");
        clean = clean.replace(/^#{1,6}\s*/gm, "");
        clean = clean.replace(/^[\*\-\+]\s+/gm, "");
        clean = clean.replace(/[*_~`]/g, "");
        clean = clean.replace(/\s+/g, " ").trim();
        return clean;
    }

    function stopSpeech(notifyServer = true) {
        if (isRecording) {
            stopRecording();
        }
        if ("speechSynthesis" in window) {
            try { window.speechSynthesis.cancel(); } catch (e) {}
        }
        if (currentAudio) {
            try {
                currentAudio.pause();
                currentAudio.currentTime = 0;
                currentAudio.src = "";
            } catch (e) {}
            currentAudio = null;
        }
        if (currentTtsAbortController) {
            try { currentTtsAbortController.abort(); } catch (e) {}
            currentTtsAbortController = null;
        }
        if (notifyServer) {
            fetch(`${VOICE_API}/stop`, { method: "POST" }).catch(() => {});
        }
        updatePillStatus("Голос готов", "idle");
        document.querySelectorAll(".oh-tts-speak-btn.speaking").forEach(b => b.classList.remove("speaking"));
    }

    // -------------------------------------------------------------
    // STT Recording
    // -------------------------------------------------------------
    async function startRecording() {
        stopSpeech(true);
        triggerHaptic([60]);

        try {
            const stream = await navigator.mediaDevices.getUserMedia({
                audio: { channelCount: 1, sampleRate: 16000, echoCancellation: true, noiseSuppression: true }
            });
            activeMediaStream = stream;

            audioChunks = [];
            mediaRecorder = new MediaRecorder(stream);

            mediaRecorder.ondataavailable = (e) => {
                if (e.data && e.data.size > 0) audioChunks.push(e.data);
            };

            mediaRecorder.onstop = async () => {
                if (activeMediaStream) {
                    try {
                        activeMediaStream.getTracks().forEach(t => t.stop());
                    } catch (e) {}
                    activeMediaStream = null;
                }
                if (audioChunks.length === 0) {
                    updatePillStatus("Голос готов", "idle");
                    return;
                }

                updatePillStatus("Распознавание...", "recognizing");
                const audioBlob = new Blob(audioChunks, { type: mediaRecorder.mimeType || "audio/webm" });

                try {
                    const resp = await fetch(`${VOICE_API}/stt`, {
                        method: "POST",
                        headers: { "Content-Type": audioBlob.type },
                        body: audioBlob
                    });

                    if (resp.ok) {
                        const data = await resp.json();
                        const recognizedText = data.text ? data.text.trim() : "";
                        if (recognizedText) {
                            insertTextIntoInput(recognizedText);
                            triggerHaptic([30, 30]);
                            if (config.autoSend) {
                                setTimeout(triggerSendMessage, 250);
                            }
                        }
                    } else {
                        updatePillStatus("Ошибка STT", "error");
                    }
                } catch (err) {
                    console.error("[VoiceBridge] STT fetch failed:", err);
                    updatePillStatus("Ошибка связи", "error");
                } finally {
                    updatePillStatus("Голос готов", "idle");
                    setMicButtonState(false);
                }
            };

            mediaRecorder.start(250);
            isRecording = true;
            setMicButtonState(true);
            updatePillStatus("Запись...", "recording");

        } catch (err) {
            if (activeMediaStream) {
                try {
                    activeMediaStream.getTracks().forEach(t => t.stop());
                } catch (e) {}
                activeMediaStream = null;
            }
            console.error("[VoiceBridge] Mic error:", err);
            triggerHaptic([100, 50, 100]);
            updatePillStatus("Ошибка микрофона", "error");
            setMicButtonState(false);
        }
    }

    function stopRecording() {
        if (mediaRecorder && mediaRecorder.state !== "inactive") {
            try {
                mediaRecorder.stop();
            } catch (e) {}
        }
        if (activeMediaStream && (!mediaRecorder || mediaRecorder.state === "inactive")) {
            try {
                activeMediaStream.getTracks().forEach(t => t.stop());
            } catch (e) {}
            activeMediaStream = null;
        }
        isRecording = false;
        triggerHaptic([40, 40]);
        setMicButtonState(false);
    }

    function setMicButtonState(recording) {
        const micBtn = document.getElementById("oh-composer-mic-btn");
        if (micBtn) {
            if (recording) {
                micBtn.classList.add("recording");
                micBtn.setAttribute("aria-label", "Остановить запись голоса");
                micBtn.setAttribute("aria-pressed", "true");
            } else {
                micBtn.classList.remove("recording");
                micBtn.setAttribute("aria-label", "Голосовой ввод (Микрофон)");
                micBtn.setAttribute("aria-pressed", "false");
            }
        }
    }

    function findChatInput() {
        return document.querySelector(".chat-input, [contenteditable='true'], textarea, input[type='text']");
    }

    function insertTextIntoInput(text) {
        const input = findChatInput();
        if (!input) {
            console.warn("[VoiceBridge] No chat input found.");
            return;
        }

        input.focus();

        if (input.isContentEditable || input.getAttribute("contenteditable") === "true") {
            const range = document.createRange();
            const sel = window.getSelection();
            range.selectNodeContents(input);
            range.collapse(false);
            sel.removeAllRanges();
            sel.addRange(range);

            const existing = input.innerText ? input.innerText.trim() : "";
            const insertStr = existing ? ` ${text}` : text;
            const success = document.execCommand("insertText", false, insertStr);

            if (!success) {
                input.innerText = existing ? `${existing} ${text}` : text;
            }
            input.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: insertStr }));
            input.dispatchEvent(new Event("change", { bubbles: true }));
        } else {
            const existing = input.value ? input.value.trim() : "";
            const combined = existing ? `${existing} ${text}` : text;
            const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value")?.set
                || Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value")?.set;

            if (nativeSetter) {
                nativeSetter.call(input, combined);
            } else {
                input.value = combined;
            }
            input.dispatchEvent(new Event("input", { bubbles: true }));
            input.dispatchEvent(new Event("change", { bubbles: true }));
        }
    }

    function triggerSendMessage() {
        const input = findChatInput();
        const composerRoot = input ? (input.closest("div[class*='rounded'], form") || input.parentElement.parentElement) : document;
        const sendBtn = composerRoot ? composerRoot.querySelector("button:last-child") : null;

        if (sendBtn && !sendBtn.disabled) {
            sendBtn.click();
            return;
        }
        if (input) {
            const enterEvent = new KeyboardEvent("keydown", { key: "Enter", code: "Enter", keyCode: 13, which: 13, bubbles: true });
            input.dispatchEvent(enterEvent);
        }
    }

    // -------------------------------------------------------------
    // TTS Engines: Android Native & Supertonic
    // -------------------------------------------------------------
    function getRussianVoice() {
        if (!availableVoices || availableVoices.length === 0) {
            if ("speechSynthesis" in window) availableVoices = window.speechSynthesis.getVoices();
        }
        return availableVoices.find(v => {
            const l = (v.lang || "").toLowerCase().replace("_", "-");
            return l === "ru-ru" || l.startsWith("ru");
        });
    }

    function playNativeTts(text, onComplete) {
        if (!("speechSynthesis" in window)) {
            updatePillStatus("Native TTS недоступен", "error");
            if (onComplete) onComplete();
            return;
        }

        stopSpeech(true);
        const cleanText = cleanTextForSpeech(text);
        if (!cleanText) {
            if (onComplete) onComplete();
            return;
        }

        const utterance = new SpeechSynthesisUtterance(cleanText);
        utterance.lang = "ru-RU";
        utterance.rate = config.speechRate || 1.0;

        const ruVoice = getRussianVoice();
        if (ruVoice) utterance.voice = ruVoice;

        utterance.onstart = () => updatePillStatus("Озвучка (Samsung TTS)...", "speaking");
        utterance.onend = () => {
            updatePillStatus("Голос готов", "idle");
            if (onComplete) onComplete();
        };
        utterance.onerror = (e) => {
            updatePillStatus("Голос готов", "idle");
            if (onComplete) onComplete();
        };

        window.speechSynthesis.speak(utterance);
    }

    async function playSupertonicTts(text, onComplete) {
        stopSpeech(true);
        const cleanText = cleanTextForSpeech(text);
        if (!cleanText) {
            if (onComplete) onComplete();
            return;
        }

        currentTtsAbortController = new AbortController();
        updatePillStatus("Озвучка (Supertonic)...", "speaking");

        try {
            const resp = await fetch(`${VOICE_API}/tts`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ text: cleanText, voice: config.voiceStyle }),
                signal: currentTtsAbortController.signal
            });

            if (!resp.ok) {
                updatePillStatus("Голос готов", "idle");
                if (onComplete) onComplete();
                return;
            }

            const audioBlob = await resp.blob();
            if (audioBlob.size === 0) {
                updatePillStatus("Голос готов", "idle");
                if (onComplete) onComplete();
                return;
            }

            const audioUrl = URL.createObjectURL(audioBlob);
            currentAudio = new Audio(audioUrl);

            currentAudio.onplay = () => updatePillStatus("Озвучка (Supertonic)...", "speaking");
            currentAudio.onended = () => {
                URL.revokeObjectURL(audioUrl);
                currentAudio = null;
                updatePillStatus("Голос готов", "idle");
                if (onComplete) onComplete();
            };
            currentAudio.onerror = () => {
                URL.revokeObjectURL(audioUrl);
                currentAudio = null;
                updatePillStatus("Голос готов", "idle");
                if (onComplete) onComplete();
            };

            await currentAudio.play();

        } catch (err) {
            if (err.name !== "AbortError") console.error("[VoiceBridge] Supertonic error:", err);
            updatePillStatus("Голос готов", "idle");
            if (onComplete) onComplete();
        }
    }

    function playTts(text, onComplete) {
        if (config.ttsMode === "off") {
            if (onComplete) onComplete();
            return;
        } else if (config.ttsMode === "native") {
            playNativeTts(text, onComplete);
        } else if (config.ttsMode === "supertonic") {
            playSupertonicTts(text, onComplete);
        }
    }

    // -------------------------------------------------------------
    // Inject Mic Button into Composer
    // -------------------------------------------------------------
    function injectComposerMic() {
        const input = findChatInput();
        if (!input) return;

        const composerRoot = input.closest("div[class*='rounded'], form") || input.parentElement.parentElement;
        const rightActions = composerRoot ? composerRoot.querySelector(".ml-auto") : null;
        if (!rightActions) return;

        if (document.getElementById("oh-composer-mic-btn")) return;

        const micBtn = document.createElement("button");
        micBtn.id = "oh-composer-mic-btn";
        micBtn.type = "button";
        micBtn.setAttribute("aria-label", "Голосовой ввод (Микрофон)");
        micBtn.setAttribute("aria-pressed", "false");
        micBtn.setAttribute("title", "Голосовой ввод");
        if (input && !input.getAttribute("aria-label")) {
            input.setAttribute("aria-label", "Сообщение для OpenHands");
        }
        micBtn.innerHTML = `
            <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
                <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z"/>
                <path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z"/>
            </svg>
        `;

        micBtn.addEventListener("click", (e) => {
            e.preventDefault();
            e.stopPropagation();
            if (isRecording) {
                stopRecording();
            } else {
                startRecording();
            }
        });

        // Insert immediately before the Send button (last child of rightActions)
        rightActions.insertBefore(micBtn, rightActions.lastElementChild);
    }

    // -------------------------------------------------------------
    // Inject Speaker Buttons on Assistant Messages
    // -------------------------------------------------------------
    function injectSpeakerButtons() {
        const agentArticles = document.querySelectorAll("article[data-testid='agent-message']");
        agentArticles.forEach((art) => {
            if (art.querySelector(".oh-tts-speak-btn")) return;

            const speakBtn = document.createElement("button");
            speakBtn.className = "oh-tts-speak-btn";
            speakBtn.type = "button";
            speakBtn.setAttribute("aria-label", "Озвучить этот ответ");
            speakBtn.setAttribute("title", "Озвучить ответ (TTS)");
            speakBtn.innerHTML = `
                <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
                    <path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"/>
                </svg>
            `;

            speakBtn.addEventListener("click", (e) => {
                e.preventDefault();
                e.stopPropagation();

                if (speakBtn.classList.contains("speaking")) {
                    stopSpeech(true);
                    speakBtn.classList.remove("speaking");
                    return;
                }

                document.querySelectorAll(".oh-tts-speak-btn.speaking").forEach(b => b.classList.remove("speaking"));
                speakBtn.classList.add("speaking");

                const clean = cleanTextForSpeech(art.innerText || art.textContent);
                playTts(clean, () => {
                    speakBtn.classList.remove("speaking");
                });
            });

            // Find a good spot in the article (e.g. inside header or near actions)
            const actionsRow = art.querySelector(".flex.items-center.gap-1, .flex.gap-2") || art;
            actionsRow.appendChild(speakBtn);
        });
    }

    // -------------------------------------------------------------
    // Floating Status Pill & Settings Popover
    // -------------------------------------------------------------
    function createFloatingWidget() {
        if (document.getElementById("oh-voice-pill")) return;

        // 1. Floating pill
        const pill = document.createElement("div");
        pill.id = "oh-voice-pill";
        pill.className = "oh-voice-pill idle";
        pill.setAttribute("role", "status");
        pill.setAttribute("aria-live", "polite");
        pill.setAttribute("title", "Настройки голосового управления и статус");
        pill.innerHTML = `
            <span class="oh-voice-pill-dot"></span>
            <span id="oh-voice-pill-text">Голос готов</span>
        `;

        pill.addEventListener("click", () => {
            if (pill.classList.contains("speaking")) {
                stopSpeech(true);
            } else {
                togglePopover();
            }
        });

        // 2. Settings popover
        const popover = document.createElement("div");
        popover.id = "oh-voice-popover";
        popover.className = "oh-voice-popover";
        popover.style.display = "none";
        popover.setAttribute("role", "dialog");
        popover.setAttribute("aria-label", "Настройки голосового ввода");
        popover.innerHTML = `
            <div class="oh-voice-popover-header">
                <span class="oh-voice-popover-title">🎙️ Голосовой ввод и озвучка</span>
                <button type="button" class="oh-voice-popover-close" id="oh-voice-close-btn">&times;</button>
            </div>
            <div class="oh-voice-field">
                <label for="oh-voice-popover-mode">Режим озвучки (TTS):</label>
                <select id="oh-voice-popover-mode">
                    <option value="native" ${config.ttsMode === "native" ? "selected" : ""}>Системный Android TTS (Samsung TTS)</option>
                    <option value="supertonic" ${config.ttsMode === "supertonic" ? "selected" : ""}>Supertonic LAN TTS (Сервер)</option>
                    <option value="off" ${config.ttsMode === "off" ? "selected" : ""}>Озвучка выключена</option>
                </select>
            </div>
            <label class="oh-voice-checkbox-row">
                <input type="checkbox" id="oh-voice-popover-autosend" ${config.autoSend ? "checked" : ""}>
                <span>Автоотправка после диктовки</span>
            </label>
            <div class="oh-voice-stop-btn-row">
                <button type="button" class="oh-voice-stop-action-btn" id="oh-voice-stop-action">⏹ Прервать озвучку</button>
            </div>
        `;

        document.body.appendChild(pill);
        document.body.appendChild(popover);

        document.getElementById("oh-voice-close-btn").addEventListener("click", () => togglePopover(false));
        document.getElementById("oh-voice-popover-mode").addEventListener("change", (e) => {
            config.ttsMode = e.target.value;
            saveConfig();
            if (config.ttsMode === "off") stopSpeech(true);
        });
        document.getElementById("oh-voice-popover-autosend").addEventListener("change", (e) => {
            config.autoSend = e.target.checked;
            saveConfig();
        });
        document.getElementById("oh-voice-stop-action").addEventListener("click", () => {
            stopSpeech(true);
            togglePopover(false);
        });

        // Close when clicking outside
        document.addEventListener("click", (e) => {
            if (isPopoverOpen && !popover.contains(e.target) && !pill.contains(e.target)) {
                togglePopover(false);
            }
        });

        // Virtual keyboard adaptation
        if (window.visualViewport) {
            window.visualViewport.addEventListener("resize", () => {
                const isKb = window.visualViewport.height < (window.innerHeight - 150);
                if (isKb) {
                    pill.classList.add("keyboard-hidden");
                    togglePopover(false);
                } else {
                    pill.classList.remove("keyboard-hidden");
                }
            });
        }
    }

    function togglePopover(force) {
        const popover = document.getElementById("oh-voice-popover");
        if (!popover) return;
        isPopoverOpen = force !== undefined ? force : (popover.style.display === "none");
        popover.style.display = isPopoverOpen ? "flex" : "none";
    }

    // -------------------------------------------------------------
    // Assistant Observer
    // -------------------------------------------------------------
    function observeAssistantMessages() {
        let debounceTimer = null;
        const observer = new MutationObserver(() => {
            if (debounceTimer) clearTimeout(debounceTimer);
            debounceTimer = setTimeout(() => {
                injectComposerMic();
                injectSpeakerButtons();

                // Auto-speak new assistant messages if TTS enabled
                if (config.ttsMode !== "off") {
                    const messages = document.querySelectorAll("article[data-testid='agent-message']");
                    if (messages.length > 0) {
                        const lastMsg = messages[messages.length - 1];
                        const msgId = lastMsg.getAttribute("data-message-id") || lastMsg.textContent.slice(0, 40);
                        if (msgId !== lastSpokenMessageId) {
                            const isStreaming = lastMsg.querySelector(".typing-cursor, [data-streaming='true'], .loading-spinner");
                            if (!isStreaming) {
                                const clean = cleanTextForSpeech(lastMsg.innerText || lastMsg.textContent);
                                if (clean && clean.length > 3) {
                                    lastSpokenMessageId = msgId;
                                    playTts(clean);
                                }
                            }
                        }
                    }
                }
            }, 150);
        });

        observer.observe(document.body, { childList: true, subtree: true });
    }

    // Health check
    fetch(`${VOICE_API}/health`)
        .then(r => r.json())
        .then(() => updatePillStatus("Голос готов", "idle"))
        .catch(() => updatePillStatus("Голос офлайн", "error"));

    function setup() {
        if ("speechSynthesis" in window) {
            availableVoices = window.speechSynthesis.getVoices();
            window.speechSynthesis.onvoiceschanged = () => {
                availableVoices = window.speechSynthesis.getVoices();
            };
        }
        createFloatingWidget();
        injectComposerMic();
        injectSpeakerButtons();
        observeAssistantMessages();
    }

    // Ensure microphone stream is released on navigation or page close
    window.addEventListener("beforeunload", () => {
        if (activeMediaStream) {
            try {
                activeMediaStream.getTracks().forEach(t => t.stop());
            } catch (e) {}
            activeMediaStream = null;
        }
    });
    window.addEventListener("pagehide", () => {
        if (activeMediaStream) {
            try {
                activeMediaStream.getTracks().forEach(t => t.stop());
            } catch (e) {}
            activeMediaStream = null;
        }
    });

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", setup);
    } else {
        setup();
    }
})();
