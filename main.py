"""
Short Squeeze Monitor - Main Entry Point
=========================================
空头挤压监控器 - 主程序入口

监控 Binance USDT 永续合约，检测潜在的挤压信号

用法:
    python main.py              # 持续运行 (每5分钟)
    python main.py --once       # 只运行一次
    python main.py --interval 3 # 自定义间隔 (分钟)
"""

import argparse
import asyncio
import csv
import logging
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path

# 确保项目根目录在 Python 路径中
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import (
    DATA_CONFIG,
    LOG_CONFIG,
    NETWORK,
    TELEGRAM,
    THRESHOLDS,
    validate_config,
    print_config,
)
from data_collector import BinanceDataCollector, IPBannedError
from analyzer import MarketAnalyzer, SqueezeSignal
from notifier import TelegramNotifier


# ============================================================================
# 日志配置
# ============================================================================

def setup_logging(level: str = None) -> logging.Logger:
    """配置日志系统"""
    if level is None:
        level = LOG_CONFIG.LOG_LEVEL
    
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format=LOG_CONFIG.LOG_FORMAT,
        datefmt=LOG_CONFIG.LOG_DATE_FORMAT,
        handlers=[
            logging.StreamHandler(sys.stdout),
        ]
    )
    
    # 抑制第三方库的过多日志
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    
    return logging.getLogger("ShortSqueezeMonitor")


logger = setup_logging()


# ============================================================================
# 信号处理 (优雅退出)
# ============================================================================

class GracefulExit:
    """优雅退出处理器"""
    
    def __init__(self):
        self.should_exit = False
        # Windows 和 Unix 兼容
        try:
            signal.signal(signal.SIGINT, self._exit_handler)
            signal.signal(signal.SIGTERM, self._exit_handler)
        except (ValueError, OSError):
            pass  # 在某些环境下可能不支持
    
    def _exit_handler(self, signum, frame):
        logger.info("📴 收到退出信号，正在优雅停止...")
        self.should_exit = True


# ============================================================================
# 主监控类
# ============================================================================

class ShortSqueezeMonitor:
    """
    空头挤压监控器
    
    整合数据采集、分析和通知功能，定期运行监控循环
    """
    
    def __init__(self, interval_seconds: int = None):
        """
        初始化监控器
        
        Args:
            interval_seconds: 采集间隔 (秒)，默认使用配置文件值
        """
        self.interval = interval_seconds or DATA_CONFIG.CHECK_INTERVAL
        self.analyzer = MarketAnalyzer()
        self.notifier: TelegramNotifier = None
        self.exit_handler = GracefulExit()
        self.run_count = 0
        
        # 告警历史记录 (用于冷却/抑制逻辑)
        # 格式: {symbol: {'timestamp': datetime, 'severity': 'NORMAL'/'STRONG'}}
        self.alert_history: dict[str, dict] = {}
        self.cooldown_minutes = TELEGRAM.ALERT_COOLDOWN_MINUTES
    
    def display_banner(self) -> None:
        """显示启动横幅和配置清单"""
        telegram_status = "✅ 已启用" if TELEGRAM.ENABLED else "❌ 未配置"
        
        # 网络模式显示
        if NETWORK.is_direct_mode:
            network_mode = "🌐 Direct"
            network_detail = "直连"
        else:
            network_mode = "🔌 Proxy"
            network_detail = NETWORK.PROXY_URL
        
        # BTC Veto 状态
        btc_veto_status = "✅ 启用" if THRESHOLDS.BTC_VETO_ENABLED else "❌ 关闭"
        btc_veto_pct = THRESHOLDS.BTC_VETO_THRESHOLD * 100
        
        # 格式化数值
        min_vol_m = THRESHOLDS.MIN_VOLUME_24H / 1_000_000
        normal_fr_pct = THRESHOLDS.NORMAL_FUNDING_RATE * 100
        strong_fr_pct = THRESHOLDS.STRONG_FUNDING_RATE * 100
        
        # 双窗口 OI 阈值
        oi_15m_strong_pct = THRESHOLDS.OI_15M_STRONG * 100
        oi_15m_normal_pct = THRESHOLDS.OI_15M_NORMAL * 100
        oi_1h_strong_pct = THRESHOLDS.OI_1H_STRONG * 100
        oi_1h_normal_pct = THRESHOLDS.OI_1H_NORMAL * 100
        
        banner = f"""
╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║       🔍  SHORT SQUEEZE MONITOR  🔍                              ║
║       ━━━━━━━━━━━━━━━━━━━━━━━━━━                                 ║
║       Binance USDT Futures Real-time Monitor                     ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
        """
        print(banner)
        
        # ========================================
        # 📋 配置清单 (Configuration Manifest)
        # ========================================
        config_manifest = f"""
╔══════════════════════════════════════════════════════════════════╗
║  🚀 CONFIGURATION MANIFEST (已加载配置)                          ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  [Filter]  最小交易量 :       {min_vol_m:>6,.0f}M USDT                    ║
║                                                                  ║
║  📊 费率阈值                                                     ║
║  [Normal]  费率阈值   : {normal_fr_pct:>+10.2f}%   |  OI: {THRESHOLDS.NORMAL_OI_RATIO:.1f}x              ║
║  [Strong]  费率阈值   : {strong_fr_pct:>+10.2f}%   |  OI: {THRESHOLDS.STRONG_OI_RATIO:.1f}x              ║
║                                                                  ║
║  ⏱️ OI 双窗口阈值 (15m + 1h)                                     ║
║  [Normal]  15m: {oi_15m_normal_pct:>+6.0f}%   |  1h: {oi_1h_normal_pct:>+6.0f}%                        ║
║  [Strong]  15m: {oi_15m_strong_pct:>+6.0f}%   |  1h: {oi_1h_strong_pct:>+6.0f}%                        ║
║                                                                  ║
║  [Safety]  BTC Veto   : {btc_veto_pct:>+10.2f}% (15m)  {btc_veto_status}           ║
║                                                                  ║
║  [System]  轮询间隔   : {self.interval:>10}s   ({self.interval // 60}分钟)              ║
║  [System]  网络模式   : {network_mode:<10}   {network_detail:<19}║
║  [System]  告警冷却   : {self.cooldown_minutes:>10}分钟                              ║
║                                                                  ║
║  [Notify]  Telegram   : {telegram_status:<40}║
║  [Notify]  最大告警   : {TELEGRAM.MAX_ALERTS_PER_ROUND:>10}条/轮                             ║
║                                                                  ║
║  [Data]    CSV存储    : data/*.csv                               ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
        """
        print(config_manifest)
        
        # 日志记录关键配置
        logger.info(f"Network Mode: {NETWORK.network_mode}")
        logger.info(f"Min Volume: {min_vol_m:.0f}M USDT | Normal FR: {normal_fr_pct:.2f}% | Strong FR: {strong_fr_pct:.2f}%")
        logger.info(f"BTC Veto: {btc_veto_pct:.2f}% ({btc_veto_status})")
    
    def should_send_alert(self, signal: SqueezeSignal) -> tuple[bool, str]:
        """
        检查是否应该发送告警 (冷却/抑制逻辑)
        
        告警条件:
        1. 新信号 (不在历史记录中)
        2. 冷却时间已过 (超过 ALERT_COOLDOWN_MINUTES)
        3. 信号升级 (从 NORMAL 升级到 STRONG)
        
        Args:
            signal: 待发送的信号
            
        Returns:
            (should_send, reason) - 是否发送及原因
        """
        symbol = signal.symbol
        current_severity = signal.severity
        current_time = datetime.now(timezone.utc)
        
        # 情况 1: 新信号
        if symbol not in self.alert_history:
            return True, "🆕 新信号"
        
        last_alert = self.alert_history[symbol]
        last_time = last_alert['timestamp']
        last_severity = last_alert['severity']
        
        # 计算距离上次告警的时间
        time_since_last = (current_time - last_time).total_seconds() / 60  # 分钟
        
        # 情况 2: 冷却时间已过
        if time_since_last >= self.cooldown_minutes:
            return True, f"⏰ 冷却已过 ({time_since_last:.0f}分钟)"
        
        # 情况 3: 信号升级 (NORMAL -> STRONG)
        if current_severity == "STRONG" and last_severity == "NORMAL":
            return True, "⬆️ 信号升级 (NORMAL → STRONG)"
        
        # 抑制: 冷却期内且无升级
        remaining = self.cooldown_minutes - time_since_last
        return False, f"🔇 冷却中 ({remaining:.0f}分钟后解除)"
    
    def update_alert_history(self, signal: SqueezeSignal) -> None:
        """更新告警历史记录"""
        self.alert_history[signal.symbol] = {
            'timestamp': datetime.now(timezone.utc),
            'severity': signal.severity
        }
    
    def display_signals(self, signals: list[SqueezeSignal]) -> None:
        """显示检测到的信号"""
        if not signals:
            logger.info("📭 本轮未检测到信号")
            return
        
        print("\n" + "=" * 70)
        print(f"🚨 检测到 {len(signals)} 个潜在挤压信号!")
        print("=" * 70)
        
        # 按强度分组
        strong = [s for s in signals if s.signal_strength == "STRONG"]
        moderate = [s for s in signals if s.signal_strength == "MODERATE"]
        weak = [s for s in signals if s.signal_strength == "WEAK"]
        
        if strong:
            print("\n🔴 STRONG SIGNALS (高优先级):")
            print("-" * 70)
            for s in strong:
                print(s.to_alert_message())
        
        if moderate:
            print("\n🟠 MODERATE SIGNALS (中优先级):")
            print("-" * 70)
            for s in moderate[:5]:
                print(s.to_short_message())
            if len(moderate) > 5:
                print(f"   ... 还有 {len(moderate) - 5} 个")
        
        if weak:
            print(f"\n🟡 WEAK SIGNALS: {len(weak)} 个")
            print("-" * 70)
            for s in weak[:3]:
                print(s.to_short_message())
            if len(weak) > 3:
                print(f"   ... 还有 {len(weak) - 3} 个")
    
    def display_market_summary(self, summary: dict) -> None:
        """显示市场概况"""
        print("\n📈 市场概况:")
        print(f"   • 监控交易对: {summary['total_symbols']}")
        print(
            f"   • 资金费率分布: "
            f"正费率 {summary['positive_funding']} | "
            f"负费率 {summary['negative_funding']}"
        )
        print(
            f"   • 极端资金费率: "
            f"极端正 {summary['extreme_positive_funding']} | "
            f"极端负 {summary['extreme_negative_funding']}"
        )
        print(f"   • 市场情绪: {summary['market_sentiment']}")
    
    async def send_telegram_alerts_with_charts(
        self,
        signals: list[SqueezeSignal],
        collector: BinanceDataCollector
    ) -> None:
        """
        发送带图表的 Telegram 告警
        
        流程:
        1. 按 severity (STRONG > NORMAL) 和 signal_strength 排序
        2. 获取 K 线数据
        3. 生成图表
        4. 发送告警 (图片 + 文字 + 按钮)
        5. 如果图表生成失败，降级到纯文字发送
        
        Args:
            signals: 信号列表
            collector: 数据采集器 (用于获取K线)
        """
        if not self.notifier or not self.notifier.is_enabled:
            return
        
        if not signals:
            return
        
        # 根据配置过滤信号
        if TELEGRAM.STRONG_ONLY:
            signals_to_send = [s for s in signals if s.severity == "STRONG"]
        else:
            signals_to_send = signals
        
        if not signals_to_send:
            return
        
        # 按 severity 和 signal_strength 排序
        # STRONG severity 优先，然后按 signal_strength 排序
        sorted_signals = sorted(
            signals_to_send,
            key=lambda s: (
                1 if s.severity == "STRONG" else 0,  # STRONG 优先
                {"STRONG": 3, "MODERATE": 2, "WEAK": 1}.get(s.signal_strength, 0)
            ),
            reverse=True
        )
        
        # 统计信号类型
        strong_count = sum(1 for s in sorted_signals if s.severity == "STRONG")
        normal_count = len(sorted_signals) - strong_count
        
        if strong_count > 0:
            logger.info(f"🚨 检测到 {strong_count} 个强信号!")
        
        sent_count = 0
        skipped_count = 0
        failed_count = 0
        max_alerts = TELEGRAM.MAX_ALERTS_PER_ROUND
        alerts_sent_this_round = 0
        
        for signal in sorted_signals:
            # 检查是否达到本轮发送上限
            if alerts_sent_this_round >= max_alerts:
                break
            
            # ========== 冷却/抑制逻辑 ==========
            should_send, reason = self.should_send_alert(signal)
            
            if not should_send:
                # 抑制: 记录日志并跳过
                logger.debug(f"⏭️ 跳过 {signal.symbol} - {reason}")
                skipped_count += 1
                continue
            
            logger.debug(f"📤 发送 {signal.symbol} - {reason}")
            
            try:
                # 1. 获取 K 线数据
                logger.debug(f"📊 获取 {signal.symbol} K线数据...")
                klines_df = await collector.fetch_klines(
                    signal.symbol,
                    interval="15m",
                    limit=50
                )
                
                # 2. 按需获取高级指标 (仅在发送告警时获取)
                logger.debug(f"📊 获取 {signal.symbol} 高级指标...")
                advanced_metrics = None
                try:
                    advanced_metrics = await collector.fetch_advanced_metrics(signal.symbol)
                except Exception as metric_error:
                    # 高级指标获取失败不阻塞告警发送
                    logger.debug(f"⚠️ 高级指标获取失败: {metric_error}")
                
                # 3. 发送带图表和指标的告警
                success = await self.notifier.send_signal_with_chart(
                    signal,
                    klines_df,
                    advanced_metrics
                )
                
                if success:
                    sent_count += 1
                    alerts_sent_this_round += 1
                    # 更新告警历史记录
                    self.update_alert_history(signal)
                    severity_icon = "🚨" if signal.severity == "STRONG" else "📊"
                    metrics_info = " (含指标)" if advanced_metrics else ""
                    logger.info(f"{severity_icon} 已发送 {signal.symbol} 告警{metrics_info} (Severity: {signal.severity})")
                else:
                    failed_count += 1
                
                # 避免发送过快
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"发送 {signal.symbol} 告警失败: {e}")
                failed_count += 1
                
                # 降级到纯文本发送 (无图表和高级指标)
                try:
                    logger.debug(f"尝试降级发送 {signal.symbol} (纯文字)...")
                    message = self.notifier.format_signal_message(signal, None)
                    keyboard = self.notifier._build_inline_keyboard(signal)
                    if await self.notifier.send_message(message, reply_markup=keyboard):
                        sent_count += 1
                        alerts_sent_this_round += 1
                        failed_count -= 1
                        # 更新告警历史记录
                        self.update_alert_history(signal)
                        logger.info(f"📝 已发送 {signal.symbol} 告警 (纯文字)")
                except Exception as fallback_error:
                    logger.error(f"降级发送也失败: {fallback_error}")
        
        # 日志汇总
        if skipped_count > 0:
            logger.info(f"🔇 已抑制 {skipped_count} 个重复信号 (冷却期 {self.cooldown_minutes} 分钟)")
        
        if sent_count > 0:
            logger.info(f"📱 已发送 {sent_count} 条 Telegram 告警")
    
    async def run_once(self) -> list[SqueezeSignal]:
        """
        执行一次完整的监控循环
        
        Returns:
            检测到的信号列表
        """
        self.run_count += 1
        logger.info(f"🔄 开始第 {self.run_count} 轮监控...")
        
        try:
            # 使用 collector 上下文管理器
            async with BinanceDataCollector() as collector:
                # 1. 采集数据
                current_data = await collector.collect_all_data()
                
                if not current_data:
                    logger.warning("⚠️ 未能获取有效数据")
                    return []
                
                # 2. 获取 BTC 变化 (用于 BTC Veto)
                btc_change = self._get_btc_change(current_data)
                if btc_change < THRESHOLDS.BTC_VETO_THRESHOLD:
                    logger.warning(f"⚠️ BTC 下跌 {btc_change*100:.2f}%，触发安全检查")
                
                # 3. 显示市场概况
                summary = self.analyzer.get_market_summary(current_data)
                self.display_market_summary(summary)
                
                # 4. 分析信号
                signals = self.analyzer.analyze_all(current_data, min_strength="WEAK")
                
                # 5. 应用 BTC Veto (安全检查)
                signals = self.analyzer.apply_btc_veto(signals, btc_change)
                
                # 6. 记录信号到历史 CSV
                self._log_signals_to_csv(signals, btc_change)
                
                # 7. 显示信号
                self.display_signals(signals)
                
                # 8. 发送带图表的 Telegram 告警
                await self.send_telegram_alerts_with_charts(signals, collector)
            
            return signals
            
        except IPBannedError:
            logger.error("🚫 IP 被封禁! 请检查代理设置或等待解封")
            self.exit_handler.should_exit = True
            return []
        except Exception as e:
            logger.error(f"❌ 监控循环出错: {e}", exc_info=True)
            return []
    
    def _get_btc_change(self, current_data: dict) -> float:
        """获取 BTC 价格变化百分比"""
        if "BTCUSDT" not in current_data:
            return 0.0
        
        btc_data = current_data["BTCUSDT"]
        # price_change_percent 是 Binance 返回的 24h 变化
        change_pct = btc_data.get("price_change_percent", 0) / 100
        return change_pct
    
    def _log_signals_to_csv(
        self,
        signals: list[SqueezeSignal],
        btc_change: float
    ) -> None:
        """
        记录信号到历史 CSV (用于性能追踪)
        
        文件: data/signal_history.csv
        列: Time, Symbol, Price, BTC_Change, Severity, Funding, OI_Change, Trend, Advice
        """
        if not signals:
            return
        
        csv_path = Path(DATA_CONFIG.DATA_DIR) / "signal_history.csv"
        file_exists = csv_path.exists()
        
        fieldnames = [
            "timestamp", "symbol", "price", "btc_change_pct", 
            "severity", "funding_rate", "oi_ratio", "oi_change_pct",
            "trend", "advice", "btc_veto"
        ]
        
        try:
            with open(csv_path, mode="a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                
                if not file_exists:
                    writer.writeheader()
                
                for signal in signals:
                    row = {
                        "timestamp": signal.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                        "symbol": signal.symbol,
                        "price": f"{signal.price:.6f}",
                        "btc_change_pct": f"{btc_change*100:.2f}%",
                        "severity": signal.severity,
                        "funding_rate": f"{signal.funding_rate*100:.4f}%",
                        "oi_ratio": f"{signal.oi_ratio:.2f}x",
                        "oi_change_pct": f"{signal.oi_change_pct*100:.2f}%",
                        "trend": signal.trend,
                        "advice": signal.advice,
                        "btc_veto": "Yes" if signal.btc_veto else "No",
                    }
                    writer.writerow(row)
            
            logger.debug(f"📝 已记录 {len(signals)} 个信号到历史日志")
            
        except Exception as e:
            logger.error(f"❌ 记录信号历史失败: {e}")
    
    async def run_forever(self) -> None:
        """持续运行监控循环"""
        self.display_banner()
        logger.info("🚀 监控器已启动，按 Ctrl+C 停止")
        
        # 初始化 Telegram 通知器
        async with TelegramNotifier() as notifier:
            self.notifier = notifier
            
            # 发送启动消息
            if notifier.is_enabled:
                await notifier.send_startup_message()
            
            while not self.exit_handler.should_exit:
                start_time = datetime.now(timezone.utc)
                
                await self.run_once()
                
                # 计算下次运行时间
                elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
                sleep_time = max(0, self.interval - elapsed)
                
                if sleep_time > 0 and not self.exit_handler.should_exit:
                    logger.info(
                        f"⏳ 本轮完成! 下一轮将在 {sleep_time/60:.1f} 分钟后开始..."
                    )
                    
                    # 分段睡眠，以便更快响应退出信号
                    for _ in range(int(sleep_time)):
                        if self.exit_handler.should_exit:
                            break
                        await asyncio.sleep(1)
            
            # 发送关闭消息
            if notifier.is_enabled:
                await notifier.send_shutdown_message()
        
        logger.info("👋 监控器已停止")


# ============================================================================
# 命令行参数解析
# ============================================================================

def parse_args() -> argparse.Namespace:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="Short Squeeze Monitor - 空头挤压监控器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
示例:
  python main.py                  # 持续运行，间隔从 .env 读取 (当前: {DATA_CONFIG.CHECK_INTERVAL}s)
  python main.py --once           # 只运行一次
  python main.py --interval 180   # 每180秒更新
  python main.py --debug          # 启用调试日志
  python main.py --show-config    # 显示当前配置
  python main.py --test-telegram  # 测试 Telegram 连接
        """
    )
    
    parser.add_argument(
        "--once",
        action="store_true",
        help="只运行一次后退出"
    )
    
    parser.add_argument(
        "--interval",
        type=int,
        default=None,
        help=f"更新间隔 (秒), 默认从配置读取: {DATA_CONFIG.CHECK_INTERVAL}s"
    )
    
    parser.add_argument(
        "--debug",
        action="store_true",
        help="启用调试模式"
    )
    
    parser.add_argument(
        "--show-config",
        action="store_true",
        help="显示当前配置后退出"
    )
    
    parser.add_argument(
        "--test-telegram",
        action="store_true",
        help="测试 Telegram 连接后退出"
    )
    
    return parser.parse_args()


# ============================================================================
# 主函数
# ============================================================================

async def test_telegram():
    """测试 Telegram 连接"""
    logger.info("📱 测试 Telegram 连接...")
    
    async with TelegramNotifier() as notifier:
        if not notifier.is_enabled:
            logger.error("❌ Telegram 未配置，请在 .env 中设置:")
            logger.error("   TELEGRAM_BOT_TOKEN=your_bot_token")
            logger.error("   TELEGRAM_CHAT_ID=your_chat_id")
            return False
        
        success = await notifier.send_startup_message()
        if success:
            logger.info("✅ Telegram 测试成功!")
            return True
        else:
            logger.error("❌ Telegram 测试失败，请检查配置和网络")
            return False


async def main():
    """异步主函数"""
    args = parse_args()
    
    # 设置日志级别
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("🔧 调试模式已启用")
    
    # 显示配置
    if args.show_config:
        print_config()
        return
    
    # 测试 Telegram
    if args.test_telegram:
        await test_telegram()
        return
    
    # 验证配置
    errors = validate_config()
    if errors:
        logger.error("❌ 配置验证失败:")
        for error in errors:
            logger.error(f"   • {error}")
        sys.exit(1)
    
    # 创建监控器
    monitor = ShortSqueezeMonitor(interval_seconds=args.interval)
    
    if args.once:
        # 只运行一次
        logger.info("📌 单次运行模式")
        monitor.display_banner()
        
        # 初始化通知器用于单次运行
        async with TelegramNotifier() as notifier:
            monitor.notifier = notifier
            signals = await monitor.run_once()
        
        if signals:
            print(f"\n✅ 检测到 {len(signals)} 个信号")
        else:
            print("\n📭 未检测到信号 (可能需要更多历史数据)")
    else:
        # 持续运行
        await monitor.run_forever()


def run():
    """同步入口点"""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 程序已退出")
    except Exception as e:
        logger.error(f"💥 程序异常退出: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    run()
