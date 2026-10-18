import { useEffect, useRef, useState } from "react"

import TopBar from "@/shell/TopBar/TopBar"

import Sidebar from "@/shell/Sidebar/Sidebar"

import MobileNav from "@/shell/MobileNav"

import Inspector from "@/shell/Inspector/Inspector"

import { useMockDomainStore } from "@/store/MockDomainStore"

import { useConversationStore } from "@/store/ConversationStore"

import { useSessionStore } from "@/store/SessionStore"

import { useWorkingContext } from "@/state/WorkingContextProvider"

import { useTransactionSession } from "@/state/TransactionSessionProvider"
import { useUiFeedback } from "@/store/UiFeedbackStore"
import type { ActiveSurfaceStack } from "@/types/nav"

import type { Student } from "@/types/student"

import type { Phase } from "@/types/transaction"

import {
  AudioLines,
  Archive,
  Bot,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  FileSpreadsheet,
  FileText,
  FolderOpen,
  Grid2X2,
  Image,
  LayoutList,
  LoaderCircle,
  Mic,
  MoreHorizontal,
  Paperclip,
  Plus,
  Search,
  Send,
  Settings,
  Sparkles,
  Users,
  WandSparkles,
  X,
  SlidersHorizontal,
  Table2,
  BedDouble,
  Network,
  Database,
  CalendarClock,
} from "lucide-react"

type Workspace = "conversation" | "dashboard" | "students" | "views" | "work" | "data" | "roster" | "spreadsheet" | "document" | "seat" | "dorm" | "group" | "inbox" | "automation" | "knowledge" | "reports" | "settings"

const labels: Record<Workspace, string> = {
  conversation: "对话",
  dashboard: "总览",
  students: "学生",
  views: "视图",
  work: "工作",
  data: "数据与内容",
  roster: "名单事务",
  spreadsheet: "表格",
  document: "文档",
  seat: "座位",
  dorm: "宿舍",
  group: "分组",
  inbox: "AI 待处理",
  automation: "自动化",
  knowledge: "知识库",
  reports: "报告与导出",
  settings: "设置",
}

const navItems: { label: string; target: Workspace; icon: typeof Grid2X2 }[] = [
  { label: "总览", target: "dashboard", icon: Grid2X2 },
  { label: "学生", target: "students", icon: Users },
  { label: "视图", target: "views", icon: LayoutList },
  { label: "工作", target: "work", icon: ClipboardList },
  { label: "数据与内容", target: "data", icon: Database },
  { label: "自动化", target: "automation", icon: CalendarClock },
  { label: "设置", target: "settings", icon: Settings },
]

const stacks: Record<Workspace, ActiveSurfaceStack> = {
  conversation: {
    domain: "conversation",
    rootSurfaceId: "HOME-CONVERSATION-IDLE",
    modeSurfaceIds: [],
    params: {},
  },
  dashboard: {
    domain: "dashboard",
    rootSurfaceId: "DASHBOARD-MAIN",
    modeSurfaceIds: [],
    params: {},
  },
  students: {
    domain: "students",
    rootSurfaceId: "STUDENT-LIST",
    viewSurfaceId: "VIEW-LIST",
    modeSurfaceIds: [],
    params: {},
  },
  views: {
    domain: "students",
    rootSurfaceId: "STUDENT-LIST",
    viewSurfaceId: "VIEW-TABLE",
    modeSurfaceIds: [],
    params: {},
  },
  work: {
    domain: "work",
    rootSurfaceId: "WORK-TASKS",
    modeSurfaceIds: [],
    params: {},
  },
  data: {
    domain: "data",
    rootSurfaceId: "DATA-FILES",
    modeSurfaceIds: [],
    params: {},
  },
  roster: {
    domain: "work",
    rootSurfaceId: "WORK-TRANSACTIONS",
    modeSurfaceIds: [],
    params: {},
  },
  spreadsheet: {
    domain: "data",
    rootSurfaceId: "SPREADSHEET-WORKSPACE",
    modeSurfaceIds: [],
    params: { fileId: "score-001" },
  },
  document: {
    domain: "data",
    rootSurfaceId: "DOCUMENT-WORKSPACE",
    modeSurfaceIds: [],
    params: { fileId: "parents-001" },
  },
  seat: {
    domain: "students",
    rootSurfaceId: "STUDENT-LIST",
    viewSurfaceId: "VIEW-SEAT",
    modeSurfaceIds: [],
    params: {},
  },
  dorm: {
    domain: "students",
    rootSurfaceId: "STUDENT-LIST",
    viewSurfaceId: "VIEW-DORM",
    modeSurfaceIds: [],
    params: {},
  },
  group: {
    domain: "students",
    rootSurfaceId: "STUDENT-LIST",
    viewSurfaceId: "VIEW-GROUP",
    modeSurfaceIds: [],
    params: {},
  },
  inbox: {
    domain: "inbox",
    rootSurfaceId: "REVIEW-INBOX",
    modeSurfaceIds: [],
    params: {},
  },
  automation: {
    domain: "automation",
    rootSurfaceId: "AUTOMATION-PLANS",
    modeSurfaceIds: [],
    params: {},
  },
  knowledge: {
    domain: "knowledge",
    rootSurfaceId: "KNOWLEDGE-LIBRARY",
    modeSurfaceIds: [],
    params: {},
  },
  reports: {
    domain: "reports",
    rootSurfaceId: "REPORTS-LIST",
    modeSurfaceIds: [],
    params: {},
  },
  settings: {
    domain: "settings",
    rootSurfaceId: "SETTINGS-USER-SECURITY",
    modeSurfaceIds: [],
    params: {},
  },
}

const stackForWorkspace = (workspace: Workspace) => stacks[workspace]
const workspaceByDomain: Record<ActiveSurfaceStack["domain"], Workspace> = {
  conversation: "conversation",
  dashboard: "dashboard",
  students: "students",
  work: "work",
  data: "data",
  inbox: "inbox",
  automation: "automation",
  knowledge: "knowledge",
  reports: "reports",
  settings: "settings",
}
const workspaceFromStack = (stack: ActiveSurfaceStack): Workspace =>
  stack.viewSurfaceId === "VIEW-SEAT"
    ? "seat"
    : stack.viewSurfaceId === "VIEW-DORM"
      ? "dorm"
      : stack.viewSurfaceId === "VIEW-GROUP"
        ? "group"
        : stack.rootSurfaceId === "SPREADSHEET-WORKSPACE"
          ? "spreadsheet"
          : stack.rootSurfaceId === "DOCUMENT-WORKSPACE"
            ? "document"
            : stack.rootSurfaceId === "WORK-TRANSACTIONS"
              ? "roster"
              : workspaceByDomain[stack.domain]
export const resolveActiveSurface = (stack: ActiveSurfaceStack) =>
  stack.modeSurfaceIds.at(-1) ||
  stack.viewSurfaceId ||
  stack.subpageSurfaceId ||
  stack.rootSurfaceId

function AppShell() {
  const { students } = useMockDomainStore()

  const { messagesByConversationId, appendMessage } = useConversationStore()

  const {
    activeSurfaceStack,
    navigate,
    activeConversationId,
    inspectorOpen,
    setInspectorOpen,
    mobileMoreOpen,
    setMobileMoreOpen,
  } = useSessionStore()

  const { activeStudentId, setActiveStudentId } = useWorkingContext()

  const {
    phase: transaction,
    setPhase: setTransaction,
    commitSeatSwap,
  } = useTransactionSession()

  const workspace = workspaceFromStack(activeSurfaceStack)

  const setWorkspace = (next: Workspace) => navigate(stackForWorkspace(next))

  const [conversationState, setConversationState] =
    useState<"idle" | "focus" | "active">("idle")

  const [input, setInput] = useState("")

  const messages = messagesByConversationId[activeConversationId] || []

  const setMessages = (
    next: { role: "user" | "assistant"; text: string; action?: boolean }[] | ((
      previous: { role: "user" | "assistant"; text: string; action?: boolean }[],
    ) => { role: "user" | "assistant"; text: string; action?: boolean }[]),
  ) => {
    const resolved = typeof next === "function" ? next(messages) : next

    resolved
      .slice(messages.length)
      .forEach((message) => appendMessage(activeConversationId, message))
  }

  const [voice, setVoice] =
    useState<"idle" | "recording" | "transcribing" | "draft">("idle")

  const [attachment, setAttachment] = useState<"image" | "file" | null>(null)

  const [noticeState, setNoticeState] =
    useState<"idle" | "candidate" | "mine" | "waiting" | "dismissed">("idle")

  const [noticeFeedback, setNoticeFeedback] = useState("")

  const committedSeats = Object.fromEntries(
    students.map((student) => [student.id, student.seat]),
  )

  const activeStudent = students.find((s) => s.id === activeStudentId)

  const activeStudentWithSeat = activeStudent

  function makeSeatDraft() {
    setTransaction("preview-ready")
    navigate({ ...stackForWorkspace("seat"), modeSurfaceIds: ["TX-PREVIEW"] })
    setInspectorOpen(true)
    setConversationState("active")

    setMessages((prev) => [
      ...prev,
      {
        role: "assistant",
        text: "已核对身份并生成座位调整草稿。两项变更尚未写入班级数据。",
        action: true,
      },
    ])
  }

  function sendMessage() {
    const value = input.trim()
    if (!value && !attachment && voice === "idle") return

    setConversationState("active")

    if (value) setMessages((prev) => [...prev, { role: "user", text: value }])

    setInput("")

    if (/换座|座位/.test(value)) makeSeatDraft()
    else {
      const route: [RegExp, Workspace, string][] = [
        [/名单|改名单/, "roster", "已为你打开名单事务，可先核对字段变更。"],
        [
          /Excel|表格文件|表格/,
          "spreadsheet",
          "已切换到表格工作区，文件将以候选数据方式解析。",
        ],
        [/Word|文档/, "document", "已切换到文档工作区，可在草稿中审阅改动。"],
        [/总体|概览/, "dashboard", "已打开班级总览。"],
        [/宿舍/, "dorm", "已打开宿舍视图。"],
        [/分组/, "group", "已打开分组画布。"],
      ]

      const found = route.find(([r]) => r.test(value))

      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text: found
            ? found[2]
            : "我会先将你的请求整理为候选操作，再由你确认是否应用。",
        },
      ])

      if (found) setWorkspace(found[1])
    }

    setAttachment(null)
  }

  function processSchoolNotice() {
    setConversationState("active")
    setNoticeState("candidate")
    setMessages((prev) => [
      ...prev,
      {
        role: "user",
        text: "【合成演示通知】请在演示截止时间前核对虚构清单；缺项可暂存为待确认事项。本通知不是学校指令，不包含真实学生信息，所有分流与确认仅演示交互。",
      },
      {
        role: "assistant",
        text: "已识别一项可能需要你负责的事项，并保留原始通知作为来源证据。",
      },
    ])
  }

  function commit() {
    setTransaction("confirming")
    navigate({ ...activeSurfaceStack, modeSurfaceIds: ["TX-CONFIRM"] })
  }

  function confirmCommit() {
    setTransaction("committing")

    commitSeatSwap()
  }

  const selectStudent = (id: string) => {
    setActiveStudentId(id)
    setInspectorOpen(true)
  }

  const openStudentDetail = (id: string) => {
    setActiveStudentId(id)
    setInspectorOpen(false)
    navigate({
      domain: "students",
      rootSurfaceId: "STUDENT-DETAIL-OVERVIEW",
      modeSurfaceIds: [],
      params: { studentId: id },
    })
  }

  return (
    <div className="app-shell">
      <Sidebar workspace={workspace} setWorkspace={setWorkspace} />
      <div className="shell-main">
        <TopBar
          workspace={workspace}
          transaction={transaction}
          inspectorOpen={inspectorOpen}
          onInspector={() => setInspectorOpen(!inspectorOpen)}
        />
        <div className="body-grid" data-inspector={inspectorOpen}>
          <main className="workspace">
            {workspace === "conversation" ? (
              <Conversation
                state={conversationState}
                setState={setConversationState}
                input={input}
                setInput={setInput}
                messages={messages}
                attachment={attachment}
                setAttachment={setAttachment}
                voice={voice}
                setVoice={setVoice}
                onSend={sendMessage}
                onSeat={makeSeatDraft}
                onOpenSeat={() => setWorkspace("seat")}
                noticeState={noticeState}
                noticeFeedback={noticeFeedback}
                onNotice={processSchoolNotice}
                onNoticeAction={(action: string) => {
                  setNoticeState(action as any)
                  setNoticeFeedback(
                    action === "mine"
                      ? "已加入「需要我处理」"
                      : action === "waiting"
                        ? "已交给班长收集信息；明天 16:00 前未完成会重新提醒你。"
                        : "已标记为不属于你的责任范围，这条通知不会继续占用你的当前注意力。",
                  )
                }}
              />
            ) : (
              <WorkspaceView
                workspace={workspace}
                setWorkspace={setWorkspace}
                activeStudentId={activeStudentId}
                selectStudent={selectStudent}
                transaction={transaction}
                seats={committedSeats}
                activeSurfaceStack={activeSurfaceStack}
                openStudentDetail={openStudentDetail}
              />
            )}
          </main>
          {inspectorOpen && (
            <Inspector
              activeStudent={activeStudentWithSeat}
              transaction={transaction}
              onSelect={selectStudent}
              onDiscard={() => setTransaction("discarded")}
              onCommit={commit}
              onConfirmCommit={confirmCommit}
              onCancelConfirm={() => setTransaction("preview-ready")}
              onUnknown={() => setTransaction("outcome-unknown")}
              onCheck={() => setTransaction("committed")}
            />
          )}
        </div>
      </div>
      <MobileNav
        workspace={workspace}
        setWorkspace={setWorkspace}
        moreOpen={mobileMoreOpen}
        setMoreOpen={setMobileMoreOpen}
      />
    </div>
  )
}

function Conversation({
  state,
  setState,
  input,
  setInput,
  messages,
  attachment,
  setAttachment,
  voice,
  setVoice,
  onSend,
  onSeat,
  onOpenSeat,
  noticeState,
  noticeFeedback,
  onNotice,
  onNoticeAction,
}: any) {
  const active = state === "active"

  return (
    <div className={`conversation ${state}`}>
      <div className="conversation-scroll">
      <div className="conversation-head">
        <p className="eyebrow">CLASSMATTER · 对话</p>
        <h1>{active ? "班级工作" : "今天想处理什么？"}</h1>
        <p>
          {active
            ? "对话中的操作会先生成候选或草稿，由你确认后再写入。"
            : "查询、记录、安排，或让 ClassMatter 帮你整理下一步。"}
        </p>
      </div>
      {!active && <Ambient compact={state === "focus"} />}{" "}
      {active && (
        <div className="collapsed-ambient">
          需要我处理 3 项 · 等待别人 2 项 · 可能遗漏 1 项{" "}
          <ChevronDown size={15} />
        </div>
      )}
      <div className="message-list">
        {messages.map((m: any, i: number) => (
          <div key={i} className={`message ${m.role}`}>
            <p>{m.text}</p>
            {m.action && (
              <div className="action-card">
                <div>
                  <span className="action-icon">
                    <Grid2X2 size={18} />
                  </span>
                  <div>
                    <strong>已生成座位调整草稿</strong>
                    <small>合成学生02 · 99002，与 合成学生05 · 99005</small>
                  </div>
                </div>
                <button onClick={onOpenSeat}>
                  查看调整 <ChevronRight size={16} />
                </button>
              </div>
            )}
          </div>
        ))}
        {noticeState !== "idle" && (
          <ResponsibilityCandidate
            state={noticeState}
            feedback={noticeFeedback}
            onAction={onNoticeAction}
          />
        )}
      </div>
      </div>
      <Composer
        input={input}
        setInput={setInput}
        attachment={attachment}
        setAttachment={setAttachment}
        voice={voice}
        setVoice={setVoice}
        onSend={onSend}
        onFocus={() => setState("focus")}
        onSeat={onSeat}
        onNotice={onNotice}
      />
    </div>
  )
}

function Ambient({ compact }: { compact: boolean }) {
  const { openDetail, notify } = useUiFeedback()
  const data = [
    [
      "需要我处理",
      [
        "合成清单信息最终核对 · 明天 17:00",
        "合成学生01迟到后续 · 今天 12:30",
        "合成返校跟进（未关联学生） · 已逾期",
      ],
    ],
    ["可能遗漏", ["合成通知频道 · 1 条通知尚未确认责任"]],
    ["等待别人", ["合成学生05家长 · 等待补充信息", "家长会回执 · 等待班长收集"]],
  ]
  return (
    <div className={`ambient ${compact ? "compact" : ""}`}>
      {data.map(([title, items]) => (
        <section key={title as string}>
          <p>{title}</p>
          {(items as string[]).slice(0, compact ? 1 : 3).map((x) => (
            <button
              key={x}
              onClick={() =>
                openDetail({
                  eyebrow: `注意力 · ${title}`,
                  title: x.split(" · ")[0],
                  description:
                    "打开后可以查看来源、责任判断和下一步，不会自动执行任何业务变更。",
                  status: x.split(" · ").slice(1).join(" · "),
                  sections: [
                    { label: "责任状态", value: title as string },
                    { label: "当前范围", value: "合成演示班" },
                    {
                      label: "来源",
                      value:
                        title === "可能遗漏" ? "合成通知频道" : "已确认记录",
                    },
                  ],
                  actions: [
                    {
                      label: "稍后提醒",
                      onSelect: () => notify("已设置稍后提醒"),
                    },
                    {
                      label: "开始处理",
                      tone: "primary",
                      onSelect: () => notify("已加入当前工作"),
                    },
                  ],
                })
              }
            >
              {x}
              <ChevronRight size={14} />
            </button>
          ))}
        </section>
      ))}
    </div>
  )
}

function ResponsibilityCandidate({ state, feedback, onAction }: any) {
  const { openDetail } = useUiFeedback()
  if (state === "dismissed")
    return (
      <div className="action-card">
        <p>{feedback}</p>
      </div>
    )
  if (state === "mine")
    return (
      <div className="action-card">
        <strong>合成清单信息最终核对</strong>
        <small>9月21日 17:00 · 已加入「需要我处理」</small>
        <p>{feedback}</p>
      </div>
    )
  if (state === "waiting")
    return (
      <div className="action-card">
        <strong>已交给班长收集信息</strong>
        <small>你仍负责最终核对与提交 · 明天 16:00 重新提醒</small>
        <p>{feedback}</p>
      </div>
    )
  return (
    <div className="action-card responsibility-card">
      <strong>识别到一项可能需要你负责的事项</strong>
      <small>学生合成清单信息核对 · 截止 9月21日 17:00</small>
      <p>来源：合成通知频道 · 今天 14:26</p>
      <p>
        你需要负责：最终核对 + 提交
        <br />
        可以转交：学生信息收集
        <br />
        当前缺口：2 名学生信息未齐
      </p>
      <div>
        <button className="primary" onClick={() => onAction("mine")}>
          加入需要我处理
        </button>
        <button onClick={() => onAction("waiting")}>先交给班长收集</button>
      </div>
      <div>
        <button onClick={() => onAction("dismissed")}>不是我的事</button>
        <button
          onClick={() =>
            openDetail({
              eyebrow: "原始通知 · 来源证据",
              title: "合成通知频道",
              description:
                "【合成演示通知】请在演示截止时间前核对虚构清单；缺项可暂存为待确认事项。本通知不是学校指令，不包含真实学生信息，所有分流与确认仅演示交互。",
              status: "今天 14:26 · 未修改原文",
              sections: [
                { label: "识别责任", value: "最终核对 + 提交" },
                { label: "可转交部分", value: "学生信息收集" },
                { label: "不确定性", value: "是否由班长收集需由你确认" },
              ],
              actions: [{ label: "关闭", tone: "primary" }],
            })
          }
        >
          查看原通知
        </button>
      </div>
    </div>
  )
}

function Composer({
  input,
  setInput,
  attachment,
  setAttachment,
  voice,
  setVoice,
  onSend,
  onFocus,
  onSeat,
  onNotice = () => {},
}: any) {
  const [addOpen, setAddOpen] = useState(false)
  const [modelOpen, setModelOpen] = useState(false)
  const [model, setModel] = useState("自动选择")
  const [dragging, setDragging] = useState(false)
  const [uploadedName, setUploadedName] = useState("")
  const [voiceWorkspaceOpen, setVoiceWorkspaceOpen] = useState(false)
  const imageInputRef = useRef<HTMLInputElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const dragDepth = useRef(0)

  const receiveFiles = (files: FileList | null) => {
    const file = files?.[0]
    if (!file) return
    setUploadedName(file.name)
    setAttachment(file.type.startsWith("image/") ? "image" : "file")
    onFocus()
  }

  const startTranscription = () => {
    setVoice("recording")
    setVoiceWorkspaceOpen(false)
    onFocus()
  }

  const models = ["自动选择", "GPT-5.6 Sol", "DeepSeek V4", "本地模型"]
  return (
    <div className="composer-wrap">
      <input
        ref={imageInputRef}
        className="sr-only"
        type="file"
        accept="image/*"
        tabIndex={-1}
        aria-hidden="true"
        onChange={(event) => receiveFiles(event.target.files)}
      />
      <input
        ref={fileInputRef}
        className="sr-only"
        type="file"
        tabIndex={-1}
        aria-hidden="true"
        onChange={(event) => receiveFiles(event.target.files)}
      />
      <div className="chips">
        <span>
          合成演示班 <X size={12} />
        </span>
        <span>
          2026–2027上学期 <X size={12} />
        </span>
        <button onClick={onSeat}>试试：把合成学生02和合成学生05换一下座位</button>
        <button onClick={onNotice}>处理这条班主任群通知</button>
      </div>
      {attachment && (
        <div className="attachment">
          <span>
            {attachment === "image" ? (
              <Image size={16} />
            ) : (
              <FileSpreadsheet size={16} />
            )}
          </span>
          <div>
            <strong>
              {uploadedName ||
                (attachment === "image"
                  ? "课堂板书.jpg"
                  : "合成演示班9月成绩.xlsx")}
            </strong>
            <small>
              {attachment === "image"
                ? "图片候选 · 待确认后处理"
                : "文件候选 · 待确认后处理"}
            </small>
          </div>
          <button
            aria-label="移除附件"
            onClick={() => {
              setAttachment(null)
              setUploadedName("")
            }}
          >
            <X size={15} />
          </button>
        </div>
      )}
      {voice !== "idle" && (
        <div className="voice-state">
          <Mic size={16} />
          {voice === "recording" ? (
            <>
              <span className="wave">▁▃▅▂▆▃▂</span>
              <strong>00:08</strong>
              <button
                onClick={() => {
                  setVoice("transcribing")
                  window.setTimeout(() => {
                    setVoice("draft")
                    setInput("请提醒合成学生05今天补交数学作业")
                  }, 700)
                }}
              >
                停止
              </button>
            </>
          ) : voice === "transcribing" ? (
            <>
              <span>正在转写为可编辑草稿…</span>
              <LoaderCircle className="spin" size={16} />
            </>
          ) : (
            <>
              <span>转写草稿已放入输入框 · 请检查后发送</span>
              <button onClick={() => setVoice("idle")}>删除</button>
            </>
          )}
        </div>
      )}
      {voiceWorkspaceOpen && (
        <div className="voice-workspace-panel" role="dialog" aria-label="语音工作区">
          <div>
            <span className="voice-orb"><AudioLines size={18} /></span>
            <div>
              <strong>语音工作区</strong>
              <small>前端交互演示 · 当前不会保存或上传音频</small>
            </div>
            <button
              className="panel-close"
              aria-label="关闭语音工作区"
              onClick={() => setVoiceWorkspaceOpen(false)}
            >
              <X size={15} />
            </button>
          </div>
          <p>开始后可预览“录音 → 转写草稿 → 人工确认”的完整状态。</p>
          <button className="voice-start" onClick={startTranscription}>
            <Mic size={15} /> 开始转写演示
          </button>
        </div>
      )}
      {addOpen && (
        <div className="composer-menu add-menu">
          <button
            onClick={() => {
              imageInputRef.current?.click()
              setAddOpen(false)
            }}
          >
            <Image size={16} />
            添加图片
          </button>
          <button
            onClick={() => {
              fileInputRef.current?.click()
              setAddOpen(false)
            }}
          >
            <Paperclip size={16} />
            添加文件
          </button>
          <button
            onClick={() => {
              onNotice()
              setAddOpen(false)
            }}
          >
            <ClipboardList size={16} />
            粘贴学校通知
          </button>
        </div>
      )}
      {modelOpen && (
        <div className="model-menu" role="menu" aria-label="选择模型">
          <p>本次对话模型</p>
          {models.map((name) => (
            <button
              key={name}
              role="menuitem"
              onClick={() => {
                setModel(name)
                setModelOpen(false)
              }}
            >
              <span>
                <strong>{name}</strong>
                <small>
                  {name === "自动选择"
                    ? "按任务选择已配置模型"
                    : name === "本地模型"
                      ? "未连接 · 仅展示入口"
                      : "当前会话展示选项"}
                </small>
              </span>
              {model === name && <Check size={15} />}
            </button>
          ))}
        </div>
      )}
      <div
        className={`composer ${dragging ? "dragging" : ""}`}
        onDragEnter={(event) => {
          event.preventDefault()
          dragDepth.current += 1
          setDragging(true)
        }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={(event) => {
          event.preventDefault()
          dragDepth.current -= 1
          if (dragDepth.current <= 0) {
            dragDepth.current = 0
            setDragging(false)
          }
        }}
        onDrop={(event) => {
          event.preventDefault()
          dragDepth.current = 0
          setDragging(false)
          receiveFiles(event.dataTransfer.files)
        }}
      >
        {dragging && (
          <div className="composer-drop-overlay">
            <Paperclip size={20} />
            松开以添加图片或文件
          </div>
        )}
        <textarea
          value={input}
          rows={2}
          onFocus={onFocus}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault()
              onSend()
            }
          }}
          placeholder="输入、查询、记录或安排班级工作……"
        />
        <div className="composer-footer">
          <div className="compose-tools">
          <button
            aria-label="添加内容"
            aria-expanded={addOpen}
            onClick={() => {
              setAddOpen(!addOpen)
              setModelOpen(false)
            }}
          >
            <Plus size={19} />
          </button>
          <span className="tool-policy">受控工具</span>
          </div>
          <div className="composer-actions">
            <button
              className="model-switch"
              aria-expanded={modelOpen}
              onClick={() => {
                setModelOpen(!modelOpen)
                setAddOpen(false)
              }}
            >
              {model} <ChevronDown size={14} />
            </button>
          <button
            onClick={startTranscription}
            aria-label="语音转文字"
            title="语音转文字"
          >
            <Mic size={18} />
          </button>
            {input.trim() || attachment ? (
              <button className="send" onClick={onSend} aria-label="发送">
                <Send size={17} />
              </button>
            ) : (
              <button
                className="voice-workspace-trigger"
                aria-label="打开语音工作区"
                title="语音工作区"
                onClick={() => {
                  setVoiceWorkspaceOpen(!voiceWorkspaceOpen)
                  setAddOpen(false)
                  setModelOpen(false)
                }}
              >
                <AudioLines size={18} />
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

function WorkspaceView({
  workspace,
  setWorkspace,
  activeStudentId,
  selectStudent,
  transaction,
  seats,
  activeSurfaceStack,
  openStudentDetail,
}: any) {
  if (workspace === "seat")
    return (
      <SeatWorkspace
        activeStudentId={activeStudentId}
        selectStudent={selectStudent}
        transaction={transaction}
        seats={seats}
      />
    )

  if (
    workspace === "students" &&
    activeSurfaceStack.rootSurfaceId === "STUDENT-DETAIL-OVERVIEW"
  )
    return (
      <StudentDetailWorkspace
        studentId={activeSurfaceStack.params.studentId}
        activeTab={activeSurfaceStack.subpageSurfaceId}
        onBack={() => setWorkspace("students")}
      />
    )

  if (workspace === "students" || workspace === "views")
    return (
      <StudentWorkspace
        title={workspace === "views" ? "视图" : "学生"}
        activeStudentId={activeStudentId}
        selectStudent={selectStudent}
        openStudentDetail={openStudentDetail}
        transaction={transaction}
        seats={seats}
      />
    )

  if (workspace === "settings") return <SettingsWorkspace />

  if (workspace === "dashboard") return <DashboardWorkspace />

  if (workspace === "work")
    return (
      <WorkWorkspace
        transaction={transaction}
        onSeat={() => setWorkspace("seat")}
      />
    )

  if (workspace === "data") return <DataWorkspace setWorkspace={setWorkspace} />

  if (workspace === "spreadsheet") return <SpreadsheetWorkspace />

  if (workspace === "document") return <DocumentWorkspace />

  if (workspace === "dorm")
    return (
      <DormWorkspace
        activeStudentId={activeStudentId}
        selectStudent={selectStudent}
      />
    )

  if (workspace === "group")
    return (
      <GroupWorkspace
        activeStudentId={activeStudentId}
        selectStudent={selectStudent}
      />
    )

  if (workspace === "inbox") return <InboxWorkspace />

  if (workspace === "automation") return <AutomationWorkspace />

  if (workspace === "knowledge") return <KnowledgeWorkspace />

  if (workspace === "reports") return <ReportsWorkspace />

  return (
    <WorkspaceShell
      title="名单事务"
      description="从名单中发起字段调整；所有变更先进入草稿。"
      icon={LayoutList}
    >
      <TablePreview
        selectStudent={selectStudent}
        activeStudentId={activeStudentId}
        seats={seats}
      />
    </WorkspaceShell>
  )
}

function WorkspaceShell({ title, description, icon: Icon, children }: any) {
  return (
    <div className="surface">
      <div className="surface-title">
        <span className="surface-icon">
          <Icon size={22} />
        </span>
        <div>
          <p className="eyebrow">工作空间</p>
          <h1>{title}</h1>
          <p>{description}</p>
        </div>
      </div>
      {children}
    </div>
  )
}

function DashboardWorkspace() {
  const [editing, setEditing] = useState(false)
  const [range, setRange] = useState("今天")
  const [hidden, setHidden] = useState<string[]>([])
  const { openDetail, notify } = useUiFeedback()
  const cards = [
    ["需要我处理", "3 项", "合成学生01迟到后续 · 今天 12:30"],
    ["48h 内截止", "2 项", "家长会材料、合成清单信息核对"],
    ["等待别人", "6 项", "班长、家长与学生信息补充"],
    ["可能遗漏", "1 项", "班主任群通知尚未确认责任"],
    ["请假 / 缺勤", "1 人", "赵一诺 · 已请假"],
    ["作业待跟进", "4 项", "数学补交 · 截止今日"],
    ["学生近期动态", "3 条", "合成学生02 · 座位草稿"],
    ["成绩摘要", "待导入", "9月成绩表已识别"],
    ["AI 待处理", "7 条", "候选记录等待核对"],
    ["自动化运行", "正常", "2 条提醒将在今天执行"],
    ["最近文件", "3 份", "家长会方案 · 草稿"],
    ["班级位置", "已同步", "座位 / 宿舍 / 小队"],
    ["最近活动", "刚刚", "创建了座位调整草稿"],
  ]
  const visible = cards.filter(([title]) => !hidden.includes(title))
  return (
    <WorkspaceShell
      title="班级总览"
      description="按时间和工作优先级查看班级运行状态。"
      icon={Grid2X2}
    >
      <div className="dash-toolbar">
        <div>
          {["今天", "本周", "本学期"].map((x) => (
            <button
              className={range === x ? "active" : ""}
              onClick={() => setRange(x)}
              key={x}
            >
              {x}
            </button>
          ))}
        </div>
        <button
          className="primary"
          onClick={() => {
            setEditing(!editing)
            if (editing) notify("总览布局已保存到当前设备")
          }}
        >
          {editing ? "完成编辑" : "编辑总览"}
        </button>
      </div>
      {hidden.length > 0 && editing && (
        <button className="restore-widgets" onClick={() => setHidden([])}>
          恢复已隐藏的 {hidden.length} 个组件
        </button>
      )}
      <div className="widget-grid">
        {visible.map(([title, value, detail]) => (
          <article className="widget" key={title}>
            <div>
              <span>{title}</span>
              {editing && (
                <button
                  aria-label={`隐藏${title}`}
                  onClick={() => setHidden([...hidden, title])}
                >
                  <X size={14} />
                </button>
              )}
            </div>
            <strong>{value}</strong>
            <p>{detail}</p>
            <button
              onClick={() =>
                openDetail({
                  eyebrow: `班级总览 · ${range}`,
                  title,
                  description: detail,
                  status: "数据来自当前班级范围；最后更新于刚刚",
                  sections: [
                    { label: "当前状态", value },
                    { label: "时间范围", value: range },
                    {
                      label: "下一步",
                      value: title.includes("遗漏")
                        ? "确认责任归属"
                        : "查看相关记录并决定是否处理",
                    },
                  ],
                  timeline: [
                    "系统汇总了当前范围内的相关记录",
                    "尚未执行任何业务写入",
                  ],
                  actions: [{ label: "知道了", tone: "primary" }],
                })
              }
            >
              查看 <ChevronRight size={14} />
            </button>
          </article>
        ))}
      </div>
    </WorkspaceShell>
  )
}
function WorkWorkspace({ onSeat }: any) {
  const [tab, setTab] = useState("需要我处理")
  const [completed, setCompleted] = useState<string[]>([])
  const { openDetail, notify } = useUiFeedback()
  const rows =
    tab === "等待别人"
      ? [
          ["合成清单信息收集", "等待：班长", "明天 16:00 检查"],
          ["合成学生05家庭信息补充", "等待：合成学生05家长", "等待"],
        ]
      : tab === "即将截止"
        ? [
            ["家长会材料提交", "18 小时", "即将截止"],
            ["学生合成清单名单", "1 天 3 小时", "即将截止"],
          ]
        : tab === "已闭环"
          ? [["学生保险名单", "36 / 36 已核对", "有留痕"]]
          : [
              ["合成清单信息最终核对", "明天 17:00", "班主任群"],
              ["合成学生01迟到后续", "今天 12:30", "课堂记录"],
              ["合成返校跟进（未关联学生）", "已逾期", "需要跟进"],
            ]
  const open = (row: string[]) =>
    openDetail({
      eyebrow: `工作 · ${tab}`,
      title: row[0],
      description:
        "此事项按注意力状态管理。系统保留来源、责任判断与每次处理记录。",
      status: completed.includes(row[0])
        ? "已闭环 · 保留审计留痕"
        : `${row[2]} · 尚未修改正式数据`,
      sections: [
        { label: "时限 / 等待", value: row[1] },
        { label: "来源", value: row[2] },
        {
          label: "责任",
          value:
            tab === "等待别人"
              ? "你负责最终确认；当前动作由他人完成"
              : "等待班主任确认",
        },
      ],
      timeline: [
        "来源被加入当前工作空间",
        "系统生成注意力候选",
        "等待你的确认或转交",
      ],
      actions: [
        { label: "稍后提醒", onSelect: () => notify("已设置明天 09:00 提醒") },
        {
          label: "标记完成",
          tone: "primary",
          onSelect: () => {
            setCompleted([...completed, row[0]])
            notify("事项已闭环并保留处理记录")
          },
        },
      ],
    })
  return (
    <WorkspaceShell
      title="工作"
      description="按注意力状态组织，帮助你以最低必要注意力控制责任风险。"
      icon={ClipboardList}
    >
      <div className="tabbar">
        {["需要我处理", "等待别人", "即将截止", "已闭环", "全部"].map((x) => (
          <button
            key={x}
            className={tab === x ? "active" : ""}
            onClick={() => setTab(x)}
          >
            {x}
          </button>
        ))}
      </div>
      <div className="work-list">
        {rows.map((row) => (
          <button
            key={row[0]}
            onClick={() => (row[0] === "座位调整" ? onSeat() : open(row))}
          >
            <strong>{row[0]}</strong>
            <span>{row[1]}</span>
            <em>{completed.includes(row[0]) ? "已闭环" : row[2]}</em>
            <ChevronRight size={16} />
          </button>
        ))}
      </div>
    </WorkspaceShell>
  )
}
function DataWorkspace({ setWorkspace }: any) {
  const [tab, setTab] = useState("文件")
  const { openDetail, notify } = useUiFeedback()
  const data = {
    文件: ["合成演示班9月成绩.xlsx", "家长会方案.docx", "课堂板书.jpg"],
    表格: ["9月成绩汇总", "作业跟进表", "学生清单"],
    文档: ["家长会方案", "班会材料", "周报草稿"],
    "图片 / OCR": ["课堂板书.jpg", "请假条.png"],
    采集: ["语音转写草稿", "图片候选", "文件解析队列"],
    最近内容: ["座位调整预览", "9月成绩导入"],
  }
  const openItem = (item: string, i: number) => {
    if (item.includes("成绩")) {
      setWorkspace("spreadsheet")
      return
    }
    if (item.includes("方案")) {
      setWorkspace("document")
      return
    }
    openDetail({
      eyebrow: `数据与内容 · ${tab}`,
      title: item,
      description:
        "原始内容与 AI 提取结果分开保存；候选内容不会自动成为正式业务事实。",
      status: i === 0 ? "候选 · 等待人工核对" : "已更新",
      sections: [
        { label: "范围", value: "合成演示班 · 2026–2027上学期" },
        { label: "来源", value: tab },
        {
          label: "处理方式",
          value:
            item.includes("OCR") || item.includes("图片")
              ? "OCR 候选提取"
              : "本地前端演示数据",
        },
      ],
      actions: [
        { label: "延后处理", onSelect: () => notify("已移入稍后处理") },
        {
          label: "标记已核对",
          tone: "primary",
          onSelect: () => notify("已记录核对结果"),
        },
      ],
    })
  }
  return (
    <WorkspaceShell
      title="数据与内容"
      description="所有文件、来源与候选内容都先在这里整理和核对。"
      icon={Database}
    >
      <div className="tabbar">
        {Object.keys(data).map((x) => (
          <button
            key={x}
            className={tab === x ? "active" : ""}
            onClick={() => setTab(x)}
          >
            {x}
          </button>
        ))}
      </div>
      <div className="content-list">
        {data[(tab as keyof typeof data)].map((item, i) => (
          <button key={item} onClick={() => openItem(item, i)}>
            <FileText size={18} />
            <span>
              <strong>{item}</strong>
              <small>
                {tab} · 合成演示班 · {i === 0 ? "候选，待确认" : "已更新"}
              </small>
            </span>
            <MoreHorizontal size={18} />
          </button>
        ))}
      </div>
    </WorkspaceShell>
  )
}
function SpreadsheetWorkspace() {
  const [sheet, setSheet] = useState("成绩汇总")
  const [selected, setSelected] = useState("C3")
  const [menu, setMenu] = useState(false)
  const { openDetail, notify, requestConfirm } = useUiFeedback()
  const showMapping = () =>
    openDetail({
      eyebrow: "表格导入 · 字段映射",
      title: "确认字段映射",
      description: "只有通过验证并明确确认的行才会形成导入提案。",
      status: "2 项需要处理",
      sections: [
        { label: "姓名", value: "源列 A → 学生姓名" },
        { label: "数学", value: "源列 C → 数学成绩" },
        { label: "空白值", value: "按缺考候选处理，需人工确认" },
      ],
      actions: [
        { label: "返回表格" },
        {
          label: "保存映射",
          tone: "primary",
          onSelect: () => notify("字段映射已保存为导入草稿"),
        },
      ],
    })
  const showIssues = () =>
    openDetail({
      eyebrow: "表格导入 · 校验",
      title: "发现 2 项待确认问题",
      description: "问题不会被静默修复。你可以逐项确认后再继续。",
      sections: [
        { label: "合成学生05 · 数学", value: "源文件内容为“缺考”" },
        { label: "第 36 行", value: "学号为空，已跳过" },
      ],
      actions: [
        {
          label: "回到对应单元格",
          tone: "primary",
          onSelect: () => setSelected("C4"),
        },
      ],
    })
  return (
    <WorkspaceShell
      title="表格"
      description="合成演示班9月成绩.xlsx · 导入候选，尚未写入正式成绩。"
      icon={FileSpreadsheet}
    >
      <div className="sheet-tools">
        <div className="compact-menu">
          <button onClick={() => setMenu(!menu)}>
            {sheet} <ChevronDown size={14} />
          </button>
          {menu && (
            <div className="floating-menu">
              {["成绩汇总", "原始数据", "导入问题"].map((item) => (
                <button
                  key={item}
                  onClick={() => {
                    setSheet(item)
                    setMenu(false)
                  }}
                >
                  {item}
                </button>
              ))}
            </div>
          )}
        </div>
        <button onClick={showMapping}>字段映射</button>
        <button onClick={showIssues}>验证 2 项</button>
      </div>
      <div className="formula">
        <span>{selected}</span>
        <input
          value={
            selected === "C3" ? "92" : selected === "C4" ? "缺考" : "合成学生02"
          }
          readOnly
        />
      </div>
      <div className="sheet rich-sheet">
        {Array.from({ length: 9 }).map((_, r) => (
          <div className="sheet-row" key={r}>
            {Array.from({ length: 7 }).map((_, c) => {
              const value =
                r === 0
                  ? "" + String.fromCharCode(64 + c)
                  : c === 0
                    ? String(r)
                    : r === 1
                      ? ["姓名", "语文", "数学", "英语", "总分", "备注"][c - 1]
                      : r === 2
                        ? ["合成学生01", "88", "90", "86", "264", ""][c - 1]
                        : r === 3
                          ? ["合成学生02", "91", "92", "89", "272", ""][c - 1]
                          : r === 4
                            ? ["合成学生05", "75", "缺考", "78", "153", "待确认"][
                                c - 1
                              ]
                            : ""
              const cell = `${String.fromCharCode(64 + c)}${r}`
              return (
                <button
                  key={c}
                  className={selected === cell ? "selected-cell" : ""}
                  onClick={() => setSelected(cell)}
                >
                  {value}
                </button>
              )
            })}
          </div>
        ))}
      </div>
      <div className="import-summary">
        <strong>导入预览</strong>
        <span>导入 34 行 · 跳过 2 行 · 空白按缺考处理</span>
        <button
          className="primary"
          onClick={() =>
            requestConfirm({
              title: "确认生成成绩导入提案？",
              description: "这一步只生成可审阅 Diff，不会写入正式成绩。",
              confirmLabel: "生成 Diff",
              onConfirm: () => {
                notify("已生成成绩导入 Diff")
                showMapping()
              },
            })
          }
        >
          查看 Diff
        </button>
      </div>
    </WorkspaceShell>
  )
}
function DocumentWorkspace() {
  const [mode, setMode] = useState("修改后")
  const [section, setSection] = useState("会议目标")
  const { openDetail, notify } = useUiFeedback()
  return (
    <WorkspaceShell
      title="文档"
      description="家长会方案 · 所有修改都保留来源、版本与可审阅 Diff。"
      icon={FileText}
    >
      <div className="document-layout">
        <aside>
          <strong>文档结构</strong>
          {["会议目标", "到场安排", "家校沟通", "最后三项安排"].map((x) => (
            <button
              key={x}
              className={section === x ? "selected-outline" : ""}
              onClick={() => setSection(x)}
            >
              {x}
            </button>
          ))}
        </aside>
        <article>
          <div className="doc-tabs">
            {["原文", "修改后", "修订记录"].map((x) => (
              <button
                key={x}
                className={mode === x ? "active" : ""}
                onClick={() => setMode(x)}
              >
                {x}
              </button>
            ))}
          </div>
          <h2>合成演示班家长会方案</h2>
          <p className="document-anchor">当前章节：{section}</p>
          <p>本次家长会将围绕学生适应、学习习惯与家校协作展开。</p>
          <p className={mode === "原文" ? "" : "tracked"}>
            {mode === "原文"
              ? "会议流程包含班级情况、学科汇报、分组沟通、问答及后续安排。"
              : mode === "修订记录"
                ? "版本 3：删除重复的学科汇报环节，保留最后三项安排。"
                : "会议流程精简为班级情况、分组沟通及最后三项安排。"}
          </p>
          <h3>最后三项安排</h3>
          <ol>
            <li>确认学习资料领取</li>
            <li>填写沟通回执</li>
            <li>预约后续个别交流</li>
          </ol>
          <button
            className="document-save"
            onClick={() => notify("文档修改已保存为草稿版本 4")}
          >
            保存草稿
          </button>
        </article>
        <aside>
          <strong>评论与来源</strong>
          <button
            onClick={() =>
              openDetail({
                eyebrow: "文档评论",
                title: "合成教师",
                description: "保留最后三项安排，方便家长会结束前再次确认。",
                actions: [
                  {
                    label: "回复",
                    tone: "primary",
                    onSelect: () => notify("回复已保存为草稿"),
                  },
                ],
              })
            }
          >
            合成教师：保留最后三项安排
          </button>
          <button
            onClick={() =>
              openDetail({
                eyebrow: "来源证据",
                title: "班会材料 · 9月3日",
                description: "当前段落引用自班会材料，引用关系可追溯。",
                status: "来源完整",
              })
            }
          >
            来源：班会材料 · 9月3日
          </button>
          <button onClick={() => setMode("修订记录")}>
            版本 3 · 可审阅草稿
          </button>
        </aside>
      </div>
    </WorkspaceShell>
  )
}
function DormWorkspace({ activeStudentId, selectStudent }: any) {
  const { students } = useMockDomainStore()
  const [building, setBuilding] = useState("1号楼")
  const [floor, setFloor] = useState("3层")
  const [filter, setFilter] = useState(false)
  const { notify } = useUiFeedback()
  const rooms = [
    ["302寝", ["合成学生01", "合成学生02", "合成学生06"]],
    ["303寝", ["合成学生05", "合成学生03", "空床位"]],
    ["304寝", ["合成学生04", "合成学生07", "合成学生08"]],
  ]
  return (
    <WorkspaceShell
      title="宿舍"
      description={`${building} · ${floor} · 同一学生身份可在座位和小队中持续定位。`}
      icon={BedDouble}
    >
      <div className="dorm-tools">
        <button
          onClick={() => setBuilding(building === "1号楼" ? "2号楼" : "1号楼")}
        >
          {building} <ChevronDown size={14} />
        </button>
        <button onClick={() => setFloor(floor === "3层" ? "4层" : "3层")}>
          {floor} <ChevronDown size={14} />
        </button>
        <button
          className={filter ? "active" : ""}
          onClick={() => setFilter(!filter)}
        >
          仅看有空位
        </button>
        <button onClick={() => notify("宿舍调整将先生成预览草稿")}>
          发起调整
        </button>
      </div>
      <div className="room-grid">
        {rooms
          .filter(([room]) => !filter || room === "303寝")
          .map(([room, names]) => (
            <section key={room as string}>
              <strong>{room}</strong>
              {(names as string[]).map((name) => {
                const s = students.find((x) => x.name === name)
                return (
                  <button
                    key={name}
                    className={s?.id === activeStudentId ? "selected" : ""}
                    onClick={() =>
                      s
                        ? selectStudent(s.id)
                        : notify("已选择空床位；请再选择一名学生生成调整草稿")
                    }
                  >
                    {s ? (
                      <>
                        <span className="avatar">{s.name[0]}</span>
                        {s.name}
                        <small>{s.id}</small>
                      </>
                    ) : (
                      "空床位"
                    )}
                  </button>
                )
              })}
            </section>
          ))}
      </div>
    </WorkspaceShell>
  )
}
function GroupWorkspace({ activeStudentId, selectStudent }: any) {
  const { students } = useMockDomainStore()
  const [editing, setEditing] = useState(false)
  const [layout, setLayout] = useState("按小队")
  const { notify, requestConfirm } = useUiFeedback()
  const groups: [string, Student[]][] = [
    ["晨星小队", students.slice(0, 2)],
    ["远航小队", students.slice(2, 5)],
    ["探索小队", students.slice(5, 7)],
    ["待分组", students.slice(7)],
  ]
  return (
    <WorkspaceShell
      title="小队与画布"
      description="拖动前先形成分组草稿；当前内容只作为共享身份投影。"
      icon={Network}
    >
      <div className="group-tools">
        <button
          onClick={() => setLayout(layout === "按小队" ? "自由画布" : "按小队")}
        >
          {layout}
        </button>
        <button
          className={editing ? "active" : ""}
          onClick={() => setEditing(!editing)}
        >
          {editing ? "退出编辑" : "编辑布局"}
        </button>
        <button
          onClick={() =>
            requestConfirm({
              title: "生成自动分组候选？",
              description: "系统将按人数均衡生成候选，不会覆盖当前分组。",
              confirmLabel: "生成候选",
              onConfirm: () => notify("已生成 4 个均衡分组候选"),
            })
          }
        >
          自动排布
        </button>
        <button onClick={() => notify("当前视图已保存")}>保存视图</button>
      </div>
      <div className={`group-board ${editing ? "is-editing" : ""}`}>
        {groups.map(([name, members]) => (
          <section key={name}>
            <strong>{name}</strong>
            {members.map((s) => (
              <button
                key={s.id}
                className={s.id === activeStudentId ? "selected" : ""}
                onClick={() => selectStudent(s.id)}
              >
                <span className="avatar">{s.name[0]}</span>
                {s.name}
                <small>{s.id}</small>
              </button>
            ))}
          </section>
        ))}
      </div>
    </WorkspaceShell>
  )
}
function InboxWorkspace() {
  const [items, setItems] = useState([
    "课堂板书中的作业要求",
    "合成学生01迟到记录",
    "合成学生05数学作业未交",
  ])
  const [deferred, setDeferred] = useState<string[]>([])
  const { openDetail, notify, requestConfirm } = useUiFeedback()
  const act = (action: string, item: string, i: number) => {
    if (action === "查看来源")
      openDetail({
        eyebrow: "AI 候选 · 来源",
        title: item,
        description:
          "原始图片与提取文本并列展示。AI 结果只作为候选，不会自动晋升为正式事实。",
        status: `置信度 ${i === 0 ? "92%" : "88%"} · 普通敏感度`,
        sections: [
          { label: "来源", value: "课堂板书.jpg · 今天 10:18" },
          { label: "班级", value: "合成演示班" },
          { label: "提取结果", value: "等待班主任核对后生成草稿" },
        ],
        actions: [
          { label: "编辑候选" },
          {
            label: "接受为草稿",
            tone: "primary",
            onSelect: () => notify("已生成可审阅草稿，尚未写入正式数据"),
          },
        ],
      })
    else if (action === "编辑")
      openDetail({
        eyebrow: "编辑候选",
        title: item,
        description: "编辑后的内容仍然是草稿，需要在 Preview 中再次确认。",
        actions: [
          {
            label: "保存编辑",
            tone: "primary",
            onSelect: () => notify("候选编辑已保存"),
          },
        ],
      })
    else if (action === "接受")
      requestConfirm({
        title: "接受这条 AI 候选？",
        description: "接受后只生成业务草稿，仍需在预览页确认后才能提交。",
        confirmLabel: "接受为草稿",
        onConfirm: () => {
          setItems(items.filter((x) => x !== item))
          notify("已生成草稿并移出 AI 待处理")
        },
      })
    else if (action === "拒绝") {
      setItems(items.filter((x) => x !== item))
      notify("候选已拒绝；原始来源仍按保留策略保存")
    } else {
      setDeferred([...deferred, item])
      notify("已延后到明天 09:00")
    }
  }
  return (
    <WorkspaceShell
      title="AI 待处理"
      description="候选内容仅供审核；接受后仍须进入 Preview Before Commit。"
      icon={Bot}
    >
      {items.length === 0 ? (
        <div className="empty-state">
          <Bot size={26} />
          <strong>候选已经处理完了</strong>
          <p>新的图片、文件或语音候选会出现在这里。</p>
        </div>
      ) : (
        <div className="review-list">
          {items.map((item, i) => (
            <article
              key={item}
              className={deferred.includes(item) ? "deferred" : ""}
            >
              <span className="surface-icon">
                <Sparkles size={17} />
              </span>
              <div>
                <strong>{item}</strong>
                <p>
                  图片采集 · 合成演示班 · 置信度 {i === 0 ? "92%" : "88%"} ·
                  普通敏感度
                </p>
                <small>
                  {deferred.includes(item)
                    ? "已延后到明天 09:00"
                    : "提取内容：等待班主任核对后生成草稿。"}
                </small>
              </div>
              <div>
                {["查看来源", "编辑", "接受", "拒绝", "延后"].map((action) => (
                  <button key={action} onClick={() => act(action, item, i)}>
                    {action}
                  </button>
                ))}
              </div>
            </article>
          ))}
        </div>
      )}
    </WorkspaceShell>
  )
}
function AutomationWorkspace() {
  const [tab, setTab] = useState("计划")
  const [enabled, setEnabled] = useState<string[]>([
    "午休前确认迟到后续",
    "作业补交提醒",
  ])
  const { openDetail, notify } = useUiFeedback()
  const all = [
    ["午休前确认迟到后续", "今日 12:30", "已开启"],
    ["作业补交提醒", "今日 16:00", "已开启"],
    ["每周五班级周报草稿", "本周五 17:00", "等待"],
    ["导入校验", "最近运行失败", "查看结果"],
  ]
  const rows =
    tab === "触发器"
      ? [
          ["工作日 12:30", "任务仍未闭环", "触发检查"],
          ["每日 16:00", "存在作业补交", "触发草稿"],
        ]
      : tab === "运行记录"
        ? [
            ["迟到后续检查", "今天 12:30", "成功 · 无写入"],
            ["导入校验", "昨天 18:04", "失败 · 已停止"],
          ]
        : all
  return (
    <WorkspaceShell
      title="自动化"
      description="自动化先展示范围与行为，再在运行记录中保留可追溯结果。"
      icon={CalendarClock}
    >
      <div className="tabbar">
        {["计划", "触发器", "运行记录"].map((x) => (
          <button
            key={x}
            className={tab === x ? "active" : ""}
            onClick={() => setTab(x)}
          >
            {x}
          </button>
        ))}
      </div>
      <div className="work-list">
        {rows.map((row) => (
          <button
            key={row[0]}
            onClick={() =>
              openDetail({
                eyebrow: `自动化 · ${tab}`,
                title: row[0],
                description:
                  "该自动化只会生成提醒或草稿，不会绕过确认执行正式业务写入。",
                status: enabled.includes(row[0]) ? "已开启" : "等待 / 只读",
                sections: [
                  { label: "计划", value: row[1] },
                  { label: "结果", value: row[2] },
                  { label: "写入边界", value: "无直接写入权限" },
                ],
                timeline: [
                  "检查触发条件",
                  "生成候选结果",
                  "等待人工处理或记录只读结果",
                ],
                actions:
                  tab === "计划"
                    ? [
                        {
                          label: enabled.includes(row[0])
                            ? "暂停计划"
                            : "启用计划",
                          tone: "primary",
                          onSelect: () => {
                            setEnabled(
                              enabled.includes(row[0])
                                ? enabled.filter((x) => x !== row[0])
                                : [...enabled, row[0]],
                            )
                            notify(
                              enabled.includes(row[0])
                                ? "计划已暂停"
                                : "计划已启用",
                            )
                          },
                        },
                      ]
                    : [{ label: "关闭", tone: "primary" }],
              })
            }
          >
            <strong>{row[0]}</strong>
            <span>{row[1]}</span>
            <em>{enabled.includes(row[0]) ? "已开启" : row[2]}</em>
            <ChevronRight size={16} />
          </button>
        ))}
      </div>
    </WorkspaceShell>
  )
}
function KnowledgeWorkspace() {
  const [query, setQuery] = useState("")
  const { openDetail } = useUiFeedback()
  const entries = [
    ["学校规章", "德育处 · 9月1日"],
    ["班级制度", "合成演示班 · 已更新"],
    ["教师个人资料", "班主任偏好 · 私有"],
    ["模板", "家长会、班会、周报"],
    ["已索引文件", "12 份 · 可引用"],
  ].filter(([a, b]) => (a + b).includes(query))
  return (
    <WorkspaceShell
      title="知识库"
      description="知识与正式学生事实分离；对话引用会保留来源。"
      icon={Archive}
    >
      <div className="library-toolbar">
        <label>
          <SearchIcon />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="搜索规章、模板和来源"
          />
        </label>
        <button
          className="primary"
          onClick={() =>
            openDetail({
              eyebrow: "知识库",
              title: "添加知识来源",
              description:
                "当前演示仅展示接入流程。文件会先经过权限、范围和版本检查。",
              sections: [
                { label: "支持内容", value: "规章、模板、教师个人资料" },
                { label: "事实边界", value: "知识内容不会替代学生业务事实" },
              ],
              actions: [{ label: "知道了", tone: "primary" }],
            })
          }
        >
          添加来源
        </button>
      </div>
      {entries.length === 0 ? (
        <div className="empty-state">
          <Archive size={26} />
          <strong>没有找到相关内容</strong>
          <p>尝试搜索其他关键词。</p>
        </div>
      ) : (
        <div className="knowledge-grid">
          {entries.map(([a, b]) => (
            <button
              key={a}
              onClick={() =>
                openDetail({
                  eyebrow: "知识条目",
                  title: a,
                  description: "知识内容按版本保存，Agent 引用时必须附带来源。",
                  status: b,
                  sections: [
                    {
                      label: "可见范围",
                      value: a === "教师个人资料" ? "仅当前教师" : "合成演示班",
                    },
                    { label: "最近更新", value: "2026年9月19日" },
                    { label: "业务事实", value: "否 · 仅作为知识参考" },
                  ],
                  actions: [{ label: "查看引用位置", tone: "primary" }],
                })
              }
            >
              <strong>{a}</strong>
              <span>{b}</span>
              <ChevronRight size={16} />
            </button>
          ))}
        </div>
      )}
    </WorkspaceShell>
  )
}
function SearchIcon() {
  return <Search size={16} />
}
function ReportsWorkspace() {
  const { openDetail, notify, requestConfirm } = useUiFeedback()
  const items = [
    "班级工作周报",
    "学生阶段记录汇总",
    "家长会材料",
    "班会材料",
    "数据退出包",
  ]
  const openReport = (item: string, mode: string) => {
    if (item === "数据退出包" && mode === "导出") {
      requestConfirm({
        title: "确认导出数据退出包？",
        description:
          "退出包将包含当前班级可导出的结构化数据、来源和版本清单。此演示不会真的下载文件。",
        confirmLabel: "确认生成",
        onConfirm: () => notify("数据退出包已生成，可在最近内容中查看"),
      })
      return
    }
    openDetail({
      eyebrow: `报告与导出 · ${mode}`,
      title: item,
      description:
        mode === "编辑"
          ? "编辑结果会保存为 Artifact Draft，不会修改底层业务事实。"
          : "基于已授权数据生成的可审阅材料。",
      status: item === "数据退出包" ? "需要强确认" : "Artifact Draft · 版本 1",
      sections: [
        { label: "范围", value: "合成演示班 · 当前学期" },
        { label: "来源", value: "任务、事件与已确认记录" },
        {
          label: "格式",
          value: item.includes("材料") ? "DOCX / PDF" : "PDF / XLSX",
        },
      ],
      actions:
        mode === "来源"
          ? [{ label: "关闭", tone: "primary" }]
          : [
              { label: "保存草稿", onSelect: () => notify("报告草稿已保存") },
              {
                label: mode === "编辑" ? "完成编辑" : "导出",
                tone: "primary",
                onSelect: () => notify("已生成演示导出记录"),
              },
            ],
    })
  }
  return (
    <WorkspaceShell
      title="报告与导出"
      description="报告将先生成 Artifact Draft；数据退出包需要单独确认。"
      icon={FolderOpen}
    >
      <div className="report-list">
        {items.map((item) => (
          <article key={item}>
            <div>
              <strong>{item}</strong>
              <span>
                {item === "数据退出包"
                  ? "强确认后导出"
                  : "Artifact Draft · 版本 1"}
              </span>
            </div>
            <div>
              {["预览", "来源", "编辑", "导出"].map((action) => (
                <button key={action} onClick={() => openReport(item, action)}>
                  {action}
                </button>
              ))}
            </div>
          </article>
        ))}
      </div>
    </WorkspaceShell>
  )
}

function StudentDetailWorkspace({ studentId, activeTab, onBack }: any) {
  const { students } = useMockDomainStore()
  const { navigate } = useSessionStore()
  const { notify, openDetail } = useUiFeedback()
  const student = students.find((item) => item.id === studentId) || students[0]
  const tabs = [
    ["概览", undefined],
    ["时间线", "STUDENT-DETAIL-TIMELINE"],
    ["任务", "STUDENT-DETAIL-TASKS"],
    ["记录", "STUDENT-DETAIL-RECORDS"],
    ["成绩", "STUDENT-DETAIL-GRADES"],
    ["文件", "STUDENT-DETAIL-FILES"],
    ["关系", "STUDENT-DETAIL-RELATIONS"],
  ] as const
  const current = tabs.find(([, id]) => id === activeTab)?.[0] || "概览"
  const selectTab = (id: typeof tabs[number][1]) =>
    navigate({
      domain: "students",
      rootSurfaceId: "STUDENT-DETAIL-OVERVIEW",
      subpageSurfaceId: id,
      modeSurfaceIds: [],
      params: { studentId: student.id },
    })
  const content: Record<string, [string, string][]> = {
    概览: [
      ["当前座位", student.seat],
      ["宿舍", "1号楼 302寝"],
      ["小队", "晨星小队"],
      ["近期关注", "1 项待跟进 · 2 项已闭环"],
    ],
    时间线: [
      ["9月19日", "课堂表现记录 · 教师确认"],
      ["9月16日", "家长沟通已闭环"],
      ["9月12日", "座位信息已核对"],
    ],
    任务: [
      ["需要跟进", "数学作业补交 · 今天 16:00"],
      ["已完成", "合成清单信息核对 · 9月18日"],
    ],
    记录: [
      ["课堂", "积极参与小组讨论 · 有来源"],
      ["沟通", "与家长确认近期作息 · 已闭环"],
    ],
    成绩: [
      ["9月月考", "总分 272 · 班级第 8"],
      ["变化", "较上次 +12 分"],
    ],
    文件: [
      ["请假材料", "1 份 · 已核对"],
      ["沟通附件", "2 份 · 仅授权角色可见"],
    ],
    关系: [
      ["监护人", "2 位 · 联系信息受保护"],
      ["任课教师", "8 位"],
      ["小组成员", "5 位"],
    ],
  }
  return (
    <div className="surface student-detail-page">
      <button className="back-link" onClick={onBack}>
        <ChevronLeft size={16} /> 返回学生列表
      </button>
      <header className="student-profile-head">
        <span className="profile-avatar">{student.name[0]}</span>
        <div>
          <p className="eyebrow">学生详情 · 已确认事实</p>
          <h1>{student.name}</h1>
          <p>{student.id} · 合成演示班 · 在读</p>
        </div>
        <button
          className="primary"
          onClick={() => notify(`已为${student.name}创建记录草稿`)}
        >
          添加记录
        </button>
      </header>
      <div className="view-switcher" role="tablist" aria-label="学生详情栏目">
        {tabs.map(([label, id]) => (
          <button
            role="tab"
            aria-selected={current === label}
            className={current === label ? "active" : ""}
            onClick={() => selectTab(id)}
            key={label}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="student-detail-grid">
        <section>
          <p className="eyebrow">{current}</p>
          <h2>{current === "概览" ? "当前情况" : `${current}记录`}</h2>
          <div className="profile-records">
            {content[current].map(([label, value]) => (
              <button
                key={label}
                onClick={() =>
                  openDetail({
                    eyebrow: `${student.name} · ${current}`,
                    title: label,
                    description: value,
                    status: "来源与修改记录可追溯",
                    actions: [{ label: "关闭", tone: "primary" }],
                  })
                }
              >
                <span>{label}</span>
                <strong>{value}</strong>
                <ChevronRight size={16} />
              </button>
            ))}
          </div>
        </section>
        <aside>
          <p className="eyebrow">数据边界</p>
          <strong>事实、观察与推断分开显示</strong>
          <p>
            此页面只把已确认内容作为人物事实。AI 推断必须保留来源并等待确认。
          </p>
        </aside>
      </div>
    </div>
  )
}

function StudentWorkspace({
  title,
  activeStudentId,
  selectStudent,
  openStudentDetail,
  transaction,
  seats,
}: any) {
  const [view, setView] = useState("清单")
  const views = ["清单", "表格", "座位", "宿舍", "小队", "画布"]
  return (
    <div className="surface student-surface">
      <div className="surface-title">
        <span className="surface-icon">
          <Users size={22} />
        </span>
        <div>
          <p className="eyebrow">共享实体 · 多视图</p>
          <h1>{title}</h1>
          <p>同一学生、范围、筛选与选中状态在所有视图中持续保留。</p>
        </div>
      </div>
      <div className="view-switcher" role="tablist" aria-label="学生视图切换">
        {views.map((item) => (
          <button
            role="tab"
            aria-selected={view === item}
            className={view === item ? "active" : ""}
            onClick={() => setView(item)}
            key={item}
          >
            {item}
          </button>
        ))}
      </div>
      {view === "清单" || view === "表格" ? (
        <TablePreview
          selectStudent={openStudentDetail}
          activeStudentId={activeStudentId}
        />
      ) : view === "座位" ? (
        <SeatWorkspace
          embedded
          activeStudentId={activeStudentId}
          selectStudent={selectStudent}
          transaction={transaction}
          seats={seats}
        />
      ) : (
        <RepresentativeContent workspace={view === "宿舍" ? "dorm" : "group"} />
      )}
    </div>
  )
}

function RepresentativeContent({ workspace }: { workspace: Workspace }) {
  const { openDetail } = useUiFeedback()
  const content: Record<string, [string, string, string[]]> = {
    dashboard: [
      "今天",
      "需要班主任关注的节奏",
      ["3 项待办", "1 项逾期", "2 条待核记录"],
    ],
    work: [
      "待处理工作",
      "所有正式动作先停留在草稿与预览层",
      ["座位调整草稿", "班会准备", "家校沟通记录"],
    ],
    data: [
      "内容库",
      "文件与文档以来源、状态和范围组织",
      [
        "合成演示班9月成绩.xlsx · 解析中",
        "班会通知 · 可审阅草稿",
        "课堂板书.jpg · 候选",
      ],
    ],
    dorm: [
      "宿舍安排",
      "按楼层、寝室和学生身份查看",
      ["1号楼 · 302寝", "3名学生已核对", "寝室调整需确认"],
    ],
    group: [
      "小队协作",
      "六个小队共享同一班级身份集合",
      ["晨星小队 · 6人", "远航小队 · 5人", "待分组 · 2人"],
    ],
    inbox: [
      "待处理候选",
      "所有内容都等待人工核对",
      ["考勤识别 · 待确认", "作业记录 · 待核对", "语音转写 · 草稿"],
    ],
    automation: [
      "自动化",
      "提醒与触发器均可在运行前审阅",
      [
        "午休前迟到跟进 · 今日 12:30",
        "作业补交提醒 · 今日 16:00",
        "周报汇总 · 每周五",
      ],
    ],
  }
  const [heading, caption, items] = content[workspace] || content.work
  return (
    <div className="representative">
      <div>
        <p className="eyebrow">{heading}</p>
        <strong>{caption}</strong>
      </div>
      {items.map((item) => (
        <button
          key={item}
          onClick={() =>
            openDetail({
              eyebrow: heading,
              title: item.split(" · ")[0],
              description: caption,
              status: item.split(" · ").slice(1).join(" · ") || "当前视图",
              actions: [{ label: "关闭", tone: "primary" }],
            })
          }
        >
          {item}
          <ChevronRight size={16} />
        </button>
      ))}
    </div>
  )
}

function TablePreview({ selectStudent, activeStudentId }: any) {
  const { students } = useMockDomainStore()
  return (
    <div className="data-table">
      <div className="table-head">
        <span>学生</span>
        <span>学号</span>
        <span>座位</span>
        <span>状态</span>
      </div>
      {students.map((s) => (
        <button
          key={s.id}
          onClick={() => selectStudent(s.id)}
          className={
            activeStudentId === s.id ? "table-row selected" : "table-row"
          }
        >
          <span>
            <i className="avatar">{s.name[0]}</i>
            {s.name}
          </span>
          <span>{s.id}</span>
          <span>{s.seat}</span>
          <span>
            <b>在读</b>
          </span>
        </button>
      ))}
    </div>
  )
}
function GridPreview() {
  return (
    <div className="sheet">
      <div className="sheet-bar">
        成绩汇总 <span>映射：待确认</span>
      </div>
      {Array.from({ length: 6 }).map((_, r) => (
        <div className="sheet-row" key={r}>
          {Array.from({ length: 6 }).map((_, c) => (
            <span key={c}>
              {r === 0
                ? String.fromCharCode(65 + c)
                : c === 0
                  ? r
                  : r === 1
                    ? ["合成学生02", "语文", "数学", "英语", "总分"][c - 1] || ""
                    : ""}
            </span>
          ))}
        </div>
      ))}
    </div>
  )
}

function SeatWorkspace({
  activeStudentId,
  selectStudent,
  transaction,
  seats,
}: any) {
  const { students } = useMockDomainStore()
  const pending =
    transaction && !["committed", "discarded"].includes(transaction)
  const isAfter = transaction === "committed"
  const shown = (s: Student) => (isAfter ? seats[s.id] || s.seat : s.seat)
  return (
    <div className="seat-workspace">
      <div className="seat-header">
        <div>
          <p className="eyebrow">多视图 · 共享身份</p>
          <h1>座位</h1>
          <p>
            {pending
              ? "预览草稿：以下调整尚未写入正式座位表。"
              : "按当前班级座位表查看学生。"}
          </p>
        </div>
        {pending && <span className="preview-tag">预览模式 · 2 项待确认</span>}
      </div>
      {pending && (
        <div className="seat-diff-summary">
          <span>调整前</span>
          <ChevronRight size={16} />
          <strong>调整后</strong>
          <span>合成学生02：3排2座 → 2排4座　合成学生05：2排4座 → 3排2座</span>
        </div>
      )}
      <div className="seat-grid">
        {[1, 2, 3, 4, 5, 6].map((row) => (
          <div className="seat-row" key={row}>
            {[1, 2, 3, 4, 5, 6].map((col) => {
              const original = students.find(
                (s) => s.seat === `${row}排${col}座`,
              )
              let person = original
              if (pending || isAfter) {
                if (row === 2 && col === 4) person = students[1]
                if (row === 3 && col === 2) person = students[4]
              }
              const changed =
                person &&
                ["99002", "99005"].includes(person.id) &&
                (pending || isAfter)
              return (
                <button
                  key={col}
                  onClick={() => person && selectStudent(person.id)}
                  className={`${
                    person?.id === activeStudentId ? "seat selected" : "seat"
                  } ${changed ? "changed" : ""}`}
                >
                  <small>
                    {row}排{col}座
                  </small>
                  {person ? (
                    <>
                      <strong>{person.name}</strong>
                      <span>{person.id}</span>
                    </>
                  ) : (
                    <em>空</em>
                  )}
                </button>
              )
            })}
          </div>
        ))}
      </div>
    </div>
  )
}

function SettingsWorkspace() {
  const [section, setSection] = useState("模型与 API")
  const [connection, setConnection] = useState("未测试")
  const sections = [
    "用户与安全",
    "外观",
    "ClassMatter",
    "模型与 API",
    "Capture",
    "自动化",
    "集成",
    "隐私与安全",
    "数据",
    "无障碍",
  ]
  return (
    <div className="settings-page">
      <div className="settings-side">
        <p className="eyebrow">设置</p>
        {sections.map((x) => (
          <button
            key={x}
            className={section === x ? "active" : ""}
            onClick={() => setSection(x)}
          >
            {x}
          </button>
        ))}
      </div>
      <div className="settings-main">
        <p className="eyebrow">设置 / {section}</p>
        <h1>{section}</h1>
        {section === "模型与 API" ? (
          <>
            <p>为 ClassMatter 配置内置或自定义模型 Provider。</p>
            <div className="provider-card">
              <div>
                <span className="surface-icon">
                  <WandSparkles size={19} />
                </span>
                <strong>自定义 API</strong>
                <small>
                  测试连接状态：{connection} · 密钥仅作为本地配置草稿。
                </small>
              </div>
              <button onClick={() => setConnection("连接正常")}>
                测试连接
              </button>
            </div>
            <form className="api-form">
              {[
                ["Provider 名称", "例如：学校模型网关"],
                ["API Base URL", "https://api.example.com/v1"],
                ["API Key", "••••••••••••••••"],
                ["Model ID", "class-os-teacher"],
                ["Adapter 类型", "OpenAI Compatible"],
                ["Custom Headers", "X-Organization: yq-experimental"],
                ["Timeout", "60 秒"],
                ["Context limit", "128,000 tokens"],
              ].map(([label, placeholder]) => (
                <label key={label}>
                  {label}
                  <input placeholder={placeholder} />
                </label>
              ))}
            </form>
            <div className="capabilities">
              <p className="inspect-label">能力</p>
              {["Text", "Vision", "File", "Audio"].map((x) => (
                <label key={x}>
                  <input type="checkbox" defaultChecked={x !== "Audio"} />
                  {x}
                </label>
              ))}
            </div>
            <div className="api-shell">
              <section>
                <strong>工具调用</strong>
                <span>已允许</span>
              </section>
              <section>
                <strong>结构化输出</strong>
                <span>JSON Schema</span>
              </section>
              <section>
                <strong>模型路由</strong>
                <span>课堂任务默认模型</span>
              </section>
              <section>
                <strong>数据策略</strong>
                <span>仅发送已授权上下文</span>
              </section>
              <section>
                <strong>处理方</strong>
                <span>自定义 Provider</span>
              </section>
              <section>
                <strong>允许的数据级别</strong>
                <span>班级范围 · 候选内容</span>
              </section>
            </div>
          </>
        ) : (
          <SettingsSection section={section} />
        )}
      </div>
    </div>
  )
}

function SettingsSection({ section }: { section: string }) {
  const items: Record<string, string[]> = {
    用户与安全: ["用户资料", "登录与安全", "设备", "恢复码", "当前会话"],
    外观: ["浅色 / 深色 / 跟随系统", "UI 密度", "字号", "Sidebar 行为", "动效"],
    "ClassMatter": [
      "当前学校",
      "班级",
      "学期",
      "默认工作区",
      "默认学生视图",
      "Event / Task 默认规则",
    ],
    Capture: ["图片", "文件", "OCR", "语音", "Channel"],
    自动化: ["默认行为", "确认策略", "通知策略"],
    集成: ["MCP", "Drive", "Calendar", "微信", "外部学校系统"],
    隐私与安全: ["数据级别", "Retention", "Audit", "Provider Policy"],
    数据: ["Import", "Export", "Backup", "Migration"],
    无障碍: ["字号", "对比度", "Reduce Motion", "Keyboard"],
  }
  const [enabled, setEnabled] = useState<string[]>([])
  return (
    <div className="settings-controls">
      {(items[section] || []).map((item) => (
        <section key={item}>
          <div>
            <strong>{item}</strong>
            <span>使用当前班级的默认 mock 配置</span>
          </div>
          <button
            className={enabled.includes(item) ? "on" : ""}
            onClick={() =>
              setEnabled(
                enabled.includes(item)
                  ? enabled.filter((x) => x !== item)
                  : [...enabled, item],
              )
            }
            aria-label={`切换${item}`}
          >
            <i />
          </button>
        </section>
      ))}
    </div>
  )
}

export default AppShell
