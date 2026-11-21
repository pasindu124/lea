import { useEffect, useState } from 'react'
import { api } from '../api'
import { useApp } from '../context'
import { Empty, ErrorBox, Guard, Loading } from '../ui'
import { CALIBRATION, fmtDate } from '../util'

export default function Tools({ initialQuery = '' }) {
  const { asOf } = useApp()
  const [input, setInput] = useState(initialQuery)
  const [query, setQuery] = useState(initialQuery)
  const [where, setWhere] = useState('')
  const [state, setState] = useState({ loading: false, error: null, data: null })

  useEffect(() => {
    if (!query) return
    let alive = true
    setState((s) => ({ ...s, loading: true, error: null }))
    api.toolsSearch(query, where || null, asOf || null).then(
      (data) => alive && setState({ loading: false, error: null, data }),
      (error) => alive && setState({ loading: false, error, data: null }),
    )
    return () => { alive = false }
  }, [query, where, asOf])

  const { data } = state
  const unverified = data?.rows.some((r) => r.calibration.status === 'UNVERIFIED')

  return (
    <div className="page">
      <div className="page-head">
        <h1>Tools</h1>
        <p>Find a tool, see whether it is at the line or in the main workshop, and what is known about its calibration.</p>
      </div>
      <form className="searchbar" onSubmit={(e) => { e.preventDefault(); setQuery(input.trim()) }}>
        <label className="field" style={{ flex: '1 1 320px' }}>
          <span>Tool number, serial number or words</span>
          <input className="input" value={input} onChange={(e) => setInput(e.target.value)} placeholder="For example: torque wrench, gauge" autoFocus />
        </label>
        <label className="field">
          <span>Location</span>
          <select className="select" value={where} onChange={(e) => setWhere(e.target.value)}>
            <option value="">Line and main</option><option value="line">Line only</option><option value="main">Main workshop only</option>
          </select>
        </label>
        <button className="btn primary" type="submit" disabled={!input.trim()}>Search</button>
      </form>
      <ErrorBox error={state.error} />
      {state.loading && <Loading text="Searching" />}
      {!query && <Empty>Type a tool name or number to start.</Empty>}
      {data && unverified && (
        <div className="callout">
          Calibration dates cannot be trusted in this export. Nearly every tool shows the same expiry date ({fmtDate(data.placeholder_expiry)}),
          which looks like a placeholder. Tools are marked “Unverified”: check the calibration label on the tool itself.
        </div>
      )}
      {data && query && (data.rows.length === 0
        ? <Empty>No tools match “{data.query}”.</Empty>
        : (
          <>
            <p className="muted" style={{ marginBottom: 10 }}>{data.total} tool{data.total === 1 ? '' : 's'} found{data.truncated ? ', showing the first rows: add more words to narrow the search' : ''}.</p>
            <div className="panel tablewrap">
              <table>
                <thead><tr><th>Row</th><th>Tool</th><th>Description</th><th>Serial</th><th>Where</th><th>Location</th><th>Calibration</th></tr></thead>
                <tbody>
                  {data.rows.map((r) => (
                    <tr key={`${r.source_file}-${r.source_row}`}>
                      <td title={`Excel row in ${r.source_file}`}>{r.source_row}</td>
                      <td><b>{r.part_no}</b></td><td>{r.description}</td><td>{r.serial}</td>
                      <td><span className={`chip ${r.where === 'line' ? 'ok' : ''}`}>{r.where === 'line' ? 'Line' : r.where === 'main' ? 'Main workshop' : 'Other'}</span></td>
                      <td>{r.location}</td>
                      <td title={r.calibration.why}><span className={`chip ${r.calibration.tone === 'neutral' ? '' : r.calibration.tone}`}>{CALIBRATION[r.calibration.status]}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="muted small" style={{ marginTop: 8 }}>Hover over a calibration label to see the reason for it.</p>
          </>
        ))}
      <Guard />
    </div>
  )
}
