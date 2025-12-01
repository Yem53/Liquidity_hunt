"""
Short Squeeze Monitor - Telegram Notifier
==========================================
通过 Telegram Bot 发送告警通知，支持发送图表和交互按钮
"""

import asyncio
import io
import json
import logging
from datetime import datetime, timezone
from typing import Optional

import aiohttp
import pandas as pd

# ⚠️ CRITICAL for AWS: 必须在导入 pyplot 之前设置
import matplotlib
matplotlib.use('Agg')  # 非交互式后端，用于无显示器的服务器环境
import mplfinance as mpf
import matplotlib.pyplot as plt

from config import NETWORK, TELEGRAM

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """
    Telegram 通知器
    
    发送消息和图片到 Telegram Bot API (支持代理/直连)
    支持 Inline Keyboard 按钮
    """
    
    BASE_URL = "https://api.telegram.org"
    
    def __init__(self):
        self.bot_token = TELEGRAM.BOT_TOKEN
        self.chat_id = TELEGRAM.CHAT_ID
        self.proxy_url = NETWORK.PROXY_URL  # None 表示直连
        self.timeout = aiohttp.ClientTimeout(total=NETWORK.HTTP_TIMEOUT)
        self.session: Optional[aiohttp.ClientSession] = None
        self._enabled = bool(self.bot_token and self.chat_id)
        
        if not self._enabled:
            logger.warning("⚠️ Telegram 通知未配置 (缺少 BOT_TOKEN 或 CHAT_ID)")
        else:
            logger.info(f"📱 Telegram 通知器已初始化")
            logger.info(f"  → Chat ID: {self.chat_id}")
            logger.info(f"  → 网络模式: {NETWORK.network_mode}")
    
    @property
    def is_enabled(self) -> bool:
        """检查通知器是否已配置"""
        return self._enabled
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        self.session = aiohttp.ClientSession(timeout=self.timeout)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器退出"""
        if self.session:
            await self.session.close()
    
    def _get_api_url(self, method: str) -> str:
        """获取 API URL"""
        return f"{self.BASE_URL}/bot{self.bot_token}/{method}"
    
    def _build_inline_keyboard(self, signal) -> dict:
        """
        构建 Inline Keyboard 按钮
        
        Args:
            signal: SqueezeSignal 对象
            
        Returns:
            Telegram inline_keyboard 格式的字典
        """
        # Binance Futures 交易链接
        binance_url = f"https://www.binance.com/zh-CN/futures/{signal.symbol}"
        
        # TradingView 图表链接
        tv_url = f"https://www.tradingview.com/chart/?symbol=BINANCE:{signal.symbol}.P"
        
        return {
            "inline_keyboard": [
                [
                    {"text": "🔥 Trade on Binance", "url": binance_url},
                    {"text": "📈 View on TradingView", "url": tv_url}
                ]
            ]
        }
    
    async def send_message(
        self,
        text: str,
        parse_mode: str = "HTML",
        disable_notification: bool = False,
        reply_markup: Optional[dict] = None
    ) -> bool:
        """
        发送消息到 Telegram
        
        Args:
            text: 消息内容
            parse_mode: 解析模式 (HTML/Markdown)
            disable_notification: 是否静音发送
            reply_markup: Inline Keyboard 配置
            
        Returns:
            是否发送成功
        """
        if not self._enabled:
            logger.debug("Telegram 通知未启用，跳过发送")
            return False
        
        url = self._get_api_url("sendMessage")
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_notification": disable_notification,
        }
        
        if reply_markup:
            payload["reply_markup"] = json.dumps(reply_markup)
        
        try:
            request_kwargs = {"json": payload}
            if self.proxy_url:
                request_kwargs["proxy"] = self.proxy_url
            
            async with self.session.post(url, **request_kwargs) as response:
                if response.status == 200:
                    result = await response.json()
                    if result.get("ok"):
                        logger.debug("✅ Telegram 消息发送成功")
                        return True
                    else:
                        logger.error(f"❌ Telegram API 错误: {result.get('description')}")
                else:
                    error_text = await response.text()
                    logger.error(f"❌ Telegram 请求失败: {response.status} | {error_text[:200]}")
        
        except aiohttp.ClientProxyConnectionError as e:
            logger.error(f"🔌 代理连接失败: {e}")
        except aiohttp.ClientError as e:
            logger.error(f"📡 网络错误: {e}")
        except asyncio.TimeoutError:
            logger.error("⏱️ Telegram 请求超时")
        except Exception as e:
            logger.error(f"❌ 发送消息异常: {e}")
        
        return False
    
    async def send_photo(
        self,
        image_buffer: io.BytesIO,
        caption: str = "",
        parse_mode: str = "HTML",
        reply_markup: Optional[dict] = None
    ) -> bool:
        """
        发送图片到 Telegram (支持 Inline Keyboard)
        
        Args:
            image_buffer: 图片二进制缓冲区
            caption: 图片说明文字
            parse_mode: 解析模式
            reply_markup: Inline Keyboard 配置
            
        Returns:
            是否发送成功
        """
        if not self._enabled:
            logger.debug("Telegram 通知未启用，跳过发送")
            return False
        
        url = self._get_api_url("sendPhoto")
        
        # 准备 multipart/form-data
        image_buffer.seek(0)
        form_data = aiohttp.FormData()
        form_data.add_field("chat_id", str(self.chat_id))
        form_data.add_field("photo", image_buffer, filename="chart.png", content_type="image/png")
        
        if caption:
            form_data.add_field("caption", caption)
            form_data.add_field("parse_mode", parse_mode)
        
        if reply_markup:
            form_data.add_field("reply_markup", json.dumps(reply_markup))
        
        try:
            request_kwargs = {"data": form_data}
            if self.proxy_url:
                request_kwargs["proxy"] = self.proxy_url
            
            async with self.session.post(url, **request_kwargs) as response:
                if response.status == 200:
                    result = await response.json()
                    if result.get("ok"):
                        logger.debug("✅ Telegram 图片发送成功")
                        return True
                    else:
                        logger.error(f"❌ Telegram API 错误: {result.get('description')}")
                else:
                    error_text = await response.text()
                    logger.error(f"❌ Telegram 图片发送失败: {response.status} | {error_text[:200]}")
        
        except aiohttp.ClientProxyConnectionError as e:
            logger.error(f"🔌 代理连接失败: {e}")
        except aiohttp.ClientError as e:
            logger.error(f"📡 网络错误: {e}")
        except asyncio.TimeoutError:
            logger.error("⏱️ Telegram 请求超时")
        except Exception as e:
            logger.error(f"❌ 发送图片异常: {e}")
        
        return False
    
    def generate_chart_image(
        self,
        symbol: str,
        df: pd.DataFrame,
        title: Optional[str] = None,
        is_strong: bool = False
    ) -> Optional[io.BytesIO]:
        """
        生成 K 线图表 (mplfinance)
        
        Args:
            symbol: 交易对符号
            df: K线数据 DataFrame (需要有 Date 索引和 OHLCV 列)
            title: 图表标题
            is_strong: 是否为强信号 (影响标题颜色)
            
        Returns:
            图片的 BytesIO 缓冲区
        """
        if df is None or df.empty:
            logger.warning(f"无法生成图表: {symbol} 数据为空")
            return None
        
        try:
            # 设置图表样式 (Binance 风格深色主题)
            style = mpf.make_mpf_style(
                base_mpf_style='nightclouds',
                marketcolors=mpf.make_marketcolors(
                    up='#26a69a',      # 涨 - 绿色
                    down='#ef5350',    # 跌 - 红色
                    edge='inherit',
                    wick='inherit',
                    volume='inherit',
                ),
                gridstyle=':',
                gridcolor='#2a2e39',
                facecolor='#131722',
                figcolor='#131722',
                rc={
                    'font.size': 10,
                    'axes.labelcolor': '#d1d4dc',
                    'axes.titlecolor': '#ff4444' if is_strong else '#d1d4dc',
                    'xtick.color': '#d1d4dc',
                    'ytick.color': '#d1d4dc',
                }
            )
            
            if title is None:
                signal_type = "🚨 STRONG SIGNAL" if is_strong else "Signal"
                title = f"{symbol} - {signal_type}"
            
            # 创建内存缓冲区
            buffer = io.BytesIO()
            
            # 生成图表
            fig, axes = mpf.plot(
                df,
                type='candle',
                style=style,
                title=title,
                ylabel='Price',
                ylabel_lower='Volume',
                volume=True,
                figsize=(10, 6),
                returnfig=True,
                tight_layout=True,
            )
            
            # 保存到缓冲区
            fig.savefig(
                buffer,
                format='png',
                dpi=100,
                bbox_inches='tight',
                facecolor=fig.get_facecolor(),
                edgecolor='none'
            )
            
            # 关闭 figure 释放内存
            plt.close(fig)
            
            buffer.seek(0)
            logger.debug(f"✅ 图表已生成: {symbol}")
            return buffer
            
        except Exception as e:
            logger.error(f"生成图表失败 {symbol}: {e}")
            return None
    
    def format_signal_message(
        self,
        signal,
        advanced_metrics: Optional[dict] = None
    ) -> str:
        """
        格式化信号为 Telegram 消息 (中文版 - 交通灯视觉系统)
        
        🔴 STRONG = 红灯警报，立即关注
        🟠 NORMAL = 橙灯提示，加入观察
        
        Args:
            signal: SqueezeSignal 对象
            advanced_metrics: 高级指标 (可选)
            
        Returns:
            格式化后的 HTML 消息
        """
        # 格式化数值
        funding_pct = signal.funding_rate * 100  # 转换为百分比显示
        price_str = self._format_price(signal.price)
        
        # 格式化 OI 相关数据 (使用可读格式)
        oi_str = self._format_number(signal.current_oi)
        oi_short_str = self._format_number(signal.oi_short_ma)
        oi_long_str = self._format_number(signal.oi_long_ma)
        
        # 获取 OI 状态 (图标 + 文字)
        oi_emoji, oi_status = self._format_oi_status(signal.oi_ratio)
        
        # 费率状态
        if abs(signal.funding_rate) >= 0.001:
            fr_status = "极端"
        elif abs(signal.funding_rate) >= 0.0005:
            fr_status = "偏高"
        else:
            fr_status = ""
        fr_suffix = f" ({fr_status})" if fr_status else ""
        
        # ====== 大盘预警 (如果 BTC 正在下跌) ======
        btc_warning = ""
        if signal.btc_veto:
            btc_pct = signal.btc_change_pct * 100
            btc_warning = f"""⛈️⛈️ <b>大盘预警</b> ⛈️⛈️
🔻 BTC 急跌: <b>{btc_pct:.2f}%</b>
⚠️ <i>陷阱风险极高，谨慎交易!</i>

"""
        
        if signal.severity == "STRONG":
            # ═══════════════════════════════════════════════
            # 🔴 STRONG SIGNAL - 强力警报
            # ═══════════════════════════════════════════════
            
            # 如果被 BTC Veto，使用不同的头部
            if signal.btc_veto:
                header = "⛔ <b>信号被大盘压制 (VETOED)</b> ⛔"
            else:
                header = "🚨 <b>强力轧空警报 (STRONG)</b> 🚨"
            
            message = f"""{btc_warning}{header}

🎯 <b>标的:</b> #{signal.symbol}
💵 <b>价格:</b> ${price_str}

━━━━━━━━━━━━━━━━━━━━━━━━━━
🔥 <b>核心数据</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━
💰 <b>费率:</b> {funding_pct:+.4f}%{fr_suffix}
{oi_emoji} <b>持仓:</b> {signal.oi_ratio:.2f}x ({oi_status})

📊 <b>持仓详情:</b>
   当前: <b>{oi_str}</b>
   短期均线: {oi_short_str}
   长期均线: {oi_long_str}
"""
            
            # 添加双窗口 OI 变化
            message += self._format_oi_dual_window(signal)
            
            # 添加主力数据
            if advanced_metrics:
                message += self._format_smart_money_section(advanced_metrics)
            
            # 紧急提示 (如果没有 BTC Veto)
            if not signal.btc_veto:
                if signal.funding_rate < 0:
                    message += """
⚠️ <i>空头极度拥挤</i>
⚠️ <i>主力资金入场，高波动在即!</i>
"""
                else:
                    message += """
⚠️ <i>多头过度拥挤</i>
⚠️ <i>警惕回调风险!</i>
"""
        
        else:
            # ═══════════════════════════════════════════════
            # 🟠 NORMAL SIGNAL - 潜在机会
            # ═══════════════════════════════════════════════
            message = f"""{btc_warning}🟠 <b>潜在机会 (Normal)</b>

👀 <b>关注:</b> #{signal.symbol}
💵 <b>价格:</b> ${price_str}

━━━━━━━━━━━━━━━━━━━━━━
💰 <b>费率:</b> {funding_pct:+.4f}%{fr_suffix}
{oi_emoji} <b>持仓:</b> {signal.oi_ratio:.2f}x ({oi_status})

<b>持仓详情:</b>
   当前: {oi_str}
   短期均线: {oi_short_str}
   长期均线: {oi_long_str}
"""
            
            # 添加双窗口 OI 变化
            message += self._format_oi_dual_window(signal)
            
            # 添加主力数据
            if advanced_metrics:
                message += self._format_smart_money_section(advanced_metrics)
        
        # ====== 趋势分析和操作建议 ======
        if signal.trend and signal.advice:
            message += self._format_trend_section(signal)
        
        # 时间戳
        message += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━
<i>⏰ {signal.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")}</i>
"""
        return message.strip()
    
    def _format_trend_section(self, signal) -> str:
        """格式化趋势分析和操作建议区块 (中文版)"""
        price_chg = signal.price_change_pct * 100  # 转为百分比
        oi_chg = signal.oi_change_pct * 100
        
        section = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━
🧭 <b>趋势判断</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 价格: <b>{price_chg:+.2f}%</b> | 持仓: <b>{oi_chg:+.2f}%</b>

{signal.trend}

💡 <b>战术建议:</b> {signal.advice}
"""
        return section
    
    def _format_smart_money_section(self, metrics: dict) -> str:
        """格式化主力数据区块 (中文版)"""
        ls_ratio = metrics.get('ls_ratio')
        top_ratio = metrics.get('top_trader_ratio')
        taker_buy = metrics.get('taker_buy_vol')
        taker_sell = metrics.get('taker_sell_vol')
        
        # 如果没有任何数据，返回空
        if all(v is None for v in [ls_ratio, top_ratio, taker_buy, taker_sell]):
            return ""
        
        section = """
━━━━━━━━━━━━━━━━━━━━━━━━━━
🧠 <b>主力数据</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        
        if top_ratio is not None:
            section += f"🐳 <b>大户多空比:</b> {top_ratio:.2f}\n"
        
        if ls_ratio is not None:
            section += f"👥 <b>散户多空比:</b> {ls_ratio:.2f}\n"
        
        if taker_buy is not None and taker_sell is not None:
            buy_str = self._format_volume(taker_buy)
            sell_str = self._format_volume(taker_sell)
            section += f"💥 <b>主动成交:</b> 买 {buy_str} / 卖 {sell_str}\n"
        
        # 智能分析
        if ls_ratio is not None and top_ratio is not None:
            if top_ratio > ls_ratio * 1.1:
                section += "\n🔔 <b>大户比散户更看多!</b>\n"
            elif top_ratio < ls_ratio * 0.9:
                section += "\n🔔 <b>大户比散户更看空!</b>\n"
        
        return section
    
    def _format_price(self, price: float) -> str:
        """智能格式化价格"""
        if price >= 1000:
            return f"{price:,.2f}"
        elif price >= 1:
            return f"{price:.4f}"
        elif price >= 0.01:
            return f"{price:.6f}"
        else:
            return f"{price:.8f}"
    
    def _format_volume(self, volume: float) -> str:
        """格式化成交量为 K/M/B"""
        return self._format_number(volume)
    
    def _format_number(self, value: float) -> str:
        """
        格式化大数字为可读格式
        
        1,000,000,000 -> "1.00B"
        1,000,000 -> "1.00M"
        1,000 -> "1.00K"
        """
        if value >= 1_000_000_000:
            return f"{value / 1_000_000_000:.2f}B"
        elif value >= 1_000_000:
            return f"{value / 1_000_000:.2f}M"
        elif value >= 1_000:
            return f"{value / 1_000:.2f}K"
        else:
            return f"{value:.2f}"
    
    def _format_oi_status(self, oi_ratio: float) -> tuple[str, str]:
        """
        根据 OI 比率返回图标和状态文本
        
        Returns:
            (emoji, status_text)
        """
        if oi_ratio >= 2.0:
            return "🚀", "激增"
        elif oi_ratio >= 1.5:
            return "📈", "大幅增加"
        elif oi_ratio >= 1.05:
            return "↗️", "增加"
        elif oi_ratio >= 0.95:
            return "➡️", "持平"
        elif oi_ratio >= 0.8:
            return "↘️", "减少"
        else:
            return "📉", "大幅减少"
    
    def _format_oi_dual_window(self, signal) -> str:
        """
        格式化双窗口 OI 变化显示
        
        格式:
        ⏱️ **持仓异动:**
         • 15m 增速: +12.5%
         • 1h 累计: +35.2%
        """
        oi_15m_pct = signal.oi_change_15m * 100
        oi_1h_pct = signal.oi_change_1h * 100
        
        # 确定触发标志
        trigger = getattr(signal, 'oi_trigger', '')
        
        # 15分钟状态图标
        if oi_15m_pct >= 12:  # STRONG
            icon_15m = "🔥"
            tag_15m = " ⬅ <b>触发!</b>"
        elif oi_15m_pct >= 5:  # NORMAL
            icon_15m = "⚡"
            tag_15m = " ⬅ 触发"
        elif oi_15m_pct > 0:
            icon_15m = "📈"
            tag_15m = ""
        elif oi_15m_pct < -5:
            icon_15m = "📉"
            tag_15m = ""
        else:
            icon_15m = "➡️"
            tag_15m = ""
        
        # 1小时状态图标
        if oi_1h_pct >= 30:  # STRONG
            icon_1h = "🔥"
            tag_1h = " ⬅ <b>触发!</b>"
        elif oi_1h_pct >= 15:  # NORMAL
            icon_1h = "⚡"
            tag_1h = " ⬅ 触发"
        elif oi_1h_pct > 0:
            icon_1h = "📈"
            tag_1h = ""
        elif oi_1h_pct < -10:
            icon_1h = "📉"
            tag_1h = ""
        else:
            icon_1h = "➡️"
            tag_1h = ""
        
        section = f"""
⏱️ <b>持仓异动:</b>
   {icon_15m} 15m 增速: <b>{oi_15m_pct:+.1f}%</b>{tag_15m}
   {icon_1h} 1h 累计: <b>{oi_1h_pct:+.1f}%</b>{tag_1h}
"""
        return section
    
    async def send_signal_with_chart(
        self,
        signal,
        klines_df: Optional[pd.DataFrame] = None,
        advanced_metrics: Optional[dict] = None
    ) -> bool:
        """
        发送带图表和按钮的信号告警
        
        Args:
            signal: SqueezeSignal 对象
            klines_df: K线数据 DataFrame
            advanced_metrics: 高级指标 (散户多空比、大户多空比、买卖比等)
            
        Returns:
            是否发送成功
        """
        # 格式化消息 (包含高级指标)
        message = self.format_signal_message(signal, advanced_metrics)
        
        # 构建 Inline Keyboard
        keyboard = self._build_inline_keyboard(signal)
        
        # 生成图表
        chart_buffer = None
        if klines_df is not None and not klines_df.empty:
            chart_buffer = self.generate_chart_image(
                signal.symbol,
                klines_df,
                is_strong=(signal.severity == "STRONG")
            )
        
        # 发送 (图片 + 按钮，或纯文字 + 按钮)
        if chart_buffer:
            return await self.send_photo(
                chart_buffer,
                caption=message,
                reply_markup=keyboard
            )
        else:
            # 降级到纯文字发送
            return await self.send_message(
                message,
                reply_markup=keyboard
            )
    
    async def send_alert(
        self,
        message: str,
        image_buffer: Optional[io.BytesIO] = None,
        reply_markup: Optional[dict] = None
    ) -> bool:
        """
        发送告警消息
        """
        if image_buffer:
            return await self.send_photo(image_buffer, caption=message, reply_markup=reply_markup)
        else:
            return await self.send_message(message, reply_markup=reply_markup)
    
    async def send_startup_message(self) -> bool:
        """发送启动消息"""
        if not self._enabled:
            return False
        
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        network = "Direct" if NETWORK.is_direct_mode else f"Proxy ({NETWORK.PROXY_URL})"
        
        message = f"""
🚀 <b>Short Squeeze Monitor 已启动</b>

⏰ 启动时间: {now}
🌐 网络模式: {network}
📊 监控中...

━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ 系统已就绪
🔔 检测到信号时将自动发送告警
"""
        
        success = await self.send_message(message.strip())
        if success:
            logger.info("📱 启动消息已发送到 Telegram")
        return success
    
    async def send_shutdown_message(self) -> bool:
        """发送关闭消息"""
        if not self._enabled:
            return False
        
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        
        message = f"""
📴 <b>Short Squeeze Monitor 已停止</b>

⏰ 停止时间: {now}
"""
        
        return await self.send_message(message.strip())
    
    async def send_signals(self, signals: list, max_alerts: int = 5) -> int:
        """
        发送多个信号告警 (纯文字版本)
        
        Args:
            signals: 信号列表
            max_alerts: 最大发送数量
            
        Returns:
            成功发送的数量
        """
        if not self._enabled or not signals:
            return 0
        
        sent_count = 0
        
        # 按 severity 和 signal_strength 排序
        sorted_signals = sorted(
            signals,
            key=lambda s: (
                1 if s.severity == "STRONG" else 0,
                {"STRONG": 3, "MODERATE": 2, "WEAK": 1}.get(s.signal_strength, 0)
            ),
            reverse=True
        )
        
        for signal in sorted_signals[:max_alerts]:
            message = self.format_signal_message(signal)
            keyboard = self._build_inline_keyboard(signal)
            if await self.send_message(message, reply_markup=keyboard):
                sent_count += 1
                await asyncio.sleep(0.5)
        
        remaining = len(signals) - max_alerts
        if remaining > 0:
            await self.send_message(f"📊 还有 {remaining} 个信号未显示")
        
        return sent_count


# ============================================================================
# 测试代码
# ============================================================================

async def test_notifier():
    """测试通知器"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(message)s"
    )
    
    async with TelegramNotifier() as notifier:
        if not notifier.is_enabled:
            print("❌ Telegram 未配置，请设置 BOT_TOKEN 和 CHAT_ID")
            return
        
        print("📱 发送测试消息...")
        success = await notifier.send_startup_message()
        
        if success:
            print("✅ 测试消息发送成功!")
        else:
            print("❌ 测试消息发送失败")


if __name__ == "__main__":
    asyncio.run(test_notifier())
