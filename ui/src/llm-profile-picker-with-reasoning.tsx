// Replaces Canvas's chat-input-llm-profile-picker.js: the same model button and menu, with the
// conversation's reasoning level under the model name and a "Рассуждения" group at the top of
// the menu (reasoning.ts). Two short lines keep the button as wide as before, so Canvas still
// fits it into the input row.
import { useEffect, useLayoutEffect, useRef, useState, useSyncExternalStore } from "react";
import { useTranslation } from "react-i18next";
import { ChatInputLlmProfileMenuContent as CanvasMenuContent } from "../node_modules/@openhands/agent-canvas/dist/components/features/chat/components/chat-input-llm-profile-picker.js";
import { useChatInputLlmProfileState } from "../node_modules/@openhands/agent-canvas/dist/hooks/use-chat-input-llm-profile-state.js";
import { useModelCatalogWarning } from "../node_modules/@openhands/agent-canvas/dist/hooks/use-model-catalog-warning.js";
import { useClickOutsideElement } from "../node_modules/@openhands/agent-canvas/dist/hooks/use-click-outside-element.js";
import { ModelCatalogWarning } from "../node_modules/@openhands/agent-canvas/dist/components/shared/model-catalog-warning.js";
import { ComboboxCaretInline } from "../node_modules/@openhands/agent-canvas/dist/ui/combobox-caret.js";
import { ContextMenu } from "../node_modules/@openhands/agent-canvas/dist/ui/context-menu.js";
import { chatInputPillButtonClassName } from "../node_modules/@openhands/agent-canvas/dist/utils/form-control-classes.js";
import { displayErrorToast } from "../node_modules/@openhands/agent-canvas/dist/utils/custom-toast-handlers.js";
import { cn } from "../node_modules/@openhands/agent-canvas/dist/utils/utils.js";
import { errorMessage, requestJson } from "./api";
import { useNavigation } from "./navigation-context";
import { setPreferences, usePreferences } from "./preferences";
import { REASONING, REASONING_CHANGED_EVENT, REASONING_LEVELS, reasoningOf, switchReasoning, type ReasoningLevel } from "./reasoning";

// Level each conversation runs with, read from agent-server: null when no level matches.
const levels = new Map<string, ReasoningLevel | null>();
const listeners = new Set<() => void>();
// Newest read per conversation: a read started before a switch must not overwrite the one after.
const reads = new Map<string, number>();
let lastRead = 0;

function loadLevel(conversationId: string) {
  const read = ++lastRead;
  reads.set(conversationId, read);
  requestJson<{ agent?: { llm?: unknown } }>(`/api/conversations/${encodeURIComponent(conversationId)}`)
    .then((info) => {
      if (reads.get(conversationId) !== read) return;
      levels.set(conversationId, reasoningOf(info.agent?.llm));
      for (const listener of listeners) listener();
    })
    .catch((error) => {
      console.warn("[reasoning] level not read", error);
      if (reads.get(conversationId) === read) reads.delete(conversationId);
    });
}

if (typeof window !== "undefined") {
  window.addEventListener(REASONING_CHANGED_EVENT, (event) => loadLevel((event as CustomEvent<{ conversationId: string }>).detail.conversationId));
}

const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
};

/** The open conversation's level; without a conversation, the one new conversations get. */
function useReasoningLevel() {
  const { conversationId } = useNavigation();
  const preferred = usePreferences().reasoning;
  const level = useSyncExternalStore(subscribe, () => (conversationId ? levels.get(conversationId) : preferred));
  useEffect(() => {
    if (conversationId && !levels.has(conversationId) && !reads.has(conversationId)) loadLevel(conversationId);
  }, [conversationId]);
  return { conversationId, level: level ?? null };
}

function ReasoningGroup({ onClose }: { onClose: () => void }) {
  const { conversationId, level } = useReasoningLevel();
  const { currentProfileName, canSwitchProfile } = useChatInputLlmProfileState();
  const choose = (next: ReasoningLevel) => {
    onClose();
    if (next === level) return;
    setPreferences({ reasoning: next });
    if (!conversationId || !canSwitchProfile || !currentProfileName) return;
    switchReasoning(conversationId, currentProfileName).catch((error) => {
      console.warn("[reasoning] switch failed", error);
      displayErrorToast(`Уровень рассуждений не изменён: ${errorMessage(error)}`);
      // A slow server may still have switched: show the level it actually has.
      loadLevel(conversationId);
    });
  };
  return (
    <li role="presentation" className="nexus-reasoning-group">
      <span id="nexus-reasoning-title" className="text-[11px] font-medium text-text-dim uppercase tracking-wide leading-4">Рассуждения</span>
      <div role="radiogroup" aria-labelledby="nexus-reasoning-title" className="nexus-reasoning-options">
        {REASONING_LEVELS.map((option) => (
          <button key={option} type="button" role="radio" aria-checked={option === level}
            data-testid={`chat-input-reasoning-${option}`}
            title={REASONING[option].budget ? `До ${REASONING[option].budget} токенов на размышление` : "Отвечает без размышлений"}
            onClick={(event) => { event.preventDefault(); event.stopPropagation(); choose(option); }}>
            {REASONING[option].label}
          </button>
        ))}
      </div>
    </li>
  );
}

type MenuProps = Parameters<typeof CanvasMenuContent>[0];

/** Also used by Canvas's overflow menu when the model button does not fit the row. */
export function ChatInputLlmProfileMenuContent(props: MenuProps) {
  return <><ReasoningGroup onClose={props.onClose} /><CanvasMenuContent {...props} /></>;
}

const LABEL_CHARS = 18;
const shortLabel = (label: string) => (label.length <= LABEL_CHARS ? label : `${label.slice(0, LABEL_CHARS)}…`);

export function ChatInputLlmProfilePicker() {
  const { t } = useTranslation();
  const { profiles, currentProfileName, currentProfileModel, isLoading, isSwitching } = useChatInputLlmProfileState();
  const catalogWarning = useModelCatalogWarning();
  const { level } = useReasoningLevel();
  const [open, setOpen] = useState(false);
  const button = useRef<HTMLButtonElement>(null);
  const [maxHeight, setMaxHeight] = useState<number>();
  const menu = useClickOutsideElement(() => setOpen(false), button);
  useLayoutEffect(() => {
    if (!open) return;
    const fit = () => {
      const top = button.current?.getBoundingClientRect().top;
      if (top !== undefined) setMaxHeight(Math.max(0, Math.min(window.innerHeight * 0.6, top - 16)));
    };
    fit();
    window.addEventListener("resize", fit);
    window.addEventListener("scroll", fit, true);
    return () => {
      window.removeEventListener("resize", fit);
      window.removeEventListener("scroll", fit, true);
    };
  }, [open]);
  if (isLoading || profiles.length === 0) return null;
  const name = currentProfileName ?? t("LLM$SELECT_MODEL_PLACEHOLDER");
  const levelLabel = level ? REASONING[level].label : null;
  return (
    <div className="relative min-w-0">
      <button ref={button} type="button" className={cn(chatInputPillButtonClassName, "max-w-50 nexus-model-pill")}
        title={currentProfileName ?? undefined} data-testid="chat-input-llm-profile"
        aria-label={levelLabel ? `${name}, рассуждения: ${levelLabel}` : undefined}
        aria-expanded={open} aria-haspopup="dialog" disabled={isSwitching} aria-busy={isSwitching}
        onClick={(event) => { event.preventDefault(); event.stopPropagation(); setOpen((value) => !value); }}>
        <span className="nexus-model-pill-text">
          <span className="truncate">{shortLabel(name)}</span>
          {levelLabel && <span className="nexus-model-pill-level">{levelLabel}</span>}
        </span>
        {catalogWarning(currentProfileModel) && <ModelCatalogWarning compact />}
        <ComboboxCaretInline isOpen={open} />
      </button>
      {open && (
        <ContextMenu ref={menu} testId="chat-input-llm-profile-popover" style={{ maxHeight }} position="top" alignment="left"
          spacing="none" className="z-[60] mb-2 min-w-50 max-w-80 max-h-[60vh] overflow-y-auto">
          <ChatInputLlmProfileMenuContent onClose={() => setOpen(false)} />
        </ContextMenu>
      )}
    </div>
  );
}
