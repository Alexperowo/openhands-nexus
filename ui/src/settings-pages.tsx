import { useState } from "react";
import { audioService, useAudioStatus } from "./audio-service";
import { setPreferences, stateCuesEnabled, usePreferences } from "./preferences";
import { playCue, unlockCues } from "./status-cues";

const VOICES = [
  { id: "xenia", label: "Ксения" },
  { id: "kseniya", label: "Ксения, второй вариант" },
  { id: "baya", label: "Бая" },
  { id: "aidar", label: "Айдар" },
  { id: "eugene", label: "Евгений" },
];
const SPEEDS = [0.75, 1, 1.25, 1.5];
const VOLUMES = [0.25, 0.5, 0.75, 1];
const FONT_SIZES = [
  { size: 18, label: "Обычный" },
  { size: 20, label: "Крупный" },
  { size: 24, label: "Очень крупный" },
  { size: 28, label: "Максимальный" },
];
const SAMPLE = "Здравствуйте! Так я буду читать ответы.";

export function VoiceSettings() {
  const preferences = usePreferences();
  const { currentId, error } = useAudioStatus();
  const sampling = currentId === "voice-sample";
  const [cueError, setCueError] = useState("");
  const playDone = async () => {
    const ready = await unlockCues();
    setCueError(ready ? "" : "Браузер не разрешил звук. Нажмите ещё раз.");
    if (ready) playCue("done");
  };
  return (
    <section className="nexus-settings" aria-labelledby="voice-title">
      <h2 id="voice-title">Голос</h2>
      <label className="nexus-field">
        Режим речи
        <select value={preferences.autoSpeak ? "auto" : "signals"} aria-describedby="speech-mode-help"
          onChange={(event) => audioService.setAutoSpeak(event.target.value === "auto")}>
          <option value="auto">Автоматически читать ответы</option>
          <option value="signals">Только сигналы — для TalkBack</option>
        </select>
      </label>
      <p id="speech-mode-help">
        С TalkBack выберите «Только сигналы»: ответы не читаются автоматически,
        сигналы состояния включены. Важные статусы объявляет скринридер.
        Кнопки «Прочитать вслух» и «Полностью» работают по нажатию.
      </p>
      <label className="nexus-field">
        Голос
        <select value={preferences.voice} onChange={(event) => setPreferences({ voice: event.target.value })}>
          {VOICES.map((voice) => <option key={voice.id} value={voice.id}>{voice.label}</option>)}
        </select>
      </label>
      <label className="nexus-field">
        Скорость речи
        <select value={preferences.speed} onChange={(event) => setPreferences({ speed: Number(event.target.value) })}>
          {SPEEDS.map((speed) => <option key={speed} value={speed}>{`${speed}×`.replace(".", ",")}</option>)}
        </select>
      </label>
      <label className="nexus-field">
        Громкость речи
        <select value={preferences.volume} onChange={(event) => setPreferences({ volume: Number(event.target.value) })}>
          {VOLUMES.map((volume) => <option key={volume} value={volume}>{`${volume * 100} %`}</option>)}
        </select>
      </label>
      <button type="button" className="nexus-button" aria-pressed={sampling}
        onClick={() => (sampling ? audioService.stop() : audioService.playNow("voice-sample", SAMPLE))}>
        {sampling ? "Остановить" : "Прослушать голос"}
      </button>
      {error && <p className="nexus-error" role="alert">{error}</p>}
      <label className="nexus-check">
        <input type="checkbox" checked={stateCuesEnabled(preferences)} disabled={!preferences.autoSpeak}
          onChange={(event) => setPreferences({ cues: event.target.checked })} />
        Звуковые сигналы состояния агента
      </label>
      <label className="nexus-check">
        <input type="checkbox" checked={preferences.speakSteps} disabled={!preferences.autoSpeak}
          onChange={(event) => setPreferences({ speakSteps: event.target.checked })} />
        Озвучивать промежуточные шаги
      </label>
      <button type="button" className="nexus-button" onClick={() => void playDone()}>
        Прослушать сигнал «Готово»
      </button>
      {cueError && <p className="nexus-error" role="alert">{cueError}</p>}
    </section>
  );
}

export function AccessibilitySettings() {
  const preferences = usePreferences();
  return (
    <section className="nexus-settings" aria-labelledby="accessibility-title">
      <h2 id="accessibility-title">Доступность</h2>
      <label className="nexus-field">
        Анимации
        <select value={preferences.motion} onChange={(event) => setPreferences({ motion: event.target.value as typeof preferences.motion })}>
          <option value="system">Как в системе</option>
          <option value="full">Включены</option>
          <option value="reduced">Уменьшены</option>
          <option value="off">Выключены</option>
        </select>
      </label>
      <fieldset className="nexus-field">
        <legend>Размер текста</legend>
        {FONT_SIZES.map(({ size, label }) => (
          <label key={size} className="nexus-check">
            <input type="radio" name="font-size" checked={preferences.fontSize === size}
              onChange={() => setPreferences({ fontSize: size })} />
            {label}
          </label>
        ))}
      </fieldset>
      <label className="nexus-check">
        <input type="checkbox" checked={preferences.highContrast}
          onChange={(event) => setPreferences({ highContrast: event.target.checked })} />
        Высокий контраст
      </label>
    </section>
  );
}
