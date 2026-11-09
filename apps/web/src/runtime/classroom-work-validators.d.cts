type Validator = ((value: unknown) => boolean) & { errors: unknown }
export const capabilities: Validator
export const listing: Validator
export const results: Validator
export const seating: Validator
export const preview: Validator
