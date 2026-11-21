import { useState } from 'react'
import { api } from '../api'
import { useApp } from '../context'
import AircraftCard from '../AircraftCard'
import { Empty, ErrorBox, Guard, Loading, SourceTag, StatusChip, WhyDeferral } from '../ui'
import { STATUS, deadlineLine, fmtDate, useAsync } from '../util'

// The most urgent item of the shift, drawn like a flight strip.
function Strip({ flag }) {
  if (!flag) {
    return (
      <div className="strip calm">
        <div className="reg">All clear<small>No deadlines today, soon, or past in tonight's aircraft</small></div>
        <div className="what muted">Check the aircraft below for items with no calculated date.</div>
        <div />
      </div>
    )
  }
  const tone = STATUS[flag.status].tone
  return (
    <div className={`strip ${tone === 'caution' ? 'caution' : ''}`} role="region" aria-label="Most urgent item">
      <div className="reg">{flag.aircraft_reg}<small>Most urgent item tonight</small></div>
      <div className="what">
        <h2>{flag.title}</h2>
        <div className="row small muted">
          <SourceTag source={flag.source} /> <StatusChip status={flag.status} />
        </div>
      </div>
      <div className="when">
        <b>{flag.status_text}</b>
        <span className="muted small">{flag.expires_on ? `Deadline ${fmtDate(flag.expires_on)}` : ''}</span>
      </div>
      <details>
        <summary>Why this is flagged</summary>
        <div className="why">
          <p>{flag.rule}</p>
          {flag.status === 'OVERDUE' && <p>It is still open in the records after its deadline: confirm the real status.</p>}
          <p>Source: {flag.source.file}, row {flag.source.row}.</p>
        </div>
      </details>
    </div>
  )
}

function FlagList({ flags }) {
  const [all, setAll] = useState(false)
  if (!flags.length) return null
  const shown = all ? flags : flags.slice(0, 6)
  return (
    <section className="panel" style={{ marginBottom: 14 }}>
      <div className="panel-head"><h2>Needs attention first</h2><span className="chip">{flags.length} items</span></div>
      <div className="panel-body">
        {shown.map((f) => (
          <div key={f.wo_number} className={`item ${STATUS[f.status].tone}`}>
            <div className="top">
              <span><b className="reg-inline">{f.aircraft_reg}</b></span>
              <span className="title">{f.title}</span>
              <StatusChip status={f.status} />
            </div>
            <div className="meta">
              {deadlineLine(f)} <SourceTag source={f.source} />
            </div>
          </div>
        ))}
        {flags.length > 6 && <button className="btn quiet small" onClick={() => setAll(!all)}>{all ? 'Show fewer' : `Show all ${flags.length}`}</button>}
      </div>
    </section>
  )
}

export default function Brief() {
  const { asOf } = useApp()
  const { data, error, loading, reload } = useAsync(() => api.brief(asOf || null), [asOf])
  const [tab, setTab] = useState(0)

  return (
    <div className="page">
      <div className="page-head">
        <h1>Shift brief</h1>
        <p>What each engineer needs to know before the shift: what is urgent, what can wait, and where to look. Every line links to its source.</p>
      </div>
      <ErrorBox error={error} />
      {loading && !data && <Loading text="Building the brief" />}
      {data && (
        <>
          <div className="callout info">
            This roster is a placeholder: aircraft were split between engineers automatically for the demo, with the most urgent spread out.
            Planning's real roster replaces it. <a href="#/shift">Change the split</a>.
          </div>
          <Strip flag={data.shift_top_flag} />
          <div className="tabs" role="tablist">
            {data.engineers.map((e, i) => (
              <button key={e.name} role="tab" className="tab" aria-selected={tab === i} onClick={() => setTab(i)}>
                {e.name}
                <span className="chip">{e.aircraft.length} aircraft</span>
                {e.flags.length > 0 && <span className="chip danger">{e.flags.length} flagged</span>}
              </button>
            ))}
          </div>
          {data.engineers[tab] && (
            data.engineers[tab].aircraft.length === 0
              ? <Empty>No aircraft assigned to {data.engineers[tab].name}. Assign some in <a href="#/shift">Shift setup</a>.</Empty>
              : (
                <>
                  <FlagList flags={data.engineers[tab].flags} />
                  <div className="stack">
                    {data.engineers[tab].aircraft.map((a, i) => (
                      <AircraftCard key={`${tab}-${a.aircraft_reg}`} detail={a} defaultOpen={i === 0} onChanged={reload} />
                    ))}
                  </div>
                </>
              )
          )}
        </>
      )}
      <Guard />
    </div>
  )
}
