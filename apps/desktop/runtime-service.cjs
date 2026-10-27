// Owned loopback process supervision only; never a user/Agent command runner.
const { spawn } = require('node:child_process');
const { randomBytes, createHmac, timingSafeEqual } = require('node:crypto');
const http = require('node:http');
const path = require('node:path');
const fs = require('node:fs');

function serviceURL(value) {
  try {
    const url = new URL(value);
    return url.protocol === 'http:' && url.hostname === '127.0.0.1' && /^\d+$/.test(url.port) && Number(url.port) >= 1024 && !url.username && !url.password && url.pathname === '/' && !url.search && !url.hash;
  } catch { return false; }
}

function readJSON(origin, route, headers = {}) {
  return new Promise((resolve, reject) => {
    const request = http.get(origin + route, { headers, agent: false }, response => {
      let bytes = 0, body = '';
      response.on('data', chunk => {
        bytes += chunk.length;
        if (bytes > 2048) { response.destroy(); request.destroy(new Error('invalid_service_response')); return; }
        body += chunk.toString('utf8');
      });
      response.on('end', () => {
        try { if (response.statusCode !== 200) throw new Error(); resolve(JSON.parse(body)); }
        catch { reject(new Error('service_unavailable')); }
      });
      response.on('error', () => reject(new Error('service_unavailable')));
    });
    request.setTimeout(500, () => request.destroy(new Error('service_timeout')));
    request.on('error', () => reject(new Error('service_unavailable')));
  });
}

function validProof(reply, key, challenge) {
  if (!reply || Object.keys(reply).sort().join(',') !== 'challenge,mode,proof,schema_version' || reply.schema_version !== 'classmatter.desktop-proof.v1' || reply.mode !== 'synthetic-only' || reply.challenge !== challenge || !/^[a-f0-9]{64}$/.test(reply.proof)) return false;
  const expected = createHmac('sha256', Buffer.from(key, 'hex')).update('classmatter.desktop.v1:' + challenge).digest();
  return timingSafeEqual(expected, Buffer.from(reply.proof, 'hex'));
}

class OwnedService {
  constructor({ origin, spawnService, timeout = 30000, onUnexpectedExit = () => {} }) {
    if (!serviceURL(origin) || typeof spawnService !== 'function') throw new Error('invalid_service_configuration');
    this.origin = new URL(origin).origin;
    this.spawnService = spawnService;
    this.timeout = timeout;
    this.onUnexpectedExit = onUnexpectedExit;
    this.state = 'idle';
    this.child = null;
    this.closed = Promise.resolve();
  }
  async start() {
    if (this.state !== 'idle') throw new Error('service_already_started');
    this.state = 'starting';
    const key = randomBytes(32).toString('hex');
    try {
      this.child = this.spawnService(key);
      this.closed = new Promise(resolve => this.child.once('close', resolve));
      this.child.on('error', () => { this.state = 'failed'; });
      this.child.on('exit', () => {
        if (this.state === 'ready') { this.state = 'failed'; this.onUnexpectedExit(); }
        else if (this.state === 'starting') this.state = 'failed';
      });
      const deadline = Date.now() + this.timeout;
      while (Date.now() < deadline && this.state === 'starting') {
        try {
          const challenge = randomBytes(32).toString('hex');
          const proof = await readJSON(this.origin, '/health/desktop', {'x-classmatter-challenge': challenge});
          if (!validProof(proof, key, challenge)) throw new Error('service_identity_mismatch');
          const ready = await readJSON(this.origin, '/health/ready');
          if (ready.schema_version !== 'class-os.health.v1' || ready.mode !== 'synthetic-development' || ready.service !== 'class-os-api' || ready.status !== 'ready' || ['database','identity','business_gateways'].some(name => ready.components?.[name] !== 'connected')) throw new Error('service_not_ready');
          if (this.state !== 'starting' || this.child.exitCode !== null || this.child.signalCode !== null) throw new Error('service_exited');
          this.state = 'ready';
          return this.origin;
        } catch (error) {
          if (error.message === 'service_identity_mismatch') throw error;
          await new Promise(resolve => setTimeout(resolve, 50));
        }
      }
      throw new Error('service_start_failed');
    } catch {
      await this.stop();
      throw new Error('Desktop service unavailable; existing runtime was not changed.');
    }
  }
  async stop() {
    if (this.state === 'stopped') return;
    this.state = 'stopping';
    const child = this.child;
    if (child && child.exitCode === null && child.signalCode === null) child.kill();
    let timer;
    try {
      await Promise.race([this.closed, new Promise((_, reject) => { timer = setTimeout(() => reject(new Error('Owned service did not stop')), 5000); })]);
    } finally { clearTimeout(timer); this.state = 'stopped'; }
  }
}

function desktopService(repositoryRoot, uiRoot, onUnexpectedExit, runtimeRoot, profile = 'r1', servicePort = profile === 'conversation-d1' ? 8001 : 8000) {
  if (!['r1', 'conversation-d1'].includes(profile)) throw new Error('Unknown synthetic runtime profile');
  if (!Number.isInteger(servicePort) || servicePort < 1024 || servicePort > 65535 || (profile === 'r1' && servicePort !== 8000)) throw new Error('Invalid owned service port');
  if (process.platform !== 'win32' || !path.isAbsolute(repositoryRoot) || !path.isAbsolute(uiRoot)) throw new Error('Unsupported desktop runtime');
  const root = fs.realpathSync(repositoryRoot), ui = fs.realpathSync(uiRoot);
  const runtime = runtimeRoot || path.join(root, profile === 'r1' ? '.local-runtime/synthetic-v1' : '.local-runtime/synthetic-conversation-d1');
  if (!path.isAbsolute(runtime)) throw new Error('Invalid operator runtime root');
  const executable = path.join(root, 'backend/.venv/Scripts/python.exe');
  const entry = path.join(root, 'backend/desktop.py');
  const marker = JSON.parse(fs.readFileSync(path.join(ui, 'desktop-runtime.json'), 'utf8'));
  if (!fs.existsSync(executable) || !fs.existsSync(entry) || marker.mode !== (profile === 'r1' ? 'synthetic-runtime' : 'synthetic-conversation-d1') || !fs.existsSync(path.join(ui,'index.html'))) throw new Error('Build the synthetic desktop runtime and sync backend dependencies first');
  return new OwnedService({ origin: `http://127.0.0.1:${servicePort}`, onUnexpectedExit, spawnService: key => {
    const env = { ...process.env, CLASS_OS_MODE: 'synthetic-development', CLASS_OS_HOST: '127.0.0.1', CLASS_OS_PORT: String(servicePort), CLASS_OS_MODEL_PROVIDER: 'fake', CLASSMATTER_DESKTOP_PROCESS_KEY: key };
    delete env.PYTHONPATH; delete env.PYTHONHOME;
    const args = ['-I', entry, '--ui-root', ui, '--runtime-root', runtime, '--parent-pipe'];
    if (profile !== 'r1') args.push('--profile', profile);
    return spawn(executable, args, { cwd: path.dirname(entry), env, shell: false, windowsHide: true, stdio: ['pipe', 'ignore', 'ignore'] });
  }});
}

module.exports = { OwnedService, desktopService, serviceURL, validProof };
