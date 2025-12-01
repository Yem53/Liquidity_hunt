"""
🚀 Squeeze Command Center - Streamlit Dashboard
================================================
实时可视化轧空信号和市场数据

运行方式:
    streamlit run dashboard.py
"""

import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

# ============================================================================
# 配置
# ============================================================================

# 数据目录
DATA_DIR = Path("data")
SIGNAL_HISTORY_FILE = DATA_DIR / "signal_history.csv"

# 页面配置
st.set_page_config(
    page_title="Squeeze Command Center",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 自动刷新 (每 30 秒)
# 使用 streamlit-autorefresh 或手动刷新按钮
try:
    from streamlit_autorefresh import st_autorefresh
    # 每 30 秒刷新一次
    st_autorefresh(interval=30 * 1000, key="datarefresh")
except ImportError:
    # 如果没有安装 streamlit-autorefresh，使用手动刷新
    pass


# ============================================================================
# 样式
# ============================================================================

def apply_custom_css():
    """应用自定义 CSS 样式"""
    st.markdown("""
    <style>
    /* 主题色 */
    :root {
        --bg-dark: #0e1117;
        --bg-card: #1a1d24;
        --accent-red: #ff4b4b;
        --accent-green: #00d26a;
        --accent-orange: #ffa500;
        --text-primary: #fafafa;
        --text-secondary: #8b949e;
    }
    
    /* 标题样式 */
    .main-header {
        font-size: 2.5rem;
        font-weight: 700;
        color: var(--text-primary);
        text-align: center;
        padding: 1rem 0;
        background: linear-gradient(90deg, #ff4b4b, #ffa500);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    
    /* 信号卡片 */
    .signal-strong {
        background-color: rgba(255, 75, 75, 0.2);
        border-left: 4px solid #ff4b4b;
        padding: 0.5rem 1rem;
        margin: 0.5rem 0;
        border-radius: 4px;
    }
    
    .signal-normal {
        background-color: rgba(255, 165, 0, 0.2);
        border-left: 4px solid #ffa500;
        padding: 0.5rem 1rem;
        margin: 0.5rem 0;
        border-radius: 4px;
    }
    
    /* 指标卡片 */
    .metric-card {
        background-color: var(--bg-card);
        padding: 1rem;
        border-radius: 8px;
        text-align: center;
    }
    
    /* 侧边栏 */
    .sidebar .sidebar-content {
        background-color: var(--bg-card);
    }
    
    /* 数据表格 */
    .dataframe {
        font-size: 0.85rem;
    }
    </style>
    """, unsafe_allow_html=True)


# ============================================================================
# 数据加载函数
# ============================================================================

@st.cache_data(ttl=10)  # 缓存 10 秒
def load_signal_history() -> pd.DataFrame:
    """
    加载信号历史记录
    
    Returns:
        DataFrame 或空 DataFrame
    """
    try:
        if not SIGNAL_HISTORY_FILE.exists():
            return pd.DataFrame()
        
        df = pd.read_csv(SIGNAL_HISTORY_FILE)
        
        if df.empty:
            return df
        
        # 转换时间列
        if 'Time' in df.columns:
            df['Time'] = pd.to_datetime(df['Time'], errors='coerce')
        elif 'timestamp' in df.columns:
            df['Time'] = pd.to_datetime(df['timestamp'], errors='coerce')
        
        # 按时间降序排序
        if 'Time' in df.columns:
            df = df.sort_values('Time', ascending=False)
        
        return df
        
    except Exception as e:
        st.error(f"❌ 加载信号历史失败: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=10)
def load_symbol_data(symbol: str) -> pd.DataFrame:
    """
    加载指定交易对的历史数据
    
    Args:
        symbol: 交易对符号
        
    Returns:
        DataFrame 或空 DataFrame
    """
    try:
        csv_path = DATA_DIR / f"{symbol}.csv"
        
        if not csv_path.exists():
            return pd.DataFrame()
        
        df = pd.read_csv(csv_path)
        
        if df.empty:
            return df
        
        # 转换时间列
        if 'timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
            df = df.sort_values('timestamp', ascending=True)
        
        return df
        
    except Exception as e:
        st.error(f"❌ 加载 {symbol} 数据失败: {e}")
        return pd.DataFrame()


def get_available_symbols() -> list:
    """
    获取可用的交易对列表
    
    Returns:
        交易对符号列表
    """
    try:
        if not DATA_DIR.exists():
            return []
        
        csv_files = list(DATA_DIR.glob("*.csv"))
        symbols = [
            f.stem for f in csv_files 
            if f.stem != "signal_history" and not f.stem.startswith(".")
        ]
        
        return sorted(symbols)
        
    except Exception:
        return []


# ============================================================================
# 可视化函数
# ============================================================================

def create_candlestick_chart(df: pd.DataFrame, symbol: str) -> go.Figure:
    """
    创建 K 线图 + OI + 资金费率
    
    Args:
        df: 包含 OHLCV 数据的 DataFrame
        symbol: 交易对符号
        
    Returns:
        Plotly Figure
    """
    # 创建子图 (3 行: 价格, OI, 资金费率)
    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        row_heights=[0.5, 0.25, 0.25],
        subplot_titles=(
            f"📈 {symbol} 价格走势",
            "📊 持仓量 (Open Interest)",
            "💰 资金费率 (Funding Rate)"
        )
    )
    
    # 使用的时间列
    time_col = 'timestamp' if 'timestamp' in df.columns else df.index
    
    # ======== Row 1: 蜡烛图 ========
    # 判断列名格式 (大写或小写)
    open_col = 'Open' if 'Open' in df.columns else 'open'
    high_col = 'High' if 'High' in df.columns else 'high'
    low_col = 'Low' if 'Low' in df.columns else 'low'
    close_col = 'Close' if 'Close' in df.columns else 'close'
    
    fig.add_trace(
        go.Candlestick(
            x=df[time_col] if isinstance(time_col, str) else time_col,
            open=df[open_col],
            high=df[high_col],
            low=df[low_col],
            close=df[close_col],
            name="Price",
            increasing_line_color='#00d26a',
            decreasing_line_color='#ff4b4b'
        ),
        row=1, col=1
    )
    
    # ======== Row 2: 持仓量 ========
    oi_col = 'open_interest' if 'open_interest' in df.columns else None
    
    if oi_col and oi_col in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df[time_col] if isinstance(time_col, str) else time_col,
                y=df[oi_col],
                name="Open Interest",
                line=dict(color='#00bfff', width=2),
                fill='tozeroy',
                fillcolor='rgba(0, 191, 255, 0.1)'
            ),
            row=2, col=1
        )
    
    # ======== Row 3: 资金费率 ========
    fr_col = 'funding_rate' if 'funding_rate' in df.columns else None
    
    if fr_col and fr_col in df.columns:
        # 颜色根据正负值
        colors = ['#00d26a' if v >= 0 else '#ff4b4b' for v in df[fr_col]]
        
        fig.add_trace(
            go.Bar(
                x=df[time_col] if isinstance(time_col, str) else time_col,
                y=df[fr_col] * 100,  # 转为百分比
                name="Funding Rate (%)",
                marker_color=colors
            ),
            row=3, col=1
        )
    
    # ======== 布局 ========
    fig.update_layout(
        height=700,
        template="plotly_dark",
        showlegend=False,
        margin=dict(l=60, r=20, t=60, b=40),
        xaxis_rangeslider_visible=False,
        paper_bgcolor='#0e1117',
        plot_bgcolor='#0e1117'
    )
    
    # 更新 Y 轴标签
    fig.update_yaxes(title_text="Price", row=1, col=1)
    fig.update_yaxes(title_text="OI", row=2, col=1)
    fig.update_yaxes(title_text="FR (%)", row=3, col=1)
    
    return fig


def style_signal_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    为信号 DataFrame 添加样式
    """
    def highlight_severity(row):
        if 'Severity' in row.index:
            if row['Severity'] == 'STRONG':
                return ['background-color: rgba(255, 75, 75, 0.3)'] * len(row)
        return [''] * len(row)
    
    return df.style.apply(highlight_severity, axis=1)


# ============================================================================
# 主界面
# ============================================================================

def main():
    """主函数"""
    apply_custom_css()
    
    # ======== 侧边栏 ========
    with st.sidebar:
        st.markdown("# 🚀 Squeeze Radar")
        st.markdown("---")
        
        # 最后更新时间
        signals_df = load_signal_history()
        
        if not signals_df.empty and 'Time' in signals_df.columns:
            last_update = signals_df['Time'].iloc[0]
            if pd.notna(last_update):
                st.metric(
                    label="⏰ 最后更新",
                    value=last_update.strftime("%H:%M:%S") if hasattr(last_update, 'strftime') else str(last_update)[:19]
                )
        else:
            st.metric(label="⏰ 最后更新", value="暂无数据")
        
        st.markdown("---")
        
        # 过滤器
        st.markdown("### 🎚️ 过滤器")
        show_strong_only = st.checkbox("🔥 仅显示强信号", value=False)
        
        st.markdown("---")
        
        # 统计信息
        if not signals_df.empty:
            total_signals = len(signals_df)
            strong_signals = len(signals_df[signals_df.get('Severity', '') == 'STRONG']) if 'Severity' in signals_df.columns else 0
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric("📊 总信号", total_signals)
            with col2:
                st.metric("🔥 强信号", strong_signals)
        
        st.markdown("---")
        
        # 刷新按钮
        if st.button("🔄 手动刷新", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
        
        st.markdown("---")
        st.markdown("""
        <div style="text-align: center; color: #8b949e; font-size: 0.8rem;">
            📡 自动刷新: 30秒<br>
            Made with ❤️ by Quant Bot
        </div>
        """, unsafe_allow_html=True)
    
    # ======== 主内容区 ========
    st.markdown('<h1 class="main-header">🎯 Squeeze Command Center</h1>', unsafe_allow_html=True)
    
    # -------- Section 1: 信号流 --------
    st.markdown("## 📡 Signal Feed (信号流)")
    
    if signals_df.empty:
        st.info("📭 暂无信号记录。运行 `python main.py` 开始监控后，信号将显示在这里。")
    else:
        # 过滤
        display_df = signals_df.copy()
        if show_strong_only and 'Severity' in display_df.columns:
            display_df = display_df[display_df['Severity'] == 'STRONG']
        
        if display_df.empty:
            st.warning("⚠️ 没有符合条件的信号")
        else:
            # 显示最近 50 条
            display_df = display_df.head(50)
            
            # 格式化显示
            st.dataframe(
                display_df,
                use_container_width=True,
                height=300,
                column_config={
                    "Time": st.column_config.DatetimeColumn(
                        "时间",
                        format="YYYY-MM-DD HH:mm:ss"
                    ),
                    "Symbol": st.column_config.TextColumn("交易对", width="medium"),
                    "Price": st.column_config.NumberColumn("价格", format="%.4f"),
                    "Severity": st.column_config.TextColumn("级别", width="small"),
                    "Trend": st.column_config.TextColumn("趋势", width="medium"),
                }
            )
    
    st.markdown("---")
    
    # -------- Section 2: 市场分析器 --------
    st.markdown("## 📊 Market Analyzer (市场分析)")
    
    # 获取可用交易对
    available_symbols = get_available_symbols()
    
    if not available_symbols:
        st.warning("📂 `data/` 目录中没有找到交易对数据文件。")
    else:
        # 交易对选择器
        col1, col2, col3 = st.columns([2, 1, 1])
        
        with col1:
            selected_symbol = st.selectbox(
                "🎯 选择交易对",
                options=available_symbols,
                index=0 if available_symbols else None
            )
        
        with col2:
            # 显示数据点数量
            if selected_symbol:
                symbol_df = load_symbol_data(selected_symbol)
                st.metric("📊 数据点", len(symbol_df))
        
        with col3:
            # 显示最新价格
            if selected_symbol and not symbol_df.empty:
                close_col = 'close' if 'close' in symbol_df.columns else 'Close'
                if close_col in symbol_df.columns:
                    latest_price = symbol_df[close_col].iloc[-1]
                    st.metric("💵 最新价", f"${latest_price:.4f}")
        
        # 图表
        if selected_symbol:
            symbol_df = load_symbol_data(selected_symbol)
            
            if symbol_df.empty:
                st.warning(f"⚠️ {selected_symbol} 暂无数据")
            else:
                # 创建并显示图表
                fig = create_candlestick_chart(symbol_df, selected_symbol)
                st.plotly_chart(fig, use_container_width=True)
                
                # 数据概览
                with st.expander("📋 原始数据预览"):
                    st.dataframe(
                        symbol_df.tail(20),
                        use_container_width=True
                    )
    
    # -------- Footer --------
    st.markdown("---")
    st.markdown("""
    <div style="text-align: center; color: #8b949e; font-size: 0.8rem; padding: 1rem;">
        🔍 Short Squeeze Monitor | 
        📊 Data refreshes every 30 seconds | 
        ⚠️ Not financial advice
    </div>
    """, unsafe_allow_html=True)


# ============================================================================
# 运行
# ============================================================================

if __name__ == "__main__":
    main()

