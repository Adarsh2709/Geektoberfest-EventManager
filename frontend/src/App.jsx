import { useEffect, useState } from 'react'
import { Link, Navigate, Route, Routes, useNavigate, useParams } from 'react-router-dom'
import { api } from './api'
import EventCard from './components/EventCard'
import EventForm from './components/EventForm'

function Navbar({ user, onLogout }) {
  return <header className="navbar"><Link to="/" className="brand"><span className="brand-mark">E</span> Event Hub</Link>
    <nav>{user ? <><Link to="/my-events">My events</Link><Link to="/create">Create event</Link>
      <span className="nav-user">Hi, {user.username}</span><button className="button button-small button-quiet" onClick={onLogout}>Log out</button></>
      : <><Link to="/login">Log in</Link><Link to="/register" className="button button-small">Get started</Link></>}</nav>
  </header>
}

function Home() {
  const [events, setEvents] = useState([])
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState('upcoming')
  const [sort, setSort] = useState('soonest')
  const [error, setError] = useState('')

  async function fetchEvents(currentFilter = filter, currentSort = sort, currentQuery = query) {
    try {
      const q = currentQuery.trim()
      const url = q
        ? `/events/search?q=${encodeURIComponent(q)}&filter=${currentFilter}&sort=${currentSort}`
        : `/events?filter=${currentFilter}&sort=${currentSort}`
      setEvents(await api(url))
    } catch (err) {
      setError(err.message)
    }
  }

  useEffect(() => { fetchEvents(filter, sort, query) }, [filter, sort])

  async function search(event) {
    event.preventDefault()
    setError('')
    await fetchEvents(filter, sort, query)
  }

  const headingText = filter === 'upcoming' ? 'Coming up' : filter === 'past' ? 'Past events' : 'All events'
  return <><section className="hero"><div className="hero-copy"><span className="eyebrow">MAKE ROOM FOR SOMETHING GOOD</span>
    <h1>Your next favorite<br />memory starts here.</h1><p>Find people, ideas, and moments worth showing up for.</p>
    <form className="search-form" onSubmit={search}><span aria-hidden="true">⌕</span><input aria-label="Search events" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search events, places, ideas..." /><button className="button">Search</button></form>
  </div><div className="hero-art" aria-hidden="true"><div className="sun"></div><div className="art-note note-one">✳</div><div className="art-note note-two">♫</div><div className="art-card"><span>YOUR PLANS, SORTED</span><strong>Good things<br />are happening.</strong><div className="art-card-bottom"><i></i><i></i><i></i><small>and you're invited</small></div></div><div className="art-orbit"></div></div></section>
    <main className="page-content"><div className="section-heading"><div><span className="eyebrow">THE GOOD STUFF</span><h2>{headingText}</h2></div>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <button type="button" className={`button button-small ${filter === 'upcoming' ? '' : 'button-quiet'}`} onClick={() => setFilter('upcoming')}>Upcoming</button>
          <button type="button" className={`button button-small ${filter === 'past' ? '' : 'button-quiet'}`} onClick={() => setFilter('past')}>Past</button>
          <button type="button" className={`button button-small ${filter === 'all' ? '' : 'button-quiet'}`} onClick={() => setFilter('all')}>All</button>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <label htmlFor="sort-select" className="muted" style={{ fontSize: '0.85rem' }}>Sort by:</label>
          <select id="sort-select" value={sort} onChange={(e) => setSort(e.target.value)} style={{ padding: '0.35rem 0.6rem', borderRadius: '6px', border: '1px solid #ccc', background: '#fff', fontSize: '0.85rem' }}>
            <option value="soonest">Soonest first</option>
            <option value="latest">Latest first</option>
          </select>
        </div>
        <span className="event-total" style={{ marginLeft: '0.5rem' }}>{events.length} {events.length === 1 ? 'event' : 'events'}</span>
      </div>
    </div>
      {error && <p className="notice notice-error">{error}</p>}
      {events.length ? <div className="event-grid">{events.map((item) => <EventCard event={item} key={item.id} />)}</div> : <div className="empty-state"><span>✳</span><h3>{filter === 'past' ? 'No past events found' : query ? 'No matching events found' : 'No events just yet'}</h3><p>{query ? 'Try adjusting your search terms or date filter.' : filter === 'past' ? 'Past events will appear here once gatherings finish.' : 'Check back soon, or be the first to put something on.'}</p></div>}
    </main></>
}

function AuthPage({ mode, onLogin }) {
  const navigate = useNavigate()
  const [values, setValues] = useState({ username: '', email: '', password: '' })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const registering = mode === 'register'
  async function submit(event) {
    event.preventDefault(); setError(''); setBusy(true)
    try {
      if (registering) await api('/auth/register', { method: 'POST', body: JSON.stringify(values) })
      const token = await api('/auth/login', { method: 'POST', body: JSON.stringify({ email: values.email, password: values.password }) })
      localStorage.setItem('eventhub_token', token.access_token)
      await onLogin()
      navigate('/')
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }
  return <main className="auth-wrap"><div className="auth-card"><span className="eyebrow">WELCOME {registering ? 'ABOARD' : 'BACK'}</span>
    <h1>{registering ? 'Make yourself at home.' : 'Good to see you.'}</h1><p className="muted">{registering ? 'Create an account to join the fun.' : 'Log in to pick up where you left off.'}</p>
    {error && <p className="notice notice-error">{error}</p>}
    <form className="stack-form" onSubmit={submit}>{registering && <label>Your name<input required minLength="2" maxLength="50" value={values.username} onChange={(e) => setValues({ ...values, username: e.target.value })} /></label>}
      <label>Email<input type="email" required value={values.email} onChange={(e) => setValues({ ...values, email: e.target.value })} /></label>
      <label>Password<input type="password" required minLength={registering ? 8 : 1} value={values.password} onChange={(e) => setValues({ ...values, password: e.target.value })} /></label>
      <button className="button button-wide" disabled={busy}>{busy ? 'One moment…' : registering ? 'Create account' : 'Log in'}</button>
    </form><p className="auth-switch">{registering ? 'Already part of the crowd?' : 'New around here?'} <Link to={registering ? '/login' : '/register'}>{registering ? 'Log in' : 'Create an account'}</Link></p>
  </div></main>
}

function EventDetails({ user }) {
  const { eventId } = useParams()
  const navigate = useNavigate()
  const [event, setEvent] = useState(null); const [registered, setRegistered] = useState(false); const [waitlistPosition, setWaitlistPosition] = useState(null)
  const [error, setError] = useState(''); const [message, setMessage] = useState('')
  async function load() {
    try {
      const item = await api(`/events/${eventId}`); setEvent(item)
      if (user) { const mine = await api('/users/me/events'); setRegistered(mine.attending.some((e) => e.id === item.id)); setWaitlistPosition(mine.waitlisted.find((e) => e.id === item.id)?.waitlist_position ?? null) }
    } catch (err) { setError(err.message) }
  }
  useEffect(() => { load() }, [eventId, user])
  async function toggleRegistration() {
    if (!user) return navigate('/login')
    setError(''); setMessage('')
    try {
      await api(`/events/${eventId}/register`, { method: registered ? 'DELETE' : 'POST' })
      setRegistered(!registered); setMessage(registered ? 'Your spot has been released.' : 'You’re on the list!')
      await load()
    } catch (err) {
      setError(err.message)
      await load()
    }
  }
  async function toggleWaitlist() {
    if (!user) return navigate('/login')
    setError(''); setMessage('')
    const leaving = waitlistPosition !== null
    try {
      const result = await api(`/events/${eventId}/waitlist`, { method: leaving ? 'DELETE' : 'POST' })
      setMessage(leaving ? 'You left the waitlist.' : `You’re on the waitlist at position ${result.position}. We’ll move you in if a spot opens.`)
      await load()
    } catch (err) { setError(err.message) }
  }
  const full = event && event.attendee_count >= event.capacity
  if (error && !event) return <main className="page-content"><p className="notice notice-error">{error}</p><Link to="/">Back to events</Link></main>
  if (!event) return <main className="page-content"><p className="muted">Loading event…</p></main>
  return <main className="detail-wrap"><Link to="/" className="back-link">← All events</Link><article className="detail-card"><div className="detail-banner"><span className="eyebrow">YOU'RE INVITED</span><span className="detail-date">{dateLabel(event.start_time)}</span></div><div className="detail-body"><span className="eyebrow">{event.location}</span><h1>{event.title}</h1><p className="detail-description">{event.description}</p><div className="detail-facts"><div><span>WHEN</span><strong>{dateLabel(event.start_time)}</strong><p>{timeLabel(event.start_time)} – {timeLabel(event.end_time)}</p></div><div><span>WHERE</span><strong>{event.location}</strong><p>Come as you are</p></div><div><span>HOSTED BY</span><strong>{event.organizer.username}</strong><p>Your event host</p></div><div><span>ATTENDEES</span><strong>{event.attendee_count} {event.attendee_count === 1 ? 'attendee' : 'attendees'}</strong><p>{event.capacity - event.attendee_count > 0 ? `${event.capacity - event.attendee_count} spots available` : 'Full capacity'}</p></div></div><div className="capacity-row"><span className="capacity-text">{event.attendee_count} of {event.capacity} spots taken</span><div className="capacity-track"><i style={{ width: `${Math.min(100, (event.attendee_count / event.capacity) * 100)}%` }} /></div></div>
      {error && <p className="notice notice-error">{error}</p>}{message && <p className="notice notice-success">{message}</p>}
      {event.waitlist_count > 0 && <p className="muted">{event.waitlist_count} on the waitlist</p>}
      {!registered && full
        ? <button className="button" onClick={toggleWaitlist}>{waitlistPosition !== null ? `Leave waitlist (you’re #${waitlistPosition})` : user ? 'Join the waitlist' : 'Log in to join the waitlist'}</button>
        : <button className="button" onClick={toggleRegistration}>{registered ? 'Cancel my spot' : user ? 'Save my spot' : 'Log in to join'}</button>}
    </div></article></main>
}

function CreateEvent() {
  const navigate = useNavigate(); const [error, setError] = useState('')
  async function save(values) {
    try { const event = await api('/events', { method: 'POST', body: JSON.stringify(values) }); navigate(`/events/${event.id}`) }
    catch (err) { setError(err.message) }
  }
  return <main className="form-page"><Link to="/" className="back-link">← Back home</Link><div className="form-heading"><span className="eyebrow">HOST SOMETHING</span><h1>Put it on the calendar.</h1><p className="muted">A good gathering starts with an invitation.</p></div>{error && <p className="notice notice-error">{error}</p>}<EventForm onSubmit={save} submitLabel="Create event" /></main>
}

function EditEvent({ user }) {
  const { eventId } = useParams(); const navigate = useNavigate()
  const [event, setEvent] = useState(null); const [error, setError] = useState('')
  useEffect(() => { api(`/events/${eventId}`).then(setEvent).catch((err) => setError(err.message)) }, [eventId])
  async function save(values) {
    try { await api(`/events/${eventId}`, { method: 'PUT', body: JSON.stringify(values) }); navigate('/my-events') }
    catch (err) { setError(err.message) }
  }
  return <main className="form-page"><Link to="/my-events" className="back-link">← My events</Link><div className="form-heading"><span className="eyebrow">YOUR EVENT</span><h1>Make a change.</h1><p className="muted">Update the details for your gathering.</p></div>
    {error && <p className="notice notice-error">{error}</p>}{event && event.organizer_id !== user.id ? <p className="notice notice-error">Only the organizer can edit this event.</p> : event ? <EventForm onSubmit={save} submitLabel="Save changes" initialValues={event} /> : !error && <p className="muted">Loading event…</p>}
  </main>
}

function MyEvents() {
  const navigate = useNavigate()
  const [data, setData] = useState({ attending: [], organized: [], waitlisted: [] }); const [notifications, setNotifications] = useState([]); const [error, setError] = useState('')
  async function load() { try { setData(await api('/users/me/events')); setNotifications(await api('/users/me/notifications')) } catch (err) { setError(err.message) } }
  async function markRead() { try { await api('/users/me/notifications/read', { method: 'POST' }); await load() } catch (err) { setError(err.message) } }
  useEffect(() => { load() }, [])
  async function deleteEvent(event) {
    if (!window.confirm(`Delete “${event.title}”? This also removes its registrations.`)) return
    try { await api(`/events/${event.id}`, { method: 'DELETE' }); await load() }
    catch (err) { setError(err.message) }
  }
  return <main className="page-content my-events"><span className="eyebrow">YOUR LITTLE BLACK BOOK</span><h1>My events</h1>{error && <p className="notice notice-error">{error}</p>}
    {notifications.length > 0 && <section><div className="section-heading"><h2>Notifications</h2>{notifications.some((n) => !n.read) && <button className="button button-small button-quiet" onClick={markRead}>Mark all read</button>}</div>{notifications.map((n) => <p className={`notice ${n.read ? '' : 'notice-success'}`} key={n.id}>{n.message}</p>)}</section>}
    <section><div className="section-heading"><h2>I'm attending</h2></div>{data.attending.length ? <div className="event-grid">{data.attending.map((event) => <EventCard event={event} key={event.id} />)}</div> : <p className="muted">No plans on the books yet. Find something to join.</p>}</section>
    {data.waitlisted.length > 0 && <section><div className="section-heading"><h2>I'm on the waitlist</h2></div><div className="event-grid">{data.waitlisted.map((event) => <EventCard event={event} key={event.id} actions={<span>You’re #{event.waitlist_position} in line</span>} />)}</div></section>}
    <section><div className="section-heading"><h2>I'm hosting</h2></div>{data.organized.length ? <div className="event-grid">{data.organized.map((event) => <EventCard event={event} key={event.id} actions={<><button onClick={() => navigate(`/events/${event.id}/edit`)}>Edit</button><button className="delete-action" onClick={() => deleteEvent(event)}>Delete</button></>} />)}</div> : <p className="muted">Nothing on the calendar yet. Host your first event!</p>}</section>
  </main>
}

export default function App() {
  const [user, setUser] = useState(null); const [ready, setReady] = useState(false)
  async function refreshUser() {
    const token = localStorage.getItem('eventhub_token')
    if (!token) { setUser(null); setReady(true); return }
    try { setUser(await api('/auth/me')) } catch { localStorage.removeItem('eventhub_token'); setUser(null) }
    setReady(true)
  }
  useEffect(() => { refreshUser() }, [])
  function logout() { localStorage.removeItem('eventhub_token'); setUser(null) }
  if (!ready) return <div className="loading">Event Hub</div>
  return <><Navbar user={user} onLogout={logout} /><Routes><Route path="/" element={<Home />} />
    <Route path="/login" element={user ? <Navigate to="/" /> : <AuthPage mode="login" onLogin={refreshUser} />} />
    <Route path="/register" element={user ? <Navigate to="/" /> : <AuthPage mode="register" onLogin={refreshUser} />} />
    <Route path="/events/:eventId" element={<EventDetails user={user} />} />
    <Route path="/events/:eventId/edit" element={user ? <EditEvent user={user} /> : <Navigate to="/login" />} />
    <Route path="/create" element={user ? <CreateEvent /> : <Navigate to="/login" />} />
    <Route path="/my-events" element={user ? <MyEvents /> : <Navigate to="/login" />} />
    <Route path="*" element={<main className="page-content"><h1>That page wandered off.</h1><Link to="/">Back home</Link></main>} />
  </Routes><footer>Made for good company. <span>Event Hub · Open-source starter</span></footer></>
}

function dateLabel(value) { return new Date(value).toLocaleDateString(undefined, { day: 'numeric', month: 'long', year: 'numeric' }) }
function timeLabel(value) { return new Date(value).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' }) }
