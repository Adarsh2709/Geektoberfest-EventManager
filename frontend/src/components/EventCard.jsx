import { Link } from 'react-router-dom'
import { dateLabel, timeLabel } from '../api'
import './EventCard.css'

export default function EventCard({ event, actions }) {
  return <article className="event-card"><div className="event-card-top"><span className="event-day">{new Date(event.start_time).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }).toUpperCase()}</span><span className="event-location">{event.location}</span></div>
    <h3>{event.title}</h3><p className="event-date">{dateLabel(event.start_time)} · {timeLabel(event.start_time)}</p><p className="event-description">{event.description}</p>
    <div className="event-card-bottom"><span className="host-avatar">{event.organizer.username.slice(0, 1).toUpperCase()}</span><span className="host-name">Hosted by {event.organizer.username}</span><Link className="text-link" to={`/events/${event.id}`}>Come see →</Link></div>
    {actions && <div className="event-actions">{actions}</div>}
  </article>
}
