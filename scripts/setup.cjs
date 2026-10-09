const { spawnSync } = require('node:child_process');
const path = require('node:path');
const fs = require('node:fs');
const root = path.resolve(__dirname, '..');
const windows = process.platform === 'win32';
const python = path.join(root, '.venv', windows ? 'Scripts/python.exe' : 'bin/python');
function run(command, args) {
  const result = spawnSync(command, args, { cwd: root, stdio: 'inherit' });
  if (result.error) console.error(result.error.message);
  if (result.status !== 0) process.exit(result.status || 1);
}
if (!fs.existsSync(python)) run(windows ? 'python' : 'python3', ['-m', 'venv', '.venv']);
run(python, ['-m', 'pip', 'install', '-r', 'backend/requirements.txt']);
// npm provides its CLI path, avoiding Windows shell quoting for paths with spaces.
run(process.execPath, [process.env.npm_execpath, 'ci']);
run(process.execPath, [process.env.npm_execpath, 'ci', '--prefix', 'frontend']);
run(process.execPath, [path.join(root, 'node_modules/@playwright/test/cli.js'), 'install', 'chromium']);
console.log('Setup complete. Run npm run dev to start CaseSeva locally.');
