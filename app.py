import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta

# --- 页面设置 ---
st.set_page_config(page_title="直播主播能力分析看板", layout="wide")

st.title("📊 直播间主播能力评估系统")
st.markdown("### 核心目标：剥离时间段红利，还原主播真实转化力")

# --- 侧边栏：数据上传 ---
st.sidebar.header("1. 数据导入")
uploaded_file = st.sidebar.file_uploader("上传 Excel 或 CSV 表格", type=['csv', 'xlsx', 'xls'])

# --- 核心逻辑函数：处理 Excel 序列号日期 ---
def excel_date_to_datetime(serial):
    if pd.isna(serial) or serial == '':
        return None
    try:
        # 尝试直接转 float，处理类似 46023.25 的数字
        serial_float = float(serial)
        # Excel 的基准日期通常是 1899-12-30
        return datetime(1899, 12, 30) + timedelta(days=serial_float)
    except:
        # 如果不是数字，尝试直接解析字符串日期
        try:
            return pd.to_datetime(serial)
        except:
            return None

if uploaded_file is not None:
    # 1. 读取数据
    try:
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        else:
            # 兼容旧版 xls 和新版 xlsx
            df = pd.read_excel(uploaded_file)
    except Exception as e:
        st.error(f"文件读取失败: {e}")
        st.stop()

    # 2. 数据清洗与列名映射
    required_cols = ['日期与时间', '主播姓名', '千川消耗', '销售数量', '销售额']
    
    # 检查关键列是否存在
    if not set(required_cols).issubset(df.columns):
        st.warning("⚠️ 警告：系统检测到表格列名可能不完全匹配，正在尝试自动修正...")
        # 强制按顺序重命名（如果列数够的话）
        if len(df.columns) >= 7:
            df.columns = ['日期序列', '主播姓名', '千川消耗', '销售数量', '售价', '销售额', '单台成本'] + list(df.columns[7:])
            time_col = '日期序列'
            st.success("已自动识别列结构！")
        else:
            st.error(f"表格格式严重不符，请确保包含以下列：{required_cols}")
            st.write("你上传的列名:", df.columns.tolist())
            st.stop()
    else:
        time_col = '日期与时间'

    # 3. 数据清洗核心步骤
    
    # (A) 转换时间
    df['标准时间'] = df[time_col].apply(excel_date_to_datetime)
    df['标准时间'] = pd.to_datetime(df['标准时间'], errors='coerce')
    df = df.dropna(subset=['标准时间']) # 剔除时间无效的行

    # (B) 提取日期和小时
    try:
        df['日期'] = df['标准时间'].dt.date
        df['小时段'] = df['标准时间'].dt.hour.astype(str) + ":00"
    except Exception as e:
        st.error(f"日期处理出错: {e}")
        st.stop()

    # (C) 数值列强制转换 (防止Excel里有空格或文本)
    numeric_cols = ['千川消耗', '销售数量', '销售额']
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    # (D) 剔除无效数据
    df = df.dropna(subset=['主播姓名'])
    df = df[df['主播姓名'].astype(str).str.strip() != '']
    df = df[df['千川消耗'] > 0]

    # (E) 计算单行 ROI (仅用于参考)
    df['ROI'] = df.apply(lambda x: x['销售额'] / x['千川消耗'] if x['千川消耗'] > 0 else 0, axis=1)

    # --- 侧边栏：筛选器 ---
    st.sidebar.header("2. 筛选分析维度")
    
    if df.empty:
        st.warning("数据清洗后为空，请检查表格格式。")
        st.stop()

    # 日期范围
    min_date = df['日期'].min()
    max_date = df['日期'].max()
    
    if min_date == max_date:
        st.sidebar.info(f"📅 当前数据日期: {min_date}")
        date_range = (min_date, max_date)
    else:
        date_range = st.sidebar.date_input("选择日期范围", [min_date, max_date])
    
    # 时间段筛选
    all_hours = sorted(df['小时段'].unique(), key=lambda x: int(x.split(':')[0]))
    selected_hours = st.sidebar.multiselect(
        "⏰ 选择对比时间段 (排除垃圾时间)", 
        all_hours, 
        default=all_hours
    )
    
    # 主播筛选
    all_streamers = sorted(df['主播姓名'].unique().astype(str))
    selected_streamers = st.sidebar.multiselect(
        "🎤 选择要对比的主播", 
        all_streamers, 
        default=all_streamers
    )

    # --- 数据过滤逻辑 ---
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = date_range
        mask_date = (df['日期'] >= start_date) & (df['日期'] <= end_date)
        mask_hour = df['小时段'].isin(selected_hours)
        mask_streamer = df['主播姓名'].isin(selected_streamers)
        
        filtered_df = df[mask_date & mask_hour & mask_streamer]
    else:
        filtered_df = df

    # --- 结果展示区 ---
    
    if filtered_df.empty:
        st.warning("⚠️ 当前筛选条件下没有数据，请调整筛选器。")
    else:
        # 1. 总体大盘
        total_spend = filtered_df['千川消耗'].sum()
        total_gmv = filtered_df['销售额'].sum()
        total_sales = filtered_df['销售数量'].sum()
        avg_roi = total_gmv / total_spend if total_spend > 0 else 0
        avg_cpa = total_spend / total_sales if total_sales > 0 else 0

        st.subheader("📈 筛选范围内总览")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("💰 总千川消耗", f"¥{total_spend:,.0f}")
        c2.metric("🔥 综合 ROI", f"{avg_roi:.2f}")
        c3.metric("📦 总销售数量", f"{total_sales:,.0f} 台")
        c4.metric("📉 平均单台成本", f"¥{avg_cpa:,.0f}")

        st.divider()

        # 2. 主播能力排行榜
        st.subheader("🏆 主播能力数据表")
        
        agg_df = filtered_df.groupby('主播姓名').agg({
            '千川消耗': 'sum',
            '销售额': 'sum',
            '销售数量': 'sum',
            '日期': 'count' # 统计播了多少行数据
        }).reset_index()

        # 计算聚合指标
        agg_df['综合ROI'] = agg_df.apply(lambda x: x['销售额'] / x['千川消耗'] if x['千川消耗'] > 0 else 0, axis=1)
        agg_df['单台成本'] = agg_df.apply(lambda x: x['千川消耗'] / x['销售数量'] if x['销售数量'] > 0 else 0, axis=1)
        agg_df.rename(columns={'日期': '数据行数'}, inplace=True)

        # 排序
        sort_col = st.selectbox("按什么指标排序？", ['综合ROI', '销售额', '数据行数', '销售数量', '千川消耗', '单台成本'])
        ascending_order = True if sort_col == '单台成本' else False 
        agg_df = agg_df.sort_values(sort_col, ascending=ascending_order)

        # 格式化展示表格
        st.dataframe(
            agg_df[['主播姓名', '数据行数', '千川消耗', '销售数量', '销售额', '综合ROI', '单台成本']]
            .style.format({
                '千川消耗': '¥{:.0f}', 
                '销售额': '¥{:.0f}',
                '综合ROI': '{:.2f}', 
                '单台成本': '¥{:.0f}'
            }),
            use_container_width=True
        )

        st.divider()

        # 3. 四大核心图表
        st.subheader("📊 核心可视化分析")
        
        # 第一行：业绩核心 (ROI + 销售额)
        row1_1, row1_2 = st.columns(2)
        
        with row1_1:
            st.markdown("**🔥 主播 ROI 排行 (投产比)**")
            fig_roi = px.bar(agg_df, x='主播姓名', y='综合ROI', color='主播姓名', 
                             text_auto='.2f', # 保留2位小数
                             title="ROI (越高越好)")
            fig_roi.update_layout(showlegend=False)
            st.plotly_chart(fig_roi, use_container_width=True)

        with row1_2:
            st.markdown("**💰 主播总销售额排行**")
            # --- 【关键修改】text_auto 改成了 ',.0f' 代表显示千分位完整数字 ---
            fig_gmv = px.bar(agg_df, x='主播姓名', y='销售额', color='主播姓名', 
                             text_auto=',.0f', 
                             title="总销售额 GMV (业绩绝对值)")
            fig_gmv.update_layout(showlegend=False)
            st.plotly_chart(fig_gmv, use_container_width=True)

        # 第二行：勤奋度与综合 (上播时长 + 散点图)
        row2_1, row2_2 = st.columns(2)

        with row2_1:
            st.markdown("**⏰ 上播时间/数据量分布**")
            fig_duration = px.bar(agg_df, x='主播姓名', y='数据行数', color='数据行数',
                                  text_auto=True, # 自动显示行数数字
                                  title="上播数据行数 (样本量/时长)")
            fig_duration.update_traces(marker_color='lightslategray')
            fig_duration.update_layout(showlegend=False) # 隐藏图例让图表更大
            st.plotly_chart(fig_duration, use_container_width=True)

        with row2_2:
            st.markdown("**📉 投入产出综合散点图**")
            fig_scatter = px.scatter(agg_df, x='单台成本', y='销售数量', size='销售额', color='主播姓名', 
                                     hover_data=['综合ROI'], text='主播姓名',
                                     title="成本vs销量 (越靠左上角越强)")
            st.plotly_chart(fig_scatter, use_container_width=True)

        # 4. 详细数据明细
        with st.expander("🔍 查看原始明细数据"):
            st.dataframe(filtered_df[['标准时间', '主播姓名', '千川消耗', '销售数量', '销售额', 'ROI']])

else:
    st.info("👈 请在左侧上传包含数据的 CSV 或 Excel 文件。")