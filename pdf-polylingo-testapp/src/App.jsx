import { useState, useEffect, useRef } from 'react'
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
  const [filePreviewUrl, setFilePreviewUrl] = useState(null)
  const [targetLang, setTargetLang] = useState('es')
  const [status, setStatus] = useState('idle') // idle | uploading | translating | complete | error
  const [requestId, setRequestId] = useState('')
  const [progress, setProgress] = useState(0)
  const [translatedUrl, setTranslatedUrl] = useState(null)
  const [error, setError] = useState('')
  const pollRef = useRef(null)

  const apiEndpoint = (import.meta.env.VITE_API_ENDPOINT || '').replace(/\/$/, '')
  const maxFileSize = 5 * 1024 * 1024

  const handleFileChange = (e) => {
    const f = e.target.files?.[0]
    if (filePreviewUrl) URL.revokeObjectURL(filePreviewUrl)
    setFile(f)
    setFilePreviewUrl(f ? URL.createObjectURL(f) : null)
    setStatus('idle')
    setError('')
    setTranslatedUrl(null)
    setProgress(0)
  }

  const fileToBase64 = (f) =>
    new Promise((resolve, reject) => {
      const r = new FileReader()
      r.onload = () => resolve(r.result.split(',')[1])
      r.onerror = reject
      r.readAsDataURL(f)
    })

  const handleTranslate = async () => {
    if (!file || !apiEndpoint) {
      setError(apiEndpoint ? 'Select a file first.' : 'Set VITE_API_ENDPOINT in .env')
      setStatus('error')
      return
    }
    if (file.size > maxFileSize) {
      setError('File too large (max 5MB). Use a smaller file.')
      setStatus('error')
      return
    }

    setStatus('uploading')
    setProgress(10)
    setError('')

    try {
      const base64 = await fileToBase64(file)
      setProgress(30)
      const res = await fetch(`${apiEndpoint}/upload`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          file: base64,
          filename: file.name,
          target_language: targetLang,
          source_language: 'auto',
        }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.error || `Upload failed: ${res.status}`)
      }
      const data = await res.json()
      setRequestId(data.request_id || '')
      setProgress(50)
      setStatus('translating')
      startPolling(data.request_id)
    } catch (err) {
      setError(err.message || 'Upload failed.')
      setStatus('error')
    }
  }

  const checkStatus = async (rid) => {
    try {
      const res = await fetch(`${apiEndpoint}/status?request_id=${rid}`)
      const data = await res.json()
      if (data.status === 'complete' && data.download_url) {
        setTranslatedUrl(data.download_url)
        setProgress(100)
        setStatus('complete')
        stopPolling()
      } else if (data.status === 'in_progress') {
        setProgress((p) => Math.min(p + 5, 95))
      }
    } catch {
      // Ignore poll errors
    }
  }

  const startPolling = (rid) => {
    pollRef.current = setInterval(() => checkStatus(rid), 3000)
    checkStatus(rid)
  }
  const stopPolling = () => {
    if (pollRef.current) clearInterval(pollRef.current)
    pollRef.current = null
  }

  useEffect(() => {
    return () => {
      stopPolling()
      if (filePreviewUrl) URL.revokeObjectURL(filePreviewUrl)
    }
  }, [filePreviewUrl])

  const reset = () => {
    stopPolling()
    if (filePreviewUrl) URL.revokeObjectURL(filePreviewUrl)
    setFile(null)
    setFilePreviewUrl(null)
    setStatus('idle')
    setRequestId('')
    setProgress(0)
    setTranslatedUrl(null)
    setError('')
  }

  const isPdf = file?.name?.toLowerCase().endsWith('.pdf')
  const isHtml = file?.name?.toLowerCase().match(/\.(html?|htm)$/)

  return (
    <div className="app">
      <header className="header">
        <h1>PDF Poly Lingo</h1>
        <p className="subtitle">Translate documents</p>
      </header>

      <main className="main">
        <div className="card">
          <div className="field">
            <label htmlFor="file">Select file (TXT, HTML, or PDF — max 5MB)</label>
            <input
              id="file"
              type="file"
              accept=".txt,.html,.htm,.pdf"
              onChange={handleFileChange}
              disabled={status === 'uploading' || status === 'translating'}
            />
          </div>

          {file && (
            <div className="preview-section">
              <label>Preview</label>
              <div className="preview-frame">
                {isPdf && filePreviewUrl && (
                  <iframe src={filePreviewUrl} title="Original" />
                )}
                {isHtml && filePreviewUrl && (
                  <iframe src={filePreviewUrl} title="Original" />
                )}
                {file && !isPdf && !isHtml && (
                  <p className="preview-placeholder">Preview not available for .txt</p>
                )}
              </div>
            </div>
          )}

          <div className="field">
            <label htmlFor="lang">Target language</label>
            <select
              id="lang"
              value={targetLang}
              onChange={(e) => setTargetLang(e.target.value)}
              disabled={status === 'uploading' || status === 'translating'}
            >
              {LANGUAGES.map((l) => (
                <option key={l.code} value={l.code}>{l.name}</option>
              ))}
            </select>
          </div>

          {(status === 'uploading' || status === 'translating') && (
            <div className="progress-section">
              <div className="progress-bar">
                <div className="progress-fill" style={{ width: `${progress}%` }} />
              </div>
              <span>
                {status === 'uploading' ? 'Uploading…' : 'Translating…'}
              </span>
            </div>
          )}

          <div className="actions">
            {status === 'idle' || status === 'error' ? (
              <button
                onClick={handleTranslate}
                disabled={!file}
                className="primary"
              >
                Translate
              </button>
            ) : null}
            {(status === 'complete' || status === 'error') && (
              <button onClick={reset}>New document</button>
            )}
          </div>

          {error && <div className="message error">{error}</div>}

          {status === 'complete' && translatedUrl && (
            <div className="translated-section">
              <label>Translated document</label>
              <div className="preview-frame">
                <iframe src={translatedUrl} title="Translated" />
              </div>
              <a href={translatedUrl} download target="_blank" rel="noreferrer" className="download-btn">
                Download translated file
              </a>
            </div>
          )}
        </div>

        {!apiEndpoint && (
          <div className="env-hint">
            <p>Configure your API endpoint:</p>
            <code>VITE_API_ENDPOINT=https://xxx.execute-api.us-west-2.amazonaws.com/prod/</code>
          </div>
        )}
      </main>
    </div>
  )
}

export default App
