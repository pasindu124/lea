import { useMemo, useState } from 'react'
import { api } from '../api'
import { useApp } from '../context'
import AircraftCard from '../AircraftCard'
import { Empty, ErrorBox, Guard, Loading } from '../ui'
import { useAsync } from '../util'

export default function Aircraft({ selected }) {
  const { asOf } = useApp()
  const list = useAsync(() => api.aircraftList(asOf || null), [asOf])
  const detail = useAsync(() => (selected ? api.aircraft(selected, asOf || null) : Promise.resolve(null)), [selected, asOf])

  const [q, setQ] = useState('')
  const [onlyUrgent, setOnlyUrgent] = useState(false)
  const [sort, setSort] = useState({ key: 'urgency', dir: -1 })
  const rows = useMemo(() => {
    const urg = (a) => a.expires_today * 1000 + a.overdue * 100 + a.expires_soon * 10
    const val = (a) => (sort.key === 'urgency' ? urg(a) : sort.key === 'aircraft_reg' ? a.aircraft_reg : a[sort.key])
    return (list.data || [])
      .filter((a) => a.aircraft_reg.toLowerCase().includes(q.trim().toLowerCase()))
      .filter((a) => !onlyUrgent || a.expires_today || a.overdue || a.expires_soon)
      .sort((a, b) => (val(a) > val(b) ? 1 : val(a) < val(b) ? -1 : 0) * sort.dir)
  }, [list.data, q, onlyUrgent, sort])
  const th = (key, label, num) => (
    <th className={num ? 'num' : ''} aria-sort={sort.key === key ? (sort.dir > 0 ? 'ascending' : 'descending') : 'none'}>
      <button className="sortbtn" onClick={() => setSort({ key, dir: sort.key === key ? -sort.dir : key === 'aircraft_reg' ? 1 : -1 })}>
        {label}{sort.key === key ? (sort.dir > 0 ? ' ▲' : ' ▼') : ''}
      </button>
    </th>
  )

  return (
    <div className="page">
      <div className="page-head">
        <h1>Aircraft</h1>
        <p>Every Air Arabia aircraft with open items, most urgent first. Pick one to see its open faults, deadlines, predictive cases and recent messages.</p>
      </div>
      <ErrorBox error={list.error} />
      {list.loading && !list.data && <Loading />}
      {list.data && (
        <div className="stack">
          <div className="panel ac-list">
            <div className="searchbar" style={{ margin: 0, padding: '12px 14px' }}>
              <input className="input grow" placeholder="Filter by registration, for example A6-AOA" value={q}
                     onChange={(e) => setQ(e.target.value)} aria-label="Filter aircraft" />
              <label className="row small"><input type="checkbox" checked={onlyUrgent} onChange={(e) => setOnlyUrgent(e.target.checked)} /> Needs attention only</label>
              <span className="muted small">{rows.length} of {list.data.length} aircraft</span>
            </div>
            <div className="tablewrap ac-table">
              <table>
                <thead><tr>
                  {th('aircraft_reg', 'Aircraft')}{th('urgency', 'Urgency', true)}{th('open_faults', 'Open', true)}
                  {th('expires_today', 'Due today', true)}{th('overdue', 'Past deadline', true)}
                  {th('expires_soon', 'Due soon', true)}{th('pha_open', 'Predictive', true)}
                </tr></thead>
                <tbody>
                  {rows.map((a) => {
                    const tone = a.expires_today || a.overdue ? 'danger' : a.expires_soon ? 'caution' : ''
                    return (
                      <tr key={a.aircraft_reg} className={`pickrow ${tone}`} aria-selected={selected === a.aircraft_reg} tabIndex={0}
                          onClick={() => { window.location.hash = `#/aircraft/${a.aircraft_reg}` }}
                          onKeyDown={(e) => e.key === 'Enter' && (window.location.hash = `#/aircraft/${a.aircraft_reg}`)}>
                        <td><span className="reg-inline">{a.aircraft_reg}</span></td>
                        <td className="num">{tone ? <span className={`chip ${tone}`}>{tone === 'danger' ? 'High' : 'Medium'}</span> : <span className="muted">-</span>}</td>
                        <td className="num">{a.open_faults}</td>
                        <td className="num">{a.expires_today || <span className="muted">-</span>}</td>
                        <td className="num">{a.overdue || <span className="muted">-</span>}</td>
                        <td className="num">{a.expires_soon || <span className="muted">-</span>}</td>
                        <td className="num">{a.pha_open || <span className="muted">-</span>}</td>
                      </tr>
                    )
                  })}
                  {rows.length === 0 && <tr><td colSpan={7} className="muted">No aircraft match.</td></tr>}
                </tbody>
              </table>
            </div>
          </div>
          <div>
            {!selected && <Empty>Pick an aircraft from the table.</Empty>}
            <ErrorBox error={detail.error} />
            {selected && detail.loading && !detail.data && <Loading />}
            {detail.data && <AircraftCard key={detail.data.aircraft_reg} detail={detail.data} defaultOpen onChanged={detail.reload} />}
          </div>
        </div>
      )}
      <Guard />
    </div>
  )
}
