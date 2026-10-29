<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { downloadUrl, fetchFiles, startTask, uploadFiles, wsUrl, type FileItem } from './api'

interface MonitorEvent {
  id: number
  event: string
  message: string
  data: Record<string, unknown>
  timestamp?: string
}

const threadId = ref(loadThreadId())
const query = ref('')
const running = ref(false)
const connected = ref(false)
const uploading = ref(false)
const events = ref<MonitorEvent[]>([])
const files = ref<FileItem[]>([])
const answer = ref('')

let socket: WebSocket | null = null
let reconnectTimer: number | undefined
let seq = 0
let disposed = false

function newThreadId(): string {
  const raw =
    typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID()
      : String(Date.now()) + Math.random().toString(16).slice(2)
  return raw.replace(/-/g, '').slice(0, 12)
}

function loadThreadId(): string {
  const saved = localStorage.getItem('ds_thread_id')
  if (saved) return saved
  const created = newThreadId()
  localStorage.setItem('ds_thread_id', created)
  return created
}

function push(item: Omit<MonitorEvent, 'id'>) {
  events.value.push({ ...item, id: ++seq })
  void scrollDown()
}

async function scrollDown() {
  await nextTick()
  const el = document.querySelector('.timeline')
  if (el) el.scrollTop = el.scrollHeight
}

function connect() {
  socket = new WebSocket(wsUrl(threadId.value))
  socket.onopen = () => {
    connected.value = true
  }
  socket.onclose = () => {
    connected.value = false
    if (disposed) return
    reconnectTimer = window.setTimeout(connect, 3000)
  }
  socket.onerror = () => socket?.close()
  socket.onmessage = (msg: MessageEvent<string>) => {
    let payload: any
    try {
      payload = JSON.parse(msg.data)
    } catch {
      return
    }
    if (payload.type === 'pong') return

    if (payload.event === 'task_result') {
      answer.value = String(payload.data?.result ?? '')
      running.value = false
      void refreshFiles()
    }
    if (payload.event === 'error') running.value = false

    push({
      event: String(payload.event ?? 'message'),
      message: String(payload.message ?? ''),
      data: (payload.data ?? {}) as Record<string, unknown>,
      timestamp: payload.timestamp
    })
  }
}

async function refreshFiles() {
  try {
    const result = await fetchFiles(threadId.value)
    files.value = result.files ?? []
  } catch {
    files.value = []
  }
}

async function submit() {
  const text = query.value.trim()
  if (!text || running.value) return
  events.value = []
  answer.value = ''
  running.value = true
  push({ event: 'user', message: text, data: {} })
  try {
    const result = await startTask(text, threadId.value)
    if (result.status !== 'started') {
      running.value = false
      push({ event: 'error', message: `任务未启动：${result.status}`, data: {} })
      return
    }
    query.value = ''
  } catch (err) {
    running.value = false
    push({ event: 'error', message: `请求失败：${(err as Error).message}`, data: {} })
  }
}

async function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  const picked = input.files ? Array.from(input.files) : []
  if (picked.length === 0) return
  uploading.value = true
  try {
    const result = await uploadFiles(threadId.value, picked)
    push({
      event: 'upload',
      message: `已上传 ${result.files?.length ?? 0} 个文件`,
      data: { files: result.files }
    })
  } catch (err) {
    push({ event: 'error', message: `上传失败：${(err as Error).message}`, data: {} })
  } finally {
    uploading.value = false
    input.value = ''
  }
}

function switchSession() {
  const next = newThreadId()
  threadId.value = next
  localStorage.setItem('ds_thread_id', next)
  events.value = []
  files.value = []
  answer.value = ''
  running.value = false
  socket?.close()
  connect()
}

function formatSize(size: number): string {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

function eventLabel(event: string): string {
  const table: Record<string, string> = {
    user: '提问',
    session_created: '会话',
    assistant_call: '子智能体',
    tool_start: '工具',
    tool_end: '工具',
    token: '生成',
    task_result: '完成',
    error: '异常',
    upload: '上传'
  }
  return table[event] ?? event
}

onMounted(() => {
  connect()
  void refreshFiles()
})

onBeforeUnmount(() => {
  disposed = true
  if (reconnectTimer) window.clearTimeout(reconnectTimer)
  socket?.close()
})
</script>

<template>
  <div class="shell">
    <header class="topbar">
      <div>
        <h1>Deep Search Agent</h1>
        <p class="sub">会话 <code>{{ threadId }}</code></p>
      </div>
      <div class="status">
        <span :class="['dot', connected ? 'on' : 'off']"></span>
        <span>{{ connected ? '已连接' : '连接中断' }}</span>
        <button class="ghost" @click="switchSession">新会话</button>
      </div>
    </header>

    <main class="grid">
      <section class="panel">
        <div class="panel-head">
          <h2>执行过程</h2>
          <label class="upload" :class="{ disabled: uploading }">
            {{ uploading ? '上传中...' : '上传文件' }}
            <input type="file" multiple :disabled="uploading" @change="onFileChange" />
          </label>
        </div>

        <div class="timeline">
          <div v-if="events.length === 0" class="empty">提交问题后，这里会显示检索与工具调用轨迹</div>
          <div v-for="item in events" :key="item.id" :class="['event', item.event]">
            <span class="tag">{{ eventLabel(item.event) }}</span>
            <div class="body">
              <p class="msg">{{ item.message }}</p>
              <p v-if="item.event === 'tool_end' && item.data.output" class="detail">
                {{ item.data.output }}
              </p>
              <p v-if="item.event === 'assistant_call' && item.data.task" class="detail">
                {{ item.data.task }}
              </p>
            </div>
            <span class="ts">{{ item.timestamp?.slice(11, 19) }}</span>
          </div>
        </div>

        <form class="composer" @submit.prevent="submit">
          <textarea
            v-model="query"
            rows="2"
            placeholder="例如：整理 2024 年华东区药品销售额 Top10 并生成报告"
            :disabled="running"
            @keydown.enter.exact.prevent="submit"
          />
          <button type="submit" :disabled="running || !query.trim()">
            {{ running ? '执行中' : '开始检索' }}
          </button>
        </form>
      </section>

      <section class="panel">
        <div class="panel-head">
          <h2>交付物</h2>
          <button class="ghost" @click="refreshFiles">刷新</button>
        </div>

        <div v-if="files.length === 0" class="empty">本次会话暂无产出文件</div>
        <ul v-else class="files">
          <li v-for="file in files" :key="file.path">
            <div>
              <p class="name">{{ file.name }}</p>
              <p class="meta">{{ formatSize(file.size) }}</p>
            </div>
            <a :href="downloadUrl(threadId, file.path)" :download="file.name">下载</a>
          </li>
        </ul>

        <div class="answer">
          <h3>最终回答</h3>
          <pre v-if="answer">{{ answer }}</pre>
          <p v-else class="empty">尚无结果</p>
        </div>
      </section>
    </main>
  </div>
</template>
