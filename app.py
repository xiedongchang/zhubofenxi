import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta, date
import requests
from io import BytesIO

# --- 1. 页面基础设置 ---
st.set_page_config(page_title="直播数据分析看板", layout="wide", page_icon="📊")
st.title("📊 直播间主播能力评估系统 (双向智能筛选版)")

# --- 2. 侧边栏：数据读取模块 ---
st.sidebar.header("1. 数据导入")

@st.cache_data(ttl=600)
def download_file(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers)
        r.raise_for_status()
        return BytesIO(r.content)
    except:
        return None

# 数据源选择
source_type = st.sidebar.radio("选择数据来源", ["📁 上传本地文件", "🔗 在线文件链接"])
file_obj = None

if source_type == "📁 上传本地文件":
    file_obj = st.sidebar.file_uploader("请上传 Excel 或 CSV 表格", type=['xlsx', 'xls', 'csv'])
else:
    url = st.sidebar.text_input("请输入文件直链 URL")
    if url and st.sidebar.button("📥 点击获取数据"):
        file_obj = download_file(url)
        if not file_obj:
            st.sidebar.error("下载失败，请检查链接是否有效")
        else:
            st.sidebar.success("数据获取成功！")

# --- 3. 数据处理核心逻辑 ---
if file_obj:
    try:
        # A. 读取文件
        df_raw = None
        is_excel = False
        
        try:
            excel_file = pd.ExcelFile(file_obj)
            is_excel = True
        except:
            if hasattr(file_obj, 'seek'): file_obj.seek(0)
            
        if is_excel:
            st.sidebar.markdown("---")
            sheet = st.sidebar.selectbox("2. 选择直播间 (Sheet工作表)", excel_file.sheet_names)
            header_idx = st.sidebar.number_input("表头在第几行? (0代表第1行, 1代表第2行)", value=1, min_value=0)
            df_raw = pd.read_excel(excel_file, sheet_name=sheet, header=header_idx)
        else:
            header_idx = st.sidebar.number_input("表头在第几行? (默认1)", value=1, min_value=0)
            df_raw = pd.read_csv(file_obj, header=header_idx)

        # B. 数据列匹配
        st.sidebar.markdown("---")
        st.sidebar.header("3. 列名对应设置")
        cols = df_raw.columns.tolist()
        
        def find_idx(keywords, default):
            for i, c in enumerate(cols):
                if any(k in str(c) for k in keywords): return i
            return default if default < len(cols) else 0

        c_time = st.sidebar.selectbox("📅 选择 [时间] 列", cols, index=find_idx(['时间','日期','Date'], 0))
        c_name = st.sidebar.selectbox("🎤 选择 [主播姓名] 列", cols, index=find_idx(['主播','姓名','Name'], 1))
        c_cost = st.sidebar.selectbox("💸 选择 [千川消耗] 列", cols, index=find_idx(['消耗','花费','Cost'], 2))
        c_sale = st.sidebar.selectbox("📦 选择 [成交订单数] 列", cols, index=find_idx(['订单','数量','销量','Sales'], 4))
        
        st.sidebar.markdown("---")
        price = st.sidebar.number_input("💰 设定客单价 (元)", value=3299.0, step=100.0)

        # C. 数据清洗与计算
        df = df_raw[[c_time, c_name, c_cost, c_sale]].copy()
        df.columns = ['Time', 'Name', 'Cost', 'Sales'] 

        def parse_date(x):
            try:
                return datetime(1899, 12, 30) + timedelta(days=float(x))
            except:
                return pd.to_datetime(x, errors='coerce')

        df['StdTime'] = df['Time'].apply(parse_date)
        df['StdTime'] = pd.to_datetime(df['StdTime'], errors='coerce')
        
        # 过滤无效日期
        df = df.dropna(subset=['StdTime'])
        df = df[df['StdTime'].dt.year > 2020]

        if df.empty:
            st.error("❌ 错误：有效数据为空！请检查[表头行数]是否选对。")
            st.stop()

        df['Date'] = df['StdTime'].dt.date
        df['Hour'] = df['StdTime'].dt.hour.astype(str) + ":00"
        
        df['Cost'] = pd.to_numeric(df['Cost'], errors='coerce').fillna(0)
        df['Sales'] = pd.to_numeric(df['Sales'], errors='coerce').fillna(0)
        
        df['GMV'] = df['Sales'] * price
        df['ROI'] = df.apply(lambda x: x['GMV']/x['Cost'] if x['Cost']>0 else 0, axis=1)
        df['CPA'] = df.apply(lambda x: x['Cost']/x['Sales'] if x['Sales']>0 else 0, axis=1)

        df = df.dropna(subset=['Name'])
        df = df[df['Name'].astype(str).str.strip() != '']
        df = df[df['Cost'] > 0] 

        # D. 双向智能筛选逻辑
        st.sidebar.markdown("---")
        st.sidebar.header("4. 数据筛选")

        # --- 基础：日期筛选 ---
        min_d, max_d = df['Date'].min(), df['Date'].max()
        def_start = date(2026, 1, 1)
        start_val = def_start if (min_d < def_start <= max_d) else min_d
        
        sel_date = st.sidebar.date_input(
            "1️⃣ 选日期范围", 
            [start_val, max_d], 
            min_value=min_d, 
            max_value=max_d,
            format="YYYY-MM-DD"
        )
        
        # 锁定日期范围内的数据
        mask_date = pd.Series([True]*len(df))
        if isinstance(sel_date, tuple) and len(sel_date) == 2:
            mask_date = (df['Date'] >= sel_date[0]) & (df['Date'] <= sel_date[1])
        df_period = df[mask_date]
        
        if df_period.empty:
            st.sidebar.warning("⚠️ 该日期范围内无数据")
            st.stop()

        # --- 核心：筛选模式切换 ---
        st.sidebar.markdown("---")
        filter_mode = st.sidebar.radio(
            "🔀 筛选主导模式 (决定谁过滤谁)",
            ["按时间找人 (默认)", "按人找时间"],
            help="按时间找人：选了时间，只显示该时间有班的人。\n按人找时间：选了人，只显示该人上播的时间。"
        )

        final_df = pd.DataFrame()

        if filter_mode == "按时间找人 (默认)":
            # 逻辑：先选小时 -> 再选主播
            
            # Step 1: 选小时
            available_hours = sorted(df_period['Hour'].unique(), key=lambda x: int(x.split(':')[0]))
            container_hour = st.sidebar.container()
            all_hours = container_hour.checkbox("全选时间点", value=True, key="cb_h1")
            
            if all_hours:
                sel_hours = container_hour.multiselect("2️⃣ 选时间点", available_hours, default=available_hours)
            else:
                sel_hours = container_hour.multiselect("2️⃣ 选时间点", available_hours)
            
            if not sel_hours:
                st.sidebar.warning("请至少选择一个时间点")
                st.stop()
            
            # 过滤出符合时间的数据
            df_step1 = df_period[df_period['Hour'].isin(sel_hours)]
            
            if df_step1.empty:
                st.sidebar.warning("所选时间段无数据")
                st.stop()

            # Step 2: 选主播 (基于上面的时间数据)
            # 这里的 available_streamers 只包含在所选时间上过播的人
            available_streamers = sorted(df_step1['Name'].unique().astype(str))
            
            container_name = st.sidebar.container()
            all_names = container_name.checkbox("全选主播", value=True, key="cb_n1")
            
            if all_names:
                sel_names = container_name.multiselect("3️⃣ 选主播 (自动过滤未上播人员)", available_streamers, default=available_streamers)
            else:
                sel_names = container_name.multiselect("3️⃣ 选主播", available_streamers)
                
            final_df = df_step1[df_step1['Name'].isin(sel_names)]

        else:
            # 逻辑：先选主播 -> 再选小时 (顺序调换，布局依然保持上下，但逻辑反转)
            
            # Step 1: 选主播 (基于日期数据)
            available_streamers = sorted(df_period['Name'].unique().astype(str))
            
            container_name = st.sidebar.container()
            all_names = container_name.checkbox("全选主播", value=True, key="cb_n2")
            
            # 为了布局好看，我们把主播选择放上面，时间放下面
            if all_names:
                sel_names = container_name.multiselect("2️⃣ 选主播", available_streamers, default=available_streamers)
            else:
                sel_names = container_name.multiselect("2️⃣ 选主播", available_streamers)
                
            if not sel_names:
                st.sidebar.warning("请至少选择一位主播")
                st.stop()
            
            # 过滤出符合主播的数据
            df_step1 = df_period[df_period['Name'].isin(sel_names)]
            
            # Step 2: 选小时 (基于上面的主播数据)
            # 这里的 available_hours 只包含所选主播上过播的时间点
            if df_step1.empty:
                st.sidebar.warning("所选主播在此期间无排班")
                st.stop()

            available_hours = sorted(df_step1['Hour'].unique(), key=lambda x: int(x.split(':')[0]))
            
            container_hour = st.sidebar.container()
            all_hours = container_hour.checkbox("全选时间点", value=True, key="cb_h2")
            
            if all_hours:
                sel_hours = container_hour.multiselect("3️⃣ 选时间点 (自动过滤没播的时间)", available_hours, default=available_hours)
            else:
                sel_hours = container_hour.multiselect("3️⃣ 选时间点", available_hours)
                
            final_df = df_step1[df_step1['Hour'].isin(sel_hours)]

        # E. 结果展示
        if not final_df.empty:
            
            t_cost = final_df['Cost'].sum()
            t_gmv = final_df['GMV'].sum()
            t_sale = final_df['Sales'].sum()
            avg_roi = t_gmv / t_cost if t_cost else 0
            avg_cpa = t_cost / t_sale if t_sale else 0
            
            st.subheader("📈 核心经营数据")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("总千川消耗", f"¥{t_cost:,.0f}")
            c2.metric("综合 ROI", f"{avg_roi:.2f}")
            c3.metric("总成交单量", f"{t_sale:,.0f} 单")
            c4.metric("平均单台成本", f"¥{avg_cpa:,.0f}")
            
            st.divider()
            
            # 排行榜计算
            agg = final_df.groupby('Name').agg({
                'Cost': 'sum', 
                'GMV': 'sum', 
                'Sales': 'sum', 
                'StdTime': 'count'
            }).reset_index()
            
            agg['ROI'] = agg.apply(lambda x: x['GMV']/x['Cost'] if x['Cost'] else 0, axis=1)
            agg['CPA'] = agg.apply(lambda x: x['Cost']/x['Sales'] if x['Sales'] else 0, axis=1)
            
            chinese_columns = {
                'Name': '主播姓名',
                'StdTime': '数据行数(时长)',
                'Cost': '千川消耗(元)',
                'Sales': '成交单量',
                'GMV': '销售额(GMV)',
                'ROI': 'ROI(投产比)',
                'CPA': '单台成本(元)'
            }
            display_df = agg.rename(columns=chinese_columns)
            
            st.subheader("🏆 主播能力排行榜")
            
            sort_options = {
                'ROI(投产比)': 'ROI(投产比)', 
                '销售额(GMV)': '销售额(GMV)', 
                '成交单量': '成交单量', 
                '千川消耗(元)': '千川消耗(元)',
                '单台成本(元)': '单台成本(元)'
            }
            sort_key_cn = st.selectbox("排序方式", list(sort_options.keys()))
            ascending_order = True if sort_key_cn == '单台成本(元)' else False
            
            sorted_df = display_df.sort_values(sort_key_cn, ascending=ascending_order)
            
            # 表格样式
            st.dataframe(
                sorted_df,
                column_config={
                    "数据行数(时长)": st.column_config.NumberColumn(
                        "数据行数(时长)",
                        help="上播数据量的统计",
                        format="%d" 
                    ),
                    "成交单量": st.column_config.NumberColumn(
                        "成交单量",
                        format="%d"
                    ),
                    "千川消耗(元)": st.column_config.NumberColumn(format="¥%d"),
                    "销售额(GMV)": st.column_config.NumberColumn(format="¥%d"),
                    "ROI(投产比)": st.column_config.NumberColumn(format="%.2f"),
                    "单台成本(元)": st.column_config.NumberColumn(format="¥%d"),
                },
                use_container_width=True,
                hide_index=True 
            )
            
            st.subheader("📊 可视化对比")
            col_chart1, col_chart2 = st.columns(2)
            
            with col_chart1:
                fig1 = px.bar(agg, x='Name', y='ROI', color='Name', text_auto='.2f', 
                              title="各主播 ROI 对比 (越高越好)", 
                              labels={'Name': '主播', 'ROI': 'ROI值'})
                fig1.update_layout(showlegend=False)
                st.plotly_chart(fig1, use_container_width=True)
                
            with col_chart2:
                fig2 = px.bar(agg, x='Name', y='GMV', color='Name', text_auto=',.0f', 
                              title="各主播 销售额GMV 对比", 
                              labels={'Name': '主播', 'GMV': '销售额'})
                fig2.update_layout(showlegend=False)
                st.plotly_chart(fig2, use_container_width=True)
            
            st.markdown("---")
            col_chart3, col_chart4 = st.columns(2)
            with col_chart3:
                # 时长柱状图
                fig3 = px.bar(agg, x='Name', y='StdTime', color='Name', text_auto=True,
                              title="上播数据行数(时长) 对比",
                              labels={'Name': '主播', 'StdTime': '数据行数'})
                fig3.update_traces(marker_color='#FF9999') 
                fig3.update_layout(showlegend=False)
                st.plotly_chart(fig3, use_container_width=True)
            
            with col_chart4:
                 fig4 = px.scatter(agg, x='CPA', y='Sales', size='GMV', color='Name', 
                                     hover_data=['ROI'], text='Name', title="成本 vs 销量 (气泡大小=GMV)")
                 st.plotly_chart(fig4, use_container_width=True)
                
        else:
            st.warning("⚠️ 筛选结果为空")

    except Exception as e:
        st.error(f"发生程序错误: {e}")
else:
    st.info("👈 请在左侧侧边栏上传数据文件")
