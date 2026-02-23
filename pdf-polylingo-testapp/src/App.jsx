import { useState } from 'react'
import './App.css'

const LANGUAGES = [
  { code: 'es', name: 'Spanish' },
  { code: 'fr', name: 'French' },
  { code: 'de', name: 'German' },
  { code: 'it', name: 'Italian' },
  { code: 'pt', name: 'Portuguese' },
  { code: 'ja', name: 'Japanese' },
  { code: 'ko', name: 'Korean' },
  { code: 'zh', name: 'Chinese (Simplified)' },
  { code: 'ar', name: 'Arabic' },
  { code: 'hi', name: 'Hindi' },
  { code: 'ru', name: 'Russian' },
  { code: 'nl', name: 'Dutch' },
  { code: 'pl', name: 'Polish' },
  { code: 'tr', name: 'Turkish' },
  { code: 'vi', name: 'Vietnamese' },
]

function App() {
  const [file, setFile] = useState(null)
  const [targetLang, setTargetLang] = useState('es')
  const [status, setStatus] = useState('idle') // idle | uploading | success | error
  const [message, setMessage] = useState('')
  const [requestId, setRequestId] = useState('')

  const apiEndpoint = import.meta.env.VITE_API_ENDPOINT || ''

  const handleFileChange = (e) => {
    const f = e.target.files?.[0]
    setFile(f)
    setStatus('idle')
    setMessage('')
  }

  const handleUpload = async () => {
    if (!file || !apiEndpoint) {
      setStatus('error')
      setMessage(apiEndpoint ? 'Select a file first.' : 'Set VITE_API_ENDPOINT in .env')
      return
    }

    setStatus('uploading')
    setMessage('Requesting presigned URL...')

    try {
      const res = await fetch(`${apiEndpoint.replace(/\/$/, '')}/presigned-url`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          filename: file.name,
          target_language: targetLang,
          source_language: 'auto',
        }),
      })

      if (!res.ok) {
        throw new Error(`API error: ${res.status}`)
      }

      const data = await res.json()
      setRequestId(data.request_id || '')
      setMessage('Uploading file...')

      const contentType = file.name.match(/\.(html?|txt)$/i)
        ? (file.name.endsWith('.html') || file.name.endsWith('.htm') ? 'text/html' : 'text/plain')
        : 'application/octet-stream'

      const putRes = await fetch(data.upload_url, {
        method: 'PUT',
        body: file,
        headers: { 'Content-Type': contentType },
      })

      if (!putRes.ok) {
        throw new Error(`Upload failed: ${putRes.status}`)
      }

      setStatus('success')
      setMessage(`Translation job started! Check your SNS subscription or S3 output bucket in 1–3 minutes.`)
    } catch (err) {
      setStatus('error')
      setMessage(err.message || 'Upload failed.')
    }
  }

  const reset = () => {
    setFile(null)
    setStatus('idle')
    setMessage('')
    setRequestId('')
  }

  return (
    <div className="app">
      <header className="header">
        <h1>PDF Poly Lingo</h1>
        <p className="subtitle">Test translation service</p>
      </header>

      <main className="main">
        <div className="card">
          <div className="field">
            <label htmlFor="file">File (TXT, HTML, or PDF)</label>
            <input
              id="file"
              type="file"
              accept=".txt,.html,.htm,.pdf"
              onChange={handleFileChange}
              disabled={status === 'uploading'}
            />
            {file && <span className="filename">{file.name}</span>}
          </div>

          <div className="field">
            <label htmlFor="lang">Target language</label>
            <select
              id="lang"
              value={targetLang}
              onChange={(e) => setTargetLang(e.target.value)}
              disabled={status === 'uploading'}
            >
              {LANGUAGES.map((l) => (
                <option key={l.code} value={l.code}>{l.name}</option>
              ))}
            </select>
          </div>

          <div className="actions">
            <button
              onClick={handleUpload}
              disabled={!file || status === 'uploading'}
              className="primary"
            >
              {status === 'uploading' ? 'Uploading…' : 'Upload & Translate'}
            </button>
            {(status === 'success' || status === 'error') && (
              <button onClick={reset}>Start over</button>
            )}
          </div>

          {message && (
            <div className={`message ${status}`}>
              {message}
              {requestId && <code>Request ID: {requestId}</code>}
            </div>
          )}
        </div>

        {!apiEndpoint && (
          <div className="env-hint">
            <p>Configure your API endpoint:</p>
            <code>Create .env with: VITE_API_ENDPOINT=https://xxx.execute-api.us-west-2.amazonaws.com/prod/</code>
          </div>
        )}
      </main>
    </div>
  )
}

export default App
