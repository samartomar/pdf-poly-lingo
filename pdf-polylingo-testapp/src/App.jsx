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
  const [viewMode, setViewMode] = useState('side') // 'inline' | 'side'
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
      setError('File too large (max 5MB).')
      setStatus('error')
      return
    }

    setStatus('uploading')
    setProgress(5)
    setError('')

    try {
      setProgress(15)
      const base64 = await fileToBase64(file)
      setProgress(25)
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
      setProgress(50)
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.error || `Upload failed: ${res.status}`)
      }
      const data = await res.json()

      if (data.sync && data.translated_base64) {
        const bytes = Uint8Array.from(atob(data.translated_base64), (c) => c.charCodeAt(0))
        const blob = new Blob([bytes], { type: data.filename?.endsWith('.html') ? 'text/html' : 'text/plain' })
        setTranslatedUrl(URL.createObjectURL(blob))
        setProgress(100)
        setStatus('complete')
      } else {
        setRequestId(data.request_id || '')
        setProgress(55)
        setStatus('translating')
        startPolling(data.request_id)
      }
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
      } else if (data.status === 'failed' && data.error) {
        setError(data.error)
        setStatus('error')
        stopPolling()
      } else if (data.status === 'in_progress' || data.status === 'processing') {
        setProgress((p) => Math.min(p + 4, 95))
      }
    } catch {
      // Ignore poll errors
    }
  }

  const startPolling = (rid) => {
    pollRef.current = setInterval(() => checkStatus(rid), 2500)
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
  useEffect(() => {
    return () => {
      if (translatedUrl?.startsWith?.('blob:')) URL.revokeObjectURL(translatedUrl)
    }
  }, [translatedUrl])

  const reset = () => {
    stopPolling()
    if (filePreviewUrl) URL.revokeObjectURL(filePreviewUrl)
    if (translatedUrl && translatedUrl.startsWith('blob:')) URL.revokeObjectURL(translatedUrl)
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
  const showProgress = status === 'uploading' || status === 'translating'

  return (
    <div className="app">
      <header className="header">
        <h1>PDF Poly Lingo</h1>
        <p className="subtitle">HTML & TXT under 100 KB translate in seconds</p>
      </header>

      <div className="toolbar">
        <div className="file-picker">
          <input
            id="file"
            type="file"
            accept=".txt,.html,.htm,.pdf"
            onChange={handleFileChange}
            disabled={status === 'uploading' || status === 'translating'}
          />
          <label htmlFor="file" className="file-label">
            {file ? `${file.name} (${(file.size / 1024).toFixed(1)} KB)` : 'Choose file'}
          </label>
        </div>
        <select
          value={targetLang}
          onChange={(e) => setTargetLang(e.target.value)}
          disabled={status === 'uploading' || status === 'translating'}
          className="lang-select"
        >
          {LANGUAGES.map((l) => (
            <option key={l.code} value={l.code}>{l.name}</option>
          ))}
        </select>
        <div className="view-toggle">
          <label className={viewMode === 'inline' ? 'active' : ''}>
            <input
              type="radio"
              name="viewMode"
              checked={viewMode === 'inline'}
              onChange={() => setViewMode('inline')}
              disabled={status === 'uploading' || status === 'translating'}
            />
            Inline
          </label>
          <label className={viewMode === 'side' ? 'active' : ''}>
            <input
              type="radio"
              name="viewMode"
              checked={viewMode === 'side'}
              onChange={() => setViewMode('side')}
              disabled={status === 'uploading' || status === 'translating'}
            />
            Side by side
          </label>
        </div>
        {status === 'idle' || status === 'error' ? (
          <button
            onClick={handleTranslate}
            disabled={!file}
            className="btn-translate"
          >
            Translate
          </button>
        ) : (
          <button onClick={reset} className="btn-reset">
            Cancel
          </button>
        )}
      </div>

      {showProgress && (
        <div className="progress-futuristic">
          <div className="progress-track">
            <div className="progress-glow" style={{ width: `${progress}%` }} />
            <div className="progress-shine" style={{ width: `${progress}%` }} />
          </div>
          <div className="progress-meta">
            <span className="progress-label">
              {status === 'uploading' ? 'Uploading' : 'Translating'}
            </span>
            <span className="progress-pct">{progress}%</span>
          </div>
        </div>
      )}

      {error && <div className="toast error">{error}</div>}

      <div className={`panels ${viewMode === 'inline' ? 'panels-inline' : ''}`}>
        {viewMode === 'inline' ? (
          <div className="panel panel-single">
            <div className="panel-header">
              {status === 'complete' && translatedUrl ? 'Translated' : 'Document'}
            </div>
            <div className="panel-body">
              {status === 'complete' && translatedUrl ? (
                <>
                  <iframe src={translatedUrl} title="Translated" />
                  <a href={translatedUrl} download target="_blank" rel="noreferrer" className="btn-download">
                    Download
                  </a>
                </>
              ) : filePreviewUrl ? (
                (isPdf || isHtml) ? (
                  <iframe src={filePreviewUrl} title="Original" />
                ) : (
                  <p className="no-preview">Preview for .txt not available</p>
                )
              ) : (
                <p className="empty">
                  {showProgress ? 'Translation in progress…' : 'Select a PDF or HTML file to preview'}
                </p>
              )}
            </div>
          </div>
        ) : (
          <>
            <div className="panel">
              <div className="panel-header">Original</div>
              <div className="panel-body">
                {filePreviewUrl ? (
                  (isPdf || isHtml) ? (
                    <iframe src={filePreviewUrl} title="Original" />
                  ) : (
                    <p className="no-preview">Preview for .txt not available</p>
                  )
                ) : (
                  <p className="empty">Select a PDF or HTML file to preview</p>
                )}
              </div>
            </div>
            <div className="panel">
              <div className="panel-header">Translated</div>
              <div className="panel-body">
                {status === 'complete' && translatedUrl ? (
                  <>
                    <iframe src={translatedUrl} title="Translated" />
                    <a href={translatedUrl} download target="_blank" rel="noreferrer" className="btn-download">
                      Download
                    </a>
                  </>
                ) : (
                  <p className="empty">
                    {showProgress ? 'Translation in progress…' : 'Translated document will appear here'}
                  </p>
                )}
              </div>
            </div>
          </>
        )}
      </div>

      {!apiEndpoint && (
        <div className="env-hint">
          Set <code>VITE_API_ENDPOINT</code> in .env
        </div>
      )}
    </div>
  )
}

export default App
