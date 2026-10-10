const { spawn } = require('node:child_process');
const path = require('node:path');
const fs = require('node:fs');
const root = path.resolve(__dirname, '..');
const python = path.join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
if (!fs.existsSync(python)) {
  console.error('Create .venv and install backend/requirements.txt first; see README.md.');
  process.exit(1);
}
const mock = process.argv.includes('--mock');
const portIndex = process.argv.indexOf('--port');
const port = portIndex >= 0 ? process.argv[portIndex + 1] : '8000';
if (!/^\d+$/.test(port) || Number(port) < 1 || Number(port) > 65535) throw new Error('Invalid backend port');
const child = spawn(python, ['-m', 'uvicorn', 'backend.main:app', '--host', '127.0.0.1', '--port', port], {
  cwd: root, stdio: 'inherit',
  env: mock ? { ...process.env, USE_MOCK_AWS: 'true', USE_REAL_DATABASE: 'false', USE_REAL_STORAGE: 'false', USE_REAL_LLM: 'false' } : process.env
});
child.on('error', error => { console.error(error); process.exit(1); });
child.on('exit', code => process.exit(code ?? 1));
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => child.kill(signal));
