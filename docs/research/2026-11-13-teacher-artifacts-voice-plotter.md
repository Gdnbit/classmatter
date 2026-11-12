# 教师文书、语音与写字机集成核查

状态：2026-11-13进行中的选型/实施研究；不是全部功能已实现。下载统一使用非C盘。本轮未关闭杀毒、未发出设备运动命令、未将第三方可执行文件加入公开仓库。

## 免费文本Provider交叉核验

本日[官方定价](https://docs.bigmodel.cn/cn/guide/start/pricing)与[模型概览](https://docs.bigmodel.cn/cn/guide/start/model-overview)仍将GLM-4.7-Flash输入/输出标为免费，[型号文档](https://docs.bigmodel.cn/cn/guide/models/free/glm-4.7-flash)注明文本及Function Calling；不是免费多模态/ASR或付费FlashX。[官方思考模式](https://docs.bigmodel.cn/cn/guide/capabilities/thinking-mode)区分默认思考与关闭选项，不能套用于强制思考的新型号。现有SDK的extra_body即可传thinking.type=disabled，无需另装框架或新Key。

实际2请求/1只读合成工具、409输入/15输出Token、2.772秒回合通过；另一次429及临时脚本度量错误留档。只证明当前标准Key/端点的有限协议可用性，不证明长期稳定、账号不限流、完整班务链或相对其他模型的质量优势。选择显式独立评测配置，原用户模型保持，业务权限不变；完整原生演练结果按场景登记，不以厂商基准宣传替代验收。

原生续接的逐请求诊断进一步区分了8.367秒读取超时与HTTP429；只对该精确免费配置使用既有30秒有限单请求，45秒总期限保持。后续一次首请求成功/读进度、第二请求429，不以扩大预算掩盖限流，也不自动换付费模型。SDK已有prepare_tools可在声明的续接阶段仅开放必需只读工具，随后恢复原集合；实际Token只记录供应商正数报告值，缺失未知。这些是当前工程证据，不构成免费服务持续可用承诺。

## 奎享官方软件

用户指定[奎享官网下载页](http://www.kvenjoy.com/#downloads)。浏览工具与本机HTTPS均访问异常；本机HTTP页面可读，静态引导文件为`kvenjoyweb/kvenjoyweb.nocache.js`。从该站实际发布的GWT资源中找到Aliyun HTTPS下载地址，选取名称为“奎享雕刻(64位).exe”的链接下载，并非第三方下载站替代包。

- 原链接：`https://drawfont.oss-cn-beijing.aliyuncs.com/files/%E5%A5%8E%E4%BA%AB%E9%9B%95%E5%88%BB(64%E4%BD%8D).exe`。
- 87,152,116字节；SHA-256 `6BAA25859CE760DE0CB9487005507CDF144D790F1FB495FCE51EE3C5790457A7`。
- 保存于本机非C盘下载目录，不公开二进制。Authenticode为未签名；PE未提供ProductVersion/FileVersion，不能据文件名认定为用户指定3.8.9。
- Windows Defender实时防护保持开启；已运行该文件的CustomScan，当前威胁记录未见匹配该路径的检测。此结果不等于来源签名或版本证明，也不需要为安装关闭防护。
- 当前未宣称安装完成。下一步区分便携程序/安装包、核对3.8.9、在非C目标目录安装并检查实际界面。仅看可执行文件存在不算安装验收。
- 实际启动验证：Computer Use两次启动请求均超时，之后重读窗口与精确路径进程均未发现对应程序；不重复盲点、不绕过系统拦截、不将失败记作已安装。版本3.8.9和启动依赖继续核查，设备适配仍受型号/协议缺失限制，其余开发继续推进。
- 本机串口枚举只有两个标准蓝牙串口，尚不能识别出写字机。不能把它们当作已适配的机械控制器。

## 开源复用候选及边界

| 候选及一手来源 | 可复用点 | 必须先核实 |
|---|---|---|
| [CNCDraw](https://github.com/jiangmuran/CNCDraw) | 作者描述为奎享相关Python轨迹、布局、G-code、MCP与设备工具集；适合进一步核对兼容性 | 当前仓库小、许可证/字体再分发权和硬件兼容未完成核验；不直接挂载其通用device_command给模型；mock不等于实机 |
| [vpype](https://github.com/abey79/vpype) | 矢量路径处理候选；项目声明MIT | 它不是奎享设备驱动；先离线固定版本/路径预览，不能因此承诺可落笔 |
| [AxiDraw](https://github.com/evil-mad/axidraw) | 成熟设备栈的接口与状态处理参考 | 针对AxiDraw硬件，许可证与打包条件须核对；不假设可控制未知奎享设备 |
| [PptxGenJS](https://github.com/gitbrent/PptxGenJS) | 可编辑PPTX生成候选，复用模板/文本/图表结构 | 验证实际导出、中文字体、内容越界和重新编辑；不以截图PPT冒充可编辑课件 |
| [python-docx](https://github.com/python-openxml/python-docx) | 仓库已有依赖，优先复用为DOCX生成 | 现有读取代码不代表已实现生成/下载/编辑闭环 |
| [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | 本地ASR候选，适用于独立评估长录音成本与中文质量 | 先盘点本机已有模型/硬件，固定模型版本与许可；权重/cache到非C盘，不先盲下大模型 |

一手README用于候选能力核对，不作为稳定性、商业集成或硬件适配已通过的证明。后续记录固定commit、许可证、最近维护、负例与实际测试，再决定采用；本轮没有新增第三方运行依赖。

## 集成路径

安装进度补充：通过资源管理器打开已核验的官方安装包后出现Windows管理员授权，自动化已在该边界停止，等待用户本人处理；未关闭杀毒、添加排除项或绕过系统授权。此前启动超时不能算安装成功，当前也尚未核验安装版本为3.8.9。设备品牌、型号、固件和USB连接仍未确认，未发送运动命令。此条件不阻断聊天、文书和语音工程单元。

文书/课件生成与编辑得到版本化Artifact；写字机从被选定版本生成纸面布局/轨迹，显示页尺寸、边距、缺字和真实路径预览，再由明确的人确认提交。硬件Job要区分排队、运行、暂停、取消、断连和未知结果；断连不自动重画整页。设备型号、幅面、抬笔参数和原点未核实前，停在离线导出/预览，不发送任意G-code。

既有`ChangeComparison`/`SeatLayoutPreview`已承载座位真实前后渲染，应复验并复用。其他Artifact通过封闭类型组件接入，不把模型生成的任意JavaScript或设备命令直接执行。

语音沿现有Capture入口复用模型与转写；长叙述先分为观察/他人陈述/计划/个人随记和待澄清对象，生成可编辑候选。正式记录、任务、小结分别通过原领域规则与BCG；会话文本/ASR输出不直接成为事实或长期记忆。记忆仅保存明确必要、范围正确且可更正/退出的内容，不新建万能Memory/Fact表。

## 文书导出本轮采用结果

语音协议采用结果：继续复用现有Capture、Pydantic AI与Google原生SDK，没有安装另一套ASR或自动下载模型。[Google音频官方文档](https://ai.google.dev/gemini-api/docs/audio)说明音频理解/转写用途；本项目实际仍固定已登记模型，不跟随网页样例自动更换新型号。WebM/WAV/MP3的实际SDK序列化与文字返回已离线核验，包含MIME与原字节一致、无工具/业务写、取消释放；不能代替真实供应商转写准确率。智谱[官方模型概览](https://docs.bigmodel.cn/cn/guide/start/model-overview)本次仍将GLM-4-Flash-250414标为免费文本模型，故仅复测其文字工具链，不拿它冒充语音模型，也不自动启用付费ASR。

后续实际Google音频请求已通过一条合成样本：本机已安装的中文TTS生成488,924字节WAV，经原Capture/已启用免费Gemini8.066秒返回工作事实、计划与个人书架随记，未触发业务写入或长期记忆。所有音频/私有运行脚本只在非C本地目录。两次本机验证脚本误比查询时钟而失败的记录保留；没有据此改供应商协议。此单条样本只证明真实音频通道，不足以评价现场噪声、方言、多人说话、语音笔记全流程或全天Ambient；用量未知，不当作零费用。

优先复用项目已锁定的python-docx1.2.0及python-pptx1.0.2，没有再安装同类框架。两者对应版本的[python-docx许可证](https://raw.githubusercontent.com/python-openxml/python-docx/v1.2.0/LICENSE)及[python-pptx许可证](https://raw.githubusercontent.com/scanny/python-pptx/v1.0.2/LICENSE)均为MIT，已有依赖原始通知保留。按[官方Word用法](https://python-docx.readthedocs.io/en/latest/user/quickstart.html)和[官方PPT用法](https://python-pptx.readthedocs.io/en/latest/user/quickstart.html)生成可编辑段落/文本框，不用截图冒充可编辑文件。实际采用范围为已保存工作文档的DOCX与基础文字PPTX派生导出；PptxGenJS仍为复杂模板/图表等后续候选，未新增运行依赖或外部生成服务。代码、原界面测试、失败和边界见场景结果及实现台账。
