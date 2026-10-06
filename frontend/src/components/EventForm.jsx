import { useState } from 'react'

const blank = { title: '', description: '', location: '', start_time: '', end_time: '', capacity: 30 }

function toLocalDateTime(value) {
  if (!value) return ''
  const date = new Date(value)
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
}

export default function EventForm({ onSubmit, submitLabel, initialValues = blank }) {
  const [values, setValues] = useState({ ...initialValues, start_time: toLocalDateTime(initialValues.start_time), end_time: toLocalDateTime(initialValues.end_time) })
  const update = (event) => setValues({ ...values, [event.target.name]: event.target.value })
  function submit(event) {
    event.preventDefault()
    onSubmit({ ...values, capacity: Number(values.capacity), start_time: new Date(values.start_time).toISOString(), end_time: new Date(values.end_time).toISOString() })
  }
  return <form className="stack-form event-form" onSubmit={submit}>
    <label>Event name<input name="title" required minLength="2" maxLength="160" value={values.title} onChange={update} placeholder="e.g. Sunday morning sketch club" /></label>
    <label>A little about it<textarea name="description" required rows="5" maxLength="10000" value={values.description} onChange={update} placeholder="What should people know?" /></label>
    <label>Where is it happening?<input name="location" required minLength="2" maxLength="200" value={values.location} onChange={update} placeholder="A place, or a neighborhood" /></label>
    <div className="form-row"><label>Starts<input name="start_time" type="datetime-local" required value={values.start_time} onChange={update} /></label><label>Ends<input name="end_time" type="datetime-local" required min={values.start_time} value={values.end_time} onChange={update} /></label></div>
    <label>How many people can come?<input name="capacity" type="number" min="1" max="100000" required value={values.capacity} onChange={update} /></label>
    <button className="button button-wide">{submitLabel}</button>
  </form>
}
