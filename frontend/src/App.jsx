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
  const [error, setError] = useState('')
  useEffect(() => { api('/events').then(setEvents).catch((err) => setError(err.message)) }, [])
  async function search(event) {
    event.preventDefault()
    setError('')
    try { setEvents(query.trim() ? await api(`/events/search?q=${encodeURIComponent(query.trim())}`) : await api('/events')) }
    catch (err) { setError(err.message) }
  }
  const upcoming = events.filter((item) => new Date(item.end_time) >= new Date())
  return <><section className="hero"><div className="hero-copy"><span className="eyebrow">MAKE ROOM FOR SOMETHING GOOD</span>
    <h1>Your next favorite<br />memory starts here.</h1><p>Find people, ideas, and moments worth showing up for.</p>
    <form className="search-form" onSubmit={search}><span aria-hidden="true">⌕</span><input aria-label="Search events" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search events, places, ideas..." /><button className="button">Search</button></form>
  </div><div className="hero-art" aria-hidden="true"><div className="sun"></div><div className="art-note note-one">✳</div><div className="art-note note-two">♫</div><div className="art-card"><span>YOUR PLANS, SORTED</span><strong>Good things<br />are happening.</strong><div className="art-card-bottom"><i></i><i></i><i></i><small>and you're invited</small></div></div><div className="art-orbit"></div></div></section>
    <main className="page-content"><div className="section-heading"><div><span className="eyebrow">THE GOOD STUFF</span><h2>Coming up</h2></div><span className="event-total">{upcoming.length} {upcoming.length === 1 ? 'event' : 'events'}</span></div>
      {error && <p className="notice notice-error">{error}</p>}
      {upcoming.length ? <div className="event-grid">{upcoming.map((item) => <EventCard event={item} key={item.id} />)}</div> : <div className="empty-state"><span>✳</span><h3>No events just yet</h3><p>Check back soon, or be the first to put something on.</p></div>}
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
  const [event, setEvent] = useState(null); const [registered, setRegistered] = useState(false)
  const [error, setError] = useState(''); const [message, setMessage] = useState('')
  async function load() {
    try {
      const item = await api(`/events/${eventId}`); setEvent(item)
      if (user) { const mine = await api('/users/me/events'); setRegistered(mine.attending.some((e) => e.id === item.id)) }
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
    } catch (err) { setError(err.message) }
  }
  if (error && !event) return <main className="page-content"><p className="notice notice-error">{error}</p><Link to="/">Back to events</Link></main>
  if (!event) return <main className="page-content"><p className="muted">Loading event…</p></main>
  return <main className="detail-wrap"><Link to="/" className="back-link">← All events</Link><article className="detail-card"><div className="detail-banner"><span className="eyebrow">YOU'RE INVITED</span><span className="detail-date">{dateLabel(event.start_time)}</span></div><div className="detail-body"><span className="eyebrow">{event.location}</span><h1>{event.title}</h1><p className="detail-description">{event.description}</p><div className="detail-facts"><div><span>WHEN</span><strong>{dateLabel(event.start_time)}</strong><p>{timeLabel(event.start_time)} – {timeLabel(event.end_time)}</p></div><div><span>WHERE</span><strong>{event.location}</strong><p>Come as you are</p></div><div><span>HOSTED BY</span><strong>{event.organizer.username}</strong><p>Your event host</p></div></div><div className="capacity-row"><span>{event.attendee_count} of {event.capacity} spots taken</span><div className="capacity-track"><i style={{ width: `${Math.min(100, (event.attendee_count / event.capacity) * 100)}%` }} /></div></div>
      {error && <p className="notice notice-error">{error}</p>}{message && <p className="notice notice-success">{message}</p>}
      <button className="button" onClick={toggleRegistration} disabled={!registered && event.attendee_count >= event.capacity}>{registered ? 'Cancel my spot' : event.attendee_count >= event.capacity ? 'All spots filled' : user ? 'Save my spot' : 'Log in to join'}</button>
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

function EditEvent() {
  const { eventId } = useParams(); const navigate = useNavigate()
  const [event, setEvent] = useState(null); const [error, setError] = useState('')
  useEffect(() => { api(`/events/${eventId}`).then(setEvent).catch((err) => setError(err.message)) }, [eventId])
  async function save(values) {
    try { await api(`/events/${eventId}`, { method: 'PUT', body: JSON.stringify(values) }); navigate('/my-events') }
    catch (err) { setError(err.message) }
  }
  return <main className="form-page"><Link to="/my-events" className="back-link">← My events</Link><div className="form-heading"><span className="eyebrow">YOUR EVENT</span><h1>Make a change.</h1><p className="muted">Update the details for your gathering.</p></div>
    {error && <p className="notice notice-error">{error}</p>}{event ? <EventForm onSubmit={save} submitLabel="Save changes" initialValues={event} /> : !error && <p className="muted">Loading event…</p>}
  </main>
}

function MyEvents() {
  const navigate = useNavigate()
  const [data, setData] = useState({ attending: [], organized: [] }); const [error, setError] = useState('')
  async function load() { try { setData(await api('/users/me/events')) } catch (err) { setError(err.message) } }
  useEffect(() => { load() }, [])
  async function deleteEvent(event) {
    if (!window.confirm(`Delete “${event.title}”? This also removes its registrations.`)) return
    try { await api(`/events/${event.id}`, { method: 'DELETE' }); await load() }
    catch (err) { setError(err.message) }
  }
  return <main className="page-content my-events"><span className="eyebrow">YOUR LITTLE BLACK BOOK</span><h1>My events</h1>{error && <p className="notice notice-error">{error}</p>}
    <section><div className="section-heading"><h2>I'm attending</h2></div>{data.attending.length ? <div className="event-grid">{data.attending.map((event) => <EventCard event={event} key={event.id} />)}</div> : <p className="muted">No plans on the books yet. Find something to join.</p>}</section>
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
    <Route path="/events/:eventId/edit" element={user ? <EditEvent /> : <Navigate to="/login" />} />
    <Route path="/create" element={user ? <CreateEvent /> : <Navigate to="/login" />} />
    <Route path="/my-events" element={user ? <MyEvents /> : <Navigate to="/login" />} />
    <Route path="*" element={<main className="page-content"><h1>That page wandered off.</h1><Link to="/">Back home</Link></main>} />
  </Routes><footer>Made for good company. <span>Event Hub · Open-source starter</span></footer></>
}

function dateLabel(value) { return new Date(value).toLocaleDateString(undefined, { day: 'numeric', month: 'long', year: 'numeric' }) }
function timeLabel(value) { return new Date(value).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' }) }
