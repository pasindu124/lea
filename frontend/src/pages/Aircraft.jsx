import { api } from '../api'
import { useApp } from '../context'
import AircraftCard from '../AircraftCard'
import { Empty, ErrorBox, Guard, Loading } from '../ui'
import { useAsync } from '../util'

export default function Aircraft({ selected }) {
  const { asOf } = useApp()
  const list = useAsync(() => api.aircraftList(asOf || null), [asOf])
  const detail = useAsync(() => (selected ? api.aircraft(selected, asOf || null) : Promise.resolve(null)), [selected, asOf])

  return (
    <div className="page">
      <div className="page-head">
        <h1>Aircraft</h1>
        <p>Every Air Arabia aircraft with open items, most urgent first. Pick one to see its open faults, deadlines, predictive cases and recent messages.</p>
      </div>
      <ErrorBox error={list.error} />
      {list.loading && !list.data && <Loading />}
      {list.data && (
        <div className="split">
          <div className="pick" role="list" aria-label="Aircraft">
            {list.data.map((a) => {
              const tone = a.expires_today || a.overdue ? 'danger' : a.expires_soon ? 'caution' : ''
              return (
                <button key={a.aircraft_reg} className={tone} aria-pressed={selected === a.aircraft_reg}
                        onClick={() => { window.location.hash = `#/aircraft/${a.aircraft_reg}` }}>
                  <span className="reg">{a.aircraft_reg}</span>
                  <span className="muted small">{a.open_faults} open</span>
                  <div className="row" style={{ marginTop: 4 }}>
                    {a.expires_today > 0 && <span className="chip danger">{a.expires_today} due today</span>}
                    {a.overdue > 0 && <span className="chip danger">{a.overdue} past deadline</span>}
                    {a.expires_soon > 0 && <span className="chip caution">{a.expires_soon} due soon</span>}
                    {a.pha_open > 0 && <span className="chip brand">{a.pha_open} predictive</span>}
                  </div>
                </button>
              )
            })}
          </div>
          <div>
            {!selected && <Empty>Pick an aircraft from the list.</Empty>}
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
