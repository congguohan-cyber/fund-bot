# 📊 基金分析飞书 Bot

一个 LLM 驱动的基金分析助手，通过飞书与你对话，每日自动分析三市场（A股/港股/美股）行情，穿透基金底层持仓，生成操作建议。

## ✨ 核心功能

- 📈 **三市场全覆盖**：A股 + 港股 + 美股行情实时采集
- 🔍 **持仓穿透分析**：穿透基金前十大重仓股，逐股分析涨跌对净值的影响
- 📰 **智能新闻过滤**：自动抓取财经新闻，AI 筛选与你持仓相关的信息
- 🎯 **操作建议**：每只基金给出加仓/减仓/持有/观望/定投建议
- ⚠️ **风险提示**：宏观事件、政策变化、财报季等风险提醒
- 🗣️ **飞书对话**：@bot 即可互动，支持语音/文字指令
- ⏰ **每日自动推送**：交易日早上 7:00 自动推送分析报告
- 🔄 **交易日历**：三市场交叉判断，节假日自动跳过
- 💰 **低成本运行**：月费约 ¥10-35（Claude API 费用为主）

## 🏗️ 项目结构

```
fund-bot/
├── main.py                  # 主入口（FastAPI + FC handler）
├── config.py                # 配置管理
├── database.py              # SQLite 数据库层
├── orchestrator.py          # 分析编排器
├── requirements.txt         # Python 依赖
├── collectors/              # 数据采集层
│   ├── market.py            #   A股/港股/美股行情
│   ├── fund.py              #   基金净值 + 持仓穿透
│   ├── news.py              #   财经新闻抓取
│   └── calendar.py          #   交易日历判断
├── analyzer/                # LLM 分析引擎
│   ├── engine.py            #   Claude API 封装
│   └── prompts.py           #   Prompt 模板
├── feishu/                  # 飞书接入层
│   ├── client.py            #   飞书 API 客户端
│   ├── cards.py             #   消息卡片模板
│   └── handler.py           #   消息处理 + 指令路由
└── .github/workflows/       # GitHub Actions 定时任务
    └── daily-analysis.yml   #   每日分析 Workflow
```

## 🚀 快速开始

### 1. 创建飞书自建应用

1. 访问 [飞书开放平台](https://open.feishu.cn/)
2. 创建「自建应用」→ 添加「机器人」能力
3. 订阅事件：`im.message.receive_v1`
4. 配置消息回调 URL（部署后填入）
5. 获取 `App ID`、`App Secret`、`Verification Token`
6. 在飞书中找到你的 `Open ID`（用于推送消息）

### 2. 获取 API Keys

- **Anthropic API Key**：[console.anthropic.com](https://console.anthropic.com/)
- 推荐模型：`claude-sonnet-5-20251001`

### 3. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 填入你的实际配置
```

必填项：
- `FEISHU_APP_ID` / `FEISHU_APP_SECRET` — 飞书应用凭证
- `ANTHROPIC_API_KEY` — Claude API Key

### 4. 本地运行

```bash
# 安装依赖
pip install -r requirements.txt

# 初始化数据库 + 启动服务
python main.py
```

服务启动在 `http://localhost:8000`

### 5. 添加你的基金

在飞书中向 Bot 发送：

```
添加基金 000001 华夏成长混合 A股
添加基金 270042 广发纳斯达克100 美股
添加基金 001875 景顺长城沪港深精选 港股
```

### 6. 部署到云

#### 方案 A：GitHub Actions（零成本，推荐）

1. Push 代码到 GitHub
2. 在 Settings → Secrets 中添加所有环境变量
3. GitHub Actions 自动每个交易日 7:00 运行
4. 飞书消息回调需要公网 URL → 可用 Cloudflare Tunnel 或阿里云 FC 补充

#### 方案 B：阿里云函数计算 FC

```bash
# 安装 Serverless Devs
npm install -g @serverless-devs/s

# 部署
s deploy
```

FC 优点：原生支持 HTTP 触发器（飞书回调）+ 定时触发器

## 💬 对话指令

| 指令 | 功能 | 示例 |
|------|------|------|
| `分析` / `看看` | 触发当日分析 | `@bot 分析今天的基金` |
| `我的基金` | 查看持仓列表 | `@bot 我的基金` |
| `添加基金` | 添加持仓 | `@bot 添加基金 000001 华夏成长 A股` |
| `删除基金` | 移除持仓 | `@bot 删除基金 000001` |
| `帮助` | 显示帮助 | `@bot 帮助` |

## 📊 分析报告示例

每天早上 7:00 收到的飞书卡片包含：

- 📈 **大盘速览** — 三市场核心指数涨跌
- 📰 **关键新闻** — 与你持仓最相关的 5-8 条新闻，标注利好/利空
- 📊 **基金分析** — 每只基金的持仓穿透、涨跌归因、操作建议
- 🔮 **明日展望** — 短期趋势预判 + 关注点
- ⚠️ **风险提示** — 需要警惕的风险事件

## 🔧 技术栈

- **框架**：FastAPI（Python）
- **数据**：AKShare（A股/港股/基金）、yfinance（美股）、财联社（新闻）
- **AI**：Claude API（Anthropic）
- **推送**：飞书消息卡片
- **存储**：SQLite
- **调度**：GitHub Actions / 阿里云 FC 定时触发器

## 📋 参考项目

本项目参考了以下优秀开源项目：

- [daily_stock_analysis](https://github.com/ZhuLinsen/daily_stock_analysis) — 47k+ Stars 的 LLM 股票分析系统
- [FinClaw](https://github.com/Fin-Chelae/FinClaw) — 多通道金融 AI Copilot
- [invest-alchemy](https://github.com/Cotory/invest-alchemy) — ETF 组合交易助手
- [AI-Quant-Investment-Assistant-cn](https://github.com/sagirisensee/AI-Quant-Investment-Assistant-cn) — A股 ETF/股票 AI 量化分析

## ⚠️ 免责声明

本工具基于公开数据和 AI 模型生成分析，**仅供参考，不构成投资建议**。基金有风险，投资需谨慎。AI 模型可能存在幻觉，操作建议请结合自身判断。
