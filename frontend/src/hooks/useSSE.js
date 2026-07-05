import { useState, useCallback, useRef } from 'react'

export default function useSSE() {
  const [streaming, setStreaming] = useState(false)
  const abortRef = useRef(null)

  const send = useCallback(async (url, body, handlers) => {
    const token = localStorage.getItem('token')
    setStreaming(true)

    const controller = new AbortController()
    abortRef.current = controller

    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(body),
        signal: controller.signal,
      })

      if (res.status === 401) {
        localStorage.removeItem('token')
        window.location.href = '/login'
        return
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const payload = line.slice(6)
          if (payload === '[DONE]') {
            handlers.onDone?.()
            return
          }
          try {
            const data = JSON.parse(payload)
            handlers.onEvent?.(data)
          } catch {
            // 忽略无法解析的行
          }
        }
      }

      handlers.onDone?.()
    } catch (err) {
      if (err.name !== 'AbortError') {
        handlers.onError?.(err)
      }
    } finally {
      setStreaming(false)
      abortRef.current = null
    }
  }, [])

  const abort = useCallback(() => {
    abortRef.current?.abort()
    setStreaming(false)
  }, [])

  return { send, abort, streaming }
}
