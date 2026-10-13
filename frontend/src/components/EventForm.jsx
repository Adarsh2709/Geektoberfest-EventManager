import { useState } from 'react'

const blank = { title: '', description: '', location: '', start_time: '', end_time: '', capacity: 30 }

function toLocalDateTime(value) {
  if (!value) return ''
  const date = new Date(value)
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
}

export default function EventForm({ onSubmit, submitLabel, initialValues = blank }) {
  const [values, setValues] = useState({ ...initialValues, start_time: toLocalDateTime(initialValues.start_time), end_time: toLocalDateTime(initialValues.end_time) })
  const [errors, setErrors] = useState({})

  const update = (event) => {
    const { name, value } = event.target
    setValues((prev) => ({ ...prev, [name]: value }))
    if (errors[name]) {
      setErrors((prev) => ({ ...prev, [name]: undefined }))
    }
  }

  function submit(event) {
    event.preventDefault()
    const newErrors = {}

    const trimmedTitle = (values.title || '').trim()
    if (!trimmedTitle) {
      newErrors.title = 'Event name is required.'
    } else if (trimmedTitle.length < 2) {
      newErrors.title = 'Event name must be at least 2 characters.'
    }

    const trimmedLoc = (values.location || '').trim()
    if (!trimmedLoc) {
      newErrors.location = 'Location is required.'
    } else if (trimmedLoc.length < 2) {
      newErrors.location = 'Location must be at least 2 characters.'
    }

    if (!values.start_time) {
      newErrors.start_time = 'Start date and time is required.'
    }
    if (!values.end_time) {
      newErrors.end_time = 'End date and time is required.'
    }

    if (values.start_time && values.end_time) {
      const start = new Date(values.start_time)
      const end = new Date(values.end_time)
      if (isNaN(start.getTime())) {
        newErrors.start_time = 'Invalid start date and time.'
      }
      if (isNaN(end.getTime())) {
        newErrors.end_time = 'Invalid end date and time.'
      }
      if (!isNaN(start.getTime()) && !isNaN(end.getTime()) && end <= start) {
        newErrors.end_time = 'End time must be after start time.'
      }
    }

    if (Object.keys(newErrors).length > 0) {
      setErrors(newErrors)
      return
    }

    setErrors({})
    onSubmit({
      ...values,
      title: trimmedTitle,
      location: trimmedLoc,
      capacity: Number(values.capacity),
      start_time: new Date(values.start_time).toISOString(),
      end_time: new Date(values.end_time).toISOString(),
    })
  }

  return (
    <form className="stack-form event-form" onSubmit={submit} noValidate>
      <label>
        Event name
        <input
          name="title"
          required
          minLength="2"
          maxLength="160"
          value={values.title}
          onChange={update}
          className={errors.title ? 'input-error' : ''}
          placeholder="e.g. Sunday morning sketch club"
        />
        {errors.title && <span className="field-error">{errors.title}</span>}
      </label>

      <label>
        A little about it
        <textarea
          name="description"
          required
          rows="5"
          maxLength="10000"
          value={values.description}
          onChange={update}
          placeholder="What should people know?"
        />
      </label>

      <label>
        Where is it happening?
        <input
          name="location"
          required
          minLength="2"
          maxLength="200"
          value={values.location}
          onChange={update}
          className={errors.location ? 'input-error' : ''}
          placeholder="A place, or a neighborhood"
        />
        {errors.location && <span className="field-error">{errors.location}</span>}
      </label>

      <div className="form-row">
        <label>
          Starts
          <input
            name="start_time"
            type="datetime-local"
            required
            value={values.start_time}
            onChange={update}
            className={errors.start_time ? 'input-error' : ''}
          />
          {errors.start_time && <span className="field-error">{errors.start_time}</span>}
        </label>
        <label>
          Ends
          <input
            name="end_time"
            type="datetime-local"
            required
            min={values.start_time}
            value={values.end_time}
            onChange={update}
            className={errors.end_time ? 'input-error' : ''}
          />
          {errors.end_time && <span className="field-error">{errors.end_time}</span>}
        </label>
      </div>

      <label>
        How many people can come?
        <input
          name="capacity"
          type="number"
          min="1"
          max="100000"
          required
          value={values.capacity}
          onChange={update}
        />
      </label>

      <button className="button button-wide">{submitLabel}</button>
    </form>
  )
}
