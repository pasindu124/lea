import { useState } from 'react'
import { api } from '../api'
import { Empty, ErrorBox, Guard, Loading } from '../ui'
import { fmtDateTime, useAsync } from '../util'

const LABEL = {
  parts_search: 'Parts search', tools_search: 'Tools search', aircraft_view: 'Aircraft viewed', brief_view: 'Brief viewed',
  roster_auto: 'Split suggested', roster_change: 'Roster changed', ack_flag: 'Flag seen', work_done: 'Marked as done', work_done_undo: 'Done undone', ai_aircraft: 'AI summary', ai_parts: 'AI parts answer',
}

const describe = (e) => {
  const d = e.details || {}
  switch (e.action) {
    case 'parts_search': case 'tools_search': return `“${d.query}”, ${d.parts_found ?? d.found ?? 0} found`
    case 'aircraft_view': return d.aircraft
    case 'brief_view': return `${d.aircraft} aircraft, ${d.flags} flagged items`
    case 'roster_change': return `${d.aircraft}: ${d.before || 'not on shift'} to ${d.after || 'removed'}`
    case 'roster_auto': return `${Object.keys(d.assignments || {}).length} aircraft`
    case 'ack_flag': return `Work order ${d.wo_number}${d.note ? `: ${d.note}` : ''}`
    case 'work_done': return `Work order ${d.wo_number} (${d.aircraft}) done: ${d.note}`
    case 'work_done_undo': return `Work order ${d.wo_number}: removed "${d.removed_note}" (by ${d.was_done_by})`
    case 'ai_aircraft': return `${d.aircraft}${d.question ? `: ${d.question}` : ''}. Sources checked: ${d.citations_ok ? 'yes' : 'no'}`
    case 'ai_parts': return `“${d.query}”: ${d.question}. Sources checked: ${d.citations_ok ? 'yes' : 'no'}`
    default: return JSON.stringify(d)
  }
}

export default function Audit() {
  const { data, error, loading, reload } = useAsync(() => api.audit(300), [])
  const [action, setAction] = useState('')
  const rows = (data || []).filter((e) => !action || e.action === action)
  return (
    <div className="page">
      <div className="page-head">
        <h1>Audit log</h1>
        <p>A record of what was searched, what the agent suggested, and what people changed or confirmed. Newest first.</p>
      </div>
      <div className="searchbar">
        <label className="field"><span>Show</span>
          <select className="select" value={action} onChange={(e) => setAction(e.target.value)}>
            <option value="">All actions</option>
            {Object.entries(LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </label>
        <button className="btn" onClick={reload}>Refresh</button>
      </div>
      <ErrorBox error={error} />
      {loading && !data && <Loading />}
      {data && (rows.length === 0 ? <Empty>Nothing recorded yet.</Empty> : (
        <div className="panel tablewrap">
          <table>
            <thead><tr><th>When</th><th>Who</th><th>Action</th><th>Details</th></tr></thead>
            <tbody>
              {rows.map((e) => (
                <tr key={e.id}>
                  <td>{fmtDateTime(e.ts)}</td><td>{e.actor}</td><td>{LABEL[e.action] || e.action}</td>
                  <td style={{ overflowWrap: 'anywhere' }}>{describe(e)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
      <Guard />
    </div>
  )
}
