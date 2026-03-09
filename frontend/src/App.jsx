import { useEffect, useMemo, useState } from 'react'
import './App.css'

const PROVIDERS = {
  ds: { label: 'DeepSeek', endpoint: 'https://api.deepseek.com/chat/completions', model: 'deepseek-chat' },
  doubao: { label: '豆包(Ark)', endpoint: 'https://ark.cn-beijing.volces.com/api/v3/chat/completions', model: 'doubao-1-5-pro-32k-250115' },
  qwen: { label: '千问(DashScope)', endpoint: 'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions', model: 'qwen-plus' },
  gpt: { label: 'OpenAI GPT', endpoint: 'https://api.openai.com/v1/chat/completions', model: 'gpt-4o-mini' },
}

function fmtPct(v) {
  const n = Number(v || 0)
  return `${(n * 100).toFixed(2)}%`
}
function fitWordSize(value, min, max) {
  if (max <= min) return 18
  const ratio = (value - min) / (max - min)
  return Math.round(14 + ratio * 34)
}
function truncateTitle20(text) {
  return Array.from(String(text || '')).slice(0, 20).join('')
}
function prettyOwnDataStatus(status) {
  const s = String(status || '')
  if (s === 'live_data') return '今日有数据'
  if (s === 'empty_today_fallback_last_valid') return '今日空数据（已回退）'
  if (s === 'empty_today_no_fallback') return '今日空数据'
  if (!s) return '未知'
  return s
}
function prettyArmStatus(status) {
  const s = String(status || '')
  if (s === 'generated') return '已生成'
  if (s === 'selected') return '已选中'
  if (s === 'ready_to_publish') return '待发布'
  if (s === 'published') return '已发布'
  if (s === 'failed') return '失败'
  return s || '未知'
}
function wordColor(value, min, max) {
  if (max <= min) return 'hsl(198 45% 34%)'
  const r = (value - min) / (max - min)
  const hue = 198 - Math.round(r * 22)
  const light = 34 - Math.round(r * 8)
  return `hsl(${hue} 58% ${light}%)`
}

function inferCategory(topic) {
  const t = String(topic || '')
  if (/跨境|亚马逊|独立站|电商/.test(t)) return '跨境学习'
  if (/面试|简历|校招|求职|实习/.test(t)) return '求职'
  if (/ai|AIGC|提示词|大模型|自动化/.test(t)) return 'AI学习'
  return '通用'
}

function normalizeTopics(list) {
  const dedup = new Map()
  for (const item of list || []) {
    if (!item?.topic) continue
    const topic = String(item.topic).trim()
    if (!topic || dedup.has(topic)) continue
    dedup.set(topic, {
      id: `${topic}-${dedup.size}`,
      topic,
      category: item.category || inferCategory(topic),
      reason: item.reason || `从输入文本提取：${topic}`,
    })
  }
  return [...dedup.values()]
}

function parseIntentText(input) {
  const cleaned = String(input || '').replace(/[\n；;。！？!？]/g, ',').replace(/，/g, ',')
  const stopPhrases = [/我想要生成一些/g, /我想要/g, /我想/g, /相关的爆款贴文/g, /相关的/g, /如果可以列出选题给我选择就更好了/g, /如果可以/g, /给我选择/g, /帮我/g, /请/g]
  const parts = cleaned
    .split(',')
    .map((x) => {
      let s = x.trim()
      for (const reg of stopPhrases) s = s.replace(reg, '')
      return s.trim()
    })
    .filter((x) => x.length >= 2)
  return normalizeTopics(parts.map((topic) => ({ topic })))
}

function extractJsonObject(text) {
  const s = String(text || '').trim()
  try {
    return JSON.parse(s)
  } catch {
    const start = s.indexOf('{')
    const end = s.lastIndexOf('}')
    if (start >= 0 && end > start) {
      try {
        return JSON.parse(s.slice(start, end + 1))
      } catch {
        return null
      }
    }
    return null
  }
}

async function callOpenClawIntent(openclawUrl, text) {
  const resp = await fetch(openclawUrl, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text }),
  })
  if (!resp.ok) throw new Error(`OpenClaw HTTP ${resp.status}`)
  const payload = await resp.json()
  const topics = normalizeTopics(payload?.topics || [])
  if (!topics.length) throw new Error('OpenClaw returned empty topics')
  return topics
}

async function callProviderIntent({ provider, endpoint, model, apiKey, text }) {
  const prompt = '你是小红书选题策略助手。将用户输入解析成 3-8 个可执行选题。仅输出 JSON 对象。格式：{"topics":[{"topic":"...","category":"求职|AI学习|跨境学习|通用","reason":"..."}]}'
  const resp = await fetch(endpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${apiKey}` },
    body: JSON.stringify({
      model,
      temperature: 0.2,
      response_format: { type: 'json_object' },
      messages: [{ role: 'system', content: prompt }, { role: 'user', content: text }],
    }),
  })
  if (!resp.ok) {
    const msg = await resp.text()
    throw new Error(`${provider} HTTP ${resp.status}: ${msg.slice(0, 160)}`)
  }
  const raw = await resp.json()
  const content = raw?.choices?.[0]?.message?.content || ''
  const parsed = extractJsonObject(content)
  const topics = normalizeTopics(parsed?.topics || [])
  if (!topics.length) throw new Error('LLM returned empty topics')
  return topics
}

function App() {
  const [data, setData] = useState(null)
  const [topic, setTopic] = useState('全部')
  const [word, setWord] = useState('')
  const [customTopic, setCustomTopic] = useState('')
  const [customCategory, setCustomCategory] = useState('通用')
  const [customDrafts, setCustomDrafts] = useState([])
  const [intentText, setIntentText] = useState('')
  const [intentTopics, setIntentTopics] = useState([])
  const [intentEngine, setIntentEngine] = useState('rule')
  const [intentError, setIntentError] = useState('')
  const [isAnalyzing, setIsAnalyzing] = useState(false)

  const [preferOpenClaw, setPreferOpenClaw] = useState(true)
  const [openclawUrl, setOpenclawUrl] = useState('http://127.0.0.1:8787/intent')
  const [provider, setProvider] = useState('ds')
  const [apiKey, setApiKey] = useState('')
  const [customEndpoint, setCustomEndpoint] = useState('')
  const [customModel, setCustomModel] = useState('')

  const [bridgeBaseUrl, setBridgeBaseUrl] = useState('http://127.0.0.1:8788')
  const [accounts, setAccounts] = useState([{ name: 'default', alias: '默认账号', is_default: true }])
  const [selectedAccount, setSelectedAccount] = useState('default')
  const [newAccountName, setNewAccountName] = useState('')
  const [newAccountAlias, setNewAccountAlias] = useState('')
  const [isLoggingInAccount, setIsLoggingInAccount] = useState(false)
  const [isCreatingAccount, setIsCreatingAccount] = useState(false)
  const [accountMessage, setAccountMessage] = useState('')
  const [isSavingDrafts, setIsSavingDrafts] = useState(false)
  const [isRunningPreview, setIsRunningPreview] = useState(false)
  const [isCollectingMarket, setIsCollectingMarket] = useState(false)
  const [flowMessage, setFlowMessage] = useState('')
  const [selectedCandidateIdx, setSelectedCandidateIdx] = useState(0)
  const [showAdvancedIntent, setShowAdvancedIntent] = useState(false)
  const [expandedCandidateKeys, setExpandedCandidateKeys] = useState({})

  async function refreshAccounts() {
    try {
      const r = await fetch(`${bridgeBaseUrl}/api/accounts`)
      const payload = await r.json()
      if (!payload?.ok || !Array.isArray(payload.accounts) || !payload.accounts.length) return
      setAccounts(payload.accounts)
      const next = payload.defaultAccount || payload.accounts.find((x) => x.is_default)?.name || payload.accounts[0].name
      setSelectedAccount((prev) => (payload.accounts.some((x) => x.name === prev) ? prev : next))
    } catch {
      // ignore
    }
  }

  useEffect(() => {
    fetch('/data/dashboard.json').then((r) => r.json()).then(setData).catch(() => setData({ error: true }))
  }, [])
  useEffect(() => {
    refreshAccounts()
  }, [bridgeBaseUrl])

  const topics = useMemo(() => ['全部', ...(data?.topics || [])], [data])
  const categories = ['通用', '求职', '面试', 'AI学习', '跨境学习']

  const filteredCandidates = useMemo(() => {
    const all = data?.candidates || []
    return all.filter((item) => {
      const topicPass = topic === '全部' || item.topic === topic
      const wordPass = !word || `${item.title} ${item.content}`.includes(word)
      return topicPass && wordPass
    })
  }, [data, topic, word])

  const feedbackRows = useMemo(() => {
    const rows = data?.keywordFeedback || []
    if (topic === '全部') return rows
    return rows.filter((x) => x.keyword === topic)
  }, [data, topic])

  const wordCloud = data?.wordCloud || []
  const maxWord = Math.max(...wordCloud.map((x) => x.value), 1)
  const minWord = Math.min(...wordCloud.map((x) => x.value), 1)
  const effectiveCandidates = customDrafts.length ? customDrafts : filteredCandidates
  const selectedCandidate = effectiveCandidates[selectedCandidateIdx] || null
  const selectedAccountInfo = accounts.find((x) => x.name === selectedAccount) || null
  const learnKeywords = useMemo(() => [...new Set(intentTopics.map((x) => x.topic).filter(Boolean))].slice(0, 8), [intentTopics])
  useEffect(() => {
    if (selectedCandidateIdx >= effectiveCandidates.length) {
      setSelectedCandidateIdx(0)
    }
  }, [effectiveCandidates.length, selectedCandidateIdx])

  const providerMeta = PROVIDERS[provider]
  const effectiveEndpoint = customEndpoint.trim() || providerMeta.endpoint
  const effectiveModel = customModel.trim() || providerMeta.model
  const strategyLearning = data?.strategyLearning || data?.summary?.strategy_learning || { has_run: false, arms: [], status_breakdown: {} }
  const experimentSync = data?.experimentSync || data?.summary?.experiment_sync || { linked_publish_records: 0 }
  const rewardSources = experimentSync?.reward_sources || {}
  const strategyArms = Array.isArray(strategyLearning.arms) ? strategyLearning.arms : []
  const strategyBreakdown = strategyLearning.status_breakdown || {}
  const policySummary = Array.isArray(strategyLearning.policy_summary) ? strategyLearning.policy_summary : []
  const runtimeBridge = data?.runtimeBridge || { has_data: false, steps: [], retry_count: 0, failed_steps: 0 }
  const runtimeSteps = Array.isArray(runtimeBridge.steps) ? runtimeBridge.steps : []
  const autopilot = data?.autopilot || { exists: false, alive: false }
  const autopilotTrace = Array.isArray(data?.autopilotTrace) ? data.autopilotTrace : []
  const autopilotMilestones = Array.isArray(data?.autopilotMilestones) ? data.autopilotMilestones : []

  function buildCustomDrafts() {
    const seed = customTopic.trim()
    if (!seed) return
    const hooks = ['3步上手', '实战避坑', '从0到1路线', '一页清单版']
    const drafts = Array.from({ length: 3 }).map((_, idx) => {
      const hook = hooks[idx % hooks.length]
      const chosen = customCategory === '通用' ? seed : `${customCategory}${seed}`
      const rawTitle = `${chosen}｜${seed}${hook}`
      return {
        candidate_no: idx + 1,
        topic: chosen,
        title: truncateTitle20(rawTitle),
        content:
          `目标：围绕「${seed}」快速产出可执行内容。\n` +
          `1) 先讲一个真实场景痛点\n` +
          `2) 给出${customCategory}向的可执行步骤\n` +
          `3) 结尾放模板与行动引导\n` +
          `#${chosen} #经验分享 #实操`,
        tags: `#${chosen} #经验分享 #实操`,
      }
    })
    setCustomDrafts(drafts)
    setSelectedCandidateIdx(0)
  }

  async function analyzeIntent() {
    const text = intentText.trim()
    if (!text) return
    setIsAnalyzing(true)
    setIntentError('')
    try {
      if (preferOpenClaw) {
        try {
          const result = await callOpenClawIntent(openclawUrl, text)
          setIntentTopics(result)
          setIntentEngine('openclaw')
          return
        } catch (e) {
          setIntentError(`OpenClaw 不可用，已降级：${e.message}`)
        }
      }
      if (apiKey.trim()) {
        try {
          const result = await callProviderIntent({ provider, endpoint: effectiveEndpoint, model: effectiveModel, apiKey: apiKey.trim(), text })
          setIntentTopics(result)
          setIntentEngine(`llm:${provider}`)
          return
        } catch (e) {
          setIntentError(`LLM 解析失败，已降级规则：${e.message}`)
        }
      }
      setIntentTopics(parseIntentText(text))
      setIntentEngine('rule')
    } finally {
      setIsAnalyzing(false)
    }
  }

  function useIntentTopic(item) {
    setCustomTopic(item.topic)
    setCustomCategory(item.category)
    setCustomDrafts([])
    setSelectedCandidateIdx(0)
  }

  async function saveDraftsToPool() {
    if (!customDrafts.length) return
    setIsSavingDrafts(true)
    setFlowMessage('')
    try {
      const resp = await fetch(`${bridgeBaseUrl}/api/save-drafts`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ drafts: customDrafts }),
      })
      const payload = await resp.json()
      if (!resp.ok || !payload.ok) throw new Error(payload.error || `HTTP ${resp.status}`)
      setFlowMessage(`已写入候选池：${payload.count} 条\nactive: ${payload.activePath}`)
    } catch (e) {
      setFlowMessage(`写入失败：${e.message}`)
    } finally {
      setIsSavingDrafts(false)
    }
  }

  async function runPreviewFromDraft() {
    if (!selectedCandidate) return
    setIsRunningPreview(true)
    setFlowMessage('')
    try {
      const resp = await fetch(`${bridgeBaseUrl}/api/preview-draft`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ draft: selectedCandidate, account: selectedAccount }),
      })
      const payload = await resp.json()
      if (!resp.ok || !payload.ok) throw new Error(payload.error || `HTTP ${resp.status}`)
      setFlowMessage(`预览已触发成功（账号: ${payload.account || selectedAccount}）。\n${payload.output || ''}`)
    } catch (e) {
      setFlowMessage(`预览触发失败：${e.message}`)
    } finally {
      setIsRunningPreview(false)
    }
  }

  async function collectMarketByIntent() {
    if (!learnKeywords.length) return
    setIsCollectingMarket(true)
    setFlowMessage('')
    try {
      const resp = await fetch(`${bridgeBaseUrl}/api/collect-market`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ keywords: learnKeywords }),
      })
      const payload = await resp.json()
      if (!resp.ok || !payload.ok) throw new Error(payload.error || `HTTP ${resp.status}`)
      setFlowMessage(`市场采集已触发：${learnKeywords.join(', ')}\n${payload.output || ''}`)
    } catch (e) {
      setFlowMessage(`市场采集失败：${e.message}`)
    } finally {
      setIsCollectingMarket(false)
    }
  }

  async function loginSelectedAccount() {
    setIsLoggingInAccount(true)
    setAccountMessage('')
    try {
      const resp = await fetch(`${bridgeBaseUrl}/api/login-account`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ account: selectedAccount, port: '9333' }),
      })
      const payload = await resp.json()
      if (!resp.ok || !payload.ok) throw new Error(payload.error || `HTTP ${resp.status}`)
      setAccountMessage(`已触发登录：${payload.account}（请在隔离浏览器扫码）`)
    } catch (e) {
      setAccountMessage(`登录触发失败：${e.message}`)
    } finally {
      setIsLoggingInAccount(false)
    }
  }

  async function createAccount() {
    const name = newAccountName.trim()
    if (!name) {
      setAccountMessage('请先输入账号名，例如 work')
      return
    }
    setIsCreatingAccount(true)
    setAccountMessage('')
    try {
      const resp = await fetch(`${bridgeBaseUrl}/api/add-account`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, alias: newAccountAlias.trim() }),
      })
      const payload = await resp.json()
      if (!resp.ok || !payload.ok) throw new Error(payload.error || `HTTP ${resp.status}`)
      setAccountMessage(`账号已创建：${payload.name}`)
      setNewAccountName('')
      setNewAccountAlias('')
      await refreshAccounts()
      setSelectedAccount(payload.name)
    } catch (e) {
      setAccountMessage(`创建账号失败：${e.message}`)
    } finally {
      setIsCreatingAccount(false)
    }
  }

  if (!data) return <div className="loading">Loading dashboard...</div>
  if (data.error) return <div className="loading">数据加载失败，请先执行 `npm run sync:data`。</div>

  return (
    <div className="page">
      <header className="hero hero-row">
        <div>
          <h1>XHS Growth Loop 控制台</h1>
          <p>从意图到预览发布的可视化工作台：解析、选题、选稿、预览一条线完成</p>
          <div className="workflow">
            <span className="wf-step">1. 解析意图</span>
            <span className="wf-step">2. 生成草稿</span>
            <span className="wf-step">3. 选择候选</span>
            <span className="wf-step">4. 预览发布</span>
          </div>
        </div>
        <div className="account-box">
          <h3>发布账号</h3>
          <select className="topic-select" value={selectedAccount} onChange={(e) => setSelectedAccount(e.target.value)}>
            {accounts.map((acc) => (
              <option key={acc.name} value={acc.name}>{acc.alias} ({acc.name})</option>
            ))}
          </select>
          <div className="account-actions">
            <button className="topic-clear" onClick={refreshAccounts}>刷新</button>
            <button className="topic-generate" onClick={loginSelectedAccount} disabled={isLoggingInAccount}>
              {isLoggingInAccount ? '触发中...' : '登录该账号'}
            </button>
          </div>
          <div className="account-create">
            <input className="topic-input" value={newAccountName} onChange={(e) => setNewAccountName(e.target.value)} placeholder="新账号名，例如 work" />
            <input className="topic-input" value={newAccountAlias} onChange={(e) => setNewAccountAlias(e.target.value)} placeholder="别名（可选）" />
            <button className="topic-clear" onClick={createAccount} disabled={isCreatingAccount}>
              {isCreatingAccount ? '创建中...' : '新增账号'}
            </button>
          </div>
          <p className="hint">当前账号：{selectedAccount}</p>
          {selectedAccountInfo?.profile_dir && (
            <p className="hint profile-line" title={selectedAccountInfo.profile_dir}>
              Profile: {selectedAccountInfo.profile_dir}
            </p>
          )}
          {accountMessage && <p className="warn">{accountMessage}</p>}
        </div>
      </header>

      <section className="metrics">
        <div className="card metric"><span>分析日期</span><strong>{data.summary?.date || '-'}</strong></div>
        <div className="card metric">
          <span>自有数据状态</span>
          <strong>{prettyOwnDataStatus(data.summary?.own_data_status)}</strong>
          <small className="metric-code" title={data.summary?.own_data_status || ''}>{data.summary?.own_data_status || '-'}</small>
        </div>
        <div className="card metric"><span>市场样本数</span><strong>{data.summary?.market_learning?.total_feeds || 0}</strong></div>
        <div className="card metric"><span>互动率</span><strong>{fmtPct(data.summary?.interaction_rate)}</strong></div>
      </section>

      <section className="card">
        <h2>策略实验看板</h2>
        <div className="strategy-metrics">
          <div className="strategy-metric">
            <span>策略版本</span>
            <strong>{strategyLearning.selection_policy || '-'}</strong>
          </div>
          <div className="strategy-metric">
            <span>生成模式</span>
            <strong>{strategyLearning.generation_mode || '-'}</strong>
          </div>
          <div className="strategy-metric">
            <span>实验 Run</span>
            <strong>{strategyLearning.run_id || '-'}</strong>
          </div>
          <div className="strategy-metric">
            <span>已回流记录</span>
            <strong>{experimentSync.linked_publish_records || 0}</strong>
          </div>
          <div className="strategy-metric">
            <span>待归因样本</span>
            <strong>{experimentSync?.reward_update?.pending || 0}</strong>
          </div>
          <div className="strategy-metric">
            <span>当前选中候选</span>
            <strong>{strategyLearning.selected_candidate_no || '-'}</strong>
          </div>
        </div>
        <div className="strategy-metrics">
          <div className="strategy-metric">
            <span>Runtime 重试次数</span>
            <strong>{runtimeBridge.retry_count || 0}</strong>
          </div>
          <div className="strategy-metric">
            <span>Runtime 失败步骤</span>
            <strong>{runtimeBridge.failed_steps || 0}</strong>
          </div>
          <div className="strategy-metric">
            <span>Runtime 最近步骤</span>
            <strong>{runtimeBridge?.latest?.step_id || '-'}</strong>
          </div>
          <div className="strategy-metric">
            <span>Runtime 最近结果</span>
            <strong>{runtimeBridge?.latest?.ok ? '成功' : (runtimeBridge?.latest ? '失败' : '-')}</strong>
          </div>
          <div className="strategy-metric">
            <span>Runtime 决策动作</span>
            <strong>{runtimeBridge?.latest?.decision?.action || '-'}</strong>
          </div>
          <div className="strategy-metric">
            <span>Runtime 决策原因</span>
            <strong>{runtimeBridge?.latest?.decision?.reason || '-'}</strong>
          </div>
        </div>
        <div className="strategy-metrics">
          <div className="strategy-metric">
            <span>Autopilot 状态</span>
            <strong>{autopilot.exists ? (autopilot.alive ? '运行中' : '疑似停止') : '未检测到'}</strong>
          </div>
          <div className="strategy-metric">
            <span>Autopilot 周期</span>
            <strong>{autopilot.cycle || '-'}</strong>
          </div>
          <div className="strategy-metric">
            <span>Autopilot 阶段</span>
            <strong>{autopilot.state || '-'}</strong>
          </div>
          <div className="strategy-metric">
            <span>Autopilot 延迟(s)</span>
            <strong>{autopilot.age_seconds ?? '-'}</strong>
          </div>
          <div className="strategy-metric">
            <span>Autopilot 原因</span>
            <strong>{autopilot.reason || '-'}</strong>
          </div>
          <div className="strategy-metric">
            <span>Autopilot 心跳</span>
            <strong>{autopilot.exists ? '已上报' : '无'}</strong>
          </div>
        </div>
        {strategyLearning.openclaw_enabled && (
          <p className="hint">
            OpenClaw：已启用
            {strategyLearning.openclaw_error ? `（本轮已回退：${strategyLearning.openclaw_error}）` : '（本轮调用成功）'}
          </p>
        )}
        <div className="strategy-status-row">
          {Object.keys(strategyBreakdown).length === 0 && <span className="hint">暂无状态分布</span>}
          {Object.entries(strategyBreakdown).map(([k, v]) => (
            <span key={k} className="status-chip">{prettyArmStatus(k)}: {v}</span>
          ))}
        </div>
        <div className="strategy-status-row">
          {Object.keys(rewardSources).length === 0 && <span className="hint">暂无奖励归因来源</span>}
          {Object.entries(rewardSources).map(([k, v]) => (
            <span key={k} className="status-chip">{k}: {v}</span>
          ))}
        </div>
        <div className="strategy-arms">
          {strategyArms.length === 0 && <p className="hint">暂无实验 Arm 数据</p>}
          {strategyArms.map((arm) => (
            <div key={`${arm.candidate_no}-${arm.topic}`} className="strategy-arm-item">
              <div className="strategy-arm-head">
                <strong>候选 #{arm.candidate_no}</strong>
                <span className="status-chip">{prettyArmStatus(arm.status)}</span>
              </div>
              <p>topic: {arm.topic || '-'}</p>
              <p>hook: {arm.hook_type || '-'} · structure: {arm.structure_type || '-'} · cta: {arm.cta_type || '-'}</p>
              <p>score: {Number(arm.score || 0).toFixed(4)}</p>
            </div>
          ))}
        </div>
        {policySummary.length > 0 && (
          <div className="policy-summary">
            <h3>策略学习统计（Bandit）</h3>
            <div className="policy-grid">
              {policySummary.map((row) => (
                <div key={row.arm_key} className="policy-item">
                  <strong>{row.arm_key}</strong>
                  <p>pulls: {row.pulls} · wins: {row.wins}</p>
                  <p>alpha: {Number(row.alpha || 0).toFixed(2)} · beta: {Number(row.beta || 0).toFixed(2)}</p>
                  <p>last_reward: {row.last_reward == null ? '-' : Number(row.last_reward).toFixed(3)}</p>
                </div>
              ))}
            </div>
          </div>
        )}
        {runtimeSteps.length > 0 && (
          <div className="policy-summary">
            <h3>Runtime 执行轨迹</h3>
            <div className="policy-grid">
              {runtimeSteps.map((row) => (
                <div key={row.step_id} className="policy-item">
                  <strong>{row.step_id}</strong>
                  <p>attempts: {row.attempts} · ok: {row.ok ? 'true' : 'false'}</p>
                  <p>returncode: {row.returncode} · action: {row.action || '-'}</p>
                  <p>reason: {row.reason || '-'}</p>
                </div>
              ))}
            </div>
          </div>
        )}
        <details className="autopilot-trace">
          <summary>Autopilot 实时轨迹（折叠）</summary>
          {autopilotTrace.length === 0 && <p className="hint">暂无轨迹数据</p>}
          {autopilotTrace.length > 0 && (
            <div className="autopilot-trace-list">
              {autopilotTrace.slice().reverse().map((row, idx) => (
                <div key={`${row.kind}-${row.cycle}-${row.step_id || idx}`} className="autopilot-trace-item">
                  {row.kind === 'decision' ? (
                    <p>
                      [cycle {row.cycle}] decision: reason={row.reason || '-'} | plan={row.plan_len} | continue={String(row.continue_flag)} | sleep={row.sleep_seconds}s
                    </p>
                  ) : (
                    <p>
                      [cycle {row.cycle}] step: {row.step_id || '-'} | rc={row.rc} | cmd={row.cmd || '-'}
                    </p>
                  )}
                </div>
              ))}
            </div>
          )}
        </details>
        <details className="autopilot-trace">
          <summary>每轮里程碑与结论（折叠）</summary>
          {autopilotMilestones.length === 0 && <p className="hint">暂无里程碑数据（重启 autopilot 后会持续生成）</p>}
          {autopilotMilestones.length > 0 && (
            <div className="autopilot-trace-list">
              {autopilotMilestones.slice().reverse().map((row, idx) => (
                <div key={`ms-${row.cycle}-${idx}`} className="autopilot-trace-item">
                  <p>[cycle {row.cycle}] 结论：{row.conclusion || '-'}</p>
                  <p>里程碑：{Array.isArray(row.milestones) ? row.milestones.join('；') : '-'}</p>
                  <p>变化：run_id {row?.base?.run_id ?? '-'} {'->'} {row?.after?.run_id ?? '-'} | score {row?.base?.score ?? '-'} {'->'} {row?.after?.score ?? '-'} | pending {row?.base?.pending_reward ?? '-'} {'->'} {row?.after?.pending_reward ?? '-'}</p>
                </div>
              ))}
            </div>
          )}
        </details>
      </section>

      <section className="main-stage">
        <div className="stage-left">
          <section className="card">
            <h2><span className="step-dot">1</span>意图输入（OpenClaw / LLM / 规则冗余）</h2>
            <p className="hint">链路：OpenClaw（可用优先） → 选定 LLM API → 本地规则兜底。</p>
            <button className="topic-clear compact-toggle" onClick={() => setShowAdvancedIntent((v) => !v)}>
              {showAdvancedIntent ? '收起高级设置' : '展开高级设置'}
            </button>
            {showAdvancedIntent && (
              <div className="engine-panel">
                <label className="engine-toggle"><input type="checkbox" checked={preferOpenClaw} onChange={(e) => setPreferOpenClaw(e.target.checked)} />优先使用 OpenClaw</label>
                <input className="topic-input" value={openclawUrl} onChange={(e) => setOpenclawUrl(e.target.value)} placeholder="OpenClaw 意图接口，例如 http://127.0.0.1:8787/intent" />
                <select className="topic-select" value={provider} onChange={(e) => setProvider(e.target.value)}>{Object.entries(PROVIDERS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}</select>
                <input className="topic-input" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder="API Key（仅保存在浏览器内存）" />
                <input className="topic-input" value={customEndpoint} onChange={(e) => setCustomEndpoint(e.target.value)} placeholder={`可选自定义 endpoint，默认 ${providerMeta.endpoint}`} />
                <input className="topic-input" value={customModel} onChange={(e) => setCustomModel(e.target.value)} placeholder={`可选自定义 model，默认 ${providerMeta.model}`} />
              </div>
            )}

            <div className="intent-form">
              <textarea
                className="intent-textarea"
                value={intentText}
                onChange={(e) => setIntentText(e.target.value)}
                placeholder="例如：跨境电商，小白入门跨境电商，实习生找工作"
              />
              <div className="intent-actions">
                <button className="topic-generate" onClick={analyzeIntent} disabled={isAnalyzing}>
                  {isAnalyzing ? '解析中...' : '解析输入'}
                </button>
              </div>
            </div>

            <p className="hint">当前解析引擎：{intentEngine}</p>
            {intentError && <p className="warn">{intentError}</p>}

            {intentTopics.length > 0 && (
              <div className="intent-result">
                <h3>建议选题（可选）</h3>
                <div className="intent-grid">
                  {intentTopics.map((item) => (
                    <div className="intent-item" key={item.id}>
                      <strong>{item.topic}</strong>
                      <small>{item.category}</small>
                      <span>{item.reason}</span>
                      <button className="topic-clear" onClick={() => useIntentTopic(item)}>用这个生成草稿</button>
                    </div>
                  ))}
                </div>
                <div className="cmd-box"><code>{`LEARN_KEYWORDS="${learnKeywords.join(',')}" bash scripts/01_collect_market.sh`}</code></div>
                <div className="intent-actions-inline">
                  <button className="topic-clear" onClick={collectMarketByIntent} disabled={isCollectingMarket || !learnKeywords.length}>
                    {isCollectingMarket ? '采集中...' : '一键市场采集'}
                  </button>
                </div>
              </div>
            )}
          </section>
        </div>

        <div className="stage-right">
          <section className="card">
            <h2><span className="step-dot">2</span>自定义选题输入</h2>
            <p className="hint">平台限制：标题最多 20 字（已自动截断）。</p>
            <div className="topic-form">
              <input
                className="topic-input"
                value={customTopic}
                onChange={(e) => setCustomTopic(e.target.value)}
                placeholder="输入你想要的选题，例如：应届生转产品经理"
              />
              <div className="topic-form-actions">
                <select className="topic-select" value={customCategory} onChange={(e) => setCustomCategory(e.target.value)}>
                  {categories.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
                <button className="topic-generate" onClick={buildCustomDrafts}>生成草稿</button>
                <button className="topic-clear" onClick={() => setCustomDrafts([])}>清除草稿</button>
              </div>
            </div>
          </section>
          <section className="card stage-sticky">
            <h2><span className="step-dot">4</span>发布动作</h2>
            <div className="flow-panel">
              <input className="topic-input" value={bridgeBaseUrl} onChange={(e) => setBridgeBaseUrl(e.target.value)} placeholder="Flow bridge 地址，例如 http://127.0.0.1:8788" />
              <div className="flow-actions">
                <button className="topic-clear secondary-action" onClick={saveDraftsToPool} disabled={isSavingDrafts || !customDrafts.length}>{isSavingDrafts ? '写入中...' : '写入候选池'}</button>
                <button className="topic-generate primary-action" onClick={runPreviewFromDraft} disabled={isRunningPreview || !selectedCandidate}>{isRunningPreview ? '触发中...' : '进入预览发布'}</button>
              </div>
            </div>
            {flowMessage && <pre className="flow-log">{flowMessage}</pre>}
          </section>
        </div>
      </section>

      <section className="card">
        <h2><span className="step-dot">2</span>贴文选题</h2>
        <div className="chips">{topics.map((name) => <button key={name} className={name === topic ? 'chip chip-active' : 'chip'} onClick={() => setTopic(name)}>{name}</button>)}</div>
      </section>

      <section className="grid-2">
        <article className="card">
          <h2><span className="step-dot">3</span>候选贴文（点击选择）</h2>
          {selectedCandidate && <p className="hint">当前采用：{selectedCandidate.title}</p>}
          <div className="list">
            {effectiveCandidates.length === 0 && <p className="hint">无匹配候选</p>}
            {effectiveCandidates.map((c, idx) => (
              (() => {
                const key = `${c.candidate_no || idx}-${idx}`
                const expanded = !!expandedCandidateKeys[key]
                return (
              <div
                key={key}
                className={idx === selectedCandidateIdx ? 'item item-selected' : 'item item-clickable'}
                onClick={() => setSelectedCandidateIdx(idx)}
              >
                {idx === selectedCandidateIdx && <span className="selected-badge">已选中</span>}
                <h3>{c.title}</h3>
                <p className={expanded ? 'content-full' : 'content-clamp'}>{c.content}</p>
                <button
                  className="mini-link"
                  onClick={(e) => {
                    e.stopPropagation()
                    setExpandedCandidateKeys((prev) => ({ ...prev, [key]: !prev[key] }))
                  }}
                >
                  {expanded ? '收起' : '展开全文'}
                </button>
                <small>{c.tags}</small>
              </div>
                )
              })()
            ))}
          </div>
        </article>

        <article className="card">
          <h2><span className="step-dot">4</span>搜集数据反馈</h2>
          <div className="list">
            {feedbackRows.map((row) => (
              <div key={row.keyword} className="item"><h3>{row.keyword} · {row.count} 条</h3><ul>{row.topTitles.slice(0, 3).map((t, idx) => <li key={`${row.keyword}-${idx}`}>{t}</li>)}</ul></div>
            ))}
          </div>
        </article>
      </section>

      <section className="card">
        <h2>词云洞察</h2>
        <p className="hint">点击词语可联动过滤候选内容</p>
        <div className="word-cloud">
          {wordCloud.map((w) => (
            <button
              key={w.text}
              className={word === w.text ? 'word active-word' : 'word'}
              style={{
                fontSize: `${fitWordSize(w.value, minWord, maxWord)}px`,
                color: wordColor(w.value, minWord, maxWord),
                opacity: 0.62 + ((w.value - minWord) / Math.max(1, (maxWord - minWord))) * 0.38,
              }}
              onClick={() => setWord((prev) => (prev === w.text ? '' : w.text))}
              title={`出现 ${w.value} 次`}
            >
              {w.text}
            </button>
          ))}
        </div>
      </section>
    </div>
  )
}

export default App
