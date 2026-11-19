export const num = (n: number | undefined | null) => (n ?? 0).toLocaleString('en-IN')

export const pct = (x: number | undefined | null, digits = 1) => `${(x ?? 0).toFixed(digits)}%`

export const conf = (x: number) => `${Math.round(x * 100)}%`

export const ISSUE_LABELS: Record<string, string> = {
  missing: 'Missing', disguised_missing: 'Placeholder', invalid_format: 'Invalid format', inconsistent: 'Inconsistent',
  fd_violation: 'Rule violation', crossfield: 'Cross-field', anomaly: 'Unusual', duplicate: 'Duplicate',
  near_duplicate: 'Near duplicate', sparse_column: 'Optional column',
}

export const TYPE_LABELS: Record<string, string> = {
  id: 'ID', name: 'Name', email: 'Email', phone: 'Phone', pin: 'PIN code', date: 'Date', age: 'Age', money: 'Amount (₹)',
  pan: 'PAN', gstin: 'GSTIN', aadhaar: 'Aadhaar', ifsc: 'IFSC', city: 'City', state: 'State', district: 'District',
  locality: 'Locality', category: 'Category', text: 'Free text', number: 'Number', unknown: 'Unknown',
}

export const OVERRIDABLE_TYPES = Object.keys(TYPE_LABELS)

export const DIMENSION_LABELS: Record<string, string> = {
  completeness: 'Completeness', validity: 'Validity', consistency: 'Consistency', uniqueness: 'Uniqueness',
  clean_rows: 'Clean rows',
}

/** Never show raw personal data in the UI: mask samples of PII-typed columns. */
export function maskSample(x: string, type: string): string {
  const v = x.trim()
  if (!v) return v
  const digits = v.replace(/\D/g, '')
  if (digits.length >= 5 && /^(\d)\1+$/.test(digits)) return v  // placeholder like 9999999999, not personal data
  switch (type) {
    case 'phone': return digits.length >= 4 ? `${digits.slice(0, 2)}XXXXXX${digits.slice(-2)}` : 'XXXX'
    case 'email': { const [l, d] = v.split('@'); return d ? `${l.slice(0, 2)}***@${d}` : '***' }
    case 'aadhaar': return `XXXX XXXX ${digits.slice(-4)}`
    case 'pan': return `${v.slice(0, 5)}****${v.slice(-1)}`
    case 'gstin': return `${v.slice(0, 2)}XXXXXXXXXX${v.slice(-3)}`
    case 'text': return v.replace(/\d{4,}/g, (m) => 'X'.repeat(m.length - 2) + m.slice(-2))
    default: return v
  }
}

export function cn(...parts: (string | false | null | undefined)[]) {
  return parts.filter(Boolean).join(' ')
}
