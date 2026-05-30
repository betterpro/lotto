import { createWorker } from 'tesseract.js'
import { ticketLayout, isVariableRowLayout } from './lottery.js'

let workerPromise = null

async function getWorker() {
  if (!workerPromise) {
    workerPromise = (async () => {
      const worker = await createWorker('eng')
      await worker.setParameters({
        tessedit_char_whitelist: '0123456789 \n/-.',
      })
      return worker
    })()
  }
  return workerPromise
}

function numbersInRange(text, min, max) {
  const found = []
  for (const m of text.matchAll(/\b0*(\d{1,2})\b/g)) {
    const n = parseInt(m[1], 10)
    if (n >= min && n <= max) found.push(n)
  }
  return found
}

/** @returns {number[][]} */
export function parseOcrText(text, lotteryType) {
  const layout = ticketLayout(lotteryType)
  const lines = text.split(/\n/).map(l => l.trim()).filter(Boolean)

  if (lotteryType === '649' || isVariableRowLayout(layout)) {
    const spec = layout.repeatRow
    const rows = []
    for (const line of lines) {
      const nums = numbersInRange(line, spec.min, spec.max)
      if (nums.length >= spec.count) {
        rows.push(nums.slice(0, spec.count))
      }
    }
    const max = layout.maxRows ?? 10
    return rows.slice(0, max)
  }

  if (lotteryType === 'daily_grand') {
    const mainSpec = layout.rows[0]
    const grandSpec = layout.rows[1]
    let main = []
    let grand = null
    for (const line of lines) {
      const nums = numbersInRange(line, 1, 49)
      if (!main.length && nums.length >= mainSpec.count) {
        main = nums.slice(0, mainSpec.count)
        continue
      }
      const g = numbersInRange(line, grandSpec.min, grandSpec.max)
      if (g.length >= 1) grand = g[0]
    }
    if (main.length === mainSpec.count && grand != null) {
      return [main, [grand]]
    }
    return main.length === mainSpec.count ? [main] : []
  }

  const rows = []
  for (const spec of layout.rows) {
    for (const line of lines) {
      const nums = numbersInRange(line, spec.min, spec.max)
      if (nums.length >= spec.count) {
        rows.push(nums.slice(0, spec.count))
        break
      }
    }
  }
  if (rows.length === layout.rows.length) return rows

  const all = numbersInRange(text, layout.rows[0].min, layout.rows[0].max)
  const count = layout.rows[0].count
  const rebuilt = []
  for (let i = 0; i + count <= all.length && rebuilt.length < layout.rows.length; i += count) {
    rebuilt.push(all.slice(i, i + count))
  }
  return rebuilt.length === layout.rows.length ? rebuilt : rows
}

export async function scanTicketImage(dataUrl, lotteryType, onProgress) {
  const worker = await getWorker()
  const { data: { text } } = await worker.recognize(dataUrl, {
    logger: m => {
      if (m.status === 'recognizing text' && onProgress) {
        onProgress(Math.round((m.progress || 0) * 100))
      }
    },
  })
  return parseOcrText(text, lotteryType)
}
