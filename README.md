# 项目名称

## 简介

此项目是一个Telegram到Notion的集成工具，旨在帮助用户将Telegram中的文件和消息上传到Notion。

## 项目结构

```
.
├── LICENSE
├── README.md
├── bot_setup.py
├── common_utils.py
├── config.py
├── main.py
├── notion_bot_utils.py
├── requirements.txt
├── run_local_bot.py
└── webhook_handlers.py
```

## 主要功能

- 支持多种文件类型的上传，包括照片、文档、视频、音频和语音消息。
- 支持通过Telegram Bot上传文本文件（Telegram API限制为20MB）。
- 支持Notion API分块上传大文件。
- 支持通过接口上传文本/文件（仅受限于你的区块大小限制）。

## 安装步骤

1. 克隆此仓库：
   ```bash
   git clone <repository-url>
   ```
2. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```
3. 配置API密钥：
   - 在`config.py`或.env中设置Telegram和Notion的API密钥及相关信息。

## Telegram Bot webhook模式
- 使用`python main.py`脚本启动服务。
- 接口上传仅在webhook模式下可用。

## Telegram Bot long polling模式
- `python run_local_bot.py`脚本启动服务。

## 贡献指南

欢迎提交问题和请求合并。请确保在提交请求之前更新测试。

## 许可证

此项目使用MIT许可证。