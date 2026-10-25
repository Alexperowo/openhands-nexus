import { MicOff, Square, Volume2 } from "lucide-react";
import { audioService, useAudioStatus } from "./audio-service";

export function AudioControls() {
  const { currentId, isUnlocked, isDictating } = useAudioStatus();
  return <div className="nexus-audio-controls" role="group" aria-label="Управление звуком">
    <button type="button" className="icon-button nexus-stop-speech" aria-label="Остановить озвучку" title="Остановить озвучку"
      aria-disabled={!currentId} onClick={() => { if (currentId) audioService.stop(); }}><Square aria-hidden /></button>
    <button type="button" className="icon-button" aria-label="Отменить диктовку" title="Отменить диктовку"
      disabled={!isDictating} onClick={() => {
        audioService.cancelDictation();
        document.querySelector<HTMLElement>("[data-testid='chat-input']")?.focus({preventScroll: true});
      }}><MicOff aria-hidden /></button>
    <button type="button" className="icon-button" aria-label={isUnlocked ? "Звук включён" : "Включить звук"}
      title={isUnlocked ? "Звук включён" : "Включить звук"} disabled={isUnlocked || isDictating}
      onClick={() => void audioService.unlockAudio()}><Volume2 aria-hidden /></button>
  </div>;
}
