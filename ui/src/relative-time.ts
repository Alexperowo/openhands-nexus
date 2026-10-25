// Replaces Canvas's utils/format-time-delta.js: its "5m", "2h" ignore the interface language,
// and TalkBack reads "5m" as "5 metres". Same contract (a duration; some callers append
// "ago" from the dictionary), but in words of the page language: "47 минут", "2 часа".
// The page language is kept equal to the interface language by i18n.ts (importing i18n
// here would be a cycle).

// Unchanged from Canvas: server dates without a zone are UTC.
export const parseDateAsUTC = (dateString: string) =>
  dateString.includes("Z") || /[+-]\d{2}:\d{2}$/.test(dateString) ? new Date(dateString) : new Date(`${dateString}Z`);

const UNITS: [string, number][] = [
  ["year", 365 * 86400], ["month", 30 * 86400], ["day", 86400], ["hour", 3600], ["minute", 60], ["second", 1],
];

export const formatTimeDelta = (date: Date | string) => {
  const time = (typeof date === "string" ? parseDateAsUTC(date) : date).getTime();
  if (Number.isNaN(time)) return "";
  const seconds = Math.max(0, Math.floor((Date.now() - time) / 1000));
  const [unit, size] = UNITS.find(([, size]) => seconds >= size) ?? UNITS[UNITS.length - 1];
  return new Intl.NumberFormat(document.documentElement.lang || undefined, { style: "unit", unit, unitDisplay: "long" })
    .format(Math.floor(seconds / size));
};
