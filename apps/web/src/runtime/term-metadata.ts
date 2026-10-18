import { DateTime } from "luxon"
import { term as termSchema } from "./command-receipts-validators.cjs"
import type { Classroom, TermMetadata } from "./api"

// A private QG projection, not a fact inference or a client-owned aggregate.
export function decodeTermMetadata(input: unknown, scope: Classroom): Readonly<TermMetadata> {
  const valid = termSchema(input); termSchema.errors = null
  const invalid = () => new Error("学期信息未通过范围或格式校验，请刷新后重试；尚未生成变更。")
  if (!valid || !input || typeof input !== "object" || !("schema_version" in input)
    || !Object.prototype.hasOwnProperty.call(input, "schema_version")
    || input.schema_version !== "class-os.term-metadata.v1") throw invalid()
  const value = input as TermMetadata
  if (value.class_id !== scope.class_id || value.term_id !== scope.term_id
    || value.start_date >= value.end_date
    || !Number.isSafeInteger(value.version) || value.name.trim() !== value.name
    || /[\p{Cc}\p{Cf}\p{Cs}]/u.test(value.name)
    || ![value.start_date, value.end_date].every(date => {
      const parsed = DateTime.fromISO(date, { zone: "UTC" })
      return parsed.isValid && parsed.year >= 1
    })) throw invalid()
  return Object.freeze({ schema_version: value.schema_version, class_id: value.class_id, term_id: value.term_id,
    name: value.name, start_date: value.start_date, end_date: value.end_date, version: value.version })
}
