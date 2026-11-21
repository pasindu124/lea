import { STATUS, KIND, fmtDate } from './util'

export const Loading = ({ text = 'Loading' }) => <p className="muted"><span className="spinner" />{text}</p>

export const ErrorBox = ({ error }) => (error ? <div className="error" role="alert">{error.message || String(error)}</div> : null)

export const Empty = ({ children }) => <div className="empty">{children}</div>

export function StatusChip({ status, text }) {
  const s = STATUS[status] || STATUS.CHECK_SOURCE
  return <span className={`chip ${s.tone}`}>{text || s.label}</span>
}

// Where a line of information came from, so anyone can check it.
export function SourceTag({ source, label }) {
  if (!source) return null
  if (source.url) return <a className="tag" href={source.url} target="_blank" rel="noopener noreferrer">{label || 'Open case'}</a>
  const where = source.row ? `${source.file}, row ${source.row}` : source.file
  const title = `Source: ${where}${source.wo_number ? `, work order ${source.wo_number}` : ''}`
  return <span className="tag" title={title}>{label || `WO ${source.wo_number}`}</span>
}

// The rule behind a deadline, in plain language.
export function WhyDeferral({ item }) {
  const d = item.deferral
  return (
    <details>
      <summary>Why this status</summary>
      <div className="why">
        <p><b>{KIND[d.kind]}.</b> {d.rule}</p>
        {d.status === 'OVERDUE' && (
          <p>The work order is still open in the records after this date. It may be a record that was never closed, or a real overdue item. Confirm the real status before relying on this.</p>
        )}
        {d.is_assumption && <p>The day count for the category is an assumption (standard MMEL practice). Confirm it against the full MMEL.</p>}
        <p className="quote">{d.evidence}</p>
      </div>
    </details>
  )
}

export const Guard = () => (
  <p className="guard">
    Information only. The licensed engineer decides. This tool never signs, defers or releases an aircraft, and it never
    changes a record. Every status shows its rule and its source.
  </p>
)
