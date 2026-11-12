# 教师文书、语音与写字机集成核查

状态：2026-11-13进行中的选型/实施研究；不是全部功能已实现。下载统一使用非C盘。本轮未关闭杀毒、未发出设备运动命令、未将第三方可执行文件加入公开仓库。

## 奎享官方软件

用户指定[奎享官网下载页](http://www.kvenjoy.com/#downloads)。浏览工具与本机HTTPS均访问异常；本机HTTP页面可读，静态引导文件为`kvenjoyweb/kvenjoyweb.nocache.js`。从该站实际发布的GWT资源中找到Aliyun HTTPS下载地址，选取名称为“奎享雕刻(64位).exe”的链接下载，并非第三方下载站替代包。

- 原链接：`https://drawfont.oss-cn-beijing.aliyuncs.com/files/%E5%A5%8E%E4%BA%AB%E9%9B%95%E5%88%BB(64%E4%BD%8D).exe`。
- 87,152,116字节；SHA-256 `6BAA25859CE760DE0CB9487005507CDF144D790F1FB495FCE51EE3C5790457A7`。
- 保存于本机非C盘下载目录，不公开二进制。Authenticode为未签名；PE未提供ProductVersion/FileVersion，不能据文件名认定为用户指定3.8.9。
- Windows Defender实时防护保持开启；已运行该文件的CustomScan，当前威胁记录未见匹配该路径的检测。此结果不等于来源签名或版本证明，也不需要为安装关闭防护。
- 当前未宣称安装完成。下一步区分便携程序/安装包、核对3.8.9、在非C目标目录安装并检查实际界面。仅看可执行文件存在不算安装验收。
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

文书/课件生成与编辑得到版本化Artifact；写字机从被选定版本生成纸面布局/轨迹，显示页尺寸、边距、缺字和真实路径预览，再由明确的人确认提交。硬件Job要区分排队、运行、暂停、取消、断连和未知结果；断连不自动重画整页。设备型号、幅面、抬笔参数和原点未核实前，停在离线导出/预览，不发送任意G-code。

既有`ChangeComparison`/`SeatLayoutPreview`已承载座位真实前后渲染，应复验并复用。其他Artifact通过封闭类型组件接入，不把模型生成的任意JavaScript或设备命令直接执行。

语音沿现有Capture入口复用模型与转写；长叙述先分为观察/他人陈述/计划/个人随记和待澄清对象，生成可编辑候选。正式记录、任务、小结分别通过原领域规则与BCG；会话文本/ASR输出不直接成为事实或长期记忆。记忆仅保存明确必要、范围正确且可更正/退出的内容，不新建万能Memory/Fact表。
