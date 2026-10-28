import type { ReactNode } from "react";
import { FileCode, Square, Volume2 } from "lucide-react";
import { audioService, fullReadingId, useAudioStatus } from "./audio-service";
import { forSpeech } from "./speech-events";

/**
 * ▶/■ under an answer, as in ChatGPT and Claude: always visible, no hover needed.
 * When the reading skips code or paths, a second button reads the answer in full.
 */
export function SpeakButton({ id, text }: { id: string; text: string }) {
  const { currentId } = useAudioStatus();
  const hasSkipped = forSpeech(text) !== forSpeech(text, true);
  return (
    <div className="speak-row">
      <ReadButton id={id} current={currentId} label="Прочитать вслух" icon={<Volume2 aria-hidden />}
        onPlay={() => audioService.playNow(id, text)} />
      {hasSkipped && (
        <ReadButton id={fullReadingId(id)} current={currentId} label="Прочитать полностью, с кодом и путями"
          icon={<FileCode aria-hidden />} caption="Полностью" onPlay={() => audioService.playNow(id, text, true)} />
      )}
    </div>
  );
}

// A caption makes an icon of uncommon meaning clear without hovering.
function ReadButton({ id, current, label, icon, caption, onPlay }:
  { id: string; current: string | null; label: string; icon: ReactNode; caption?: string; onPlay: () => void }) {
  const isCurrent = current === id;
  const { isDictating } = useAudioStatus();
  const name = isCurrent ? "Остановить чтение" : audioService.resumes(id) ? "Продолжить чтение" : label;
  return (
    <button type="button" className="speak-button" data-testid="speak-button"
      aria-label={name} title={name} aria-pressed={isCurrent}
      disabled={isDictating}
      onClick={() => (isCurrent ? audioService.stop() : onPlay())}>
      {isCurrent ? <Square aria-hidden /> : icon}
      {caption && <span aria-hidden>{caption}</span>}
    </button>
  );
}
