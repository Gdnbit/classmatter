# 教师工具生态与 Policy Intelligence Agent：ClassMatter 专用工具与政策主动感知研究

> **2026-10-23 · Discovery / Future · 公开来源研究稿，不是正式产品需求或发布承诺。**
> 仅讨论面向中国初中班主任/任课教师的候选能力、第三方工具与公开政策来源。无真实学校、教师、学生、家庭、客户材料；不改变冻结 R1、正式权限、R1 Agent 只读/草稿或真实数据准入。文内项目能力依据项目作者 README；尚未做代码安全、许可证兼容或端到端部署验收。
> 关联：[个人工作画像、自学习 Skill 与教师工具体系](../product/2026-10-23-personal-working-profile-and-adaptive-agent.md) · [持续工作](../product/agent-owned-work-and-attention.md) · [规则依据层级](../product/legal-evidence-and-rule-hierarchy.md) · [长期需求](../specs/class-os-v1/long-term-requirements.md)。

## 1. 研究要解决什么

老师不仅需要记录/闭环学生和班级事务，也需要完成备课、PPT、题库、组卷、批改、总结、通知、模板填报等重复产物工作。上述领域工具最好由 ClassMatter AI 工作入口按需编排，可依据经确认的个人偏好与可复用 Skill 运行，产物经教师审核后留存来源与版本，而非若干无法协作的独立工具菜单。

此外，教师在学校及教育行政规则约束下工作：法律、行政法规、部门规范/指导、地方政策、学校正式制度、岗位职责及临时通知可能变化。**Policy Intelligence Agent** 候选工作为：合法来源发现 → 原文留证 → 生效/效力核验 → 新旧比对 → 范围匹配 → 影响/行动建议 → 分级通知 → 可选生成待办/文书草稿 → 人审、纠错和追踪。不是以 AI 宣告法律结论，也不是替学校发布制度。

## 2. 候选工具与开源项目：先借鉴再决定复用

| 项目及官方仓库 | 研究价值 | 边界与验证任务 |
|---|---|---|
| [Claw-ED](https://github.com/SirhanMacx/Claw-ED) | local-first 教学助理；读取已有 PDF/DOCX/PPTX 等形成教学风格画像、制作教案和可编辑 PPTX | 作者标 Beta；核对上游许可、模型连接/真实资料外传、中文教材、版权、实际文档保真 |
| [Rumi Platform](https://github.com/Orenda-Project/rumi-platform) / [官方介绍](https://hellorumi.ai/open-source) | 教师任务生态：教案、测验、出勤、作业、阅读评估、考试检查 | 其 WhatsApp 主入口不宜直接移植到中国学校；研究其场景/插件式能力边界 |
| [Presenton](https://github.com/presenton/presenton) | 可自托管生成 PPT/可编辑 PPTX、可用 API | 评测版式、中文字体、图表、源文档、模板和导出稳定性 |
| [PPT Master](https://github.com/tomoro-ai/ppt-master-tomoro) | Agent 驱动的原生可编辑 PPTX 与模板复用；最贴近「生成材料 Skill」 | 不默认加载未审计 Shell/依赖；校验真实性和第三方素材许可 |
| [EduGraderAI](https://github.com/wangchunyang888/EduGraderAI) | OCR/规则评分/低置信度转教师/发布前确认的分层批改工作流 | 作者描述为 demo；评分公正性、隐私、笔迹/OCR 与生产适用性均需单独验收 |
| [SmartKBS](https://github.com/youufis/SmartKBS) | 题库、组卷、任务、学情分析和教师端 AI 组合参考 | 比较领域模型而不是直接复制完整学校管理后端 |
| [question-bank-assistant](https://github.com/HelloTheWorld12138/question-bank-assistant) | 本地教师题库及组卷范式（公开仓库简介为高中物理） | 先核对许可证、数学公式/插图支持、导出格式和安装可靠性 |
| [taotao-skills](https://github.com/ichangting/taotao-skills) | 一线初中教师的备课、教研、分层教学 Skill 编排 | 借鉴任务和 Skill 合同，不假定跨学科、跨学校规则可直接泛化 |
| [hermes-edu-skills](https://github.com/hezkvectory/hermes-edu-skills) | 中文教育 Skill 目录与可发现、参数化的 SKILL.md | 审核来源、实际工具调用、运行时依赖和潜在权限，不能把 170 个 Skill 等同可直接交付 |
| [Docling](https://github.com/docling-project/docling) | 布局/表格/公式文档解析，为题库和政策 PDF 提供候选文本 | 与 OCR 结果均需回到原文/页面坐标核对，不默认推断正式事实 |

**选型默认**：先以 teacher task/outcome 和权限/数据边界定义 Tool Port，优先重用经过评估的专用工具（PPT/文档/OCR/题库组件），避免功能被某一个 SaaS、Agent Runtime 或前端捆绑。真正复用代码前必须做 License/SBOM/网络与凭据/版权/隐私/维护活跃度审计。

## 3. Policy Intelligence Agent：不是 RAG 问答，而是带版本的政策变更监测

### 3.1 信息源层级与来源可信度

首批原始渠道（按实际覆盖能力和链接有效性配置，不臆测 RSS、API 或完整覆盖）：

- 国家法律法规、国务院/中国政府网：[中国政府网](https://www.gov.cn/)；教育部正式文件与政策解读：[教育部](https://www.moe.gov.cn/)；
- 湖南省：[湖南省教育厅](https://jyt.hunan.gov.cn/) 与 [规范性文件](https://jyt.hunan.gov.cn/sjyt/xxgk/zcfg/gfxwj/)（目录具有文号、发文日期、效力状态）；省人大地方性法规、省政府政策文件；
- 长沙：[长沙市教育局](https://jyj.changsha.gov.cn/) 及市政府正式发布渠道；
- 宁乡：[宁乡市人民政府](https://www.nxcity.gov.cn/) 中教育局及政策/公告栏目，须单独验证可用路径；
- 学校：只有经明确授权上传/接入的正式学校规章、工作通知、岗位安排、发文附件等。群聊转发/非官方解读作为待核验线索，不可直接认定正式文件。

**政策 ≠ 通知 ≠ 新闻 ≠ 征求意见稿 ≠ 学校安排。** 原始发文机关、文件类型、文号、适用日期、修订/废止关系与地域/主体范围必须分别存储。正式政策目录展示为「有效」也不证明对某一个人、某一学期立即适用。

### 3.2 个人适用性画像（与班主任工作画像分离）

只需最低必要的配置：任教地区、学段、岗位（班主任/任课教师/其他）、公办或民办、教师资格及职称阶段（仅在本人愿意提供时）、所关注的政策主题、提醒强度、已授权校内资料范围。

Policy Applicability = 文件对地域/主体/学校类型/学段/时间/岗位/职责的具体适用判断与依据；它**不能**仅靠向量相似度、关键词匹配或模型自报置信度。条件不全时输出「可能相关，尚需确认」，不认定教师已经符合职称、补贴或工作义务。

区分主题：
- **职业权益/机会**：职称、培训、资格认定、评优评先、公费定向服务协议（只有用户明确说明适用时才监测个人合同）、可能的待遇与申报窗口；
- **工作责任/风险**：学生安全、未成年人保护、心理健康/转介、请假/寄宿、家校沟通、教学与考核规范；
- **事务动作**：新发布校内通知、报表、期限、教学材料/课程标准更新。
- 每类可设置「要实时/要周报/不提醒」；不把政策监测变成全天政策新闻推送。

### 3.3 事件管道（候选）

```text
Trusted Source Registry（官网源清单 / 所属机关 / 采集方式）
  → RSS/API/结构化列表采集，或页面变化检测
  → Source Snapshot（URL、官方机关、抓取时间、原始 HTML/PDF/附件、内容哈希）
  → Parsed Document（文号、类型、发/公布/实施/失效日期、地域、主体、条款定位）
  → Deduplicate & Version / Amendment Graph（转载去重、修订/废止、替代、未确认缺口）
  → Provenance-backed Policy Retrieval + Rule Matching
  → Policy Change / Applicability Candidate
  → Human-readable Impact Memo（改变了什么、为什么相关、何时生效、是否需要行动、引用）
  → Attention Rules（紧急提醒 / 每日周报 / 仅归档）
  → Teacher Review → 可选 Task/Calendar/文书草稿，绝不静默正式派责或自动外发
```

建议公共政策快照作为**跨用户共享、独立更新**的 Policy Corpus；各教师仅持有隐私隔离的 Policy Subscription、适用性配置、阅读状态与个人行动事项。这样不必每位用户各运行一个爬虫和全量独立大模型 Agent。

公开页面监测候选： [changedetection.io](https://github.com/dgtlmoon/changedetection.io) 可监控政府公告网页变化并通知/触发 webhook；[RSSHub](https://github.com/DIYgod/RSSHub) 可将适配站点转为 RSS。但**应先核对官方 RSS/API，遵循 robots、站点使用规则与限速**；RSSHub 的 AGPL-3.0 及后续组合部署许可需单独评估；工具检测到网页 HTML 变更并不等于产生法律政策变动。

### 3.4 通知体验与行动边界

**高优先提醒**：明确适用于当前岗位/地区且即将生效、涉及可验证的义务变更或本人已关注且存在真实截止日；包含原文、影响条款、适用条件、需确认项、截止日性质。优先审查，不自动生成/发送正式通知。

**普通更新**：已生效的解释、工作流程微调、非急迫机会 → 每日/每周聚合。

**归档或待核验**：教育新闻、不同地区、征求意见稿、无明确适用性/原始来源不完整 → 不打扰或以低置信度标注供自查。

引入持续工作 Agent 时，应只为已确定的合法、低风险且获得授权的动作创建 Work Item；学生安全等急迫事件遵循学校线下预案；政策情报不能替代学校行政正式发布与律师/主管部门解释。

**示例提醒（历史文件，非当日新政）**：
> 湖南省中小学教师职称评价规则变化；湖南省教育厅站点2026-08-19转载的湖南日报报道提到新办法2026-09-01起实施。可能涉及班主任年限、代表作与课堂教学要求。[官方站点转载报道](https://jyt.hunan.gov.cn/jyt/sjyt/hnzxxjsfzzx/jsfzzxxwdt/202608/t20260819_34047335.html)。该页面不是办法原文，不能单独核定规范内容、效力或个人适用性；是否适用于本人申报、任教年限如何核算、岗位材料是否满足，仍须核验原始办法和实施细则，不生成已符合的结论。

### 3.5 结构合同候选

```text
PolicySource {id, issuing_body, official_origin_url, jurisdiction, source_type, refresh_policy, health_state}
PolicyDocument {id, canonical_url, source_snapshot_ref, document_no, authority, doc_type,
 published_at, issued_at, effective_from, effective_until, validity_status, scope, version, replaces_refs}
PolicyChange {old_version_ref, new_version_ref, clause_refs, diff, change_type, extraction_status}
ApplicabilityCandidate {policy_ref, user_scope_ref, rationale_with_clause_refs, uncertainties, required_confirmation}
PolicyAttention {candidate_ref, urgency, reason, deadline_if_explicit, notification_state, next_check_at}
```

版本号、时间生效/发布/发现时刻要分别表示。若原文修订、撤销或来源获取失败，应撤回或标记过期的派生摘要和提醒，不能继续作为最新证据。引用需能定位到官方原文条款/附件/页码；有 OCR 误差的扫描件应标记待复核。对抓取失败设置来源健康状态告警，不能承诺「绝不漏政策」。

### 3.6 评测目标

- 官方发布召回/覆盖率（按已登记来源）、发现延迟；转载去重、附件漏抓、修订漏检；
- 文件类型、发文机关、实施时间、地域/主体适用条件抽取与人工核对正确率；
- 新旧条款引用准确率、是否错误推断了教师义务/权益、截止日与效力状态；
- 错误提醒/漏提醒/重复打扰，教师处理通知实际净时间；
- 新政策发布到推送、教师确认、必要工作项目成立/关闭的全链路可复现；
- 安全硬门槛：不能越权访问校内/个人信息、不得把外部文档中的指令作为 Agent 授权、不得伪称法律结论、不得静默修改真实工作状态或未经授权对外发送。

先固定小规模历史样例（有效/已废止/征求意见/跨省不相关/官方转载/同名文号/同一文多附件/附件替换/超期补发/网站访问失败），人工建立 golden，再自动化回归。

## 4. 研发路线：先验证政策作用，而非先造全能 Personal Agent

**阶段 P0（研究）**：核验 4-6 个官方渠道的稳定获取方式；登记来源及覆盖盲区；用历史文件跑采集、PDF/HTML、正文/附件解析、版本比对；不发提醒、不处理个人敏感资料。

**阶段 P1（可用的 Policy Watch）**：公有政策快照 + 公开原文引用 + 任教地区/学段/岗位的基础过滤，输出基于证据的「可能相关」简报，低打扰，允许教师确认/纠错。

**阶段 P2（个人 Policy Agent）**：用户自愿提供岗位/职业阶段/关注主题，增加个人适用性匹配、变更通知、时间窗口与来源失效；校内来源另经授权单独接入并进行租户隔离。

**阶段 P3（任务与 Skill）**：可把已确认行动变成草稿 Todo/提醒/办公室材料准备 Skill；由教师确认正式任务和外发。之后才考虑受控持续运行与经验沉淀。

**阶段 P4（跨领域复用）**：同样的采集、适用性引擎可适配企业制度/地方政策研究，但领域权威与专业审查不同；不在 ClassMatter R1 抽象「万能合规 Agent」。

## 5. 公开依据（核验来源）

- 湖南省教育厅规范性文件/效力目录：https://jyt.hunan.gov.cn/sjyt/xxgk/zcfg/gfxwj/
- 湖南省教师发展中心 2026-08-19 职称规则解读：https://jyt.hunan.gov.cn/jyt/sjyt/hnzxxjsfzzx/jsfzzxxwdt/202608/t20260819_34047335.html
- 教育部 2026 年《“人工智能+教育”行动计划》：https://www.moe.gov.cn/srcsite/A16/s3342/202604/t20260410_1433240.html
- 湖南省教育厅发布首页：https://jyt.hunan.gov.cn/
- 长沙市教育局官网：https://jyj.changsha.gov.cn/
- 宁乡市人民政府官网：https://www.nxcity.gov.cn/

## 6. 尚需讨论，而非定案

1. 政策 Agent 是否在产品里作为独立「政策情报」入口，还是个人助理按需唤起的受限 Tool/Skill？建议 UI 独立、状态/采集共享、Agent 运行按需。
2. 用户关心的第一类政策是什么：日常安全/职责、职业发展/职称、个人申报/补贴、校内通知？默认不读取个人合同或猜测编制/公费师范生合同义务。
3. 哪些提醒需要立即推送，哪些只在 Today/周报出现？用户可以关闭低价值来源/主题。
4. 初期要监测全部官方信息还是只覆盖少量明确渠道并公开展示覆盖范围？建议后者，以可测召回与误报率迭代。
5. 如何在正式规则与个人工作偏好、自动 Skill 之间维持权限与来源版本一致性？一旦规则变化，相关 Skill 与生成模板应重新评测。

**状态声明：本文件为研究索引和可验证实验建议，未安装第三方依赖、未启动爬虫/定时任务、未发送提醒、未更改 R1、未处理任何真实学校/学生资料。**
