import { getDocument, GlobalWorkerOptions } from 'pdfjs-dist'
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'

GlobalWorkerOptions.workerSrc = workerUrl

// Render one page at a time and await scanning to bound memory and API usage.
export async function scanPdfPages(file, onPage, onProgress) {
  if (file.size > 25 * 1024 * 1024) throw new Error('PDF must be 25 MB or smaller.')
  const task = getDocument({ data: new Uint8Array(await file.arrayBuffer()), isEvalSupported: false })
  try {
    const pdf = await task.promise
    if (pdf.numPages > 50) throw new Error('PDF must contain 50 pages or fewer. Split it into smaller files.')
    for (let number = 1; number <= pdf.numPages; number++) {
      onProgress?.(number, pdf.numPages)
      const page = await pdf.getPage(number)
      const original = page.getViewport({ scale: 1 })
      const viewport = page.getViewport({ scale: Math.min(3, 2400 / Math.max(original.width, original.height)) })
      const canvas = document.createElement('canvas')
      try {
        canvas.width = Math.ceil(viewport.width)
        canvas.height = Math.ceil(viewport.height)
        await page.render({ canvasContext: canvas.getContext('2d'), viewport, background: '#ffffff' }).promise
        await onPage(canvas.toDataURL('image/jpeg', 0.95), `${file.name} · Page ${number} of ${pdf.numPages}`)
      } finally {
        canvas.width = canvas.height = 0
        page.cleanup()
      }
    }
  } catch (error) {
    if (error.name === 'PasswordException') throw new Error('This PDF is password protected. Upload an unlocked copy.')
    throw error
  } finally {
    await task.destroy()
  }
}
