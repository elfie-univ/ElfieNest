import { spawn, execFileSync } from 'node:child_process';
import { realpathSync } from 'node:fs';
import { createInterface } from 'node:readline';

const [directory, title = 'Worktree 干净新对话'] = process.argv.slice(2);
if (!directory) throw new Error('Usage: node create_fresh_chat.mjs WORKTREE [TITLE]');
const cwd = realpathSync(directory);
const git = (...args) => execFileSync('git', ['-C', cwd, ...args], { encoding: 'utf8' }).trim();
if (realpathSync(git('rev-parse', '--show-toplevel')) !== cwd) {
  throw new Error('Pass the exact worktree root, not a subdirectory.');
}
const head = git('rev-parse', 'HEAD');
const status = git('status', '--short');
const server = spawn('codex', ['app-server'], { cwd, stdio: ['pipe', 'pipe', 'pipe'] });
const lines = createInterface({ input: server.stdout });
const pending = new Map();
let nextId = 0, threadId, ended = false;
let stderrTail = '';
server.stderr.on('data', data => { stderrTail = (stderrTail + data).slice(-2000); });
const send = value => server.stdin.write(JSON.stringify(value) + '\n');
const request = (method, params) => new Promise((resolve, reject) => {
  const id = nextId++;
  pending.set(id, { resolve, reject });
  send({ id, method, params });
});
const failPending = error => {
  for (const p of pending.values()) p.reject(error);
  pending.clear();
};
server.on('error', failPending);
server.on('exit', code => {
  if (!ended) failPending(new Error(`App Server exited (${code}): ${stderrTail}`));
});
lines.on('line', line => {
  let message;
  try { message = JSON.parse(line); } catch { return; }
  if (pending.has(message.id)) {
    const p = pending.get(message.id); pending.delete(message.id);
    if (message.error) p.reject(new Error(JSON.stringify(message.error)));
    else p.resolve(message.result);
  } else if (message.id !== undefined && message.method) {
    // No interactive approvals or external actions belong in this bootstrap turn.
    send({ id: message.id, error: { code: -32601, message: 'Interactive request unsupported in read-only fresh-chat bootstrap' } });
  }
});
const timer = setTimeout(() => {
  failPending(new Error(`Timed out; do not create another thread. Existing threadId: ${threadId || 'not returned'}`));
  server.kill('SIGTERM');
}, 30000);

try {
  await request('initialize', { clientInfo: { name: 'worktree_fresh_chat', version: '1.0.0' } });
  send({ method: 'initialized', params: {} });
  const started = await request('thread/start', { cwd, sandbox: 'read-only', approvalPolicy: 'on-request' });
  threadId = started.thread.id;
  console.log(JSON.stringify({ event: 'created', threadId, cwd: started.thread.cwd, head, sandbox: 'read-only' }));
  if (realpathSync(started.thread.cwd) !== cwd) throw new Error('Created thread cwd mismatch');
  await request('thread/name/set', { threadId, name: title });
  const stored = await request('thread/read', { threadId, includeTurns: false });
  if (realpathSync(stored.thread.cwd) !== cwd || stored.thread.turns?.length) {
    throw new Error('Stored fresh thread metadata mismatch');
  }
  if (git('rev-parse', 'HEAD') !== head || git('status', '--short') !== status) {
    throw new Error('Git state changed during bootstrap; inspect the existing thread before further work.');
  }
  console.log(JSON.stringify({ event: 'created-empty', threadId, cwd, head, gitStateUnchanged: true,
    next: 'Use the desktop send_message_to_thread tool for the read-only bootstrap; then verify with read_thread.' }));
} catch (error) {
  console.error(JSON.stringify({ event: 'failed', threadId: threadId || null, message: error.message }));
  process.exitCode = 1;
} finally {
  ended = true; clearTimeout(timer); server.stdin.end(); lines.close();
  // Allow normal persistence/shutdown before terminating only our own child.
  const cleanupTimer = setTimeout(() => server.kill('SIGTERM'), 3000);
  server.once('exit', () => clearTimeout(cleanupTimer));
}
