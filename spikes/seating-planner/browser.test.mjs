import assert from "node:assert/strict"
import { test, before, after, beforeEach, afterEach } from "node:test"
import { createRequire } from "node:module"
import { spawn } from "node:child_process"
import { createInterface } from "node:readline"
import { fileURLToPath } from "node:url"
import { mkdir } from "node:fs/promises"
import path from "node:path"

const require = createRequire(new URL("../../apps/web/package.json", import.meta.url))
const { chromium, expect } = require(process.env.PLAYWRIGHT_TEST_MODULE || "@playwright/test")
const directory = path.dirname(fileURLToPath(import.meta.url))
let server, browser, context, page, baseURL, errors, requests
before(async () => {
  server = spawn(process.env.SEATING_PYTHON || "python", [path.join(directory, "serve.py"), "--port", "0"], { stdio: ["ignore", "pipe", "pipe"] })
  baseURL = await new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error("owned preview server readiness timed out")), 10000)
    const output = createInterface({ input: server.stdout })
    output.once("line", line => { clearTimeout(timeout); try { resolve(JSON.parse(line).url) } catch (error) { reject(error) } })
    server.once("error", error => { clearTimeout(timeout); reject(error) })
  })
  assert.match(baseURL, /^http:\/\/127\.0\.0\.1:[0-9]+\/$/)
  browser = await chromium.launch({ headless: true, ...(process.env.SEATING_BROWSER_CHANNEL ? { channel: process.env.SEATING_BROWSER_CHANNEL } : {}) })
})
after(async () => { await browser?.close(); server?.kill() })
beforeEach(async () => {
  context = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
  page = await context.newPage(); errors = []; requests = []
  page.setDefaultTimeout(8000)
  page.on("pageerror", error => errors.push(error.message))
  page.on("request", request => requests.push({ url: request.url(), method: request.method() }))
  await page.goto(baseURL)
  await expect(page.getByRole("heading", { name: "座位方案预览" })).toBeVisible()
})
afterEach(async () => {
  assert.deepEqual(errors, [])
  assert.ok(requests.every(request => request.url.startsWith(baseURL) && request.method === "GET"))
  await context.close()
})
const generate = async () => {
  await page.getByRole("button", { name: "生成候选方案", exact: true }).click()
  await expect(page.getByRole("button", { name: /方案 1 ·/ })).toBeVisible()
}
const seat = (position, student) => page.getByRole("button", { name: new RegExp(`^${position} ${student}(?: 固定)?$`) })
const screenshotDirectory = process.env.SEATING_SCREENSHOT_DIR || path.resolve(directory, "../../test-results/seating-preview")

test("actual solver generates candidates with fixed and apart constraints", async () => {
  await generate()
  await expect(seat("1排 1座", "S001")).toBeVisible()
  await expect(page.getByRole("status")).toContainText("条件全部满足")
  await expect(page.getByRole("button", { name: "3排 4座 不可用" })).toBeDisabled()
  await page.getByRole("button", { name: /方案 2 ·/ }).click()
  await expect(page.getByRole("status")).toContainText("已显示方案 2")
  await expect(seat("1排 1座", "S001")).toBeVisible()
  await mkdir(screenshotDirectory, { recursive: true })
  await page.screenshot({ path: path.join(screenshotDirectory, "desktop.png"), fullPage: true })
})
test("keyboard manual move updates diff and undo restores the original preview", async () => {
  await generate()
  await seat("2排 1座", "S005").focus(); await page.keyboard.press("Enter")
  await seat("3排 1座", "空位").focus(); await page.keyboard.press("Space")
  await expect(seat("3排 1座", "S005")).toBeVisible()
  await expect(page.getByRole("row").filter({ hasText: "S005" })).toContainText("2排 1座")
  await page.getByRole("button", { name: "撤销上次调整" }).click()
  await expect(seat("2排 1座", "S005")).toBeVisible()
})
test("invalid manual move explains fixed constraint and keeps prior assignment", async () => {
  await generate()
  await seat("1排 1座", "S001").click(); await seat("3排 1座", "空位").click()
  await expect(page.getByRole("alert")).toContainText("固定座位不能改变")
  await expect(seat("1排 1座", "S001")).toBeVisible()
  await expect(page.getByRole("button", { name: "撤销上次调整" })).toBeDisabled()
})
test("actual drag and drop moves a student and remains undoable", async () => {
  await generate()
  await seat("2排 2座", "S006").dragTo(seat("3排 2座", "空位"))
  await expect(seat("3排 2座", "S006")).toBeVisible()
  await expect(page.getByRole("button", { name: "撤销上次调整" })).toBeEnabled()
})
test("changing a constraint invalidates all old candidates and manual controls", async () => {
  await generate()
  await page.getByLabel("不可用座位", { exact: true }).fill("3-3,3-4")
  await expect(page.getByRole("status")).toContainText("旧方案已失效")
  await expect(page.getByRole("button", { name: /方案 1 ·/ })).toHaveCount(0)
  await expect(page.getByRole("button", { name: "撤销上次调整" })).toBeDisabled()
  await generate()
  await expect(page.getByRole("button", { name: "3排 3座 不可用" })).toBeDisabled()
})
async function smallProblem() {
  await page.getByText("当前方案与比较基准", { exact: true }).click()
  await page.getByLabel("当前座位（可选，每行 ID=排-列）", { exact: true }).fill("")
  await page.getByLabel("固定座位（每行 ID=排-列）", { exact: true }).fill("")
  await page.getByLabel("不可相邻（每行两个 ID）", { exact: true }).fill("")
  await page.getByLabel("不可用座位", { exact: true }).fill("")
  await page.getByLabel("合成学生 ID（每行一个）", { exact: true }).fill("S001\nS002")
  await page.getByLabel("排数", { exact: true }).fill("1")
  await page.getByLabel("每排列数", { exact: true }).fill("1")
}
test("seat shortage is actionable and creates no mock candidate", async () => {
  await smallProblem()
  await page.getByRole("button", { name: "生成候选方案", exact: true }).click()
  await expect(page.getByRole("alert")).toContainText("座位不足")
  await expect(page.getByRole("button", { name: /方案 1 ·/ })).toHaveCount(0)
})
test("exhaustive incompatible adjacency is explained in the rendered UI", async () => {
  await smallProblem()
  await page.getByLabel("每排列数", { exact: true }).fill("2")
  await page.getByLabel("不可相邻（每行两个 ID）", { exact: true }).fill("S001,S002")
  await page.getByRole("button", { name: "生成候选方案", exact: true }).click()
  await expect(page.getByRole("alert")).toContainText("无可行方案")
})
test("mobile has no page overflow and retains keyboard-operable preview", async () => {
  await page.setViewportSize({ width: 390, height: 844 })
  await generate()
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
  await seat("1排 1座", "S001").focus()
  await expect(seat("1排 1座", "S001")).toBeFocused()
  await mkdir(screenshotDirectory, { recursive: true })
  await page.screenshot({ path: path.join(screenshotDirectory, "mobile.png"), fullPage: true })
})
test("owned static server refuses unknown paths, writes and alternate host", async () => {
  assert.equal((await context.request.get(new URL("serve.py", baseURL).href)).status(), 404)
  assert.equal((await context.request.post(baseURL, { data: "synthetic" })).status(), 501)
  assert.equal((await context.request.get(baseURL, { headers: { Host: "untrusted.invalid" } })).status(), 421)
})
