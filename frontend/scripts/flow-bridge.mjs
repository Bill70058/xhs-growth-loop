import http from 'node:http'
import fs from 'node:fs'
import path from 'node:path'
import { execFile } from 'node:child_process'

const HOST = '127.0.0.1'
const PORT = Number(process.env.FLOW_BRIDGE_PORT || 8788)
const root = path.resolve(process.cwd(), '..')
const accountsFile = path.join(root, 'vendors', 'XiaohongshuSkills', 'config', 'accounts.json')

function send(res, code, payload) {
  res.writeHead(code, {
    'Content-Type': 'application/json; charset=utf-8',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
  })
  res.end(JSON.stringify(payload))
}

function readJson(req) {
  return new Promise((resolve, reject) => {
    let body = ''
    req.on('data', (chunk) => {
      body += chunk
      if (body.length > 2_000_000) {
        reject(new Error('payload too large'))
      }
    })
    req.on('end', () => {
      try {
        resolve(body ? JSON.parse(body) : {})
      } catch (e) {
        reject(e)
      }
    })
    req.on('error', reject)
  })
}

function nowStamp() {
  const d = new Date()
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}_${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`
}

function today() {
  const d = new Date()
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

function normalizeDrafts(raw) {
  if (!Array.isArray(raw)) return []
  return raw
    .map((x, idx) => ({
      candidate_no: idx + 1,
      topic: String(x?.topic || '').trim(),
      title: String(x?.title || '').trim(),
      content: String(x?.content || '').trim(),
      tags: String(x?.tags || '').trim(),
    }))
    .filter((x) => x.title && x.content)
}

function saveDrafts(drafts) {
  const outDir = path.join(root, 'data', 'candidates')
  fs.mkdirSync(outDir, { recursive: true })

  const date = today()
  const stamp = nowStamp()
  const manualPath = path.join(outDir, `candidates_manual_${stamp}.json`)
  const activePath = path.join(outDir, `candidates_${date}.json`)

  fs.writeFileSync(manualPath, JSON.stringify(drafts, null, 2), 'utf-8')
  fs.writeFileSync(activePath, JSON.stringify(drafts, null, 2), 'utf-8')

  return { manualPath, activePath }
}

function writePreviewFiles(draft) {
  const tmpDir = path.join(root, 'data', 'published', 'tmp')
  fs.mkdirSync(tmpDir, { recursive: true })
  const titleFile = path.join(tmpDir, 'title.txt')
  const contentFile = path.join(tmpDir, 'content.txt')
  fs.writeFileSync(titleFile, draft.title, 'utf-8')
  fs.writeFileSync(contentFile, draft.content, 'utf-8')
  return { titleFile, contentFile }
}

function loadAccounts() {
  if (fs.existsSync(accountsFile)) {
    try {
      const parsed = JSON.parse(fs.readFileSync(accountsFile, 'utf-8'))
      const defaultAccount = parsed?.default_account || 'default'
      const accountsObj = parsed?.accounts || {}
      const accounts = Object.entries(accountsObj).map(([name, info]) => ({
        name,
        alias: info?.alias || name,
        profile_dir: info?.profile_dir || '',
        is_default: name === defaultAccount,
      }))
      if (accounts.length) return { defaultAccount, accounts }
    } catch {
      // ignore and fallback
    }
  }
  return {
    defaultAccount: 'default',
    accounts: [{ name: 'default', alias: '默认账号', is_default: true }],
  }
}

function resolvePythonBin() {
  const venvPy = path.join(root, '.venv', 'bin', 'python')
  return fs.existsSync(venvPy) ? venvPy : 'python3'
}

function runSkillsCommand(args, extraEnv = {}) {
  return new Promise((resolve) => {
    const env = { ...process.env, ...extraEnv }
    execFile(resolvePythonBin(), args, { cwd: path.join(root, 'vendors', 'XiaohongshuSkills'), env }, (error, stdout, stderr) => {
      resolve({
        ok: !error,
        code: error?.code ?? 0,
        stdout: String(stdout || ''),
        stderr: String(stderr || ''),
      })
    })
  })
}

function runPreview(account) {
  return new Promise((resolve) => {
    const env = {
      ...process.env,
      XHS_ACCOUNT_OVERRIDE: account || '',
    }
    execFile('bash', ['scripts/04_publish_preview.sh'], { cwd: root, env }, (error, stdout, stderr) => {
      resolve({
        ok: !error,
        code: error?.code ?? 0,
        stdout: String(stdout || ''),
        stderr: String(stderr || ''),
      })
    })
  })
}

const server = http.createServer(async (req, res) => {
  if (req.method === 'OPTIONS') {
    send(res, 200, { ok: true })
    return
  }

  if (req.method === 'GET' && req.url === '/health') {
    send(res, 200, { ok: true, service: 'flow-bridge' })
    return
  }

  if (req.method === 'GET' && req.url === '/api/accounts') {
    const payload = loadAccounts()
    send(res, 200, { ok: true, ...payload })
    return
  }

  if (req.method === 'POST' && req.url === '/api/save-drafts') {
    try {
      const body = await readJson(req)
      const drafts = normalizeDrafts(body?.drafts)
      if (!drafts.length) return send(res, 400, { ok: false, error: 'no_valid_drafts' })
      const saved = saveDrafts(drafts)
      return send(res, 200, { ok: true, count: drafts.length, ...saved })
    } catch (e) {
      return send(res, 500, { ok: false, error: e.message })
    }
  }

  if (req.method === 'POST' && req.url === '/api/preview-draft') {
    try {
      const body = await readJson(req)
      const drafts = normalizeDrafts([body?.draft])
      if (!drafts.length) return send(res, 400, { ok: false, error: 'invalid_draft' })
      const draft = drafts[0]
      const selectedAccount = String(body?.account || '').trim() || loadAccounts().defaultAccount
      writePreviewFiles(draft)
      saveDrafts([draft])
      const result = await runPreview(selectedAccount)
      return send(res, result.ok ? 200 : 500, {
        ok: result.ok,
        code: result.code,
        account: selectedAccount,
        output: `${result.stdout}\n${result.stderr}`.slice(-4000),
      })
    } catch (e) {
      return send(res, 500, { ok: false, error: e.message })
    }
  }

  if (req.method === 'POST' && req.url === '/api/add-account') {
    try {
      const body = await readJson(req)
      const name = String(body?.name || '').trim()
      const alias = String(body?.alias || '').trim()
      if (!name) return send(res, 400, { ok: false, error: 'missing_name' })
      const args = ['scripts/cdp_publish.py', 'add-account', name]
      if (alias) args.push('--alias', alias)
      const result = await runSkillsCommand(args)
      if (!result.ok) {
        return send(res, 500, { ok: false, error: 'add_account_failed', output: `${result.stdout}\n${result.stderr}`.slice(-2000) })
      }
      return send(res, 200, { ok: true, name, alias: alias || name, output: `${result.stdout}\n${result.stderr}`.slice(-2000) })
    } catch (e) {
      return send(res, 500, { ok: false, error: e.message })
    }
  }

  if (req.method === 'POST' && req.url === '/api/login-account') {
    try {
      const body = await readJson(req)
      const account = String(body?.account || '').trim() || loadAccounts().defaultAccount
      const port = String(body?.port || '9333').trim() || '9333'
      const result = await runSkillsCommand(['scripts/cdp_publish.py', '--account', account, '--port', port, 'login'])
      return send(res, result.ok ? 200 : 500, {
        ok: result.ok,
        account,
        code: result.code,
        output: `${result.stdout}\n${result.stderr}`.slice(-3000),
      })
    } catch (e) {
      return send(res, 500, { ok: false, error: e.message })
    }
  }

  send(res, 404, { ok: false, error: 'not_found' })
})

server.listen(PORT, HOST, () => {
  console.log(`[flow-bridge] listening on http://${HOST}:${PORT}`)
})
