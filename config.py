"""
Short Squeeze Monitor - Configuration
======================================
使用 python-dotenv 从 .env 文件加载配置

所有配置参数都可以通过 .env 文件设置
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Optional

from dotenv import load_dotenv

# ============================================================================
# 加载 .env 文件
# ============================================================================

PROJECT_ROOT = Path(__file__).parent
ENV_FILE = PROJECT_ROOT / ".env"

load_dotenv(ENV_FILE)


def get_env(key: str, default: str = "") -> str:
    """获取环境变量"""
    return os.getenv(key, default)


def get_env_int(key: str, default: int = 0) -> int:
    """获取整数类型环境变量"""
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        return default


def get_env_float(key: str, default: float = 0.0) -> float:
    """获取浮点数类型环境变量"""
    try:
        return float(os.getenv(key, str(default)))
    except ValueError:
        return default


def get_env_bool(key: str, default: bool = False) -> bool:
    """获取布尔类型环境变量"""
    value = os.getenv(key, str(default)).lower()
    return value in ("true", "1", "yes", "on")


# ============================================================================
# Binance Futures API Endpoints
# ============================================================================

BASE_URL: Final[str] = "https://fapi.binance.com"

API_ENDPOINTS: Final[dict] = {
    "exchange_info": "/fapi/v1/exchangeInfo",
    "premium_index": "/fapi/v1/premiumIndex",
    "ticker_24hr": "/fapi/v1/ticker/24hr",
    "open_interest": "/fapi/v1/openInterest",
    "mark_price": "/fapi/v1/markPrice",
    "klines": "/fapi/v1/klines",
    # 高级指标 (按需获取，不在主循环中调用)
    "long_short_ratio": "/futures/data/globalLongShortAccountRatio",
    "top_trader_ratio": "/futures/data/topLongShortPositionRatio",
    "taker_buy_sell_ratio": "/futures/data/takerlongshortRatio",
}


# ============================================================================
# 网络配置
# ============================================================================

def _get_proxy_url() -> Optional[str]:
    """获取代理 URL，如果为空则返回 None (直连模式)"""
    proxy = get_env("PROXY_URL", "").strip()
    return proxy if proxy else None


@dataclass
class NetworkConfig:
    """网络请求配置"""
    
    # 代理 URL (可选 - 为空时直连，AWS 部署时留空)
    PROXY_URL: Optional[str] = _get_proxy_url()
    
    # HTTP 请求超时 (秒)
    HTTP_TIMEOUT: int = get_env_int("HTTP_TIMEOUT", 15)
    
    # 最大并发请求数 (避免触发 Binance 429)
    CONCURRENCY_LIMIT: int = get_env_int("CONCURRENCY_LIMIT", 5)
    
    # 遇到 429 错误时的等待时间 (秒)
    RATE_LIMIT_WAIT: int = get_env_int("RATE_LIMIT_WAIT", 5)
    
    # 最大重试次数
    MAX_RETRIES: int = get_env_int("MAX_RETRIES", 3)
    
    # Binance API 密钥 (可选，提高速率限制)
    API_KEY: Optional[str] = get_env("BINANCE_API_KEY") or None
    API_SECRET: Optional[str] = get_env("BINANCE_API_SECRET") or None
    
    @property
    def is_direct_mode(self) -> bool:
        """是否为直连模式 (无代理)"""
        return self.PROXY_URL is None
    
    @property
    def network_mode(self) -> str:
        """网络模式描述"""
        if self.is_direct_mode:
            return "🌐 Direct (无代理)"
        return f"🔌 Proxy ({self.PROXY_URL})"


# ============================================================================
# Telegram 通知配置
# ============================================================================

@dataclass
class TelegramConfig:
    """Telegram 通知配置"""
    
    # Bot Token (从 @BotFather 获取)
    BOT_TOKEN: Optional[str] = get_env("TELEGRAM_BOT_TOKEN") or None
    
    # Chat ID (用户ID、群组ID 或频道ID)
    CHAT_ID: Optional[str] = get_env("TELEGRAM_CHAT_ID") or None
    
    # 是否启用通知
    ENABLED: bool = bool(get_env("TELEGRAM_BOT_TOKEN") and get_env("TELEGRAM_CHAT_ID"))
    
    # 每轮最大告警数量 (避免刷屏)
    MAX_ALERTS_PER_ROUND: int = get_env_int("TELEGRAM_MAX_ALERTS", 5)
    
    # 只发送强信号
    STRONG_ONLY: bool = get_env_bool("TELEGRAM_STRONG_ONLY", False)
    
    # 告警冷却时间 (分钟) - 同一信号在此时间内不重复发送
    ALERT_COOLDOWN_MINUTES: int = get_env_int("ALERT_COOLDOWN_MINUTES", 60)


# ============================================================================
# 策略阈值配置
# ============================================================================

@dataclass
class Thresholds:
    """
    策略阈值配置
    
    信号分为两级:
    - 🟠 NORMAL: 普通信号，开始关注
    - 🔴 STRONG: 强烈信号，必须置顶
    """
    
    # ==================== 基础过滤 ====================
    # 24小时最小交易量 (USDT) - 过滤低流动性土狗，防止滑点
    MIN_VOLUME_24H: float = get_env_float("MIN_VOLUME_USDT", 15_000_000)  # 1500万 U
    
    # ==================== 🟠 普通信号 (Normal) ====================
    # 满足这个条件就发通知，让你开始关注
    
    # 资金费率阈值 (开始出现看空情绪)
    NORMAL_FUNDING_RATE: float = get_env_float("NORMAL_FUNDING_RATE", -0.0005)  # -0.05%
    
    # OI 增长比率 (有资金流入)
    NORMAL_OI_RATIO: float = get_env_float("NORMAL_OI_RATIO", 1.2)  # 1.2倍 (20% 增幅)
    
    # ==================== 🔴 强烈信号 (STRONG) ====================
    # 满足这个条件必须置顶！典型的轧空前兆
    
    # 资金费率阈值 (极端负费率，空头极其拥挤)
    STRONG_FUNDING_RATE: float = get_env_float("STRONG_FUNDING_RATE", -0.0010)  # -0.10%
    
    # OI 增长比率 (持仓翻倍，庄家大举进场)
    STRONG_OI_RATIO: float = get_env_float("STRONG_OI_RATIO", 2.0)  # 2.0倍
    
    # ==================== OI 滚动窗口 ====================
    OI_SHORT_WINDOW: int = get_env_int("OI_SHORT_WINDOW", 3)   # 短期窗口 (最近3个周期)
    OI_LONG_WINDOW: int = get_env_int("OI_LONG_WINDOW", 13)    # 长期窗口 (13个周期 = 1小时, 每5分钟1个)
    
    # ==================== OI 双窗口阈值 (15m + 1h) ====================
    # 15 分钟快速增长检测
    OI_15M_STRONG: float = get_env_float("OI_15M_STRONG", 0.12)   # 12% = STRONG
    OI_15M_NORMAL: float = get_env_float("OI_15M_NORMAL", 0.05)   # 5%  = NORMAL
    
    # 1 小时持续趋势检测
    OI_1H_STRONG: float = get_env_float("OI_1H_STRONG", 0.30)     # 30% = STRONG
    OI_1H_NORMAL: float = get_env_float("OI_1H_NORMAL", 0.15)     # 15% = NORMAL
    
    # ==================== BTC Veto (安全检查) ====================
    # 当 BTC 大跌时抑制告警，避免陷阱
    BTC_VETO_THRESHOLD: float = get_env_float("BTC_VETO_THRESHOLD", -0.01)  # -1% = 触发 Veto
    BTC_VETO_ENABLED: bool = get_env_bool("BTC_VETO_ENABLED", True)
    
    # ==================== 兼容性别名 ====================
    @property
    def FUNDING_RATE_EXTREME(self) -> float:
        """兼容旧代码"""
        return abs(self.NORMAL_FUNDING_RATE)
    
    @property
    def OI_SURGE_RATIO(self) -> float:
        """兼容旧代码"""
        return self.NORMAL_OI_RATIO
    
    @property
    def STRONG_FUNDING_THRESHOLD(self) -> float:
        """兼容旧代码"""
        return self.STRONG_FUNDING_RATE
    
    @property
    def STRONG_OI_THRESHOLD(self) -> float:
        """兼容旧代码"""
        return self.STRONG_OI_RATIO


# ============================================================================
# 数据存储配置
# ============================================================================

@dataclass
class DataConfig:
    """数据存储配置"""
    
    # 数据存储目录
    DATA_DIR: str = get_env("DATA_DIR", "data")
    
    # CSV 列名
    CSV_COLUMNS: tuple = ("timestamp", "price", "open_interest", "funding_rate")
    
    # 监控轮询间隔 (秒)
    CHECK_INTERVAL: int = get_env_int("CHECK_INTERVAL_SECONDS", 300)  # 5分钟


# ============================================================================
# 日志配置
# ============================================================================

@dataclass
class LogConfig:
    """日志配置"""
    
    LOG_FORMAT: str = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    LOG_DATE_FORMAT: str = "%Y-%m-%d %H:%M:%S"
    LOG_LEVEL: str = get_env("LOG_LEVEL", "INFO")


# ============================================================================
# 实例化配置对象
# ============================================================================

NETWORK = NetworkConfig()
TELEGRAM = TelegramConfig()
THRESHOLDS = Thresholds()
DATA_CONFIG = DataConfig()
LOG_CONFIG = LogConfig()


# ============================================================================
# 告警消息模板
# ============================================================================

ALERT_TEMPLATES: Final[dict] = {
    "short_squeeze": """
🚨 SHORT SQUEEZE ALERT 🚨
━━━━━━━━━━━━━━━━━━━━━━━━━━
Symbol: {symbol}
Price: ${price:.4f}
━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 Funding Rate: {funding_rate:.4%}
   → Status: {funding_status}
━━━━━━━━━━━━━━━━━━━━━━━━━━
📈 OI Analysis:
   → Current OI: {current_oi:,.0f}
   → Short MA ({short_window}): {oi_short_ma:,.0f}
   → Long MA ({long_window}): {oi_long_ma:,.0f}
   → Surge Ratio: {oi_ratio:.2f}x
━━━━━━━━━━━━━━━━━━━━━━━━━━
⏰ Time: {timestamp}
""",
}


# ============================================================================
# 配置验证
# ============================================================================

def validate_config() -> list[str]:
    """
    验证配置是否有效
    
    Returns:
        错误消息列表 (空列表表示配置有效)
    """
    errors = []
    
    if NETWORK.HTTP_TIMEOUT <= 0:
        errors.append("HTTP_TIMEOUT 必须大于 0")
    
    if NETWORK.CONCURRENCY_LIMIT <= 0:
        errors.append("CONCURRENCY_LIMIT 必须大于 0")
    
    if THRESHOLDS.MIN_VOLUME_24H < 0:
        errors.append("MIN_VOLUME_USDT 不能为负数")
    
    if DATA_CONFIG.CHECK_INTERVAL < 60:
        errors.append("CHECK_INTERVAL_SECONDS 建议不低于 60 秒")
    
    return errors


def print_config() -> None:
    """打印当前配置 (用于调试)"""
    print("\n" + "=" * 65)
    print("📋 Short Squeeze Monitor - 当前配置")
    print("=" * 65)
    
    print("\n🌐 网络配置:")
    print(f"   模式: {NETWORK.network_mode}")
    print(f"   超时: {NETWORK.HTTP_TIMEOUT}s")
    print(f"   并发: {NETWORK.CONCURRENCY_LIMIT}")
    
    print("\n📊 策略参数:")
    print(f"   最小交易量: {THRESHOLDS.MIN_VOLUME_24H/1e6:.0f}M USDT")
    print(f"   轮询间隔: {DATA_CONFIG.CHECK_INTERVAL}s ({DATA_CONFIG.CHECK_INTERVAL//60}分钟)")
    
    print("\n🟠 普通信号阈值:")
    print(f"   资金费率: {THRESHOLDS.NORMAL_FUNDING_RATE:.4%}")
    print(f"   OI 比率: {THRESHOLDS.NORMAL_OI_RATIO:.1f}x")
    
    print("\n🔴 强烈信号阈值:")
    print(f"   资金费率: {THRESHOLDS.STRONG_FUNDING_RATE:.4%}")
    print(f"   OI 比率: {THRESHOLDS.STRONG_OI_RATIO:.1f}x")
    
    print("\n📱 Telegram:")
    print(f"   状态: {'✅ 已启用' if TELEGRAM.ENABLED else '❌ 未配置'}")
    if TELEGRAM.ENABLED:
        print(f"   Chat ID: {TELEGRAM.CHAT_ID}")
        print(f"   最大告警: {TELEGRAM.MAX_ALERTS_PER_ROUND}/轮")
        print(f"   冷却时间: {TELEGRAM.ALERT_COOLDOWN_MINUTES}分钟")
        print(f"   仅强信号: {'是' if TELEGRAM.STRONG_ONLY else '否'}")
    
    print("\n" + "=" * 65)
