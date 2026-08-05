/**
 * A minimal runtime shape checker.
 *
 * Deliberately not a schema library: the value here is that the *same*
 * definition is enforced in two places — against the mock fixtures (so the
 * mocked suite cannot drift into testing a fantasy backend) and against the
 * live backend (so a real contract change is caught). A dependency-free
 * checker keeps that pairing obvious and the failure messages precise.
 */

export type Primitive = 'string' | 'number' | 'boolean';

export interface FieldSpec {
  type: Primitive | 'array' | 'object';
  /** Absent fields are a failure unless this is set. */
  optional?: boolean;
  /** For `array` of objects: the shape each element must satisfy. */
  items?: Schema;
  /** For `array` of primitives: the type each element must be. */
  elementType?: Primitive;
  /** For `object`: the nested shape. */
  shape?: Schema;
  /** Extra constraint, e.g. `(v) => v >= 0`. */
  predicate?: (value: unknown) => boolean;
  /** Description used in the failure message when `predicate` fails. */
  predicateDescription?: string;
}

export type Schema = Record<string, FieldSpec>;

export interface ValidationResult {
  valid: boolean;
  errors: string[];
}

/** Check `value` against `schema`; unknown extra fields are allowed. */
export function validate(value: unknown, schema: Schema, path = '$'): ValidationResult {
  const errors: string[] = [];

  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    return { valid: false, errors: [`${path}: expected an object, got ${describe(value)}`] };
  }

  const record = value as Record<string, unknown>;

  for (const [key, spec] of Object.entries(schema)) {
    const fieldPath = `${path}.${key}`;
    const fieldValue = record[key];

    if (fieldValue === undefined || fieldValue === null) {
      if (!spec.optional) errors.push(`${fieldPath}: required field is missing`);
      continue;
    }

    errors.push(...checkField(fieldValue, spec, fieldPath));
  }

  return { valid: errors.length === 0, errors };
}

function checkField(value: unknown, spec: FieldSpec, path: string): string[] {
  const errors: string[] = [];

  switch (spec.type) {
    case 'array': {
      if (!Array.isArray(value)) {
        return [`${path}: expected an array, got ${describe(value)}`];
      }
      if (spec.items) {
        value.forEach((item, index) => {
          const nested = validate(item, spec.items as Schema, `${path}[${index}]`);
          errors.push(...nested.errors);
        });
      }
      if (spec.elementType) {
        value.forEach((item, index) => {
          if (typeof item !== spec.elementType) {
            errors.push(
              `${path}[${index}]: expected ${spec.elementType}, got ${describe(item)}`,
            );
          }
        });
      }
      break;
    }
    case 'object': {
      const nested = validate(value, spec.shape ?? {}, path);
      errors.push(...nested.errors);
      break;
    }
    default: {
      if (typeof value !== spec.type) {
        return [`${path}: expected ${spec.type}, got ${describe(value)}`];
      }
      if (spec.type === 'number' && !Number.isFinite(value)) {
        return [`${path}: expected a finite number, got ${String(value)}`];
      }
    }
  }

  if (spec.predicate && !spec.predicate(value)) {
    errors.push(
      `${path}: failed constraint${spec.predicateDescription ? ` (${spec.predicateDescription})` : ''}` +
        ` — value was ${JSON.stringify(value)}`,
    );
  }

  return errors;
}

/** Throw with every failure listed, rather than only the first. */
export function assertSchema(value: unknown, schema: Schema, label: string): void {
  const result = validate(value, schema, label);
  if (!result.valid) {
    throw new Error(
      `${label} does not match its declared contract:\n  - ${result.errors.join('\n  - ')}`,
    );
  }
}

function describe(value: unknown): string {
  if (value === null) return 'null';
  if (Array.isArray(value)) return 'array';
  return typeof value;
}
