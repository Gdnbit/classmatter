import { DateTime } from "luxon"

// Presentation adapter only: domain commands still carry explicit UTC instants.
const wallFormat = /^\d{4}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d(?:\.\d{1,3})?)?$/
const invalid = () => new Error("时间无效、不存在或有歧义。请核对本机时区并选择明确时间后再预览。")

export function localDateTimeToUtc(value: string, zone?: string, knownInstant?: string): string {
  try {
    const timeZone = zone === undefined ? Intl.DateTimeFormat().resolvedOptions().timeZone : zone
    if (typeof value !== "string" || value.trim() !== value || !wallFormat.test(value)
      || typeof timeZone !== "string" || !timeZone || timeZone.length > 128) throw invalid()
    const wall = DateTime.fromISO(value, { zone: "UTC" })
    if (!wall.isValid || wall.year < 1) throw invalid()
    if (knownInstant !== undefined) {
      if (typeof knownInstant !== "string" || knownInstant.trim() !== knownInstant || knownInstant.length > 40
        || !/(?:Z|\+00:00)$/.test(knownInstant)) throw invalid()
      const known = DateTime.fromISO(knownInstant, { setZone: true })
      if (!known.isValid || known.year < 1 || known.offset !== 0) throw invalid()
      // An unchanged server instant already has a known offset and precision.
      // Preserve it rather than guessing a fold or dropping microseconds.
      if (known.setZone(timeZone).toISO({ includeOffset: false }) === wall.toISO({ includeOffset: false })) return knownInstant
    }
    const local = DateTime.fromISO(value, { zone: timeZone })
    if (!local.isValid
      || wall.toISO({ includeOffset: false }) !== local.toISO({ includeOffset: false })
      || local.getPossibleOffsets().length !== 1) throw invalid()
    const result = local.toUTC().toISO({ suppressMilliseconds: false })
    if (result === null) throw invalid()
    return result
  } catch {
    // Never echo untrusted wall/zone values or library exception details.
    throw invalid()
  }
}
