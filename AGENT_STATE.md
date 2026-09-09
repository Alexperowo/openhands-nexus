OBJECTIVE:      OpenHands Nexus — Remote Control & Working Profile UI Unification
PHASE:          Conversation-Level Model Switching & Dynamic Turn Lock Complete (PASS)
STATE:          Unified Working Profile card across root (/) and conversation (/conversations/<id>) pages. Removed artificial locked drawer banner. Implemented dynamic active-task turn locking: selectors disabled and sync status pulses amber (⏳ Выполняется...) during task execution; selectors re-enabled and full model switching restored between conversation turns without starting a new chat. Full bidirectional synchronization with composer model picker.
DONE:
  - Unified Card Layout: Replaced in-flight locked banner and accordion drawer with the standard high-contrast, responsive Working Profile card mounted above the prompt composer in both root and active conversations.
  - Dynamic Turn Lock: Added isTaskRunning() detection (monitoring stop buttons, streaming indicators, spinners, and disabled input states). During task execution, selectors are disabled, card receives .is-running class, and status displays amber pulsing "⏳ Выполняется...".
  - In-Conversation Switching: After turn completion, selectors immediately re-enable, allowing seamless switching of working profiles and reasoning/thinking modes between turns within the same conversation.
  - Universal Composer Sync: Made syncComposerLlmProfile() and setupComposerPickerWatcher() universal across root and conversation pages, maintaining bidirectional sync with OpenHands' native dropdown.
  - Observer & Polling Hardening: MutationObserver and 3s periodic polling now track taskRunningChanged to trigger dynamic re-render on execution start and finish.
  - CSS Cleanup: Removed obsolete .oh-wp-conv-* drawer classes; added .is-running, .oh-wp-sync-indicator.running (amber pulse), and disabled selector styling.
  - Patcher Verification: Successfully re-applied patch-agent-canvas-working-profile.ps1 with exit code 0.
EVIDENCE:
  - Syntax verification: node --check openhands-working-profile/working-profile-ui.js -> exit code 0.
  - CSS bracket parity: python bracket balance check (77 open, 77 close) -> OK.
  - Patcher execution: powershell -ExecutionPolicy Bypass -File .\openhands-working-profile\patch-agent-canvas-working-profile.ps1 -> exit code 0.
  - Clean working tree: 0 extraneous files, 0 secrets/tokens exposed.
OPEN_ISSUES:    None
NEXT_ACTION:    Commit changes to master and push to origin/master.

