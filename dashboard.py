"""
🦅 猎杀终端 (Liquidity Hunt Terminal)
=====================================
专业级金融终端风格仪表板

运行: streamlit run dashboard.py
"""

import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

# ============================================================================
# 页面配置 (必须在第一行)
# ============================================================================

st.set_page_config(
    page_title="🦅 猎杀终端 (Liquidity Hunt)",
    page_icon="📉",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        'About': "🦅 猎杀终端 v2.0 - 专业轧空信号监控系统"
    }
)

# ============================================================================
# 配置常量
# ============================================================================

DATA_DIR = Path("data")
SIGNAL_HISTORY_FILE = DATA_DIR / "signal_history.csv"
REFRESH_INTERVAL = 30  # 秒

# ============================================================================
# 自动刷新
# ============================================================================

try:
    from streamlit_autorefresh import st_autorefresh
    count = st_autorefresh(interval=REFRESH_INTERVAL * 1000, key="terminal_refresh")
except ImportError:
    count = 0

# ============================================================================
# 专业级 CSS 样式
# ============================================================================

def inject_custom_css():
    """注入彭博终端风格 CSS"""
    st.markdown("""
    <style>
    /* ========== 全局样式 ========== */
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&display=swap');
    
    :root {
        --bg-primary: #0a0a0f;
        --bg-secondary: #12121a;
        --bg-card: #1a1a24;
        --bg-hover: #252530;
        --border-color: #2a2a3a;
        --text-primary: #e8e8e8;
        --text-secondary: #8b8b9a;
        --text-muted: #5a5a6a;
        --accent-red: #ff3b3b;
        --accent-green: #00c853;
        --accent-orange: #ff9100;
        --accent-blue: #2196f3;
        --accent-purple: #9c27b0;
    }
    
    /* 主背景 */
    .stApp {
        background: linear-gradient(180deg, var(--bg-primary) 0%, #0d0d14 100%);
    }
    
    /* 隐藏默认元素 */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .stDeployButton {display: none;}
    
    /* 减少内边距 */
    .block-container {
        padding-top: 1rem !important;
        padding-bottom: 0 !important;
        max-width: 100% !important;
    }
    
    /* ========== 侧边栏 ========== */
    section[data-testid="stSidebar"] {
        background: var(--bg-secondary) !important;
        border-right: 1px solid var(--border-color);
    }
    
    section[data-testid="stSidebar"] > div {
        background: transparent;
    }
    
    /* ========== 标题样式 ========== */
    .terminal-header {
        font-family: 'JetBrains Mono', monospace;
        font-size: 1.8rem;
        font-weight: 700;
        background: linear-gradient(135deg, #ff9100 0%, #ff3b3b 50%, #ff9100 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        padding: 0.5rem 0;
        letter-spacing: 2px;
        text-transform: uppercase;
    }
    
    .section-title {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.9rem;
        font-weight: 600;
        color: var(--text-secondary);
        text-transform: uppercase;
        letter-spacing: 1px;
        border-bottom: 1px solid var(--border-color);
        padding-bottom: 0.5rem;
        margin-bottom: 1rem;
    }
    
    /* ========== 指标卡片 ========== */
    .metric-container {
        background: var(--bg-card);
        border: 1px solid var(--border-color);
        border-radius: 4px;
        padding: 1rem;
        text-align: center;
    }
    
    .metric-label {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.7rem;
        color: var(--text-muted);
        text-transform: uppercase;
        letter-spacing: 1px;
        margin-bottom: 0.3rem;
    }
    
    .metric-value {
        font-family: 'JetBrains Mono', monospace;
        font-size: 1.4rem;
        font-weight: 700;
        color: var(--text-primary);
    }
    
    .metric-value.positive { color: var(--accent-green); }
    .metric-value.negative { color: var(--accent-red); }
    .metric-value.warning { color: var(--accent-orange); }
    
    .metric-delta {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.75rem;
        margin-top: 0.2rem;
    }
    
    .metric-delta.up { color: var(--accent-green); }
    .metric-delta.down { color: var(--accent-red); }
    
    /* ========== 状态指示器 ========== */
    .status-indicator {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.8rem;
        padding: 0.5rem 1rem;
        border-radius: 4px;
        background: var(--bg-card);
        border: 1px solid var(--border-color);
    }
    
    .status-dot {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        animation: pulse 2s infinite;
    }
    
    .status-dot.online { background: var(--accent-green); }
    .status-dot.offline { background: var(--accent-red); }
    .status-dot.syncing { background: var(--accent-orange); }
    
    @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.5; }
    }
    
    /* ========== 信号表格 ========== */
    .signal-table-container {
        background: var(--bg-card);
        border: 1px solid var(--border-color);
        border-radius: 4px;
        overflow: hidden;
    }
    
    /* Streamlit DataFrame 样式覆盖 */
    .stDataFrame {
        font-family: 'JetBrains Mono', monospace !important;
    }
    
    [data-testid="stDataFrame"] > div {
        background: var(--bg-card) !important;
    }
    
    /* ========== 分析卡片 ========== */
    .analysis-card {
        background: var(--bg-card);
        border: 1px solid var(--border-color);
        border-radius: 4px;
        padding: 1rem;
        height: 100%;
    }
    
    .analysis-card h4 {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.8rem;
        color: var(--accent-orange);
        text-transform: uppercase;
        letter-spacing: 1px;
        margin-bottom: 0.5rem;
        padding-bottom: 0.5rem;
        border-bottom: 1px solid var(--border-color);
    }
    
    .analysis-item {
        display: flex;
        justify-content: space-between;
        padding: 0.4rem 0;
        border-bottom: 1px dashed var(--border-color);
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.8rem;
    }
    
    .analysis-item:last-child {
        border-bottom: none;
    }
    
    .analysis-label {
        color: var(--text-secondary);
    }
    
    .analysis-value {
        color: var(--text-primary);
        font-weight: 600;
    }
    
    /* ========== 滚动条 ========== */
    ::-webkit-scrollbar {
        width: 6px;
        height: 6px;
    }
    
    ::-webkit-scrollbar-track {
        background: var(--bg-primary);
    }
    
    ::-webkit-scrollbar-thumb {
        background: var(--border-color);
        border-radius: 3px;
    }
    
    ::-webkit-scrollbar-thumb:hover {
        background: var(--text-muted);
    }
    
    /* ========== 响应式 ========== */
    @media (max-width: 768px) {
        .terminal-header { font-size: 1.2rem; }
        .metric-value { font-size: 1.1rem; }
    }
    </style>
    """, unsafe_allow_html=True)


# ============================================================================
# 数据加载函数 (带完善的错误处理)
# ============================================================================

@st.cache_data(ttl=5)
def load_signal_history() -> pd.DataFrame:
    """
    安全加载信号历史
    处理文件锁定、空文件、格式错误等情况
    """
    try:
        if not SIGNAL_HISTORY_FILE.exists():
            return pd.DataFrame()
        
        # 检查文件是否正在被写入 (文件大小为 0 或修改时间在 1 秒内)
        file_stat = SIGNAL_HISTORY_FILE.stat()
        if file_stat.st_size == 0:
            return pd.DataFrame()
        
        # 尝试读取
        df = pd.read_csv(
            SIGNAL_HISTORY_FILE,
            on_bad_lines='skip',
            encoding='utf-8'
        )
        
        if df.empty:
            return df
        
        # 标准化时间列
        time_col = None
        for col in ['Time', 'timestamp', 'time', 'Timestamp']:
            if col in df.columns:
                time_col = col
                break
        
        if time_col:
            df['Time'] = pd.to_datetime(df[time_col], errors='coerce')
            df = df.sort_values('Time', ascending=False)
        
        return df
        
    except pd.errors.EmptyDataError:
        return pd.DataFrame()
    except PermissionError:
        st.toast("⏳ 数据同步中...", icon="🔄")
        return pd.DataFrame()
    except Exception as e:
        st.toast(f"⚠️ 数据加载异常: {str(e)[:50]}", icon="⚠️")
        return pd.DataFrame()


@st.cache_data(ttl=5)
def load_symbol_data(symbol: str) -> pd.DataFrame:
    """安全加载交易对数据"""
    try:
        csv_path = DATA_DIR / f"{symbol}.csv"
        
        if not csv_path.exists():
            return pd.DataFrame()
        
        if csv_path.stat().st_size == 0:
            return pd.DataFrame()
        
        df = pd.read_csv(
            csv_path,
            on_bad_lines='skip',
            encoding='utf-8'
        )
        
        if df.empty:
            return df
        
        # 转换时间
        if 'timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
            df = df.sort_values('timestamp', ascending=True)
        
        return df
        
    except (pd.errors.EmptyDataError, PermissionError):
        return pd.DataFrame()
    except Exception:
        return pd.DataFrame()


def get_available_symbols() -> list:
    """获取可用交易对"""
    try:
        if not DATA_DIR.exists():
            return []
        
        symbols = [
            f.stem for f in DATA_DIR.glob("*.csv")
            if f.stem not in ['signal_history', ''] and not f.stem.startswith('.')
        ]
        return sorted(symbols)
    except Exception:
        return []


def get_system_status() -> tuple[str, str]:
    """
    获取系统状态
    Returns: (status_class, status_text)
    """
    try:
        if not SIGNAL_HISTORY_FILE.exists():
            return "offline", "离线"
        
        mtime = datetime.fromtimestamp(SIGNAL_HISTORY_FILE.stat().st_mtime)
        age = datetime.now() - mtime
        
        if age < timedelta(minutes=10):
            return "online", "运行中"
        elif age < timedelta(hours=1):
            return "syncing", "同步中"
        else:
            return "offline", "离线"
    except Exception:
        return "offline", "异常"


def get_btc_data() -> tuple[float, float]:
    """获取 BTC 价格和变化"""
    try:
        btc_df = load_symbol_data("BTCUSDT")
        if btc_df.empty or 'close' not in btc_df.columns:
            return 0, 0
        
        current = float(btc_df['close'].iloc[-1])
        if len(btc_df) >= 4:
            prev = float(btc_df['close'].iloc[-4])
            change = (current - prev) / prev * 100 if prev > 0 else 0
        else:
            change = 0
        
        return current, change
    except Exception:
        return 0, 0


# ============================================================================
# 图表函数
# ============================================================================

def create_professional_chart(df: pd.DataFrame, symbol: str) -> go.Figure:
    """创建专业级金融图表"""
    
    # 列名处理
    time_col = 'timestamp' if 'timestamp' in df.columns else df.index
    open_col = 'open' if 'open' in df.columns else 'Open'
    high_col = 'high' if 'high' in df.columns else 'High'
    low_col = 'low' if 'low' in df.columns else 'Low'
    close_col = 'close' if 'close' in df.columns else 'Close'
    vol_col = 'volume' if 'volume' in df.columns else 'Volume'
    oi_col = 'open_interest' if 'open_interest' in df.columns else None
    fr_col = 'funding_rate' if 'funding_rate' in df.columns else None
    
    # 创建子图
    row_heights = [0.5, 0.25, 0.25] if oi_col else [0.6, 0.4]
    rows = 3 if oi_col else 2
    
    fig = make_subplots(
        rows=rows,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.02,
        row_heights=row_heights,
        subplot_titles=None
    )
    
    x_data = df[time_col] if isinstance(time_col, str) else time_col
    
    # Row 1: 蜡烛图
    fig.add_trace(
        go.Candlestick(
            x=x_data,
            open=df[open_col],
            high=df[high_col],
            low=df[low_col],
            close=df[close_col],
            name="Price",
            increasing=dict(line=dict(color='#00c853', width=1), fillcolor='#00c853'),
            decreasing=dict(line=dict(color='#ff3b3b', width=1), fillcolor='#ff3b3b'),
        ),
        row=1, col=1
    )
    
    # Row 2: 成交量
    if vol_col in df.columns:
        colors = ['#00c853' if c >= o else '#ff3b3b' 
                  for c, o in zip(df[close_col], df[open_col])]
        
        fig.add_trace(
            go.Bar(
                x=x_data,
                y=df[vol_col],
                name="Volume",
                marker_color=colors,
                opacity=0.7
            ),
            row=2, col=1
        )
    
    # Row 3: OI + Funding Rate
    if oi_col and oi_col in df.columns and rows == 3:
        fig.add_trace(
            go.Scatter(
                x=x_data,
                y=df[oi_col],
                name="Open Interest",
                line=dict(color='#2196f3', width=2),
                fill='tozeroy',
                fillcolor='rgba(33, 150, 243, 0.1)'
            ),
            row=3, col=1
        )
        
        # 资金费率叠加 (右 Y 轴)
        if fr_col and fr_col in df.columns:
            fr_colors = ['#00c853' if v >= 0 else '#ff3b3b' for v in df[fr_col]]
            fig.add_trace(
                go.Bar(
                    x=x_data,
                    y=df[fr_col] * 100,
                    name="Funding Rate",
                    marker_color=fr_colors,
                    opacity=0.5,
                    yaxis='y4'
                ),
                row=3, col=1
            )
    
    # 布局
    fig.update_layout(
        height=450,
        margin=dict(l=50, r=50, t=30, b=30),
        paper_bgcolor='#0a0a0f',
        plot_bgcolor='#0a0a0f',
        font=dict(family='JetBrains Mono, monospace', size=10, color='#8b8b9a'),
        showlegend=False,
        xaxis_rangeslider_visible=False,
        hovermode='x unified',
    )
    
    # 网格样式
    for i in range(1, rows + 1):
        fig.update_xaxes(
            row=i, col=1,
            gridcolor='#1a1a24',
            zerolinecolor='#2a2a3a',
            showgrid=True,
            tickfont=dict(size=9)
        )
        fig.update_yaxes(
            row=i, col=1,
            gridcolor='#1a1a24',
            zerolinecolor='#2a2a3a',
            showgrid=True,
            tickfont=dict(size=9),
            side='right'
        )
    
    # Y 轴标签
    fig.update_yaxes(title_text="价格", row=1, col=1)
    fig.update_yaxes(title_text="成交量", row=2, col=1)
    if rows == 3:
        fig.update_yaxes(title_text="OI", row=3, col=1)
    
    # 添加标题注释
    fig.add_annotation(
        text=f"<b>{symbol}</b>",
        xref="paper", yref="paper",
        x=0, y=1.05,
        showarrow=False,
        font=dict(size=14, color='#ff9100', family='JetBrains Mono')
    )
    
    return fig


# ============================================================================
# UI 组件
# ============================================================================

def render_metric_card(label: str, value: str, delta: str = None, 
                       value_class: str = "", delta_class: str = ""):
    """渲染指标卡片"""
    delta_html = f'<div class="metric-delta {delta_class}">{delta}</div>' if delta else ''
    
    st.markdown(f"""
    <div class="metric-container">
        <div class="metric-label">{label}</div>
        <div class="metric-value {value_class}">{value}</div>
        {delta_html}
    </div>
    """, unsafe_allow_html=True)


def render_status_indicator(status_class: str, status_text: str):
    """渲染状态指示器"""
    st.markdown(f"""
    <div class="status-indicator">
        <div class="status-dot {status_class}"></div>
        <span>系统状态: <b>{status_text}</b></span>
    </div>
    """, unsafe_allow_html=True)


def render_analysis_card(signal_data: dict):
    """渲染分析卡片"""
    # 使用 Streamlit 原生组件避免 HTML 渲染问题
    st.markdown("##### 📊 深度分析")
    for label, value in signal_data.items():
        cols = st.columns([1, 1])
        with cols[0]:
            st.caption(label)
        with cols[1]:
            st.markdown(f"**{value}**")


# ============================================================================
# 主界面
# ============================================================================

def main():
    """主函数"""
    
    # 注入 CSS
    inject_custom_css()
    
    # 加载数据
    signals_df = load_signal_history()
    available_symbols = get_available_symbols()
    btc_price, btc_change = get_btc_data()
    status_class, status_text = get_system_status()
    
    # ======================== 侧边栏 ========================
    with st.sidebar:
        st.markdown("## 🎛️ 控制台")
        st.markdown("---")
        
        # 系统状态
        render_status_indicator(status_class, status_text)
        
        st.markdown("---")
        
        # 时间显示
        st.markdown(f"""
        <div style="font-family: 'JetBrains Mono'; font-size: 0.8rem; color: #8b8b9a;">
            🕐 本地时间<br>
            <span style="font-size: 1.2rem; color: #e8e8e8; font-weight: 600;">
                {datetime.now().strftime("%H:%M:%S")}
            </span>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("---")
        
        # 过滤器
        st.markdown("### ⚙️ 过滤器")
        strong_only = st.checkbox("🔥 仅显示强力信号", value=False, key="filter_strong")
        
        st.markdown("---")
        
        # 交易对选择
        st.markdown("### 📈 图表分析")
        if available_symbols:
            selected_symbol = st.selectbox(
                "选择交易对",
                options=available_symbols,
                index=0,
                key="symbol_select"
            )
        else:
            selected_symbol = None
            st.warning("暂无数据")
        
        st.markdown("---")
        
        # 统计
        if not signals_df.empty:
            total = len(signals_df)
            strong_count = len(signals_df[signals_df.get('Severity', signals_df.get('severity', '')) == 'STRONG']) if 'Severity' in signals_df.columns or 'severity' in signals_df.columns else 0
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric("总信号", f"{total:,}")
            with col2:
                st.metric("强信号", f"{strong_count:,}")
        
        st.markdown("---")
        
        # 刷新
        if st.button("🔄 刷新数据", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
        
        # Footer
        st.markdown("""
        <div style="text-align: center; font-size: 0.7rem; color: #5a5a6a; margin-top: 2rem;">
            🦅 猎杀终端 v2.0<br>
            自动刷新: 30秒
        </div>
        """, unsafe_allow_html=True)
    
    # ======================== 主内容区 ========================
    
    # 标题
    st.markdown('<div class="terminal-header">🦅 猎杀终端 LIQUIDITY HUNT</div>', unsafe_allow_html=True)
    
    # -------- 顶部指标行 --------
    st.markdown('<div class="section-title">📊 市场概览 MARKET OVERVIEW</div>', unsafe_allow_html=True)
    
    cols = st.columns(5)
    
    with cols[0]:
        btc_class = "positive" if btc_change >= 0 else "negative"
        delta_class = "up" if btc_change >= 0 else "down"
        delta_arrow = "▲" if btc_change >= 0 else "▼"
        render_metric_card(
            "BTC 价格",
            f"${btc_price:,.0f}" if btc_price > 0 else "---",
            f"{delta_arrow} {abs(btc_change):.2f}%" if btc_price > 0 else None,
            btc_class,
            delta_class
        )
    
    with cols[1]:
        today_signals = 0
        if not signals_df.empty and 'Time' in signals_df.columns:
            today = datetime.now().date()
            today_signals = len(signals_df[signals_df['Time'].dt.date == today])
        render_metric_card("今日信号", f"{today_signals}", None, "warning" if today_signals > 0 else "")
    
    with cols[2]:
        strong_today = 0
        if not signals_df.empty and 'Time' in signals_df.columns:
            severity_col = 'Severity' if 'Severity' in signals_df.columns else 'severity'
            if severity_col in signals_df.columns:
                today_df = signals_df[signals_df['Time'].dt.date == datetime.now().date()]
                strong_today = len(today_df[today_df[severity_col] == 'STRONG'])
        render_metric_card("强力信号", f"{strong_today}", None, "negative" if strong_today > 0 else "")
    
    with cols[3]:
        render_metric_card("监控交易对", f"{len(available_symbols)}")
    
    with cols[4]:
        render_metric_card("刷新周期", f"{REFRESH_INTERVAL}s")
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # -------- 信号表格 --------
    st.markdown('<div class="section-title">📡 信号流 SIGNAL FEED</div>', unsafe_allow_html=True)
    
    if signals_df.empty:
        st.info("📭 暂无信号记录。启动 `python main.py` 后信号将显示在此处。")
    else:
        display_df = signals_df.copy()
        
        # 过滤
        severity_col = 'Severity' if 'Severity' in display_df.columns else 'severity'
        if strong_only and severity_col in display_df.columns:
            display_df = display_df[display_df[severity_col] == 'STRONG']
        
        if display_df.empty:
            st.warning("⚠️ 没有符合条件的信号")
        else:
            # 准备显示列
            display_df = display_df.head(100)
            
            # 列配置
            column_config = {
                "Time": st.column_config.DatetimeColumn("时间", format="MM-DD HH:mm:ss", width="medium"),
                "Symbol": st.column_config.TextColumn("交易对", width="small"),
                "Price": st.column_config.NumberColumn("价格", format="$%.4f", width="small"),
                "Severity": st.column_config.TextColumn("级别", width="small"),
                "severity": st.column_config.TextColumn("级别", width="small"),
                "Trend": st.column_config.TextColumn("趋势", width="medium"),
                "trend": st.column_config.TextColumn("趋势", width="medium"),
                "funding_rate": st.column_config.NumberColumn("费率", format="%.4f%%", width="small"),
                "oi_ratio": st.column_config.NumberColumn("OI比", format="%.2fx", width="small"),
                "oi_change_pct": st.column_config.NumberColumn("OI变化", format="%.2f%%", width="small"),
                "btc_change_pct": st.column_config.NumberColumn("BTC变化", format="%.2f%%", width="small"),
            }
            
            # 选择要显示的列
            show_cols = ['Time', 'Symbol', 'Price']
            if severity_col in display_df.columns:
                show_cols.append(severity_col)
            for col in ['funding_rate', 'oi_ratio', 'Trend', 'trend']:
                if col in display_df.columns:
                    show_cols.append(col)
            
            # 只保留存在的列
            show_cols = [c for c in show_cols if c in display_df.columns]
            
            st.dataframe(
                display_df[show_cols],
                use_container_width=True,
                height=250,
                column_config=column_config,
                hide_index=True
            )
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # -------- 图表区域 (分两列) --------
    st.markdown('<div class="section-title">📈 深度分析 DEEP ANALYSIS</div>', unsafe_allow_html=True)
    
    col_chart, col_analysis = st.columns([7, 3])
    
    with col_chart:
        if selected_symbol:
            symbol_df = load_symbol_data(selected_symbol)
            
            if symbol_df.empty:
                st.warning(f"⚠️ {selected_symbol} 暂无数据")
            else:
                fig = create_professional_chart(symbol_df, selected_symbol)
                st.plotly_chart(fig, use_container_width=True, config={
                    'displayModeBar': False,
                    'scrollZoom': False
                })
        else:
            st.info("👈 请从侧边栏选择交易对")
    
    with col_analysis:
        if selected_symbol:
            symbol_df = load_symbol_data(selected_symbol)
            
            if not symbol_df.empty:
                # 计算分析数据
                close_col = 'close' if 'close' in symbol_df.columns else 'Close'
                oi_col = 'open_interest' if 'open_interest' in symbol_df.columns else None
                fr_col = 'funding_rate' if 'funding_rate' in symbol_df.columns else None
                
                latest_price = symbol_df[close_col].iloc[-1] if close_col in symbol_df.columns else 0
                
                # 计算变化
                if len(symbol_df) >= 2:
                    price_change = (symbol_df[close_col].iloc[-1] - symbol_df[close_col].iloc[-2]) / symbol_df[close_col].iloc[-2] * 100
                else:
                    price_change = 0
                
                oi_value = symbol_df[oi_col].iloc[-1] if oi_col and oi_col in symbol_df.columns else 0
                fr_value = symbol_df[fr_col].iloc[-1] * 100 if fr_col and fr_col in symbol_df.columns else 0
                
                # 格式化 OI
                if oi_value >= 1e9:
                    oi_str = f"{oi_value/1e9:.2f}B"
                elif oi_value >= 1e6:
                    oi_str = f"{oi_value/1e6:.2f}M"
                elif oi_value >= 1e3:
                    oi_str = f"{oi_value/1e3:.2f}K"
                else:
                    oi_str = f"{oi_value:.0f}"
                
                # 找到对应的信号
                trend_text = "---"
                advice_text = "---"
                if not signals_df.empty:
                    symbol_signals = signals_df[signals_df.get('Symbol', signals_df.get('symbol', '')) == selected_symbol]
                    if not symbol_signals.empty:
                        latest_signal = symbol_signals.iloc[0]
                        trend_text = latest_signal.get('Trend', latest_signal.get('trend', '---'))
                        advice_text = latest_signal.get('Advice', latest_signal.get('advice', '---'))
                
                analysis_data = {
                    "交易对": selected_symbol,
                    "最新价格": f"${latest_price:.4f}",
                    "价格变化": f"{price_change:+.2f}%",
                    "持仓量": oi_str,
                    "资金费率": f"{fr_value:+.4f}%",
                    "数据点数": f"{len(symbol_df)}",
                }
                
                render_analysis_card(analysis_data)
                
                # 趋势卡片
                st.markdown("---")
                st.markdown("##### 🧭 市场趋势")
                if trend_text and trend_text != '---':
                    st.info(trend_text)
                else:
                    st.caption("等待信号...")
        else:
            st.markdown("##### 📊 深度分析")
            st.caption("👈 从侧边栏选择交易对查看详细分析")
    
    # Footer
    st.markdown("""
    <div style="text-align: center; color: #5a5a6a; font-size: 0.75rem; padding: 1rem; border-top: 1px solid #2a2a3a; margin-top: 2rem;">
        🦅 猎杀终端 v2.0 | 数据仅供参考，不构成投资建议 | 
        <span style="color: #ff9100;">◉</span> 实时刷新中
    </div>
    """, unsafe_allow_html=True)


# ============================================================================
# 运行
# ============================================================================

if __name__ == "__main__":
    main()
