"""
Short Squeeze Monitor - Market Analyzer
========================================
分析市场数据，检测潜在的空头/多头挤压信号
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

from config import (
    THRESHOLDS,
    DATA_CONFIG,
    ALERT_TEMPLATES,
)

logger = logging.getLogger(__name__)


@dataclass
class SqueezeSignal:
    """挤压信号数据结构"""
    symbol: str
    timestamp: datetime
    price: float
    funding_rate: float
    current_oi: float
    oi_short_ma: float
    oi_long_ma: float
    oi_ratio: float
    is_extreme_funding: bool
    is_oi_surge: bool
    signal_strength: str  # "STRONG", "MODERATE", "WEAK"
    severity: str = "NORMAL"  # "STRONG" or "NORMAL"
    
    # 趋势分析 (由 determine_trend_and_advice 填充)
    price_change_pct: float = 0.0  # 价格变化百分比
    oi_change_pct: float = 0.0     # OI 变化百分比 (兼容旧逻辑)
    trend: str = ""                 # 市场趋势描述
    advice: str = ""                # 操作建议
    
    # 双窗口 OI 监控 (15分钟 + 1小时)
    oi_change_15m: float = 0.0     # 15分钟 OI 变化百分比
    oi_change_1h: float = 0.0      # 1小时 OI 变化百分比
    oi_trigger: str = ""           # 触发类型: "15m", "1h", "both", ""
    
    # BTC Veto (安全检查)
    btc_change_pct: float = 0.0    # BTC 价格变化百分比
    btc_veto: bool = False         # 是否被 BTC Veto 触发
    
    @property
    def funding_status(self) -> str:
        """资金费率状态描述"""
        if self.funding_rate < -THRESHOLDS.FUNDING_RATE_EXTREME:
            return "🔴 极度负费率 (空头拥挤)"
        elif self.funding_rate > THRESHOLDS.FUNDING_RATE_EXTREME:
            return "🟢 极度正费率 (多头拥挤)"
        return "⚪ 正常"
    
    @property
    def direction(self) -> str:
        """信号方向"""
        if self.funding_rate < 0:
            return "SHORT_SQUEEZE"
        return "LONG_SQUEEZE"
    
    @property
    def is_strong(self) -> bool:
        """是否为强信号"""
        return self.severity == "STRONG"
    
    def to_alert_message(self) -> str:
        """生成告警消息"""
        return ALERT_TEMPLATES["short_squeeze"].format(
            symbol=self.symbol,
            price=self.price,
            funding_rate=self.funding_rate,
            funding_status=self.funding_status,
            current_oi=self.current_oi,
            oi_short_ma=self.oi_short_ma,
            oi_long_ma=self.oi_long_ma,
            oi_ratio=self.oi_ratio,
            short_window=THRESHOLDS.OI_SHORT_WINDOW,
            long_window=THRESHOLDS.OI_LONG_WINDOW,
            timestamp=self.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC"),
        )
    
    def to_short_message(self) -> str:
        """生成简短告警消息"""
        direction_emoji = "🔴" if self.funding_rate < 0 else "🟢"
        return (
            f"{direction_emoji} {self.symbol:12s} | "
            f"Price: ${self.price:<10.4f} | "
            f"FR: {self.funding_rate:+.4%} | "
            f"OI Ratio: {self.oi_ratio:.2f}x | "
            f"Strength: {self.signal_strength}"
        )


class MarketAnalyzer:
    """
    市场分析器
    
    功能:
    - 读取 CSV 历史数据
    - 数据清洗 (移除无效数据)
    - 计算滚动均值
    - 检测触发条件
    """
    
    def __init__(self):
        self.data_dir = Path(DATA_CONFIG.DATA_DIR)
        self.short_window = THRESHOLDS.OI_SHORT_WINDOW
        self.long_window = THRESHOLDS.OI_LONG_WINDOW
        
        # 普通信号阈值
        self.normal_funding = THRESHOLDS.NORMAL_FUNDING_RATE
        self.normal_oi_ratio = THRESHOLDS.NORMAL_OI_RATIO
        
        # 强信号阈值
        self.strong_funding = THRESHOLDS.STRONG_FUNDING_RATE
        self.strong_oi_ratio = THRESHOLDS.STRONG_OI_RATIO
        
        # 兼容性
        self.funding_threshold = abs(THRESHOLDS.NORMAL_FUNDING_RATE)
        self.oi_surge_ratio = THRESHOLDS.NORMAL_OI_RATIO
    
    def load_symbol_data(self, symbol: str) -> Optional[pd.DataFrame]:
        """
        加载并清洗指定交易对的历史数据
        
        兼容两种 CSV 格式:
        - 旧格式: timestamp, price, open_interest, funding_rate
        - 新格式: timestamp, open, high, low, close, volume, funding_rate, open_interest
        
        Args:
            symbol: 交易对符号
            
        Returns:
            清洗后的 DataFrame 或 None
        """
        csv_path = self.data_dir / f"{symbol}.csv"
        
        if not csv_path.exists():
            logger.debug(f"数据文件不存在: {csv_path}")
            return None
        
        try:
            # 先读取表头判断格式
            with open(csv_path, 'r', encoding='utf-8') as f:
                header_line = f.readline().strip()
                header = header_line.split(',')
            
            # 判断格式并读取
            if 'close' in header:
                # 新格式 (8列) - 跳过格式不匹配的行
                df = pd.read_csv(
                    csv_path, 
                    parse_dates=["timestamp"],
                    on_bad_lines='skip'  # 跳过格式错误的行
                )
                # 统一列名：用 close 作为 price
                if 'price' not in df.columns and 'close' in df.columns:
                    df['price'] = df['close']
            elif 'price' in header:
                # 旧格式 (4列) - 跳过格式不匹配的行
                df = pd.read_csv(
                    csv_path, 
                    parse_dates=["timestamp"],
                    on_bad_lines='skip'
                )
            else:
                logger.warning(f"未知的 CSV 格式: {csv_path}")
                return None
            
            if df.empty:
                logger.debug(f"数据文件为空: {csv_path}")
                return None
            
            # 数据清洗
            df = self._sanitize_data(df, symbol)
            
            if df is None or df.empty:
                return None
            
            # 按时间排序
            df = df.sort_values("timestamp").reset_index(drop=True)
            
            return df
            
        except Exception as e:
            logger.error(f"读取数据文件失败 {csv_path}: {e}")
            return None
    
    def _sanitize_data(self, df: pd.DataFrame, symbol: str) -> Optional[pd.DataFrame]:
        """
        数据清洗
        
        移除:
        - NaN 值
        - 价格为 0 或负数的行
        - OI 为 0 或负数的行
        
        Args:
            df: 原始 DataFrame
            symbol: 交易对符号 (用于日志)
            
        Returns:
            清洗后的 DataFrame
        """
        original_len = len(df)
        
        # 1. 移除必要列中的 NaN
        required_cols = ["timestamp", "price", "open_interest", "funding_rate"]
        for col in required_cols:
            if col not in df.columns:
                logger.warning(f"{symbol}: 缺少必要列 '{col}'")
                return None
        
        df = df.dropna(subset=required_cols)
        
        # 2. 移除价格无效的行
        df = df[df["price"] > 0]
        
        # 3. 移除 OI 无效的行
        df = df[df["open_interest"] > 0]
        
        # 4. 移除重复的时间戳 (保留最新的)
        df = df.drop_duplicates(subset=["timestamp"], keep="last")
        
        cleaned_len = len(df)
        removed = original_len - cleaned_len
        
        if removed > 0:
            logger.debug(f"{symbol}: 清洗移除了 {removed} 行无效数据")
        
        return df
    
    def calculate_oi_metrics(
        self,
        df: pd.DataFrame
    ) -> tuple[float, float, float, float]:
        """
        计算 OI 相关指标 (旧版本 - 兼容)
        
        Args:
            df: 包含历史数据的 DataFrame
            
        Returns:
            (current_oi, short_ma, long_ma, ratio)
        """
        if len(df) < self.short_window:
            current_oi = df["open_interest"].iloc[-1] if len(df) > 0 else 0
            return current_oi, current_oi, current_oi, 1.0
        
        oi_series = df["open_interest"]
        current_oi = oi_series.iloc[-1]
        
        # 计算短期移动平均 (最近 3 个周期)
        short_ma = oi_series.tail(self.short_window).mean()
        
        # 计算长期移动平均 (最近 13 个周期 = 1小时)
        if len(df) >= self.long_window:
            long_ma = oi_series.tail(self.long_window).mean()
        else:
            # 数据不足时使用所有可用数据
            long_ma = oi_series.mean()
        
        # 计算比率 (防止除零)
        ratio = short_ma / long_ma if long_ma > 0 else 1.0
        
        return current_oi, short_ma, long_ma, ratio
    
    def calculate_oi_dual_window(
        self,
        df: pd.DataFrame
    ) -> tuple[float, float, str]:
        """
        计算双窗口 OI 变化 (15分钟 + 1小时)
        
        假设每 5 分钟采集一次数据:
        - 15分钟前 = index -4 (当前 -1, 5分钟前 -2, 10分钟前 -3, 15分钟前 -4)
        - 1小时前 = index -13 (60分钟 / 5分钟 = 12 个周期 + 当前 = -13)
        
        Args:
            df: 包含历史数据的 DataFrame (需要至少 13 行)
            
        Returns:
            (oi_change_15m, oi_change_1h, trigger_type)
            - oi_change_15m: 15分钟变化百分比 (0.1 = 10%)
            - oi_change_1h: 1小时变化百分比 (0.3 = 30%)
            - trigger_type: "15m", "1h", "both", ""
        """
        oi_series = df["open_interest"]
        current_oi = float(oi_series.iloc[-1])
        
        oi_change_15m = 0.0
        oi_change_1h = 0.0
        
        # 计算 15 分钟变化 (需要至少 4 条数据)
        if len(df) >= 4:
            oi_15m_ago = float(oi_series.iloc[-4])
            if oi_15m_ago > 0:
                oi_change_15m = (current_oi - oi_15m_ago) / oi_15m_ago
        
        # 计算 1 小时变化 (需要至少 13 条数据)
        if len(df) >= 13:
            oi_1h_ago = float(oi_series.iloc[-13])
            if oi_1h_ago > 0:
                oi_change_1h = (current_oi - oi_1h_ago) / oi_1h_ago
        
        # 判断触发类型
        trigger_15m_strong = oi_change_15m >= THRESHOLDS.OI_15M_STRONG
        trigger_15m_normal = oi_change_15m >= THRESHOLDS.OI_15M_NORMAL
        trigger_1h_strong = oi_change_1h >= THRESHOLDS.OI_1H_STRONG
        trigger_1h_normal = oi_change_1h >= THRESHOLDS.OI_1H_NORMAL
        
        triggers = []
        if trigger_15m_strong or trigger_15m_normal:
            triggers.append("15m")
        if trigger_1h_strong or trigger_1h_normal:
            triggers.append("1h")
        
        if len(triggers) == 2:
            trigger_type = "both"
        elif len(triggers) == 1:
            trigger_type = triggers[0]
        else:
            trigger_type = ""
        
        return oi_change_15m, oi_change_1h, trigger_type
    
    def check_extreme_funding(self, funding_rate: float) -> bool:
        """
        检查资金费率是否处于极端水平
        
        条件: funding_rate < -0.001 OR funding_rate > 0.001
        """
        return abs(funding_rate) >= self.funding_threshold
    
    def check_oi_surge(self, ratio: float) -> bool:
        """
        检查 OI 是否出现激增
        
        条件: OI_MA_3 / OI_MA_10 > 2.0
        """
        return ratio >= self.oi_surge_ratio
    
    def calculate_signal_strength(
        self,
        is_extreme_funding: bool,
        is_oi_surge: bool,
        funding_rate: float,
        oi_ratio: float
    ) -> str:
        """
        计算信号强度
        
        Returns:
            "STRONG", "MODERATE", "WEAK", or "NONE"
        """
        if is_extreme_funding and is_oi_surge:
            # 两个条件都满足
            if abs(funding_rate) > 0.003 and oi_ratio > 3.0:
                return "STRONG"
            return "MODERATE"
        elif is_extreme_funding or is_oi_surge:
            # 只满足一个条件
            return "WEAK"
        return "NONE"
    
    def determine_trend_and_advice(
        self,
        price_change_pct: float,
        oi_change_pct: float,
        funding_rate: float
    ) -> tuple[str, str]:
        """
        根据价格变化、OI变化和资金费率判断市场趋势并给出建议 (中文版)
        
        Logic Matrix:
        ┌─────────────┬───────────┬─────────────┬────────────────────────────┐
        │ 价格        │ OI        │ 费率        │ 解读                       │
        ├─────────────┼───────────┼─────────────┼────────────────────────────┤
        │ ≤ 0 (下跌)  │ > 0 (增加)│ < -0.05%    │ 吸筹蓄力                   │
        │ > 0 (上涨)  │ > 0 (增加)│ < 0         │ 轧空启动                   │
        │ > 0 (上涨)  │ < 0 (减少)│ any         │ 空头踩踏                   │
        │ < 0 (下跌)  │ < 0 (减少)│ any         │ 多头爆仓                   │
        └─────────────┴───────────┴─────────────┴────────────────────────────┘
        
        Args:
            price_change_pct: 价格变化百分比 (0.05 = 5%)
            oi_change_pct: OI 变化百分比 (0.1 = 10%)
            funding_rate: 资金费率 (-0.001 = -0.1%)
            
        Returns:
            (trend, advice) 元组
        """
        
        # Scenario 1: 吸筹蓄力 (Accumulation)
        # 价格下跌/横盘 + OI 增加 + 负费率 = 空头在建仓，可能是陷阱
        if price_change_pct <= 0 and oi_change_pct > 0 and funding_rate < -0.0005:
            trend = "📉 吸筹蓄力 (空头堆积)"
            advice = "👀 密切关注 / 埋伏突破"
            return trend, advice
        
        # Scenario 2: 轧空启动 (Squeeze Ignition)
        # 价格上涨 + OI 增加 + 负费率 = 挤压开始，空头被动加仓
        if price_change_pct > 0 and oi_change_pct > 0 and funding_rate < 0:
            trend = "🚀 轧空启动 (趋势点火)"
            advice = "🔫 市价做多 / 顺势进场"
            return trend, advice
        
        # Scenario 3: 空头踩踏 (Short Covering / Climax)
        # 价格上涨 + OI 减少 = 空头平仓离场
        if price_change_pct > 0 and oi_change_pct < 0:
            trend = "💥 空头踩踏 (高潮派发)"
            advice = "💰 分批止盈 / 切勿追高"
            return trend, advice
        
        # Scenario 4: 多头爆仓 (Long Liquidation)
        # 价格下跌 + OI 减少 = 多头被清算
        if price_change_pct < 0 and oi_change_pct < 0:
            trend = "🩸 多头爆仓"
            advice = "⛔ 空仓观望 / 远离"
            return trend, advice
        
        # Scenario 5: 多头拥挤 (Long Trap)
        # 价格上涨 + OI 增加 + 正费率 = 多头拥挤
        if price_change_pct > 0 and oi_change_pct > 0 and funding_rate > 0.0005:
            trend = "⚠️ 多头拥挤 (警惕回调)"
            advice = "🛡️ 谨慎追多 / 收紧止损"
            return trend, advice
        
        # Default: 无明确趋势
        trend = "⚖️ 震荡整理 (方向不明)"
        advice = "⏳ 等待明确信号"
        return trend, advice
    
    def analyze_symbol(
        self,
        symbol: str,
        current_data: Optional[dict] = None
    ) -> Optional[SqueezeSignal]:
        """
        分析单个交易对
        
        Args:
            symbol: 交易对符号
            current_data: 当前实时数据 (可选)
            
        Returns:
            SqueezeSignal 或 None
        """
        # 加载并清洗历史数据
        df = self.load_symbol_data(symbol)
        
        if df is None or len(df) < self.short_window:
            logger.debug(f"{symbol}: 数据不足，跳过分析 (需要至少 {self.short_window} 条)")
            return None
        
        # 获取最新数据
        latest = df.iloc[-1]
        price = float(latest["price"])
        funding_rate = float(latest["funding_rate"])
        
        # 如果提供了实时数据，优先使用
        if current_data:
            price = current_data.get("price", price)
            funding_rate = current_data.get("funding_rate", funding_rate)
        
        # 计算 OI 指标 (旧版)
        current_oi, short_ma, long_ma, oi_ratio = self.calculate_oi_metrics(df)
        
        # 计算双窗口 OI 变化 (15m + 1h)
        oi_change_15m, oi_change_1h, oi_trigger = self.calculate_oi_dual_window(df)
        
        # 检查触发条件 (包括新的双窗口逻辑)
        is_extreme_funding = self.check_extreme_funding(funding_rate)
        is_oi_surge = self.check_oi_surge(oi_ratio)
        
        # 新增: 检查 15m 和 1h OI 触发
        is_oi_15m_trigger = oi_change_15m >= THRESHOLDS.OI_15M_NORMAL
        is_oi_1h_trigger = oi_change_1h >= THRESHOLDS.OI_1H_NORMAL
        
        # 如果有任何 OI 时间窗口触发，也算作 OI surge
        if is_oi_15m_trigger or is_oi_1h_trigger:
            is_oi_surge = True
        
        # 计算信号强度
        signal_strength = self.calculate_signal_strength(
            is_extreme_funding, is_oi_surge, funding_rate, oi_ratio
        )
        
        # 只有满足至少一个条件时才返回信号
        if signal_strength == "NONE":
            return None
        
        # 计算严重程度 (STRONG / NORMAL) - 使用双窗口逻辑
        severity = self._calculate_severity(
            funding_rate, oi_ratio, oi_change_15m, oi_change_1h
        )
        
        # ====== 计算价格变化和 OI 变化 ======
        price_change_pct = 0.0
        oi_change_pct = 0.0
        
        # 尝试获取历史数据来计算变化
        if len(df) >= 2:
            # 使用第一条数据作为参考（约 15-30 分钟前的数据）
            prev_price = float(df.iloc[0]["price"]) if "price" in df.columns else float(df.iloc[0]["close"])
            if prev_price > 0:
                price_change_pct = (price - prev_price) / prev_price
        
        # 计算 OI 变化 (短期 MA vs 长期 MA)
        if long_ma > 0:
            oi_change_pct = (short_ma - long_ma) / long_ma
        
        # 也可以使用 current_data 中的 price_change_percent
        if current_data and "price_change_percent" in current_data:
            # Binance 返回的是百分比数值（如 -2.5 表示 -2.5%）
            price_change_pct = current_data["price_change_percent"] / 100
        
        # ====== 判断趋势和建议 ======
        trend, advice = self.determine_trend_and_advice(
            price_change_pct, oi_change_pct, funding_rate
        )
        
        return SqueezeSignal(
            symbol=symbol,
            timestamp=datetime.now(timezone.utc),
            price=price,
            funding_rate=funding_rate,
            current_oi=current_oi,
            oi_short_ma=short_ma,
            oi_long_ma=long_ma,
            oi_ratio=oi_ratio,
            is_extreme_funding=is_extreme_funding,
            is_oi_surge=is_oi_surge,
            signal_strength=signal_strength,
            severity=severity,
            price_change_pct=price_change_pct,
            oi_change_pct=oi_change_pct,
            trend=trend,
            advice=advice,
            oi_change_15m=oi_change_15m,
            oi_change_1h=oi_change_1h,
            oi_trigger=oi_trigger,
        )
    
    def _calculate_severity(
        self,
        funding_rate: float,
        oi_ratio: float,
        oi_change_15m: float = 0.0,
        oi_change_1h: float = 0.0
    ) -> str:
        """
        计算信号严重程度 (双窗口逻辑)
        
        STRONG 触发条件 (OR):
            - 资金费率 <= STRONG_FUNDING_RATE (强负费率)
            - 或 资金费率 >= |STRONG_FUNDING_RATE| (强正费率)
            - 或 OI 15分钟变化 >= 12%
            - 或 OI 1小时变化 >= 30%
        
        NORMAL 触发条件 (OR):
            - 资金费率达到普通阈值
            - 或 OI 15分钟变化 >= 5%
            - 或 OI 1小时变化 >= 15%
        
        Returns:
            "STRONG" or "NORMAL"
        """
        # ============ STRONG 级别检查 ============
        # 强负资金费率 (空头极度拥挤)
        if funding_rate <= THRESHOLDS.STRONG_FUNDING_THRESHOLD:
            return "STRONG"
        
        # 强正资金费率 (多头极度拥挤)
        if funding_rate >= abs(THRESHOLDS.STRONG_FUNDING_THRESHOLD):
            return "STRONG"
        
        # OI 15分钟快速增长 (>= 12%)
        if oi_change_15m >= THRESHOLDS.OI_15M_STRONG:
            return "STRONG"
        
        # OI 1小时持续趋势 (>= 30%)
        if oi_change_1h >= THRESHOLDS.OI_1H_STRONG:
            return "STRONG"
        
        # OI 比率 (旧逻辑兼容)
        if oi_ratio > THRESHOLDS.STRONG_OI_THRESHOLD:
            return "STRONG"
        
        return "NORMAL"
    
    def apply_btc_veto(
        self,
        signals: list[SqueezeSignal],
        btc_change_pct: float
    ) -> list[SqueezeSignal]:
        """
        应用 BTC Veto 安全检查
        
        当 BTC 大跌时:
        - 抑制所有 NORMAL 告警
        - STRONG 告警修改建议，警告陷阱风险
        
        Args:
            signals: 信号列表
            btc_change_pct: BTC 价格变化百分比
            
        Returns:
            过滤后的信号列表
        """
        if not THRESHOLDS.BTC_VETO_ENABLED:
            return signals
        
        # 检查是否触发 BTC Veto (BTC 下跌超过阈值)
        btc_dumping = btc_change_pct < THRESHOLDS.BTC_VETO_THRESHOLD
        
        if not btc_dumping:
            # BTC 正常，不需要 Veto
            for signal in signals:
                signal.btc_change_pct = btc_change_pct
            return signals
        
        logger.warning(f"⚠️ BTC VETO 触发! BTC 变化: {btc_change_pct*100:.2f}%")
        
        filtered_signals = []
        
        for signal in signals:
            signal.btc_change_pct = btc_change_pct
            signal.btc_veto = True
            
            if signal.severity == "STRONG":
                # STRONG 信号：保留但修改建议
                signal.advice = "🛡️ 暂停交易 / 风险极高"
                signal.trend = "⛈️ 大盘暴跌 (BTC预警)"
                filtered_signals.append(signal)
                logger.debug(f"⚠️ {signal.symbol}: STRONG 信号保留但添加警告")
            else:
                # NORMAL 信号：抑制
                logger.debug(f"🚫 {signal.symbol}: NORMAL 信号被 BTC Veto 抑制")
        
        suppressed = len(signals) - len(filtered_signals)
        if suppressed > 0:
            logger.info(f"🚫 BTC Veto 抑制了 {suppressed} 个 NORMAL 信号")
        
        return filtered_signals
    
    def analyze_all(
        self,
        current_data: Optional[dict[str, dict]] = None,
        min_strength: str = "WEAK"
    ) -> list[SqueezeSignal]:
        """
        分析所有交易对
        
        Args:
            current_data: 当前实时数据 {symbol: {price, funding_rate, ...}}
            min_strength: 最小信号强度过滤
            
        Returns:
            符合条件的信号列表
        """
        signals = []
        strength_order = {"WEAK": 1, "MODERATE": 2, "STRONG": 3}
        min_strength_value = strength_order.get(min_strength, 1)
        
        # 获取所有 CSV 文件
        if not self.data_dir.exists():
            logger.warning(f"数据目录不存在: {self.data_dir}")
            return signals
        
        csv_files = list(self.data_dir.glob("*.csv"))
        
        if not csv_files:
            logger.warning("没有找到任何数据文件")
            return signals
        
        logger.info(f"🔍 正在分析 {len(csv_files)} 个交易对...")
        
        for csv_file in csv_files:
            symbol = csv_file.stem
            
            symbol_data = current_data.get(symbol) if current_data else None
            signal = self.analyze_symbol(symbol, symbol_data)
            
            if signal:
                signal_value = strength_order.get(signal.signal_strength, 0)
                if signal_value >= min_strength_value:
                    signals.append(signal)
                    logger.debug(
                        f"检测到信号: {symbol} | "
                        f"强度: {signal.signal_strength} | "
                        f"FR: {signal.funding_rate:.4%} | "
                        f"OI Ratio: {signal.oi_ratio:.2f}x"
                    )
        
        # 按信号强度和 OI 比率排序
        signals.sort(
            key=lambda s: (
                strength_order.get(s.signal_strength, 0),
                s.oi_ratio
            ),
            reverse=True
        )
        
        logger.info(f"✅ 分析完成! 共检测到 {len(signals)} 个信号")
        return signals
    
    def get_market_summary(self, current_data: dict[str, dict]) -> dict:
        """
        获取市场概况
        
        Args:
            current_data: 当前实时数据
            
        Returns:
            市场统计摘要
        """
        total_symbols = len(current_data)
        
        positive_funding = 0
        negative_funding = 0
        extreme_positive = 0
        extreme_negative = 0
        
        for symbol, data in current_data.items():
            fr = data.get("funding_rate", 0)
            if fr > 0:
                positive_funding += 1
                if fr > self.funding_threshold:
                    extreme_positive += 1
            elif fr < 0:
                negative_funding += 1
                if fr < -self.funding_threshold:
                    extreme_negative += 1
        
        return {
            "total_symbols": total_symbols,
            "positive_funding": positive_funding,
            "negative_funding": negative_funding,
            "extreme_positive_funding": extreme_positive,
            "extreme_negative_funding": extreme_negative,
            "market_sentiment": self._calculate_sentiment(
                positive_funding, negative_funding, total_symbols
            ),
        }
    
    def _calculate_sentiment(
        self,
        positive: int,
        negative: int,
        total: int
    ) -> str:
        """计算市场情绪"""
        if total == 0:
            return "NEUTRAL"
        
        positive_ratio = positive / total
        negative_ratio = negative / total
        
        if positive_ratio > 0.7:
            return "🟢 EXTREMELY BULLISH"
        elif positive_ratio > 0.55:
            return "🟢 BULLISH"
        elif negative_ratio > 0.7:
            return "🔴 EXTREMELY BEARISH"
        elif negative_ratio > 0.55:
            return "🔴 BEARISH"
        return "⚪ NEUTRAL"


# ============================================================================
# 测试代码
# ============================================================================

def test_analyzer():
    """测试分析器"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(message)s"
    )
    
    analyzer = MarketAnalyzer()
    signals = analyzer.analyze_all()
    
    print(f"\n{'=' * 70}")
    print(f"📊 检测到 {len(signals)} 个信号")
    print("=" * 70)
    
    # 按强度分组显示
    strong = [s for s in signals if s.signal_strength == "STRONG"]
    moderate = [s for s in signals if s.signal_strength == "MODERATE"]
    weak = [s for s in signals if s.signal_strength == "WEAK"]
    
    if strong:
        print("\n🔴 STRONG SIGNALS:")
        for signal in strong:
            print(signal.to_alert_message())
    
    if moderate:
        print("\n🟠 MODERATE SIGNALS:")
        for signal in moderate[:5]:
            print(signal.to_short_message())
    
    if weak:
        print(f"\n🟡 WEAK SIGNALS: {len(weak)} 个")
        for signal in weak[:3]:
            print(signal.to_short_message())


if __name__ == "__main__":
    test_analyzer()
