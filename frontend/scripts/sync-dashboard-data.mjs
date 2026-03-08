import fs from 'node:fs'
import path from 'node:path'

const root = path.resolve(process.cwd(), '..')
const analysisFile = path.join(root, 'data', 'analysis', 'latest_summary.json')
const candidatesDir = path.join(root, 'data', 'candidates')
const outFile = path.join(process.cwd(), 'public', 'data', 'dashboard.json')

function safeReadJson(filePath, fallback) {
  try {
    return JSON.parse(fs.readFileSync(filePath, 'utf-8'))
  } catch {
    return fallback
  }
}

function latestCandidatesFile() {
  if (!fs.existsSync(candidatesDir)) return null
  const files = fs
    .readdirSync(candidatesDir)
    .filter((name) => /^candidates_\d{4}-\d{2}-\d{2}\.json$/.test(name))
    .sort()
  if (!files.length) return null
  return path.join(candidatesDir, files[files.length - 1])
}

function normalizeText(text) {
  return String(text || '')
    .replace(/[0-9]+/g, ' ')
    .replace(/[，。！？、,.!?;:()（）【】\[\]"'“”‘’/\\|]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

function tokenize(title) {
  const cleaned = normalizeText(title)
  if (!cleaned) return []
  return cleaned
    .split(' ')
    .map((s) => s.trim())
    .filter((s) => s && s.length >= 2)
}

function extractFeedTitle(feed) {
  if (!feed || typeof feed !== 'object') return ''
  if (typeof feed.title === 'string' && feed.title.trim()) return feed.title.trim()
  const noteCard = feed.noteCard
  if (noteCard && typeof noteCard === 'object') {
    if (typeof noteCard.displayTitle === 'string' && noteCard.displayTitle.trim()) {
      return noteCard.displayTitle.trim()
    }
    if (typeof noteCard.title === 'string' && noteCard.title.trim()) {
      return noteCard.title.trim()
    }
  }
  return ''
}

const summary = safeReadJson(analysisFile, {
  date: null,
  own_data_status: 'no_summary',
  market_learning: { keyword_count: 0, total_feeds: 0, by_keyword: [] },
})

const latestCandidates = latestCandidatesFile()
const candidates = latestCandidates ? safeReadJson(latestCandidates, []) : []

const marketByKeyword = Array.isArray(summary?.market_learning?.by_keyword)
  ? summary.market_learning.by_keyword
  : []

const keywordFeedback = []
const wordFreq = new Map()

for (const item of marketByKeyword) {
  const keyword = item?.keyword || '未分类'
  const file = item?.file
  const payload = file ? safeReadJson(file, {}) : {}
  const feeds = Array.isArray(payload?.feeds) ? payload.feeds : []
  const titles = []

  for (const feed of feeds) {
    const title = extractFeedTitle(feed)
    if (!title) continue
    titles.push(title)
    for (const tk of tokenize(title)) {
      wordFreq.set(tk, (wordFreq.get(tk) || 0) + 1)
    }
  }

  keywordFeedback.push({
    keyword,
    count: feeds.length,
    topTitles: titles.slice(0, 6),
  })
}

const wordCloud = [...wordFreq.entries()]
  .sort((a, b) => b[1] - a[1])
  .slice(0, 60)
  .map(([text, value]) => ({ text, value }))

const topics = [...new Set([
  ...keywordFeedback.map((x) => x.keyword),
  ...candidates.map((x) => x.topic).filter(Boolean),
])]

const dashboard = {
  generatedAt: new Date().toISOString(),
  summary,
  candidates,
  topics,
  keywordFeedback,
  wordCloud,
}

fs.mkdirSync(path.dirname(outFile), { recursive: true })
fs.writeFileSync(outFile, JSON.stringify(dashboard, null, 2), 'utf-8')
console.log(`[sync] dashboard data written: ${outFile}`)
