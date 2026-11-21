// Flight schedule pieces shared by the aircraft card, the brief and shift setup.
// Times from the API are Sharjah local time (the backend converts them) and are written without a time zone.
import { useApp } from './context'
import { SourceTag } from './ui'

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

// "2026-11-21T02:30:00" -> "21 Nov 02:30" (string slicing: no time zone shift)
export const fmtWhen = (v) => (v ? `${Number(v.slice(8, 10))} ${MONTHS[Number(v.slice(5, 7)) - 1]} ${v.slice(11, 16)}` : '')
const timeOnly = (v) => v.slice(11, 16)
const sameDay = (a, b) => a.slice(0, 10) === b.slice(0, 10)
export const fmtGround = (hours) => {
  const m = Math.round(hours * 60)
  return `${Math.floor(m / 60)}h${String(m % 60).padStart(2, '0')}`
}

function windowText(w) {
  const dest = w.next_destination ? ` to ${w.next_destination}` : ''
  const leaves = w.departure_time
    ? `leaves ${w.arrival_time && sameDay(w.arrival_time, w.departure_time) ? timeOnly(w.departure_time) : fmtWhen(w.departure_time)} (${w.departure_flight}${dest})`
    : 'no later departure in the schedule'
  if (!w.arrival_time) return `At Sharjah when the schedule starts, ${leaves}`
  const ground = w.ground_hours != null ? `, ${fmtGround(w.ground_hours)} on the ground` : ''
  return `Lands ${fmtWhen(w.arrival_time)} (${w.arrival_flight}), ${leaves}${ground}`
}

export const planned = (w) => !w.used_actuals

// The "Aircraft and times" line at the top of an aircraft card.
export function TimesLine({ schedule }) {
  const { meta } = useApp()
  if (!schedule) return null
  if (!schedule.available) return <div className="times muted small"><b>Aircraft and times</b> No flight schedule for this shift.</div>
  const w = schedule.tonight
  if (!w) {
    const n = schedule.next_arrival
    return (
      <div className="times small">
        <b>Aircraft and times</b> Not at Sharjah during the shift.
        {n ? <> Next arrival {fmtWhen(n.arrival_time)} ({n.arrival_flight}).</> : ' No later arrival in the schedule.'}
      </div>
    )
  }
  return (
    <div className="times small">
      <b>Aircraft and times</b> {windowText(w)}.
      {w.tight && <span className="chip caution">Under {meta?.schedule?.short_ground_hours ?? 2} hours on the ground</span>}
      {w.kind === 'arrival_not_in_schedule' && <span className="chip">Arrival not in the schedule</span>}
      <span className="muted"> {planned(w) ? 'Planned schedule, not actual times.' : 'Includes actual times.'}</span>
      {' '}<SourceTag source={w.sources[0]} />
    </div>
  )
}

export function TimingNotes({ notes }) {
  if (!notes || !notes.length) return null
  return <ul className="timing-notes small muted">{notes.map((n, i) => <li key={i}>{n}</li>)}</ul>
}

// Shown when no flight schedule covers the shift: the roster then falls back to the plain split.
export function NoScheduleCallout({ schedule }) {
  if (!schedule || schedule.available) return null
  return (
    <div className="callout" role="note">
      <b>No flight schedule for this shift.</b> {schedule.reason} The shift list was made without ground times,
      so it may include aircraft that are not at Sharjah tonight.
    </div>
  )
}

// Urgent aircraft that are not at Sharjah during the shift: listed, never dropped silently.
export function NotAtSharjah({ schedule }) {
  if (!schedule || !schedule.available) return null
  const list = schedule.not_at_sharjah || []
  if (!list.length && !schedule.other_away) return null
  return (
    <section className="panel" style={{ marginBottom: 14 }}>
      <div className="panel-head"><h2>Not at Sharjah tonight</h2><span className="chip">{list.length} with a deadline soon</span></div>
      <div className="panel-body">
        {list.length === 0 && <p className="muted small">None of the aircraft with a deadline today or soon is away.</p>}
        {list.map((a) => (
          <div key={a.aircraft_reg} className="item caution">
            <div className="top">
              <b className="reg-inline">{a.aircraft_reg}</b>
              <span className="title">
                {a.next_arrival ? `Next arrival at Sharjah ${fmtWhen(a.next_arrival.arrival_time)} (${a.next_arrival.arrival_flight})` : 'No later arrival at Sharjah in the schedule'}
              </span>
              {a.expires_today > 0 && <span className="chip danger">{a.expires_today} due today</span>}
              {a.expires_soon > 0 && <span className="chip caution">{a.expires_soon} due soon</span>}
            </div>
            <div className="meta">
              Left out of tonight's list because it is not on the ground at Sharjah during the shift.
              {a.next_arrival && <> <SourceTag source={a.next_arrival.sources[0]} /></>}
            </div>
          </div>
        ))}
        {schedule.other_away > 0 && <p className="muted small">{schedule.other_away} more aircraft with open items are also away, with no deadline today or soon.</p>}
      </div>
    </section>
  )
}

export function OverlapWarning({ warnings }) {
  if (!warnings || !warnings.length) return null
  return (
    <div className="callout" role="note">
      <b>Several aircraft at the same time.</b>
      <ul style={{ margin: '4px 0 0 18px' }}>
        {warnings.map((w) => (
          <li key={w.aircraft.join('-')}>
            {w.aircraft.join(' and ')} are on the ground together for {fmtGround(w.overlap_minutes / 60)}
            {' '}and both have a short ground time.
          </li>
        ))}
      </ul>
    </div>
  )
}
