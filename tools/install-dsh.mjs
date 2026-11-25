// 把 dsh-fish-house 装进 DSH 的 desktop profile：
//   1. node_modules 下建 junction（等同 pnpm 的 link: 安装）
//   2. profile package.json 里登记依赖 + bundle
// 用法：node tools/install-dsh.mjs [--uninstall]
import { copyFileSync, existsSync, lstatSync, mkdirSync, readFileSync, rmSync, symlinkSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { homedir } from 'node:os'

const HERE = dirname(fileURLToPath(import.meta.url))
const PKG = dirname(HERE)
const profile = process.env.DSH_PROFILE_DIR || join(homedir(), '.dsh', 'profiles', 'desktop')
const pkgFile = join(profile, 'package.json')
const nm = join(profile, 'node_modules')
const id = 'dsh-fish-house'
const linkPath = join(nm, id)

const uninstall = process.argv.includes('--uninstall')

if (!existsSync(pkgFile)) {
  console.error('没有找到 profile：' + pkgFile)
  process.exit(1)
}

if (uninstall) {
  try { if (existsSync(linkPath)) rmSync(linkPath, { recursive: true, force: true }) } catch { /* ignore */ }
  console.log('已移除链接')
  process.exit(0)
}

copyFileSync(pkgFile, pkgFile + '.bak-dsh-fish-house')
const pkg = JSON.parse(readFileSync(pkgFile, 'utf8'))

pkg.dependencies = pkg.dependencies || {}
pkg.dependencies[id] = 'link:' + PKG.replace(/\\/g, '/')

pkg.dsh = pkg.dsh || {}
pkg.dsh.profile = pkg.dsh.profile || {}
const bundles = pkg.dsh.profile.bundles || []
if (!bundles.includes(id)) bundles.push(id)
pkg.dsh.profile.bundles = bundles

writeFileSync(pkgFile, JSON.stringify(pkg, null, 2), 'utf8')

mkdirSync(nm, { recursive: true })
if (existsSync(linkPath)) {
  const stat = lstatSync(linkPath)
  if (stat.isSymbolicLink() || stat.isDirectory()) rmSync(linkPath, { recursive: true, force: true })
}
symlinkSync(PKG, linkPath, 'junction')
console.log('已安装：' + linkPath + ' -> ' + PKG)
console.log('bundle 列表：' + bundles.join(', '))
