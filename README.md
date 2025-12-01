# 🔍 Short Squeeze Monitor (轧空监控器)

**Binance USDT Futures 实时轧空信号监控系统**

一个专业的量化交易辅助工具，通过监控资金费率、持仓量变化等指标，实时检测潜在的空头/多头挤压机会。

## ✨ 核心功能

- 📊 **实时数据采集** - 从 Binance Futures API 获取资金费率、持仓量、K线等数据
- 🔥 **双窗口 OI 监控** - 同时追踪 15 分钟快速异动 + 1 小时持续趋势
- 📈 **信号分级** - STRONG / NORMAL 两级告警，快速区分优先级
- 🛡️ **BTC Veto 安全机制** - 大盘暴跌时自动抑制信号，避免陷阱
- 📱 **Telegram 告警** - 实时推送信号到 Telegram，附带图表和交易建议
- 🧭 **趋势分析** - 自动判断市场状态并给出操作建议

## 📦 安装

```bash
# 克隆仓库
git clone https://github.com/Yem53/Liquidity_hunt.git
cd Liquidity_hunt

# 创建虚拟环境
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/Mac

# 安装依赖
pip install -r requirements.txt
```

## ⚙️ 配置

1. 复制配置模板：
```bash
cp env.example .env
```

2. 编辑 `.env` 文件，配置以下参数：

| 参数 | 说明 | 示例 |
|------|------|------|
| `PROXY_URL` | 代理地址（可选） | `http://127.0.0.1:7890` |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot Token | `123456:ABC...` |
| `TELEGRAM_CHAT_ID` | 你的 Telegram Chat ID | `123456789` |
| `MIN_VOLUME_USDT` | 最小 24h 交易量 | `15000000` |

## 🚀 运行

```bash
# 单次运行
python main.py --once

# 持续监控
python main.py
```

## 📊 信号逻辑

### 触发条件 (OR)

| 指标 | NORMAL | STRONG |
|------|--------|--------|
| 资金费率 | ≤ -0.05% | ≤ -0.10% |
| OI 15分钟变化 | ≥ 5% | ≥ 12% |
| OI 1小时变化 | ≥ 15% | ≥ 30% |

### 趋势判断

| 价格 | OI | 费率 | 解读 |
|------|-----|------|------|
| ↓ | ↑ | 负 | 📉 吸筹蓄力 |
| ↑ | ↑ | 负 | 🚀 轧空启动 |
| ↑ | ↓ | - | 💥 空头踩踏 |
| ↓ | ↓ | - | 🩸 多头爆仓 |

## 📁 项目结构

```
Liquidity_Hunt/
├── main.py            # 主程序入口
├── config.py          # 配置管理
├── data_collector.py  # 数据采集器
├── analyzer.py        # 市场分析器
├── notifier.py        # Telegram 通知器
├── env.example        # 环境变量模板
├── requirements.txt   # Python 依赖
└── data/              # 历史数据存储
```

## 📝 License

MIT License

## ⚠️ 免责声明

本工具仅供学习和研究使用，不构成任何投资建议。加密货币交易具有高风险，请谨慎操作。

