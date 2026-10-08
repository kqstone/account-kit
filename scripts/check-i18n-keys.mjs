#!/usr/bin/env node
/** Vue / React i18n key parity: labels + errors, zh-CN vs en. */
import fs from "node:fs"
import path from "node:path"
import { fileURLToPath } from "node:url"

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..")
const vue = path.join(root, "packages/account-ui-vue/src")
const react = path.join(root, "packages/account-ui-react/src")

function read(dir, name) {
  return fs.readFileSync(path.join(dir, name), "utf8")
}

function fail(msg) {
  console.error(msg)
  process.exitCode = 1
}

function objectKeys(block) {
  const keys = []
  for (const line of block.split("\n")) {
    const m = line.match(/^\s+(?:"([A-Za-z0-9_]+)"|([A-Za-z_][A-Za-z0-9_]*))\s*:/)
    if (m) keys.push(m[1] || m[2])
  }
  return [...new Set(keys)]
}

function extractNamedObject(src, name) {
  const re = new RegExp(`(?:export )?const ${name}(?::[^=]+)? = \\{`)
  const m = src.match(re)
  if (!m) throw new Error(`object ${name} not found`)
  const start = src.indexOf("{", m.index)
  let depth = 0
  for (let i = start; i < src.length; i++) {
    const ch = src[i]
    if (ch === "{") depth++
    else if (ch === "}") {
      depth--
      if (depth === 0) return src.slice(start + 1, i)
    }
  }
  throw new Error(`unclosed object ${name}`)
}

function localeBlock(src, locale) {
  const needle = locale === "zh-CN" ? '"zh-CN": {' : "en: {"
  const idx = src.indexOf(needle)
  if (idx < 0) throw new Error(`locale ${locale} not found`)
  const start = src.indexOf("{", idx)
  let depth = 0
  for (let i = start; i < src.length; i++) {
    const ch = src[i]
    if (ch === "{") depth++
    else if (ch === "}") {
      depth--
      if (depth === 0) return src.slice(start + 1, i)
    }
  }
  throw new Error(`unclosed locale ${locale}`)
}

for (const name of ["errors.ts", "labels.ts", "utils.ts"]) {
  const a = read(vue, name)
  const b = read(react, name)
  if (a !== b) fail(`${name}: Vue and React sources differ`)
}

const errors = read(vue, "errors.ts")
const zhErr = objectKeys(localeBlock(errors, "zh-CN")).sort()
const enErr = objectKeys(localeBlock(errors, "en")).sort()
if (zhErr.join() !== enErr.join()) {
  fail(`errors.ts zh-CN vs en keys differ\n- ${zhErr.filter((k) => !enErr.includes(k))}\n+ ${enErr.filter((k) => !zhErr.includes(k))}`)
}

const labels = read(vue, "labels.ts")
for (const name of ["twoFactorZh", "twoFactorEn", "profileZh", "profileEn", "formZh", "formEn"]) {
  extractNamedObject(labels, name)
}
const pairs = [
  ["twoFactorZh", "twoFactorEn"],
  ["profileZh", "profileEn"],
  ["formZh", "formEn"],
]
for (const [a, b] of pairs) {
  const ka = objectKeys(extractNamedObject(labels, a)).sort()
  const kb = objectKeys(extractNamedObject(labels, b)).sort()
  if (ka.join() !== kb.join()) fail(`labels ${a} vs ${b} keys differ: ${ka.filter((k) => !kb.includes(k))} / ${kb.filter((k) => !ka.includes(k))}`)
}

if (process.exitCode) {
  console.error("i18n key parity check failed")
  process.exit(process.exitCode)
}
console.log(`i18n key parity ok: ${zhErr.length} error codes, labels objects aligned`)
