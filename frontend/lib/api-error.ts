/**
 * extractApiError
 *
 * Root-cause fix: FastAPI returns a 422 Validation Error whose `detail`
 * field is an ARRAY of Pydantic error objects:
 *   [{ type, loc, msg, input, url }]
 * Passing that array (or any element of it) directly to sonner's
 * toast.error() causes:
 *   "Objects are not valid as a React child (found: object with keys
 *    {type, loc, msg, input})"
 *
 * This helper converts ANY shape of `detail` or `error` field from a
 * FastAPI response into a plain, displayable string — safe to pass to
 * toast.error(), setState, or anywhere else that needs a string.
 */

type PydanticErrorItem = {
  msg?: string;
  loc?: (string | number)[];
  type?: string;
  input?: unknown;
};

/**
 * Convert a raw API response body into a human-readable error string.
 *
 * Handles all FastAPI error shapes:
 *  - string                         → returned as-is
 *  - Pydantic array [{msg, loc…}]   → "field: message" per item, joined
 *  - plain object with .message     → object.message
 *  - anything else                  → fallback string
 *
 * @param data     The parsed JSON response body (any shape).
 * @param fallback Returned when no useful message can be extracted.
 */
export function extractApiError(
  data: unknown,
  fallback = "An unexpected error occurred"
): string {
  if (!data || typeof data !== "object") {
    return typeof data === "string" && data ? data : fallback;
  }

  const obj = data as Record<string, unknown>;

  // Try `detail` first (FastAPI's canonical error key), then `error`, then `message`
  const raw = obj.detail ?? obj.error ?? obj.message;

  if (raw === undefined || raw === null) return fallback;

  // Plain string — most common for non-validation errors
  if (typeof raw === "string") return raw || fallback;

  // Pydantic 422 array: [{ type, loc, msg, input }]
  if (Array.isArray(raw)) {
    const messages = (raw as PydanticErrorItem[])
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object") {
          const field =
            Array.isArray(item.loc) && item.loc.length > 0
              ? item.loc.filter((p) => p !== "body").join(" → ")
              : null;
          const msg = item.msg ?? String(item);
          return field ? `${field}: ${msg}` : msg;
        }
        return String(item);
      })
      .filter(Boolean);
    return messages.length > 0 ? messages.join("; ") : fallback;
  }

  // Single Pydantic-style object (unlikely but guard it anyway)
  if (typeof raw === "object") {
    const item = raw as PydanticErrorItem;
    return item.msg ?? fallback;
  }

  return fallback;
}
