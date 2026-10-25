// Deterministic frame-clock experiment. These are NOT Chrome performance or CLS results.
import fs from "node:fs/promises";
import { StreamBuffer } from "../src/stream-buffer.ts";
import { answer } from "./server.mjs";
const packetEnds = [90, 380, 430, 820, answer.length];
const frames = [], buffer = new StreamBuffer();
let packet = 0, before = "", after = "", finalized = false;
for (let time = 0; time < 8000; time += 1000 / 60) {
  if (packet < packetEnds.length && time >= 1800 + packet * 900) {
    const target = answer.slice(0, packetEnds[packet++]);
    before = target; buffer.targetText(target, false, false);
  }
  if (time >= 7000 && !finalized) { finalized = true; buffer.targetText(answer, false, true); }
  const visible = buffer.frame(time);
  frames.push({time, rawLength: before.length, bufferedLength: visible.length, bufferedDelta: visible.length - after.length}); after = visible;
}
const rawDeltas = frames.map((frame, i) => frame.rawLength - (frames[i - 1]?.rawLength ?? 0));
const report = {kind: "deterministic-frame-clock", browserMeasured: false, frameIntervalMs: 1000 / 60,
  textCharacters: answer.length, packetCount: packetEnds.length,
  before: {maxCharactersPerFrame: Math.max(...rawDeltas), framesWithNewText: rawDeltas.filter(value => value > 0).length},
  after: {maxCharactersPerFrame: Math.max(...frames.map(frame => frame.bufferedDelta)), framesWithNewText: frames.filter(frame => frame.bufferedDelta > 0).length,
    finalTextComplete: after === answer}, cls: null, longFrames: null};
await fs.mkdir("dev/evidence", {recursive: true});
await fs.writeFile("dev/evidence/logic.json", JSON.stringify(report, null, 2) + "\n");
console.log(JSON.stringify(report));
