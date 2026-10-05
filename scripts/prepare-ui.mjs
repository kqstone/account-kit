// `prepare` hook for packages/account-ui-*.
//
// npm runs `prepare` on `npm install` / `npm ci` inside the package, and also
// when a host app installs the package from a local `file:` path. The published
// entry points live in `dist/` (gitignored), so build it here:
//   1. build tools installed -> build;
//   2. otherwise install this package's own devDependencies, then build
//      (a host installing the `file:` dependency from a fresh checkout);
//   3. if that fails but an old `dist/` exists, keep it;
//   4. otherwise fail with a hint, instead of letting the host's bundler fail
//      later with a vaguer "cannot resolve entry" error.
import { existsSync } from "node:fs"
import { spawnSync } from "node:child_process"
import { join } from "node:path"

const cwd = process.cwd()
const name = cwd.split(/[\\/]/).pop()
const shell = process.platform === "win32"

function npm(args) {
  const result = spawnSync("npm", args, { cwd, stdio: "inherit", shell })
  return result.status === 0
}

const hasTools = () => existsSync(join(cwd, "node_modules", "tsup", "package.json"))

if (!hasTools() && existsSync(join(cwd, "package-lock.json"))) {
  console.log(`[${name}] installing build tools (npm ci) ...`)
  // --ignore-scripts: `npm ci` would run this prepare hook again.
  npm(["ci", "--include=dev", "--ignore-scripts", "--no-audit", "--no-fund"])
}

if (hasTools() && npm(["run", "build"])) process.exit(0)

if (existsSync(join(cwd, "dist", "index.js"))) {
  console.warn(`[${name}] build failed or tools missing; using existing dist/`)
  process.exit(0)
}

console.error(
  `[${name}] dist/ is missing and could not be built.\n` +
    `Run this once in the account-kit checkout, then install again:\n` +
    `  cd packages/${name} && npm ci && npm run build`,
)
process.exit(1)
