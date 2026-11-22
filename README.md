<div align="center">
  <img src="https://repository-images.githubusercontent.com/1424619394/0730fa01-db22-4b12-a757-ab2bddf0e601" width="760" alt="班事有谱 ClassMatter，长颈鹿与书本标识">

  <h1>班事有谱 · ClassMatter</h1>
  <p><strong>开源班主任工作台</strong></p>
  <p>记录今天发生的事，看清下一步，把做过的工作整理成小结。</p>
  <p>
    <a href="README_EN.md">English</a> ·
    <a href="#日常怎么用">使用场景</a> ·
    <a href="#快速开始">快速开始</a> ·
    <a href="#文档与贡献">文档与贡献</a>
  </p>
  <p>
    <a href="LICENSE"><img alt="Apache-2.0 许可证" src="https://img.shields.io/badge/License-Apache--2.0-285b4d"></a>
    <a href="https://github.com/Gdnbit/classmatter/actions/workflows/synthetic-ci.yml"><img alt="Windows 与 Ubuntu 持续集成" src="https://github.com/Gdnbit/classmatter/actions/workflows/synthetic-ci.yml/badge.svg?branch=main"></a>
  </p>
</div>

## 日常怎么用

早上打开工作台，看一眼**需要我处理、可能遗漏、等待别人**。事情发生时，在对话里说一句。到了周五，按已有记录和跟进结果整理小结。对话、学生和工作页面可以回到同一件事。

> “周五前收齐活动回执，帮我建个跟进。”
>
> “把这两位同学的座位对调，先让我看看前后位置。”
>
> “把本周已完成的班务整理成一份工作小结。”

对话会显示可以核对的草稿或变更前后对比。确认后保存，回到原页面就能看到结果。

| 工作场景 | 用班事有谱怎么做 |
| --- | --- |
| **记下事实，继续跟进** | 从自然语言或语音转写开始，关联学生、记录与期限。查看进度、等待事项和学生时间线。 |
| **管理班级、成绩与座位** | 在名单和成绩表中查看班级信息。调整座位时先看对比，再确认应用。 |
| **整理小结和材料** | 根据已有记录准备小结，向已配对的同事收集材料。编辑文档、查看版本，并导出 Word 或 PowerPoint。 |
| **查找依据** | 在对话里查阅知识库资料，通过引用回到具体来源。 |

## 快速开始

Windows 桌面版可从源码构建。准备 PowerShell 7、Node.js 22–24、pnpm 11.19.0、Python 3.13、uv 和 PostgreSQL 18.6。下面从一个新工作区开始。已有工作区请走[备份与升级流程](apps/desktop/README.md)，保留原来的班级与对话。

```powershell
git clone https://github.com/Gdnbit/classmatter.git
cd classmatter/backend
uv sync --frozen
uv run --frozen python local.py prepare-chat --profile conversation-d1 --pg-root '<PostgreSQL 18.6 安装目录>'
uv run --frozen python local.py upgrade-classroom --profile workspace-chat-d3

cd ../apps/web
pnpm install --frozen-lockfile
cd ../desktop
pnpm install --frozen-lockfile
pnpm build
pnpm start
```

通过桌面设置连接并启用自己的模型。日常可直接开始对话，涉及班级时再关联具体范围。

## 文档与贡献

- [桌面运行与升级](apps/desktop/README.md) · [后端开发](backend/README.md) · [项目文档索引](docs/README.md)
- [产品需求](docs/specs/class-os-v1/requirements.md) · [系统架构](docs/specs/class-os-v1/architecture.md) · [实现与验收台账](docs/implementation-ledger.md)
- [贡献指南](CONTRIBUTING.md) · [提交反馈](https://github.com/Gdnbit/classmatter/issues) · [安全报告](SECURITY.md)

班事有谱以 [Apache-2.0](LICENSE) 开源。版权 © 2026 Gdnbit。 [声明](NOTICE)
