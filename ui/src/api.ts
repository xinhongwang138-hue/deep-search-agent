// 后端接口封装：开发期由 vite proxy 转发到 127.0.0.1:8000
const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? ''

export interface FileItem {
  name: string
  path: string
  size: number
  mtime: number
}

export interface TaskStart {
  status: string
  thread_id: string
  message?: string
}

async function asJson<T>(resp: Response): Promise<T> {
  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`
    try {
      const body = await resp.json()
      detail = body.message || body.detail || detail
    } catch {
      /* 响应体非 JSON 时保留状态码 */
    }
    throw new Error(detail)
  }
  return (await resp.json()) as T
}

export async function startTask(query: string, threadId: string): Promise<TaskStart> {
  const url = `${BASE}/api/task?query=${encodeURIComponent(query)}&thread_id=${encodeURIComponent(threadId)}`
  return asJson<TaskStart>(await fetch(url, { method: 'POST' }))
}

export async function fetchFiles(threadId: string, path = 'output'): Promise<{ files: FileItem[] }> {
  const url = `${BASE}/api/files?thread_id=${encodeURIComponent(threadId)}&path=${encodeURIComponent(path)}`
  return asJson<{ files: FileItem[] }>(await fetch(url))
}

export async function uploadFiles(threadId: string, files: File[]): Promise<{ files: string[] }> {
  const form = new FormData()
  files.forEach((file) => form.append('files', file))
  const url = `${BASE}/api/upload?thread_id=${encodeURIComponent(threadId)}`
  return asJson<{ files: string[] }>(await fetch(url, { method: 'POST', body: form }))
}

export function downloadUrl(threadId: string, path: string): string {
  return `${BASE}/api/download?thread_id=${encodeURIComponent(threadId)}&path=${encodeURIComponent(path)}`
}

export function wsUrl(threadId: string): string {
  if (BASE) {
    return `${BASE.replace(/^http/, 'ws')}/ws/${threadId}`
  }
  const scheme = location.protocol === 'https:' ? 'wss' : 'ws'
  return `${scheme}://${location.host}/ws/${threadId}`
}
