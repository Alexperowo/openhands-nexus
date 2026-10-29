import { useEffect, useRef, useState } from "react";
import { MODEL_LOADING, MODEL_STALLED, describeStatus, type ActivitySnapshot, type ModelState } from "./agent-activity";
import { getPreferences, stateCuesEnabled } from "./preferences";
import { cueForStatus, playConnectionCue, playCue } from "./status-cues";
import { shouldAnnounceStatus } from "./status-announcement";
import { ConnectionAnnouncements, type ConnectionPhase } from "./connection-state";

// Shown for a few seconds after the change; a request for the owner stays.
const TRANSIENT = new Set(["verified", "unverified", "paused"]);
const WORKING = new Set(["running", "checking"]);
interface Props {
  status: string;
  activity: ActivitySnapshot;
  model: ModelState;
  problems: string[];
  connection?: ConnectionPhase;
}

/** The visual slot stays mounted; live regions only change for meaningful transitions. */
export function StatusBar({ status, activity, model, problems, connection = "online" }: Props) {
  const previous = useRef({ status: "", error: "" });
  const previousCue = useRef("");
  const connectionNotices = useRef(new ConnectionAnnouncements());
  const previousProblem = useRef("");
  const [news, setNews] = useState("");
  const [announcement, setAnnouncement] = useState("");
  const [urgent, setUrgent] = useState("");
  const line = describeStatus(status, activity, model);
  const lineText = line?.text ?? "";
  const visible = Boolean(line && (!TRANSIENT.has(status) || news === status));
  // A model chosen in the list loads before the first message; the line has nothing else to say.
  const loading = model === "loading" && !WORKING.has(status) && !visible;
  const problem = connection === "lost" ? "Связь потеряна. Пробую подключиться." :
    [model === "offline" ? "Нет связи с моделью" : model === "stalled" ? MODEL_STALLED : "", ...problems].filter(Boolean).join(". ");

  useEffect(() => {
    const notice = connectionNotices.current.update(connection);
    if (!notice) return;
    setUrgent(notice === "lost" ? "Связь потеряна. Пробую подключиться." : "Связь восстановлена");
    // Critical connection cues are local Web Audio, independent of the remote TTS service.
    playConnectionCue(notice === "lost" ? "error" : "done");
  }, [connection]);
  useEffect(() => {
    if (connection === "lost") return;
    if (problem && problem !== previousProblem.current) setUrgent(problem);
    previousProblem.current = problem;
  }, [problem, connection]);
  useEffect(() => {
    if (!status || connection !== "online") return;
    const before = previous.current;
    const current = { status, error: activity.error };
    previous.current = current;
    if (shouldAnnounceStatus(before, current)) setAnnouncement(lineText);
  }, [status, activity.error, connection]);
  useEffect(() => {
    if (loading && connection === "online") setAnnouncement(MODEL_LOADING);
  }, [loading]);
  useEffect(() => {
    if (!announcement) return;
    const timer = setTimeout(() => setAnnouncement(""), 7000);
    return () => clearTimeout(timer);
  }, [announcement]);
  useEffect(() => {
    if (!urgent) return;
    const timer = setTimeout(() => setUrgent(""), 7000);
    return () => clearTimeout(timer);
  }, [urgent]);
  useEffect(() => {
    if (!status || connection !== "online") return;
    const before = previousCue.current;
    previousCue.current = status;
    if (!before || before === status) return;
    const cue = cueForStatus(status);
    if (cue && stateCuesEnabled(getPreferences())) playCue(cue);
    setNews(TRANSIENT.has(status) ? status : "");
    const timer = setTimeout(() => setNews(""), 5000);
    return () => clearTimeout(timer);
  }, [status, connection]);

  const visual = problem || (connection === "connecting" ? "Подключение к диалогу…" :
    visible ? lineText : loading ? MODEL_LOADING : "");
  return <section className="nexus-status-slot" aria-label="Состояние агента">
    <p className={`status-bar${problem ? " status-problem" : ""}`} data-tone={problem ? "error" : loading ? "work" : line?.tone}
      data-empty={!visual || undefined}>
      <span className={(WORKING.has(status) || loading) && !problem ? "nexus-working" : undefined} aria-hidden="true" />
      <span className="nexus-status-text" key={visual}>{visual || "\u00a0"}</span>
    </p>
    <p className="visually-hidden" role="status" aria-atomic="true">{announcement}</p>
    <p className="visually-hidden" role="alert" aria-atomic="true">{urgent}</p>
  </section>;
}
