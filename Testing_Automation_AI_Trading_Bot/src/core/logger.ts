/**
 * Framework-level diagnostics.
 *
 * Playwright's own reporter covers test outcomes; this covers what the
 * framework did underneath them — which mock served a request, why the
 * mutation guard refused a call, how long a live API request took. Quiet by
 * default (`VERBOSE_LOGS=1` to enable), because a suite that prints on every
 * intercepted request drowns the failure you are actually reading.
 */
import { env } from '@config/environment';

export type LogLevel = 'debug' | 'info' | 'warn' | 'error';

const LEVEL_ORDER: Record<LogLevel, number> = {
  debug: 10,
  info: 20,
  warn: 30,
  error: 40,
};

/** Errors and warnings always surface; the rest only when VERBOSE_LOGS is on. */
const threshold = (): number => (env.verbose ? LEVEL_ORDER.debug : LEVEL_ORDER.warn);

function emit(level: LogLevel, scope: string, message: string, detail?: unknown): void {
  if (LEVEL_ORDER[level] < threshold()) return;

  const line = `[${new Date().toISOString()}] ${level.toUpperCase().padEnd(5)} ${scope} — ${message}`;
  const sink = level === 'error' || level === 'warn' ? console.error : console.log;

  if (detail === undefined) {
    sink(line);
  } else {
    sink(line, typeof detail === 'string' ? detail : JSON.stringify(detail));
  }
}

export interface Logger {
  debug(message: string, detail?: unknown): void;
  info(message: string, detail?: unknown): void;
  warn(message: string, detail?: unknown): void;
  error(message: string, detail?: unknown): void;
  child(childScope: string): Logger;
}

/** Create a logger bound to a scope, e.g. `createLogger('MockBackend')`. */
export function createLogger(scope: string): Logger {
  return {
    debug: (message, detail) => emit('debug', scope, message, detail),
    info: (message, detail) => emit('info', scope, message, detail),
    warn: (message, detail) => emit('warn', scope, message, detail),
    error: (message, detail) => emit('error', scope, message, detail),
    child: (childScope) => createLogger(`${scope}:${childScope}`),
  };
}
