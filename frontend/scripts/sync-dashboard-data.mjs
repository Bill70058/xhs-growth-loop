import fs from 'node:fs'
import path from 'node:path'

const root = path.resolve(process.cwd(), '..')
const analysisFile = path.join(root, 'data', 'analysis', 'latest_summary.json')
const candidatesDir = path.join(root, 'data', 'candidates')
const runtimeDir = path.join(root, 'data', 'runtime')
const logsDir = path.join(root, 'logs')
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

function loadRuntimeBridge() {
  if (!fs.existsSync(runtimeDir)) {
    return { has_data: false, steps: [], latest: null, retry_count: 0, failed_steps: 0 }
  }
  const files = fs
    .readdirSync(runtimeDir)
    .filter((name) => /^bridge_.+\.jsonl$/.test(name) && name !== 'bridge_latest.jsonl')
    .sort()

  const steps = []
  let retryCount = 0
  let failedSteps = 0
  for (const name of files) {
    const p = path.join(runtimeDir, name)
    const lines = fs.readFileSync(p, 'utf-8').split('\n').map((x) => x.trim()).filter(Boolean)
    if (!lines.length) continue
    const events = lines.map((line) => {
      try {
        return JSON.parse(line)
      } catch {
        return null
      }
    }).filter(Boolean)
    if (!events.length) continue
    const last = events[events.length - 1]
    retryCount += Math.max(events.length - 1, 0)
    if (!last.ok) failedSteps += 1
    steps.push({
      step_id: last.step_id || name.replace(/^bridge_/, '').replace(/\.jsonl$/, ''),
      attempts: events.length,
      ok: !!last.ok,
      returncode: Number(last.returncode || 0),
      action: last?.decision?.action || null,
      reason: last?.decision?.reason || null,
      time: last.time || null,
    })
  }

  const latest = safeReadJson(path.join(runtimeDir, 'bridge_latest.json'), null)
  return {
    has_data: steps.length > 0 || !!latest,
    retry_count: retryCount,
    failed_steps: failedSteps,
    latest,
    steps,
  }
}

function loadAutopilotHeartbeat() {
  const hb = safeReadJson(path.join(runtimeDir, 'autopilot_heartbeat.json'), null)
  if (!hb || typeof hb !== 'object') {
    return { exists: false, alive: false }
  }
  const ts = Date.parse(hb.time || '')
  const ageSec = Number.isFinite(ts) ? Math.max(0, Math.round((Date.now() - ts) / 1000)) : null
  const alive = ageSec != null ? ageSec <= 90 : false
  return {
    exists: true,
    alive,
    age_seconds: ageSec,
    cycle: Number(hb.cycle || 0),
    state: hb.state || null,
    reason: hb.reason || hb.decision_reason || null,
  }
}

function loadAutopilotTrace() {
  const file = path.join(logsDir, 'autopilot.log')
  if (!fs.existsSync(file)) return []
  const lines = fs.readFileSync(file, 'utf-8').split('\n').map((x) => x.trim()).filter(Boolean).slice(-160)
  const rows = []
  for (const line of lines) {
    let obj = null
    try {
      obj = JSON.parse(line)
    } catch {
      continue
    }
    if (!obj || typeof obj !== 'object') continue
    if (obj.decision && typeof obj.decision === 'object') {
      rows.push({
        kind: 'decision',
        cycle: Number(obj.cycle || 0),
        reason: obj.decision.reason || null,
        sleep_seconds: Number(obj.decision.sleep_seconds || 0),
        plan_len: Array.isArray(obj.decision.plan) ? obj.decision.plan.length : 0,
        continue_flag: !!obj.decision.continue,
      })
      continue
    }
    rows.push({
      kind: 'step',
      cycle: Number(obj.cycle || 0),
      step_id: obj.step_id || null,
      cmd: obj.cmd || null,
      rc: Number(obj.rc || 0),
    })
  }
  return rows.slice(-60)
}

function loadAutopilotMilestones() {
  const file = path.join(runtimeDir, 'autopilot_milestones.jsonl')
  if (!fs.existsSync(file)) return []
  const lines = fs.readFileSync(file, 'utf-8').split('\n').map((x) => x.trim()).filter(Boolean).slice(-80)
  const rows = []
  for (const line of lines) {
    try {
      const obj = JSON.parse(line)
      if (obj && typeof obj === 'object') rows.push(obj)
    } catch {
      // ignore broken line
    }
  }
  return rows.slice(-40)
}

const summary = safeReadJson(analysisFile, {
  date: null,
  own_data_status: 'no_summary',
  market_learning: { keyword_count: 0, total_feeds: 0, by_keyword: [] },
  strategy_learning: { has_run: false, arms: [], status_breakdown: {} },
  experiment_sync: { linked_publish_records: 0 },
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

const strategyLearning = {
  has_run: !!summary?.strategy_learning?.has_run,
  run_id: summary?.strategy_learning?.run_id || null,
  selection_policy: summary?.strategy_learning?.selection_policy || null,
  run_status: summary?.strategy_learning?.run_status || null,
  selected_candidate_no: summary?.strategy_learning?.selected_candidate_no || null,
  status_breakdown: summary?.strategy_learning?.status_breakdown || {},
  arms: Array.isArray(summary?.strategy_learning?.arms) ? summary.strategy_learning.arms : [],
}

const experimentSync = {
  linked_publish_records: Number(summary?.experiment_sync?.linked_publish_records || 0),
  legacy_pending_publish_records: Number(summary?.experiment_sync?.legacy_pending_publish_records || 0),
  reward_update: summary?.experiment_sync?.reward_update || { applied: 0, pending: 0 },
  reward_sources: summary?.experiment_sync?.reward_sources || {},
}
const runtimeBridge = loadRuntimeBridge()
const autopilot = loadAutopilotHeartbeat()
const autopilotTrace = loadAutopilotTrace()
const autopilotMilestones = loadAutopilotMilestones()

const dashboard = {
  generatedAt: new Date().toISOString(),
  summary,
  strategyLearning,
  experimentSync,
  runtimeBridge,
  autopilot,
  autopilotTrace,
  autopilotMilestones,
  candidates,
  topics,
  keywordFeedback,
  wordCloud,
}

fs.mkdirSync(path.dirname(outFile), { recursive: true })
fs.writeFileSync(outFile, JSON.stringify(dashboard, null, 2), 'utf-8')
console.log(`[sync] dashboard data written: ${outFile}`)
