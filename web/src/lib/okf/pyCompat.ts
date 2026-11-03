// Python semantics the OKF checker's messages depend on: the values PyYAML's SafeLoader builds, repr() and str() of
// them, truthiness and the YAML 1.1 scalar rules. Pure TS, no Node or DOM (it runs in a Worker and in the browser).
// Source of truth: PyYAML 6 resolver.py / constructor.py and CPython 3.14 (the `pixi` env), mirrored by
// tests/lint/test_okf_check_parity.py. Known gaps are listed in checkBundle.ts.
import { Schema, Type, YAMLException, load } from "js-yaml";

/** A Python exception that okf_check turns into a `read` finding: `ValueError: month must be in 1..12, not 13`. */
export class PyError extends Error {
  constructor(readonly pyType: string, msg: string) {
    super(msg);
  }
  toString(): string {
    return `${this.pyType}: ${this.message}`;
  }
}

/** YAML `1.5` (Python float). JS numbers stand for Python ints. */
export class PyFloat {
  constructor(readonly v: number) {}
}
/** datetime.date */
export class PyDate {
  constructor(readonly y: number, readonly m: number, readonly d: number) {}
}
/** datetime.datetime; `tz` is the UTC offset in minutes, null for a naive one. */
export class PyDateTime {
  constructor(readonly y: number, readonly m: number, readonly d: number, readonly h: number, readonly mi: number,
              readonly s: number, readonly us: number, readonly tz: number | null) {}
}
export type PyDict = { [key: string]: PyValue };
export type PyValue = null | boolean | number | string | PyFloat | PyDate | PyDateTime | PyValue[] | PyDict;

export function isDict(v: unknown): v is PyDict {
  return typeof v === "object" && v !== null && !Array.isArray(v)
    && !(v instanceof PyFloat || v instanceof PyDate || v instanceof PyDateTime);
}

const pad = (n: number, w: number) => String(n).padStart(w, "0");

// -- repr() / str() / truthiness -----------------------------------------------------------------------------------
function strRepr(s: string): string {
  const quote = s.includes("'") && !s.includes('"') ? '"' : "'";
  let out = quote;
  for (const ch of s) {
    const c = ch.codePointAt(0)!;
    if (ch === quote || ch === "\\") out += "\\" + ch;
    else if (ch === "\t") out += "\\t";
    else if (ch === "\n") out += "\\n";
    else if (ch === "\r") out += "\\r";
    else if (ch !== " " && /[\p{C}\p{Z}]/u.test(ch)) {
      out += c < 0x100 ? "\\x" + c.toString(16).padStart(2, "0")
        : c < 0x10000 ? "\\u" + c.toString(16).padStart(4, "0") : "\\U" + c.toString(16).padStart(8, "0");
    } else out += ch;
  }
  return out + quote;
}

function floatRepr(x: number): string {
  if (Number.isNaN(x)) return "nan";
  if (!Number.isFinite(x)) return x < 0 ? "-inf" : "inf";
  if (x === 0) return Object.is(x, -0) ? "-0.0" : "0.0";
  const [mant, e] = Math.abs(x).toExponential().split("e") as [string, string];
  const digits = mant.replace(".", "");
  const exp = parseInt(e, 10);
  const sign = x < 0 ? "-" : "";
  if (exp >= -4 && exp < 16) {
    if (exp >= 0) {
      const whole = digits.padEnd(exp + 1, "0");
      return `${sign}${whole.slice(0, exp + 1)}.${whole.slice(exp + 1) || "0"}`;
    }
    return `${sign}0.${"0".repeat(-exp - 1)}${digits}`;
  }
  return `${sign}${digits[0]}${digits.length > 1 ? "." + digits.slice(1) : ""}e${exp < 0 ? "-" : "+"}${pad(Math.abs(exp), 2)}`;
}

function timedeltaRepr(totalSeconds: number): string {
  const days = Math.floor(totalSeconds / 86400);
  const seconds = totalSeconds - days * 86400;
  const parts = [days && `days=${days}`, seconds && `seconds=${seconds}`].filter(Boolean);
  return `datetime.timedelta(${parts.length ? parts.join(", ") : "0"})`;
}

function tzRepr(minutes: number): string {
  return minutes === 0 ? "datetime.timezone.utc" : `datetime.timezone(${timedeltaRepr(minutes * 60)})`;
}

export function pyRepr(v: unknown): string {
  if (v === null || v === undefined) return "None";
  if (v === true) return "True";
  if (v === false) return "False";
  if (typeof v === "number") return String(v);
  if (typeof v === "string") return strRepr(v);
  if (v instanceof PyFloat) return floatRepr(v.v);
  if (v instanceof PyDate) return `datetime.date(${v.y}, ${v.m}, ${v.d})`;
  if (v instanceof PyDateTime) {
    const args = [v.y, v.m, v.d, v.h, v.mi];
    if (v.s || v.us) args.push(v.s);
    if (v.us) args.push(v.us);
    return `datetime.datetime(${args.join(", ")}${v.tz === null ? "" : ", tzinfo=" + tzRepr(v.tz)})`;
  }
  if (Array.isArray(v)) return `[${v.map(pyRepr).join(", ")}]`;
  if (typeof v === "object") {
    return `{${Object.entries(v as object).map(([k, x]) => `${strRepr(k)}: ${pyRepr(x)}`).join(", ")}}`;
  }
  return String(v);
}

/** str(): like repr() except for str itself, date and datetime. */
export function pyStr(v: unknown): string {
  if (typeof v === "string") return v;
  if (v instanceof PyDate) return `${pad(v.y, 4)}-${pad(v.m, 2)}-${pad(v.d, 2)}`;
  if (v instanceof PyDateTime) {
    let out = `${pad(v.y, 4)}-${pad(v.m, 2)}-${pad(v.d, 2)} ${pad(v.h, 2)}:${pad(v.mi, 2)}:${pad(v.s, 2)}`;
    if (v.us) out += "." + pad(v.us, 6);
    if (v.tz !== null) out += `${v.tz < 0 ? "-" : "+"}${pad(Math.floor(Math.abs(v.tz) / 60), 2)}:${pad(Math.abs(v.tz) % 60, 2)}`;
    return out;
  }
  return pyRepr(v);
}

export function pyTruthy(v: unknown): boolean {
  if (v === null || v === undefined || v === false || v === 0 || v === "") return false;
  if (v instanceof PyFloat) return v.v !== 0;
  if (Array.isArray(v)) return v.length > 0;
  if (isDict(v)) return Object.keys(v).length > 0;
  return true;
}

/** sorted() on str: by code point, not by UTF-16 unit. */
export function cmpCodePoints(a: string, b: string): number {
  const x = Array.from(a, (c) => c.codePointAt(0)!);
  const y = Array.from(b, (c) => c.codePointAt(0)!);
  for (let i = 0; i < Math.min(x.length, y.length); i++) if (x[i] !== y[i]) return x[i]! - y[i]!;
  return x.length - y.length;
}

// -- posix.normpath ---------------------------------------------------------------------------------------------------
export function normpath(p: string): string {
  if (!p) return ".";
  let initial = p.startsWith("/") ? 1 : 0;
  if (initial && p.startsWith("//") && !p.startsWith("///")) initial = 2;
  const out: string[] = [];
  for (const c of p.split("/")) {
    if (c === "" || c === ".") continue;
    if (c !== ".." || (!initial && !out.length) || out[out.length - 1] === "..") out.push(c);
    else if (out.length) out.pop();
  }
  const path = out.join("/");
  return initial ? "/".repeat(initial) + path : path || ".";
}

// -- utf-8 decoding like open(path, encoding="utf-8").read() ----------------------------------------------------------
const hex2 = (b: number) => b.toString(16).padStart(2, "0");

/** The UnicodeDecodeError text of CPython's strict utf-8 decoder for the first bad sequence of `b`, or null. Positions
 *  are exact for files under 8 KiB (Python decodes a text file in chunks of that size). */
function utf8Error(b: Uint8Array): string | null {
  const cont = (x: number | undefined) => x !== undefined && (x & 0xc0) === 0x80;
  let i = 0;
  while (i < b.length) {
    const ch = b[i]!;
    let n = 1;
    let reason = "";
    let end = i + 1;
    const left = b.length - i;
    if (ch < 0x80) { i++; continue; }
    else if (ch < 0xc2) reason = "invalid start byte";
    else if (ch < 0xe0) {
      if (left < 2) { reason = "unexpected end of data"; end = b.length; }
      else if (!cont(b[i + 1])) reason = "invalid continuation byte";
      else n = 2;
    } else if (ch < 0xf0) {
      const c2 = b[i + 1];
      const bad2 = (c2 === undefined) ? false : !cont(c2) || (c2 < 0xa0 ? ch === 0xe0 : ch === 0xed && c2 >= 0xa0);
      if (left < 2) { reason = "unexpected end of data"; end = b.length; }
      else if (bad2) reason = "invalid continuation byte";
      else if (left < 3) { reason = "unexpected end of data"; end = b.length; }
      else if (!cont(b[i + 2])) { reason = "invalid continuation byte"; end = i + 2; }
      else n = 3;
    } else if (ch < 0xf5) {
      const c2 = b[i + 1];
      const bad2 = (c2 === undefined) ? false : !cont(c2) || (c2 < 0x90 ? ch === 0xf0 : ch === 0xf4 && c2 >= 0x90);
      if (left < 2) { reason = "unexpected end of data"; end = b.length; }
      else if (bad2) reason = "invalid continuation byte";
      else if (left < 3) { reason = "unexpected end of data"; end = b.length; }
      else if (!cont(b[i + 2])) { reason = "invalid continuation byte"; end = i + 2; }
      else if (left < 4) { reason = "unexpected end of data"; end = b.length; }
      else if (!cont(b[i + 3])) { reason = "invalid continuation byte"; end = i + 3; }
      else n = 4;
    } else reason = "invalid start byte";
    if (reason) {
      return end - i === 1
        ? `'utf-8' codec can't decode byte 0x${hex2(ch)} in position ${i}: ${reason}`
        : `'utf-8' codec can't decode bytes in position ${i}-${end - 1}: ${reason}`;
    }
    i += n;
  }
  return null;
}

const decoder = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true });   // Python keeps a BOM in the text

/** File text as Python reads it: strict utf-8, BOM kept, universal newlines. */
export function readText(content: string | Uint8Array): string {
  let text: string;
  if (typeof content === "string") text = content;
  else {
    try {
      text = decoder.decode(content);
    } catch {
      throw new PyError("UnicodeDecodeError", utf8Error(content) ?? "invalid utf-8");
    }
  }
  return text.replace(/\r\n?/g, "\n");
}

// -- yaml.safe_load (PyYAML 6, YAML 1.1 scalars) ----------------------------------------------------------------------
const scalar = (tag: string, re: RegExp, construct: (s: string) => unknown) =>
  new Type(`tag:yaml.org,2002:${tag}`, { kind: "scalar", resolve: (s: string) => re.test(s), construct });

const BOOL = /^(?:yes|Yes|YES|no|No|NO|true|True|TRUE|false|False|FALSE|on|On|ON|off|Off|OFF)$/;
const FLOAT = /^(?:[-+]?(?:[0-9][0-9_]*)\.[0-9_]*(?:[eE][-+][0-9]+)?|\.[0-9][0-9_]*(?:[eE][-+][0-9]+)?|[-+]?[0-9][0-9_]*(?::[0-5]?[0-9])+\.[0-9_]*|[-+]?\.(?:inf|Inf|INF)|\.(?:nan|NaN|NAN))$/;
const INT = /^(?:[-+]?0b[0-1_]+|[-+]?0[0-7_]+|[-+]?(?:0|[1-9][0-9_]*)|[-+]?0x[0-9a-fA-F_]+|[-+]?[1-9][0-9_]*(?::[0-5]?[0-9])+)$/;
const NULL = /^(?:~|null|Null|NULL|)$/;
const TIMESTAMP = /^(?:[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]|[0-9][0-9][0-9][0-9]-[0-9][0-9]?-[0-9][0-9]?(?:[Tt]|[ \t]+)[0-9][0-9]?:[0-9][0-9]:[0-9][0-9](?:\.[0-9]*)?(?:[ \t]*(?:Z|[-+][0-9][0-9]?(?::[0-9][0-9])?))?)$/;
const TS_PARTS = /^([0-9]{4})-([0-9][0-9]?)-([0-9][0-9]?)(?:(?:[Tt]|[ \t]+)([0-9][0-9]?):([0-9][0-9]):([0-9][0-9])(?:\.([0-9]*))?(?:[ \t]*(Z|([-+])([0-9][0-9]?)(?::([0-9][0-9]))?))?)?$/;

function sexagesimal(value: string, parse: (s: string) => number): number {
  let total = 0;
  let base = 1;
  for (const part of value.split(":").reverse()) {
    total += parse(part) * base;
    base *= 60;
  }
  return total;
}

function constructInt(raw: string): number {
  let value = raw.replace(/_/g, "");
  let sign = 1;
  if (value[0] === "-") sign = -1;
  if (value[0] === "-" || value[0] === "+") value = value.slice(1);
  if (value === "0") return 0;
  if (value.startsWith("0b")) return sign * parseInt(value.slice(2), 2);
  if (value.startsWith("0x")) return sign * parseInt(value.slice(2), 16);
  if (value[0] === "0") return sign * parseInt(value, 8);
  if (value.includes(":")) return sign * sexagesimal(value, (p) => parseInt(p, 10));
  return sign * parseInt(value, 10);
}

function constructFloat(raw: string): PyFloat {
  let value = raw.replace(/_/g, "").toLowerCase();
  let sign = 1;
  if (value[0] === "-") sign = -1;
  if (value[0] === "-" || value[0] === "+") value = value.slice(1);
  if (value === ".inf") return new PyFloat(sign * Infinity);
  if (value === ".nan") return new PyFloat(NaN);
  if (value.includes(":")) return new PyFloat(sign * sexagesimal(value, parseFloat));
  return new PyFloat(sign * parseFloat(value));
}

const daysIn = (y: number, m: number) => [31, y % 4 === 0 && (y % 100 !== 0 || y % 400 === 0) ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]!;

function constructTimestamp(raw: string): PyDate | PyDateTime | Invalid {
  try {
    return buildTimestamp(raw);
  } catch (e) {
    if (e instanceof PyError) return new Invalid(e);
    throw e;
  }
}

function buildTimestamp(raw: string): PyDate | PyDateTime {
  const m = TS_PARTS.exec(raw)!;
  const [y, mo, d] = [+m[1]!, +m[2]!, +m[3]!];
  let tz: number | null = null;
  let us = 0;
  const timed = m[4] !== undefined;
  if (timed) {
    if (m[7]) us = parseInt(m[7].slice(0, 6).padEnd(6, "0"), 10);
    if (m[9]) {
      const minutes = (+m[10]! * 60 + +(m[11] || 0)) * (m[9] === "-" ? -1 : 1);
      if (Math.abs(minutes) >= 1440) {
        throw new PyError("ValueError", "offset must be a timedelta strictly between -timedelta(hours=24) and "
          + `timedelta(hours=24), not ${timedeltaRepr(minutes * 60)}`);
      }
      tz = minutes;
    } else if (m[8]) tz = 0;
  }
  if (y < 1) throw new PyError("ValueError", `year must be in 1..9999, not ${y}`);
  if (mo < 1 || mo > 12) throw new PyError("ValueError", `month must be in 1..12, not ${mo}`);
  if (d < 1 || d > daysIn(y, mo)) {
    throw new PyError("ValueError", `day ${d} must be in range 1..${daysIn(y, mo)} for month ${mo} in year ${y}`);
  }
  if (!timed) return new PyDate(y, mo, d);
  const [h, mi, s] = [+m[4]!, +m[5]!, +m[6]!];
  if (h > 23) throw new PyError("ValueError", `hour must be in 0..23, not ${h}`);
  if (mi > 59) throw new PyError("ValueError", `minute must be in 0..59, not ${mi}`);
  if (s > 59) throw new PyError("ValueError", `second must be in 0..59, not ${s}`);
  return new PyDateTime(y, mo, d, h, mi, s, us, tz);
}

// `<<` and `=` as a value (not the merge key) have no constructor in PyYAML: the whole document is a YAMLError.
class Unconstructable {}
const UNCONSTRUCTABLE = new Unconstructable();
/** A scalar PyYAML cannot build (an impossible date). PyYAML parses the whole document before it constructs any value,
 *  so a syntax error later in the text wins over it: the error is raised only once the load has succeeded. */
class Invalid {
  constructor(readonly error: PyError) {}
}
// Resolution order of PyYAML's Resolver: bool, float, int, merge, null, timestamp, value.
const SCHEMA = new Schema({
  explicit: [
    new Type("tag:yaml.org,2002:str", { kind: "scalar", construct: (d: unknown) => (d !== null ? d : "") }),
    new Type("tag:yaml.org,2002:seq", { kind: "sequence", construct: (d: unknown) => (d !== null ? d : []) }),
    new Type("tag:yaml.org,2002:map", { kind: "mapping", construct: (d: unknown) => (d !== null ? d : {}) }),
  ],
  implicit: [
    scalar("bool", BOOL, (s) => ["yes", "true", "on"].includes(s.toLowerCase())),
    scalar("float", FLOAT, constructFloat),
    scalar("int", INT, constructInt),
    new Type("tag:yaml.org,2002:merge", { kind: "scalar", resolve: (s: string) => s === "<<", construct: () => UNCONSTRUCTABLE }),
    scalar("null", NULL, () => null),
    scalar("timestamp", TIMESTAMP, constructTimestamp),
    scalar("value", /^=$/, () => UNCONSTRUCTABLE),
  ],
});

// PyYAML's scanner skips spaces only between tokens, so a tab where a token starts (indentation, after `:` or `-`) is a
// ScannerError there; js-yaml reads it as whitespace. Tabs inside scalars are fine in both.
const TAB_TOKEN = /^[ ]*(?:[-?][ ]+)*[-?]?\t|:[ ]*\t/m;

interface Frame {
  kids: Array<Frame | Unconstructable | Invalid>;
}

/** The first failure PyYAML meets while it constructs the values. It builds a collection after the scalars of the one
 *  that holds it (a generator queue), so the order is breadth first, not document order. */
function firstFailure(root: Frame): Unconstructable | Invalid | undefined {
  const queue = [root];
  for (const frame of queue) {
    for (const kid of frame.kids) {
      if (kid instanceof Unconstructable || kid instanceof Invalid) return kid;
      queue.push(kid);
    }
  }
  return undefined;
}

/** yaml.safe_load: the value, or `undefined` when the text is not valid YAML (PyYAML's YAMLError). A construct error
 *  (an impossible date) is a PyError, like Python's ValueError. */
export function safeLoad(text: string): PyValue | undefined {
  if (TAB_TOKEN.test(text)) return undefined;
  const root: Frame = { kids: [] };                                     // repeated keys included: PyYAML builds them all
  const stack = [root];
  let value: PyValue;
  try {
    value = load(text, {
      schema: SCHEMA,
      json: true,                                                       // a repeated key keeps the last value
      listener: (type, state) => {
        const s = state as unknown as { kind: string | null; result: unknown; position: number; input: string };
        if (type === "open") {
          stack.push({ kids: [] });
          return;
        }
        const frame = stack.pop()!;
        const parent = stack[stack.length - 1]!;
        if (s.kind !== "scalar") parent.kids.push(frame);
        else if (s.result instanceof Invalid) parent.kids.push(s.result);
        else if (s.result instanceof Unconstructable) {
          if (!/^[ \t]*:/.test(s.input.slice(s.position, s.position + 64))) parent.kids.push(s.result);   // `<<:` is the merge key
        } else if (typeof s.result === "string" && s.result.endsWith("\n") && s.position >= text.length && !/["']$/.test(text)) {
          s.result = s.result.slice(0, -1);       // a block scalar that ends the text has no final line break in PyYAML
        }
      },
    }) as PyValue;
  } catch (e) {
    if (e instanceof YAMLException) return undefined;
    throw e;
  }
  const failure = firstFailure(root);
  if (failure instanceof Invalid) throw failure.error;
  return failure ? undefined : value;
}
