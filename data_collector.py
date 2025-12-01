"""
Short Squeeze Monitor - Data Collector
=======================================
异步数据采集器，通过代理从 Binance Futures API 获取数据
"""

import asyncio
import csv
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Any

import aiohttp
import pandas as pd

from config import (
    BASE_URL,
    API_ENDPOINTS,
    NETWORK,
    THRESHOLDS,
    DATA_CONFIG,
)

logger = logging.getLogger(__name__)


class IPBannedError(Exception):
    """IP 被封禁异常"""
    pass


class BinanceDataCollector:
    """
    Binance Futures 数据采集器
    
    特性:
    - 所有请求通过代理
    - 使用信号量控制并发
    - 自动重试和错误处理
    """
    
    def __init__(self):
        self.base_url = BASE_URL
        self.endpoints = API_ENDPOINTS
        self.proxy_url = NETWORK.PROXY_URL  # None 表示直连
        self.timeout = aiohttp.ClientTimeout(total=NETWORK.HTTP_TIMEOUT)
        self.semaphore = asyncio.Semaphore(NETWORK.CONCURRENCY_LIMIT)
        self.max_retries = NETWORK.MAX_RETRIES
        self.rate_limit_wait = NETWORK.RATE_LIMIT_WAIT
        self.session: Optional[aiohttp.ClientSession] = None
        self._is_banned = False
        
        self._ensure_data_dir()
        
        logger.info(f"数据采集器初始化完成")
        logger.info(f"  → 网络模式: {NETWORK.network_mode}")
        logger.info(f"  → 超时: {NETWORK.HTTP_TIMEOUT}s")
        logger.info(f"  → 并发限制: {NETWORK.CONCURRENCY_LIMIT}")
    
    def _ensure_data_dir(self) -> None:
        """确保数据目录存在"""
        Path(DATA_CONFIG.DATA_DIR).mkdir(parents=True, exist_ok=True)
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        self.session = aiohttp.ClientSession(timeout=self.timeout)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器退出"""
        if self.session:
            await self.session.close()
    
    async def fetch_with_retry(
        self,
        endpoint: str,
        params: Optional[dict] = None,
    ) -> Optional[Any]:
        """
        带重试机制的请求方法
        
        根据配置通过代理或直连发送请求，处理各种错误情况:
        - 429: 速率限制，等待后重试
        - 418/403: IP被封禁，停止所有请求
        - 网络错误: 重试
        
        Args:
            endpoint: API 端点路径
            params: 请求参数
            
        Returns:
            JSON 响应数据或 None
            
        Raises:
            IPBannedError: 当 IP 被封禁时
        """
        if self._is_banned:
            raise IPBannedError("IP 已被封禁，无法继续请求")
        
        url = f"{self.base_url}{endpoint}"
        
        # 构建请求参数 (代理为可选)
        request_kwargs = {"params": params}
        if self.proxy_url:
            request_kwargs["proxy"] = self.proxy_url
        
        for attempt in range(self.max_retries):
            async with self.semaphore:
                try:
                    async with self.session.get(url, **request_kwargs) as response:
                        
                        # 成功响应
                        if response.status == 200:
                            return await response.json()
                        
                        # 速率限制 - 等待后重试
                        elif response.status == 429:
                            retry_after = int(response.headers.get("Retry-After", self.rate_limit_wait))
                            logger.warning(
                                f"⚠️ 速率限制 (429) | 等待 {retry_after}s | "
                                f"尝试 {attempt + 1}/{self.max_retries}"
                            )
                            await asyncio.sleep(retry_after)
                            continue
                        
                        # IP 被封禁 - 停止所有请求
                        elif response.status in (418, 403):
                            self._is_banned = True
                            error_text = await response.text()
                            logger.error(
                                f"🚫 IP 被封禁! 状态码: {response.status} | "
                                f"响应: {error_text[:200]}"
                            )
                            raise IPBannedError(f"IP 被封禁: {response.status}")
                        
                        # 其他错误
                        else:
                            error_text = await response.text()
                            logger.error(
                                f"❌ API 错误 | {url} | "
                                f"状态码: {response.status} | "
                                f"响应: {error_text[:200]}"
                            )
                            # 某些错误不需要重试
                            if response.status >= 400 and response.status < 500:
                                return None
                
                except aiohttp.ClientProxyConnectionError as e:
                    logger.error(
                        f"🔌 代理连接失败 | {self.proxy_url} | "
                        f"尝试 {attempt + 1}/{self.max_retries} | {e}"
                    )
                    await asyncio.sleep(2 ** attempt)
                
                except aiohttp.ClientConnectorError as e:
                    logger.error(
                        f"🌐 网络连接失败 | "
                        f"尝试 {attempt + 1}/{self.max_retries} | {e}"
                    )
                    await asyncio.sleep(2 ** attempt)
                
                except aiohttp.ClientError as e:
                    logger.error(
                        f"📡 请求失败 | "
                        f"尝试 {attempt + 1}/{self.max_retries} | {e}"
                    )
                    await asyncio.sleep(2 ** attempt)
                
                except asyncio.TimeoutError:
                    logger.error(
                        f"⏱️ 请求超时 | {url} | "
                        f"尝试 {attempt + 1}/{self.max_retries}"
                    )
                    await asyncio.sleep(2 ** attempt)
        
        logger.error(f"❌ 请求失败，已达最大重试次数: {url}")
        return None
    
    async def get_usdt_pairs(self) -> list[str]:
        """
        获取所有 USDT 永续合约交易对
        
        Returns:
            交易对符号列表
        """
        logger.info("📋 获取所有 USDT 交易对...")
        
        data = await self.fetch_with_retry(self.endpoints["exchange_info"])
        
        if not data or "symbols" not in data:
            logger.error("无法获取交易所信息")
            return []
        
        usdt_pairs = [
            symbol["symbol"]
            for symbol in data["symbols"]
            if (
                symbol.get("quoteAsset") == "USDT"
                and symbol.get("contractType") == "PERPETUAL"
                and symbol.get("status") == "TRADING"
            )
        ]
        
        logger.info(f"✅ 找到 {len(usdt_pairs)} 个 USDT 永续合约")
        return usdt_pairs
    
    async def get_24hr_tickers(self) -> dict[str, dict]:
        """
        获取所有交易对的 24 小时行情数据 (包含 OHLCV)
        
        Returns:
            {symbol: {open, high, low, close, volume, quote_volume, ...}}
        """
        logger.info("📊 获取 24 小时行情数据...")
        
        data = await self.fetch_with_retry(self.endpoints["ticker_24hr"])
        
        if not data:
            logger.error("无法获取行情数据")
            return {}
        
        result = {}
        for item in data:
            try:
                result[item["symbol"]] = {
                    # OHLCV 数据
                    "open": float(item.get("openPrice", 0)),
                    "high": float(item.get("highPrice", 0)),
                    "low": float(item.get("lowPrice", 0)),
                    "close": float(item.get("lastPrice", 0)),  # lastPrice = close
                    "volume": float(item.get("volume", 0)),
                    # 其他数据
                    "last_price": float(item["lastPrice"]),
                    "quote_volume": float(item["quoteVolume"]),
                    "price_change_percent": float(item["priceChangePercent"]),
                }
            except (KeyError, ValueError) as e:
                logger.debug(f"解析行情数据失败: {item.get('symbol', 'unknown')} | {e}")
        
        logger.info(f"✅ 获取到 {len(result)} 个交易对的行情数据")
        return result
    
    async def get_funding_rates(self) -> dict[str, float]:
        """
        获取所有交易对的资金费率
        
        Returns:
            {symbol: funding_rate}
        """
        logger.info("💰 获取资金费率...")
        
        data = await self.fetch_with_retry(self.endpoints["premium_index"])
        
        if not data:
            logger.error("无法获取资金费率")
            return {}
        
        result = {}
        for item in data:
            try:
                if "lastFundingRate" in item:
                    result[item["symbol"]] = float(item["lastFundingRate"])
            except (KeyError, ValueError):
                continue
        
        logger.info(f"✅ 获取到 {len(result)} 个交易对的资金费率")
        return result
    
    async def get_open_interest(self, symbol: str) -> Optional[float]:
        """
        获取单个交易对的持仓量 (OI)
        
        Args:
            symbol: 交易对符号
            
        Returns:
            持仓量或 None
        """
        try:
            data = await self.fetch_with_retry(
                self.endpoints["open_interest"],
                params={"symbol": symbol}
            )
            
            if data and "openInterest" in data:
                return float(data["openInterest"])
        except IPBannedError:
            raise
        except Exception as e:
            logger.debug(f"获取 {symbol} OI 失败: {e}")
        
        return None
    
    async def get_all_open_interests(
        self,
        symbols: list[str]
    ) -> dict[str, float]:
        """
        并发获取多个交易对的持仓量
        
        使用信号量控制并发数量，避免触发速率限制
        
        Args:
            symbols: 交易对符号列表
            
        Returns:
            {symbol: open_interest}
        """
        logger.info(f"📈 获取 {len(symbols)} 个交易对的持仓量 (并发限制: {NETWORK.CONCURRENCY_LIMIT})...")
        
        async def fetch_single_oi(symbol: str) -> tuple[str, Optional[float]]:
            """获取单个交易对的 OI"""
            try:
                oi = await self.get_open_interest(symbol)
                return symbol, oi
            except IPBannedError:
                raise
            except Exception as e:
                logger.debug(f"获取 {symbol} OI 异常: {e}")
                return symbol, None
        
        # 并发获取所有 OI
        tasks = [fetch_single_oi(symbol) for symbol in symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        oi_data = {}
        failed_count = 0
        
        for result in results:
            if isinstance(result, IPBannedError):
                raise result
            elif isinstance(result, Exception):
                failed_count += 1
                logger.debug(f"OI 获取异常: {result}")
            elif result[1] is not None:
                symbol, oi = result
                oi_data[symbol] = oi
            else:
                failed_count += 1
        
        logger.info(f"✅ 成功获取 {len(oi_data)} 个 | 失败 {failed_count} 个")
        return oi_data
    
    def filter_by_volume(
        self,
        symbols: list[str],
        tickers: dict[str, dict],
        min_volume: float = None
    ) -> list[str]:
        """
        根据 24 小时交易量过滤交易对
        
        Args:
            symbols: 交易对符号列表
            tickers: 行情数据
            min_volume: 最小交易量阈值 (USDT)
            
        Returns:
            过滤后的交易对列表
        """
        if min_volume is None:
            min_volume = THRESHOLDS.MIN_VOLUME_24H
        
        filtered = [
            symbol
            for symbol in symbols
            if (
                symbol in tickers
                and tickers[symbol]["quote_volume"] >= min_volume
            )
        ]
        
        # ⚠️ 确保 BTCUSDT 始终被包含 (用于 BTC Veto 安全检查)
        if "BTCUSDT" not in filtered and "BTCUSDT" in symbols:
            filtered.append("BTCUSDT")
            logger.debug("📌 强制添加 BTCUSDT (用于 BTC Veto)")
        
        logger.info(
            f"🔍 交易量过滤: {len(symbols)} → {len(filtered)} "
            f"(阈值: {min_volume/1e6:.1f}M USDT)"
        )
        
        return filtered
    
    def get_btc_change_pct(self, tickers: dict) -> float:
        """
        获取 BTC 的价格变化百分比 (24h)
        
        Args:
            tickers: 行情数据
            
        Returns:
            价格变化百分比 (0.05 = 5%, -0.01 = -1%)
        """
        if "BTCUSDT" not in tickers:
            logger.warning("⚠️ 无法获取 BTCUSDT 数据")
            return 0.0
        
        btc_data = tickers["BTCUSDT"]
        # price_change_percent 是 Binance 返回的 24h 变化，如 -2.5 表示 -2.5%
        change_pct = btc_data.get("price_change_percent", 0) / 100
        return change_pct
    
    def save_to_csv(
        self,
        symbol: str,
        data: dict,
        timestamp: Optional[datetime] = None
    ) -> bool:
        """
        将完整数据追加保存到 CSV 文件
        
        列结构: timestamp, open, high, low, close, volume, funding_rate, open_interest
        
        Args:
            symbol: 交易对符号
            data: 数据字典 {open, high, low, close, volume, funding_rate, open_interest, ...}
            timestamp: 时间戳
            
        Returns:
            是否保存成功
        """
        try:
            if timestamp is None:
                timestamp = datetime.now(timezone.utc)
            
            csv_path = Path(DATA_CONFIG.DATA_DIR) / f"{symbol}.csv"
            
            # 构建行数据 (标准 OHLCV + 指标)
            row_data = {
                "timestamp": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                "open": data.get("open", 0),
                "high": data.get("high", 0),
                "low": data.get("low", 0),
                "close": data.get("close", data.get("price", 0)),
                "volume": data.get("volume", 0),
                "funding_rate": data.get("funding_rate", 0),
                "open_interest": data.get("open_interest", 0),
            }
            
            # 检查文件是否存在，决定是否写入表头
            file_exists = csv_path.exists()
            
            with open(csv_path, mode="a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=row_data.keys())
                
                # 只在文件不存在时写入表头
                if not file_exists:
                    writer.writeheader()
                
                writer.writerow(row_data)
            
            logger.debug(f"💾 数据已保存: {symbol}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 保存 {symbol} 数据失败: {e}")
            return False
    
    async def fetch_klines(
        self,
        symbol: str,
        interval: str = "15m",
        limit: int = 50
    ) -> Optional[pd.DataFrame]:
        """
        获取 K 线数据 (OHLCV)
        
        Args:
            symbol: 交易对符号
            interval: K 线周期 (1m, 5m, 15m, 1h, 4h, 1d 等)
            limit: 返回的 K 线数量
            
        Returns:
            DataFrame with columns: Date, Open, High, Low, Close, Volume
            Date 为 datetime index
        """
        logger.debug(f"📊 获取 {symbol} K线数据 ({interval}, {limit} 根)...")
        
        try:
            data = await self.fetch_with_retry(
                "/fapi/v1/klines",
                params={
                    "symbol": symbol,
                    "interval": interval,
                    "limit": limit
                }
            )
            
            if not data:
                logger.warning(f"无法获取 {symbol} 的 K 线数据")
                return None
            
            # 解析 K 线数据
            # Binance 返回格式: [开盘时间, 开, 高, 低, 收, 成交量, 收盘时间, ...]
            df = pd.DataFrame(data, columns=[
                "Open time", "Open", "High", "Low", "Close", "Volume",
                "Close time", "Quote volume", "Trades", 
                "Taker buy base", "Taker buy quote", "Ignore"
            ])
            
            # 转换数据类型
            df["Date"] = pd.to_datetime(df["Open time"], unit="ms")
            df["Open"] = df["Open"].astype(float)
            df["High"] = df["High"].astype(float)
            df["Low"] = df["Low"].astype(float)
            df["Close"] = df["Close"].astype(float)
            df["Volume"] = df["Volume"].astype(float)
            
            # 只保留需要的列，设置日期为索引
            df = df[["Date", "Open", "High", "Low", "Close", "Volume"]]
            df.set_index("Date", inplace=True)
            
            logger.debug(f"✅ 获取到 {len(df)} 根 K 线")
            return df
            
        except IPBannedError:
            raise
        except Exception as e:
            logger.error(f"获取 {symbol} K 线数据失败: {e}")
            return None
    
    async def collect_all_data(self) -> dict[str, dict]:
        """
        执行完整的数据采集流程
        
        步骤:
        1. 获取所有 USDT 交易对
        2. 获取 24h 行情数据
        3. 按交易量过滤
        4. 获取资金费率
        5. 获取持仓量 (使用信号量控制并发)
        6. 保存到 CSV
        
        Returns:
            {symbol: {price, open_interest, funding_rate, quote_volume}}
        """
        logger.info("=" * 60)
        logger.info("🚀 开始数据采集...")
        start_time = datetime.now(timezone.utc)
        
        try:
            # Step 1: 获取所有 USDT 交易对
            all_symbols = await self.get_usdt_pairs()
            if not all_symbols:
                logger.error("未能获取任何交易对")
                return {}
            
            # Step 2: 获取 24h 行情 (用于过滤和价格)
            tickers = await self.get_24hr_tickers()
            if not tickers:
                logger.error("未能获取行情数据")
                return {}
            
            # Step 3: 按交易量过滤
            filtered_symbols = self.filter_by_volume(all_symbols, tickers)
            if not filtered_symbols:
                logger.warning("过滤后没有符合条件的交易对")
                return {}
            
            # Step 4: 获取资金费率
            funding_rates = await self.get_funding_rates()
            
            # Step 5: 获取持仓量 (最慢的步骤)
            open_interests = await self.get_all_open_interests(filtered_symbols)
            
            # Step 6: 整合数据并保存到 CSV
            timestamp = datetime.now(timezone.utc)
            result = {}
            saved_count = 0
            
            for symbol in filtered_symbols:
                if symbol not in open_interests:
                    continue
                
                ticker = tickers.get(symbol, {})
                price = ticker.get("last_price", 0)
                oi = open_interests[symbol]
                fr = funding_rates.get(symbol, 0)
                
                # 跳过无效数据
                if price <= 0 or oi <= 0:
                    continue
                
                # 构建完整数据字典 (包含 OHLCV)
                symbol_data = {
                    "open": ticker.get("open", 0),
                    "high": ticker.get("high", 0),
                    "low": ticker.get("low", 0),
                    "close": price,  # lastPrice = close
                    "price": price,
                    "volume": ticker.get("volume", 0),
                    "open_interest": oi,
                    "funding_rate": fr,
                    "quote_volume": ticker.get("quote_volume", 0),
                    "price_change_percent": ticker.get("price_change_percent", 0),
                }
                
                result[symbol] = symbol_data
                
                # ⚠️ 关键：保存到 CSV (每个周期追加一行)
                if self.save_to_csv(symbol, symbol_data, timestamp):
                    saved_count += 1
            
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            logger.info(f"✅ 数据采集完成! 耗时: {elapsed:.2f}s | 有效交易对: {len(result)} | 已保存: {saved_count}")
            logger.info("=" * 60)
            
            return result
            
        except IPBannedError:
            logger.error("🚫 IP 被封禁，采集中止!")
            raise
        except Exception as e:
            logger.error(f"❌ 数据采集失败: {e}", exc_info=True)
            return {}
    
    async def fetch_advanced_metrics(
        self,
        symbol: str,
        period: str = "5m"
    ) -> Optional[dict]:
        """
        按需获取高级指标 (仅在触发信号时调用)
        
        这些 API 有速率限制，不能在主循环中为所有交易对调用。
        只在检测到信号后，为特定交易对获取确认指标。
        
        Args:
            symbol: 交易对符号 (如 BTCUSDT)
            period: 数据周期 (5m, 15m, 30m, 1h, 2h, 4h, 6h, 12h, 1d)
            
        Returns:
            {
                'ls_ratio': float,          # 散户多空比 (Long/Short Account Ratio)
                'top_trader_ratio': float,  # 大户多空比 (Top Trader Position Ratio)
                'taker_buy_vol': float,     # 主动买入量
                'taker_sell_vol': float,    # 主动卖出量
                'taker_ratio': float,       # 买卖比 (Buy/Sell)
            }
            如果获取失败返回 None
        """
        logger.debug(f"📊 获取 {symbol} 高级指标...")
        
        metrics = {
            'ls_ratio': None,
            'top_trader_ratio': None,
            'taker_buy_vol': None,
            'taker_sell_vol': None,
            'taker_ratio': None,
        }
        
        # 并行获取三个指标
        try:
            tasks = [
                self._fetch_long_short_ratio(symbol, period),
                self._fetch_top_trader_ratio(symbol, period),
                self._fetch_taker_ratio(symbol, period),
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 解析散户多空比
            if isinstance(results[0], dict):
                metrics['ls_ratio'] = results[0].get('ratio')
            
            # 解析大户多空比
            if isinstance(results[1], dict):
                metrics['top_trader_ratio'] = results[1].get('ratio')
            
            # 解析买卖比
            if isinstance(results[2], dict):
                metrics['taker_buy_vol'] = results[2].get('buy_vol')
                metrics['taker_sell_vol'] = results[2].get('sell_vol')
                metrics['taker_ratio'] = results[2].get('ratio')
            
            # 检查是否有任何有效数据
            if all(v is None for v in metrics.values()):
                logger.warning(f"⚠️ 无法获取 {symbol} 的任何高级指标")
                return None
            
            logger.debug(f"✅ 获取到 {symbol} 高级指标: L/S={metrics['ls_ratio']}, Top={metrics['top_trader_ratio']}")
            return metrics
            
        except Exception as e:
            logger.warning(f"⚠️ 获取 {symbol} 高级指标失败: {e}")
            return None
    
    async def _fetch_long_short_ratio(
        self,
        symbol: str,
        period: str = "5m"
    ) -> Optional[dict]:
        """
        获取散户多空账户比
        
        API: /futures/data/globalLongShortAccountRatio
        """
        try:
            data = await self.fetch_with_retry(
                self.endpoints.get("long_short_ratio", "/futures/data/globalLongShortAccountRatio"),
                params={"symbol": symbol, "period": period, "limit": 1}
            )
            
            if data and len(data) > 0:
                item = data[0]
                return {
                    'ratio': float(item.get('longShortRatio', 0)),
                    'long_account': float(item.get('longAccount', 0)),
                    'short_account': float(item.get('shortAccount', 0)),
                }
        except Exception as e:
            logger.debug(f"获取 {symbol} 散户多空比失败: {e}")
        return None
    
    async def _fetch_top_trader_ratio(
        self,
        symbol: str,
        period: str = "5m"
    ) -> Optional[dict]:
        """
        获取大户持仓多空比
        
        API: /futures/data/topLongShortPositionRatio
        """
        try:
            data = await self.fetch_with_retry(
                self.endpoints.get("top_trader_ratio", "/futures/data/topLongShortPositionRatio"),
                params={"symbol": symbol, "period": period, "limit": 1}
            )
            
            if data and len(data) > 0:
                item = data[0]
                return {
                    'ratio': float(item.get('longShortRatio', 0)),
                    'long_account': float(item.get('longAccount', 0)),
                    'short_account': float(item.get('shortAccount', 0)),
                }
        except Exception as e:
            logger.debug(f"获取 {symbol} 大户多空比失败: {e}")
        return None
    
    async def _fetch_taker_ratio(
        self,
        symbol: str,
        period: str = "5m"
    ) -> Optional[dict]:
        """
        获取主动买卖比
        
        API: /futures/data/takerlongshortRatio
        """
        try:
            data = await self.fetch_with_retry(
                self.endpoints.get("taker_buy_sell_ratio", "/futures/data/takerlongshortRatio"),
                params={"symbol": symbol, "period": period, "limit": 1}
            )
            
            if data and len(data) > 0:
                item = data[0]
                buy_vol = float(item.get('buyVol', 0))
                sell_vol = float(item.get('sellVol', 0))
                return {
                    'buy_vol': buy_vol,
                    'sell_vol': sell_vol,
                    'ratio': float(item.get('buySellRatio', 0)) if item.get('buySellRatio') else (buy_vol / sell_vol if sell_vol > 0 else 0),
                }
        except Exception as e:
            logger.debug(f"获取 {symbol} 买卖比失败: {e}")
        return None


# ============================================================================
# 测试代码
# ============================================================================

async def test_collector():
    """测试数据采集器"""
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(message)s",
        stream=sys.stdout
    )
    
    print(f"\n🔌 代理: {NETWORK.PROXY_URL}")
    print(f"⏱️  超时: {NETWORK.HTTP_TIMEOUT}s\n")
    
    try:
        async with BinanceDataCollector() as collector:
            data = await collector.collect_all_data()
            
            print(f"\n📊 采集到 {len(data)} 个交易对的数据")
            
            # 显示前 5 个
            for i, (symbol, info) in enumerate(list(data.items())[:5]):
                print(f"\n{symbol}:")
                print(f"  价格: ${info['price']:.4f}")
                print(f"  持仓量: {info['open_interest']:,.0f}")
                print(f"  资金费率: {info['funding_rate']:.4%}")
    
    except IPBannedError:
        print("\n🚫 IP 被封禁!")
    except Exception as e:
        print(f"\n❌ 错误: {e}")


if __name__ == "__main__":
    asyncio.run(test_collector())
