// Use as a Node preload for production builds; refuses opening secret files, never prints their contents.
import fs from "node:fs";
import { syncBuiltinESMExports } from "node:module";
const forbidden = file => /(^|\/)(session\.env|\.env(?:\..*)?|secrets\.json)$/.test(String(file)) || /agent\/state\/settings\.json$/.test(String(file));
for (const key of ["readFileSync", "openSync"]) {
  const original = fs[key];
  fs[key] = function(file, ...args) { if (forbidden(file)) throw new Error("Build attempted to open a secret file"); return original.call(this, file, ...args); };
}
for (const key of ["readFile", "open"]) {
  const original = fs.promises[key];
  fs.promises[key] = async function(file, ...args) { if (forbidden(file)) throw new Error("Build attempted to open a secret file"); return original.call(this, file, ...args); };
}
syncBuiltinESMExports();
