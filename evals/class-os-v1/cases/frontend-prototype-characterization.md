# Frontend Prototype Characterization

状态：repository foundation regression checklist；不属于当前 `.ai/gates/release-1-evals.yaml` required membership，不表示业务 eval 已绿。

基线：`已冻结的 React/TypeScript UX 基线@（公开版不携带私有来源标识）`

## FP-CHAR-001 Build

- setup：Node 22；从 lockfile 安装依赖。
- runner：在 `apps/web` 依次运行 `pnpm typecheck`、`pnpm build`。
- oracle：两者 exit code 0；生成 `apps/web/dist`；无 TypeScript/Vite build error。

## FP-CHAR-002 Attention-first labels

- setup：使用仓库内合成数据启动 Web。
- action：进入默认工作台/注意力视图。
- oracle：用户能看到并区分“需要我处理”“等待别人”“可能遗漏”，没有把三者压成同一待办列表。

## FP-CHAR-003 Responsibility Candidate remains a candidate

- action：从学校通知或对话演示入口进入责任判断流程。
- oracle：界面表达候选/待判断状态；用户尚未确认时，不显示已写入正式事实或已对外发送。

## FP-CHAR-004 Preview before commit

- action：触发具有业务变更含义的演示 flow。
- oracle：先展示 proposal/preview，再出现明确提交动作；取消后工作上下文可继续，不假装已经完成。

## FP-CHAR-005 One data world / multiple views

- action：从对话、工作台和结构化 surface 查看同一合成对象。
- oracle：对象标识和状态语义一致；视图差异不制造第二份业务事实。

## FP-CHAR-006 Responsive navigation

- setup：桌面与手机 viewport。
- oracle：桌面侧栏/顶部工具和手机导航可达；关键处理动作不因 viewport 丢失。

## FP-CHAR-007 No dead core controls

- action：遍历一级导航、主要列表项、总览卡片和核心 CTA。
- oracle：控制应进入页面、详情、确认、状态变化或明确反馈；核心动线不保留无响应按钮。

## FP-CHAR-008 Deep-linkable student detail

- action：从学生列表进入详情，并切换概览、时间线、任务、记录、成绩、文件和关系。
- oracle：URL 可直接恢复学生身份与栏目；浏览器前进/后退不会回到错误对象。

## FP-CHAR-009 Synthetic flow closure

- action：分别运行学校通知责任判断、座位预览提交和表格导入 Diff 演示。
- oracle：每条动线都有来源/候选、人工判断、预览或确认、结果反馈；不得伪装成真实后端写入。

## FP-CHAR-010 Visual shell separation

- setup：桌面浅色模式。
- oracle：主工作区为白色；左侧导航使用极浅莫兰迪色；层级不依赖高饱和大色块；移动端不因隐藏侧栏而丢失主要导航。

## FP-CHAR-011 Fixed conversation composer

- setup：分别使用桌面与手机 viewport，并准备可滚动的长对话内容。
- action：进入空白对话、发送消息、滚动对话内容并聚焦输入框。
- oracle：输入区始终固定在对话工作区最下方；消息与注意力内容在独立区域滚动，不推动输入区离开视口；手机端输入区不被底部导航遮挡；空白态和进行中对话使用同一位置契约。

## FP-CHAR-012 Attention lanes use the available canvas

- setup：桌面 viewport，进入空白对话页。
- action：查看“需要我处理”“可能遗漏”“等待别人”三列，并增加足以产生多行的合成事项。
- oracle：三列之间有清晰但不过度的留白；每列可自然向下增长，不使用截断高度；内容区可以延伸到输入区上方，同时保留可辨识的安全间距；新增事项不会覆盖输入区。

## FP-CHAR-013 Multimodal composer contract

- setup：进入空白或进行中对话。
- action：依次打开加号菜单、图片选择、文件选择、模型菜单、语音转写和语音工作区；将图片或文件拖入输入区域。
- oracle：所有入口均有可见状态或反馈；拖入内容只形成待确认附件候选；模型选择只改变当前会话的展示状态；语音操作明确标为前端演示，不声称已经取得麦克风权限、完成真实转写、上传或后端调用；键盘发送和输入焦点仍可用。

## Gate use

这些检查用于防止迁仓和工程清理破坏冻结 UX。它们不能替代 `E-*` 业务、安全、可用性或 Net Burden eval；要升级为 release required eval，必须走正式 change 与 machine definition approval。
