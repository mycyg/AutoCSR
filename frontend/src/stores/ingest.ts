import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  ingestStatus, listFiles, triggerIngest, uploadFiles,
  type FileEntryDTO,
} from '@/api/rest'

export const useIngestStore = defineStore('ingest', () => {
  const files = ref<FileEntryDTO[]>([])
  const polling = ref(false)
  const all_done = ref(false)
  let pollTimer: number | null = null

  async function refresh(pid: string): Promise<void> {
    files.value = await listFiles(pid)
    all_done.value = files.value.every((f) => f.status === 'done' || f.status === 'error')
  }

  async function upload(pid: string, fileList: File[]): Promise<void> {
    await uploadFiles(pid, fileList)
    await refresh(pid)
  }

  async function start(pid: string): Promise<void> {
    await triggerIngest(pid)
    startPoll(pid)
  }

  function startPoll(pid: string): void {
    if (polling.value) return
    polling.value = true
    const tick = async (): Promise<void> => {
      try {
        const s = await ingestStatus(pid)
        files.value = s.entries
        all_done.value = s.all_done
        if (s.all_done) {
          stopPoll()
        }
      } catch {
        // swallow & keep polling
      }
    }
    void tick()
    pollTimer = window.setInterval(tick, 1500)
  }

  function stopPoll(): void {
    polling.value = false
    if (pollTimer !== null) {
      window.clearInterval(pollTimer)
      pollTimer = null
    }
  }

  function reset(): void {
    files.value = []
    all_done.value = false
    stopPoll()
  }

  return { files, polling, all_done, refresh, upload, start, startPoll, stopPoll, reset }
})
