"""
🦅 猎杀终端 (Liquidity Hunt Terminal) v2.1
==========================================
专业级金融终端 - 纯 Streamlit 原生组件

运行: streamlit run dashboard.py
"""

import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

# ============================================================================
# 页面配置
# ============================================================================

st.set_page_config(
    page_title="🦅 猎杀终端",
    page_icon="📉",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================================
# 配置
# ============================================================================

DATA_DIR = Path("data")
SIGNAL_HISTORY_FILE = DATA_DIR / "signal_history.csv"
REFRESH_INTERVAL = 30

# 自动刷新
try:
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=REFRESH_INTERVAL * 1000, key="refresh")
except ImportError:
    pass

# ============================================================================
# 简洁 CSS (仅基础样式)
# ============================================================================

st.markdown("""
<style>
/* 隐藏默认元素 */
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
.stDeployButton {display: none;}

/* 紧凑布局 */
.block-container {
    padding-top: 1rem !important;
    padding-bottom: 0 !important;
}

/* 深色背景 */
.stApp {
    background-color: #0a0e14;
}
</style>
""", unsafe_allow_html=True)


# ============================================================================
# 数据加载 (带错误处理)
# ============================================================================

@st.cache_data(ttl=5)
def load_signal_history() -> pd.DataFrame:
    """安全加载信号历史"""
    try:
        if not SIGNAL_HISTORY_FILE.exists():
            return pd.DataFrame()
        
        if SIGNAL_HISTORY_FILE.stat().st_size == 0:
            return pd.DataFrame()
        
        df = pd.read_csv(SIGNAL_HISTORY_FILE, on_bad_lines='skip')
        
        if df.empty:
            return df
        
        # 标准化时间列
        for col in ['Time', 'timestamp', 'time']:
            if col in df.columns:
                df['Time'] = pd.to_datetime(df[col], errors='coerce')
                break
        
        if 'Time' in df.columns:
            df = df.sort_values('Time', ascending=False)
        
        return df
        
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=5)
def load_symbol_data(symbol: str) -> pd.DataFrame:
    """安全加载交易对数据"""
    try:
        path = DATA_DIR / f"{symbol}.csv"
        if not path.exists() or path.stat().st_size == 0:
            return pd.DataFrame()
        
        df = pd.read_csv(path, on_bad_lines='skip')
        
        if 'timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
            df = df.sort_values('timestamp')
        
        return df
    except Exception:
        return pd.DataFrame()


def get_symbols() -> list:
    """获取可用交易对"""
    try:
        if not DATA_DIR.exists():
            return []
        return sorted([
            f.stem for f in DATA_DIR.glob("*.csv")
            if f.stem not in ['signal_history', '']
        ])
    except Exception:
        return []


def get_btc_info() -> tuple:
    """获取 BTC 数据"""
    try:
        df = load_symbol_data("BTCUSDT")
        if df.empty or 'close' not in df.columns:
            return 0, 0
        
        price = float(df['close'].iloc[-1])
        change = 0
        if len(df) >= 4:
            prev = float(df['close'].iloc[-4])
            if prev > 0:
                change = (price - prev) / prev * 100
        return price, change
    except Exception:
        return 0, 0


# ============================================================================
# 图表 (高可见度配色)
# ============================================================================

def create_chart(df: pd.DataFrame, symbol: str) -> go.Figure:
    """创建高可见度图表"""
    
    # 列名适配
    time_col = 'timestamp' if 'timestamp' in df.columns else df.index
    open_col = 'open' if 'open' in df.columns else 'Open'
    high_col = 'high' if 'high' in df.columns else 'High'
    low_col = 'low' if 'low' in df.columns else 'Low'
    close_col = 'close' if 'close' in df.columns else 'Close'
    vol_col = 'volume' if 'volume' in df.columns else None
    oi_col = 'open_interest' if 'open_interest' in df.columns else None
    
    # 判断行数
    rows = 3 if oi_col and oi_col in df.columns else 2
    heights = [0.5, 0.25, 0.25] if rows == 3 else [0.6, 0.4]
    
    fig = make_subplots(
        rows=rows, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=heights
    )
    
    x = df[time_col] if isinstance(time_col, str) else time_col
    
    # Row 1: 蜡烛图 (高对比度)
    fig.add_trace(
        go.Candlestick(
            x=x,
            open=df[open_col],
            high=df[high_col],
            low=df[low_col],
            close=df[close_col],
            name="Price",
            increasing=dict(line=dict(color='#00ff88', width=1), fillcolor='#00ff88'),
            decreasing=dict(line=dict(color='#ff3366', width=1), fillcolor='#ff3366'),
        ),
        row=1, col=1
    )
    
    # Row 2: 成交量
    if vol_col and vol_col in df.columns:
        colors = ['#00ff88' if c >= o else '#ff3366' 
                  for c, o in zip(df[close_col], df[open_col])]
        fig.add_trace(
            go.Bar(x=x, y=df[vol_col], name="Vol", marker_color=colors, opacity=0.7),
            row=2, col=1
        )
    
    # Row 3: OI (亮青色)
    if rows == 3 and oi_col in df.columns:
        fig.add_trace(
            go.Scatter(
                x=x, y=df[oi_col],
                name="OI",
                line=dict(color='#00ffff', width=2),
                fill='tozeroy',
                fillcolor='rgba(0, 255, 255, 0.15)'
            ),
            row=3, col=1
        )
    
    # 布局
    fig.update_layout(
        title=dict(text=f"📈 {symbol}", font=dict(size=16, color='#ffaa00')),
        height=420,
        margin=dict(l=50, r=20, t=40, b=30),
        paper_bgcolor='#0d1117',
        plot_bgcolor='#0d1117',
        font=dict(color='#c9d1d9', size=10),
        showlegend=False,
        xaxis_rangeslider_visible=False,
        hovermode='x unified'
    )
    
    # 网格样式
    for i in range(1, rows + 1):
        fig.update_xaxes(row=i, col=1, gridcolor='#21262d', zerolinecolor='#30363d')
        fig.update_yaxes(row=i, col=1, gridcolor='#21262d', zerolinecolor='#30363d', side='right')
    
    fig.update_yaxes(title_text="价格", row=1, col=1, title_font=dict(size=10))
    fig.update_yaxes(title_text="成交量", row=2, col=1, title_font=dict(size=10))
    if rows == 3:
        fig.update_yaxes(title_text="OI", row=3, col=1, title_font=dict(size=10))
    
    return fig


# ============================================================================
# 主界面
# ============================================================================

def main():
    # 加载数据
    signals_df = load_signal_history()
    symbols = get_symbols()
    btc_price, btc_change = get_btc_info()
    
    # ======================== 侧边栏 ========================
    with st.sidebar:
        st.title("🎛️ 控制台")
        st.divider()
        
        # 状态
        if SIGNAL_HISTORY_FILE.exists():
            mtime = datetime.fromtimestamp(SIGNAL_HISTORY_FILE.stat().st_mtime)
            age = datetime.now() - mtime
            if age < timedelta(minutes=10):
                st.success("🟢 系统运行中")
            else:
                st.warning("🟡 数据较旧")
        else:
            st.error("🔴 无数据")
        
        st.caption(f"🕐 {datetime.now().strftime('%H:%M:%S')}")
        st.divider()
        
        # 过滤器
        st.subheader("⚙️ 过滤")
        strong_only = st.checkbox("🔥 仅显示 STRONG", value=False)
        
        st.divider()
        
        # 交易对选择
        st.subheader("📈 图表")
        if symbols:
            symbol = st.selectbox("选择交易对", symbols, index=0)
        else:
            symbol = None
            st.warning("暂无数据")
        
        st.divider()
        
        # 统计
        if not signals_df.empty:
            col1, col2 = st.columns(2)
            total = len(signals_df)
            sev_col = 'Severity' if 'Severity' in signals_df.columns else 'severity'
            strong = len(signals_df[signals_df.get(sev_col, '') == 'STRONG']) if sev_col in signals_df.columns else 0
            col1.metric("总信号", f"{total:,}")
            col2.metric("强信号", f"{strong:,}")
        
        st.divider()
        
        if st.button("🔄 刷新", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
        
        st.caption("🦅 猎杀终端 v2.1")
    
    # ======================== 主区域 ========================
    
    # 标题
    st.markdown("# 🦅 猎杀终端 LIQUIDITY HUNT")
    
    # -------- 顶部指标 --------
    st.subheader("📊 市场概览")
    
    m1, m2, m3, m4, m5 = st.columns(5)
    
    with m1:
        delta_str = f"{btc_change:+.2f}%" if btc_price > 0 else None
        st.metric("₿ BTC", f"${btc_price:,.0f}" if btc_price else "---", delta_str)
    
    with m2:
        today_count = 0
        if not signals_df.empty and 'Time' in signals_df.columns:
            today = datetime.now().date()
            today_count = len(signals_df[signals_df['Time'].dt.date == today])
        st.metric("📊 今日信号", today_count)
    
    with m3:
        strong_today = 0
        if not signals_df.empty and 'Time' in signals_df.columns:
            sev_col = 'Severity' if 'Severity' in signals_df.columns else 'severity'
            if sev_col in signals_df.columns:
                today_df = signals_df[signals_df['Time'].dt.date == datetime.now().date()]
                strong_today = len(today_df[today_df[sev_col] == 'STRONG'])
        st.metric("🔥 强信号", strong_today)
    
    with m4:
        st.metric("🎯 监控数", len(symbols))
    
    with m5:
        st.metric("⏱️ 刷新", f"{REFRESH_INTERVAL}s")
    
    st.divider()
    
    # -------- 信号表格 --------
    st.subheader("📡 信号流 Signal Feed")
    
    if signals_df.empty:
        st.info("📭 暂无信号。运行 `python main.py` 后数据将显示。")
    else:
        display_df = signals_df.copy()
        
        # 过滤
        sev_col = 'Severity' if 'Severity' in display_df.columns else 'severity'
        if strong_only and sev_col in display_df.columns:
            display_df = display_df[display_df[sev_col] == 'STRONG']
        
        if display_df.empty:
            st.warning("⚠️ 无符合条件的信号")
        else:
            # 准备显示数据 (纯文本，不用 HTML)
            display_df = display_df.head(50).copy()
            
            # 添加 emoji 到 Severity
            if sev_col in display_df.columns:
                display_df['级别'] = display_df[sev_col].apply(
                    lambda x: "🚨 STRONG" if x == 'STRONG' else "🟠 NORMAL"
                )
            
            # 选择要显示的列
            show_cols = []
            col_config = {}
            
            if 'Time' in display_df.columns:
                show_cols.append('Time')
                col_config['Time'] = st.column_config.DatetimeColumn("时间", format="MM-DD HH:mm")
            
            # Symbol
            sym_col = 'Symbol' if 'Symbol' in display_df.columns else 'symbol'
            if sym_col in display_df.columns:
                show_cols.append(sym_col)
                col_config[sym_col] = st.column_config.TextColumn("交易对")
            
            # Price
            price_col = 'Price' if 'Price' in display_df.columns else 'price'
            if price_col in display_df.columns:
                show_cols.append(price_col)
                col_config[price_col] = st.column_config.NumberColumn("价格", format="$%.4f")
            
            # 级别
            if '级别' in display_df.columns:
                show_cols.append('级别')
                col_config['级别'] = st.column_config.TextColumn("级别")
            
            # Funding Rate (直接显示，CSV 中已是字符串格式)
            if 'funding_rate' in display_df.columns:
                show_cols.append('funding_rate')
                col_config['funding_rate'] = st.column_config.TextColumn("费率")
            
            # OI Ratio (直接显示，CSV 中已是字符串格式)
            if 'oi_ratio' in display_df.columns:
                show_cols.append('oi_ratio')
                col_config['oi_ratio'] = st.column_config.TextColumn("OI比")
            
            # 只保留存在的列
            show_cols = [c for c in show_cols if c in display_df.columns]
            
            if show_cols:
                st.dataframe(
                    display_df[show_cols],
                    use_container_width=True,
                    height=220,
                    column_config=col_config,
                    hide_index=True
                )
    
    st.divider()
    
    # -------- 图表和分析 --------
    st.subheader("📈 深度分析 Deep Analysis")
    
    col_chart, col_info = st.columns([7, 3])
    
    with col_chart:
        if symbol:
            df = load_symbol_data(symbol)
            if df.empty:
                st.warning(f"⚠️ {symbol} 暂无数据")
            else:
                fig = create_chart(df, symbol)
                st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
        else:
            st.info("👈 从侧边栏选择交易对")
    
    with col_info:
        st.markdown("##### 🧠 主力分析")
        
        if symbol:
            df = load_symbol_data(symbol)
            
            if not df.empty:
                # 基础数据
                close_col = 'close' if 'close' in df.columns else 'Close'
                oi_col = 'open_interest' if 'open_interest' in df.columns else None
                fr_col = 'funding_rate' if 'funding_rate' in df.columns else None
                
                price = df[close_col].iloc[-1] if close_col in df.columns else 0
                
                # 价格变化
                price_chg = 0
                if len(df) >= 2 and close_col in df.columns:
                    prev = df[close_col].iloc[-2]
                    if prev > 0:
                        price_chg = (price - prev) / prev * 100
                
                # OI
                oi = df[oi_col].iloc[-1] if oi_col and oi_col in df.columns else 0
                if oi >= 1e9:
                    oi_str = f"{oi/1e9:.2f}B"
                elif oi >= 1e6:
                    oi_str = f"{oi/1e6:.2f}M"
                elif oi >= 1e3:
                    oi_str = f"{oi/1e3:.1f}K"
                else:
                    oi_str = f"{oi:.0f}"
                
                # 资金费率
                fr = df[fr_col].iloc[-1] * 100 if fr_col and fr_col in df.columns else 0
                
                # 显示指标
                st.metric("💵 最新价", f"${price:.4f}", f"{price_chg:+.2f}%")
                st.metric("📊 持仓量", oi_str)
                st.metric("💰 资金费率", f"{fr:+.4f}%")
                st.metric("📈 数据点", len(df))
                
                st.divider()
                
                # 趋势分析
                st.markdown("##### 🧭 市场趋势")
                
                # 从信号中获取趋势
                trend_text = None
                advice_text = None
                
                if not signals_df.empty:
                    sym_col = 'Symbol' if 'Symbol' in signals_df.columns else 'symbol'
                    if sym_col in signals_df.columns:
                        sym_signals = signals_df[signals_df[sym_col] == symbol]
                        if not sym_signals.empty:
                            latest = sym_signals.iloc[0]
                            trend_text = latest.get('Trend', latest.get('trend', None))
                            advice_text = latest.get('Advice', latest.get('advice', None))
                
                if trend_text:
                    st.info(trend_text)
                else:
                    st.caption("等待信号...")
                
                if advice_text:
                    st.success(f"💡 {advice_text}")
            else:
                st.caption("暂无数据")
        else:
            st.caption("👈 选择交易对查看分析")
    
    # Footer
    st.divider()
    st.caption("🦅 猎杀终端 v2.1 | 数据仅供参考，不构成投资建议 | 🟢 实时刷新中")


# ============================================================================
# 运行
# ============================================================================

if __name__ == "__main__":
    main()
