// Root-cause fix (chart timestamp audit): every chart/data path in this app
// deals with two distinct timezone concerns that were previously conflated
// and handled inconsistently (or via the viewer's own browser timezone,
// which is wrong for any user not physically in IST):
//
// 1. PARSING: the backend (broker cache, CSV cache, yfinance fallback,
//    backtest engine) writes naive "YYYY-MM-DD HH:MM[:SS]" datetime strings
//    that represent true NSE market time (IST, Asia/Kolkata) -- they carry
//    no timezone suffix. Parsing these with the bare `new Date(str)` lets
//    the BROWSER's own local timezone decide what they mean, which is only
//    correct by accident for a viewer whose machine happens to be set to
//    IST. `parseBackendDatetimeToEpochSeconds` fixes this by explicitly
//    tagging naive strings as IST before parsing, so the resulting epoch is
//    the one true, timezone-independent instant regardless of viewer.
//
// 2. DISPLAY: `lightweight-charts` (native-chart.tsx) formats the epochs it's
//    given using JS Date's *UTC* getters internally, with no built-in
//    per-chart timezone option (unlike `klinecharts`, which takes an
//    explicit `timezone` option and converts internally via Intl). Feeding
//    it a true absolute epoch and letting it render with its default UTC
//    formatter shows UTC wall-clock time (IST minus 5:30), not IST -- so
//    every chart using this library needs an explicit `Asia/Kolkata`
//    formatter wired into its `localization`/`tickMarkFormatter` options.
//    `formatEpochIST` is that formatter's building block.
//
// IST has no DST, so its offset from UTC is a fixed +05:30 year-round --
// no timezone database/library is needed, just this one constant.
const IST_OFFSET_SECONDS = 5.5 * 3600;

/**
 * Parses a datetime string from a backend API (naive "YYYY-MM-DD HH:MM[:SS]",
 * assumed to represent true IST/NSE market time, OR an already timezone-aware
 * ISO string e.g. from state.db's UTC-tagged trade records) into a true,
 * viewer-timezone-independent Unix epoch in seconds. Returns null if the
 * input is missing or unparseable.
 */
export function parseBackendDatetimeToEpochSeconds(raw: string | null | undefined): number | null {
  if (!raw) return null;
  let s = String(raw).trim();
  if (!s) return null;
  s = s.includes(' ') ? s.replace(' ', 'T') : s;
  // Explicit timezone info already present (a 'Z' suffix, or a +HH:MM /
  // -HH:MM offset after the time component) -- trust it as-is. Otherwise
  // this is a naive IST wall-clock reading; tag it explicitly rather than
  // letting the browser's own local timezone decide.
  const hasTz = /Z$|[+-]\d{2}:?\d{2}$/.test(s);
  if (!hasTz) s += '+05:30';
  const ms = new Date(s).getTime();
  if (isNaN(ms)) return null;
  return Math.floor(ms / 1000);
}

/** Same as {@link parseBackendDatetimeToEpochSeconds} but returns milliseconds
 * (for chart libraries, like klinecharts, that expect millisecond timestamps). */
export function parseBackendDatetimeToEpochMs(raw: string | null | undefined): number | null {
  const s = parseBackendDatetimeToEpochSeconds(raw);
  return s === null ? null : s * 1000;
}

export interface ISTParts {
  year: number;
  month: number; // 1-12
  day: number;
  hour: number; // 0-23
  minute: number;
  second: number;
  weekday: string; // 'Mon' | 'Tue' | ...
}

/**
 * Returns the current wall-clock date/time in IST (Asia/Kolkata), regardless
 * of the viewer's own browser/system timezone. Use this instead of `new
 * Date().getHours()`/`getMinutes()` etc. anywhere "now, in market time" is
 * needed (e.g. deciding which candle interval "now" falls into).
 */
export function getISTNowParts(): ISTParts {
  const now = new Date();
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'Asia/Kolkata',
    hour12: false,
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
    weekday: 'short',
  }).formatToParts(now);
  const get = (t: string) => parts.find(p => p.type === t)?.value ?? '0';
  const hourRaw = get('hour');
  return {
    year: parseInt(get('year'), 10),
    month: parseInt(get('month'), 10),
    day: parseInt(get('day'), 10),
    // Intl's hour12:false can format midnight as "24" in some engines
    hour: hourRaw === '24' ? 0 : parseInt(hourRaw, 10),
    minute: parseInt(get('minute'), 10),
    second: parseInt(get('second'), 10),
    weekday: get('weekday'),
  };
}

/**
 * Converts an IST wall-clock date/time (year/month/day/hour/minute/second)
 * into the true, viewer-timezone-independent Unix epoch in seconds. IST has
 * no DST, so this is always a fixed +05:30 offset.
 */
export function istWallTimeToEpochSeconds(year: number, month: number, day: number, hour: number, minute: number, second = 0): number {
  return Math.floor(Date.UTC(year, month - 1, day, hour, minute, second, 0) / 1000) - IST_OFFSET_SECONDS;
}

/** Is the NSE regular market session (09:15-15:30 IST, Mon-Fri) open right now? */
export function isMarketOpenIST(): boolean {
  const p = getISTNowParts();
  if (p.weekday === 'Sat' || p.weekday === 'Sun') return false;
  const mins = p.hour * 60 + p.minute;
  return mins >= 9 * 60 + 15 && mins < 15 * 60 + 30;
}

/**
 * Formats a true Unix epoch (seconds) for display, always in IST regardless
 * of the viewer's own browser/system timezone.
 */
export function formatEpochIST(epochSeconds: number, opts: Intl.DateTimeFormatOptions = { hour: '2-digit', minute: '2-digit', hour12: false }): string {
  return new Date(epochSeconds * 1000).toLocaleString('en-GB', { timeZone: 'Asia/Kolkata', ...opts });
}

/** Extracts formatted IST date/time parts from a true Unix epoch (seconds),
 * for chart-axis tick labels that need different granularity (year, month,
 * day, or time-of-day) depending on zoom level. `month` is a short name
 * (e.g. "Aug") for display -- use {@link getISTDateStringFromEpoch} instead
 * if you need a numeric, comparable "YYYY-MM-DD" calendar date. */
export function formatEpochISTParts(epochSeconds: number): { year: string; month: string; day: string; hour: string; minute: string } {
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Kolkata', hour12: false,
    year: 'numeric', month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit',
  }).formatToParts(new Date(epochSeconds * 1000));
  const get = (t: string) => parts.find(p => p.type === t)?.value ?? '';
  return { year: get('year'), month: get('month'), day: get('day'), hour: get('hour'), minute: get('minute') };
}

/** Returns the IST calendar date of a true Unix epoch (seconds) as a
 * numeric, directly-comparable "YYYY-MM-DD" string -- for "is this trade
 * from today (in IST)" style checks, independent of the viewer's own
 * browser/system timezone and of whichever timezone the backend originally
 * tagged the source timestamp with. */
export function getISTDateStringFromEpoch(epochSeconds: number): string {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Kolkata', year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts(new Date(epochSeconds * 1000));
  const get = (t: string) => parts.find(p => p.type === t)?.value ?? '';
  return `${get('year')}-${get('month')}-${get('day')}`;
}

/** Today's IST calendar date as a numeric "YYYY-MM-DD" string. */
export function getTodayISTDateString(): string {
  return getISTDateStringFromEpoch(Math.floor(Date.now() / 1000));
}
