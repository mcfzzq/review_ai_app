import os
import sys
import time
from io import BytesIO

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from utils.ai_client import table_to_text, analyze_one_comment
from utils.charts import (
    build_sunburst_chart,
    build_monthly_trend_chart,
    build_sku_heatmap,
    build_sku_bubble_chart,
    build_sku_compare_chart,
    build_pareto_chart,
    build_wordcloud_figure,
    build_sku_issue_table,
)
from utils.statistics import summarize_review_status, is_valid_comment


st.set_page_config(
    page_title="评论AI分析工具",
    layout="wide"
)

st.title("评论AI分析工具")

template_file_path = os.path.join(os.path.dirname(__file__), "template.xlsx")
if os.path.exists(template_file_path):
    with open(template_file_path, "rb") as f:
        template_data = f.read()

    st.download_button(
        label="📥 下载Excel模板",
        data=template_data,
        file_name="评论分析模板.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
else:
    st.warning("未找到模板文件，请联系管理员")

st.markdown("---")

with st.expander("📖 模板使用说明与AI分析逻辑", expanded=False):
    st.markdown("""
### 1. 这个工具怎么运作

用户下载模板 → 填写各个 Sheet → 上传 Excel → 输入 API Key → 设置每批分析数量 → AI 读取模板里的产品信息、分类层级、示例案例 → 逐条分析评论 → 输出分类结果和分析结果。

### 2. 各 Sheet 页作用

**评论**
- 放真正需要分析的评论数据。
- 核心字段是【买家备注】。
- 建议保留订单号、SKU、退货时间等字段，用于后续结果回填和定位来源。

**销量**
- 用于结合 SKU 与月份计算问题率。
- 需要字段：【亚马逊SKU】、【月份】、【销量】。

**层级表**
- 用于定义 AI 的分类体系。
- AI 会优先按照这里的分类框架判断评论属于哪个问题类型。

**产品描述**
- 用于告诉 AI 这个产品是什么。

**分类案例**
- 用于放人工示例，提高准确率和一致性。
    """)

uploaded_file = st.file_uploader("上传Excel文件", type=["xlsx"])
api_key = st.text_input("请输入API密钥", type="password")
batch_size = st.slider("每批发送给AI的评论数量", 1, 50, 5)

required_sheets = ["评论", "销量", "产品描述", "层级表", "分类案例"]

can_analyze = True

df_comment = None
df_sales = None
df_level = None
df_product = None
df_examples = None

if uploaded_file is None:
    st.warning("请先上传Excel文件")
    can_analyze = False
else:
    excel_file = pd.ExcelFile(uploaded_file)
    sheet_names = excel_file.sheet_names

    missing_sheets = [s for s in required_sheets if s not in sheet_names]

    if missing_sheets:
        st.error(f"缺少必要Sheet页：{missing_sheets}")
        st.write("当前文件包含Sheet页：")
        st.write(sheet_names)
        can_analyze = False
    else:
        df_comment = pd.read_excel(uploaded_file, sheet_name="评论")
        df_sales = pd.read_excel(uploaded_file, sheet_name="销量")
        df_level = pd.read_excel(uploaded_file, sheet_name="层级表")
        df_product = pd.read_excel(uploaded_file, sheet_name="产品描述")
        df_examples = pd.read_excel(uploaded_file, sheet_name="分类案例")

        if "买家备注" not in df_comment.columns:
            st.error("评论sheet中未找到【买家备注】列")
            can_analyze = False
        elif "一级场景" not in df_comment.columns:
            st.error("评论sheet中未找到【一级场景】列")
            can_analyze = False
        elif "订单号" not in df_comment.columns:
            st.error("评论sheet中未找到【订单号】列")
            can_analyze = False
        else:
            st.success("文件结构校验通过")

            try:
                review_status = summarize_review_status(df_comment)
            except KeyError as e:
                st.error(str(e))
                can_analyze = False
            else:
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("评论总数", review_status["total_comments"])
                col2.metric("已分析", review_status["analyzed_comments"])
                col3.metric("待分析", review_status["pending_comments"])
                col4.metric("空评论行", review_status["empty_comment_rows"])

                if review_status["pending_comments"] == 0:
                    st.info("当前没有新增待分析评论。点击开始分析后，将直接基于完整历史结果生成结果文件和数据分析图表。")
                else:
                    st.warning(
                        f"本次将只分析 {review_status['pending_comments']} 条新增评论，"
                        f"已分析历史评论不会重复调用 AI。"
                    )

                st.caption("空评论行指买家备注为空、NA、N/A、None、null、- 等无有效评论内容的行，不会调用 AI。")

            if can_analyze:
                tab1, tab2, tab3, tab4, tab5 = st.tabs(
                    ["评论", "销量", "分类表", "产品描述", "分类案例"]
                )

                with tab1:
                    st.write(f"评论数据：{len(df_comment)} 行，{len(df_comment.columns)} 列")
                    st.dataframe(df_comment.head(20), use_container_width=True)

                with tab2:
                    st.write(f"销量数据：{len(df_sales)} 行，{len(df_sales.columns)} 列")
                    st.dataframe(df_sales.head(20), use_container_width=True)

                with tab3:
                    st.write(f"分类层级数据：{len(df_level)} 行，{len(df_level.columns)} 列")
                    st.dataframe(df_level, use_container_width=True)

                with tab4:
                    st.write(f"产品描述：{len(df_product)} 行，{len(df_product.columns)} 列")
                    st.dataframe(df_product, use_container_width=True)

                with tab5:
                    st.write(f"分类案例：{len(df_examples)} 行，{len(df_examples.columns)} 列")
                    st.dataframe(df_examples.head(20), use_container_width=True)

if not api_key:
    st.warning("请填写API密钥")
    can_analyze = False


if st.button("开始分析", disabled=not can_analyze):
    st.success("开始AI分析")

    product_text = table_to_text(df_product)
    level_text = table_to_text(df_level)
    examples_text = table_to_text(df_examples)

    df_comment = df_comment.copy()
    df_comment["订单号"] = df_comment["订单号"].fillna("").astype(str).str.strip()
    df_comment["买家备注"] = df_comment["买家备注"].fillna("").astype(str).str.strip()
    df_comment["一级场景"] = df_comment["一级场景"].fillna("").astype(str).str.strip()

    for col in ["二级维度", "三级对象", "四级问题", "五级描述", "AI原始返回"]:
        if col not in df_comment.columns:
            df_comment[col] = ""

    pending_df = df_comment[
        df_comment["一级场景"].eq("")
        & df_comment["买家备注"].apply(is_valid_comment)
    ].copy()

    completed_count = len(df_comment) - len(pending_df)

    st.write(f"总评论行数：{len(df_comment)}")
    st.write(f"已完成分析行数：{completed_count}")
    st.write(f"本次新增分析行数：{len(pending_df)}")
    st.write(f"每批发送数量：{batch_size}")

    total = len(pending_df)

    if total == 0:
        st.info("没有需要新增分析的评论行，当前评论数据已是完整结果。")
    else:
        progress_bar = st.progress(0)
        status_text = st.empty()

        for idx, (row_index, row) in enumerate(pending_df.iterrows(), start=1):
            order_id = str(row["订单号"]).strip()
            comment = str(row["买家备注"]).strip()

            status_text.write(f"正在分析第 {idx} / {total} 条，订单号：{order_id}")

            try:
                data, raw_text = analyze_one_comment(
                    api_key=api_key,
                    comment=comment,
                    product_text=product_text,
                    level_text=level_text,
                    examples_text=examples_text
                )

                if isinstance(data, list) and len(data) > 0:
                    item = data[0]
                elif isinstance(data, dict):
                    item = data
                else:
                    item = {}

                df_comment.loc[row_index, "一级场景"] = item.get("一级场景", "")
                df_comment.loc[row_index, "二级维度"] = item.get("二级维度", "")
                df_comment.loc[row_index, "三级对象"] = item.get("三级对象", "")
                df_comment.loc[row_index, "四级问题"] = item.get("四级问题", "")
                df_comment.loc[row_index, "五级描述"] = item.get("五级描述", "")
                df_comment.loc[row_index, "AI原始返回"] = raw_text

            except Exception as e:
                df_comment.loc[row_index, "一级场景"] = "报错"
                df_comment.loc[row_index, "二级维度"] = ""
                df_comment.loc[row_index, "三级对象"] = ""
                df_comment.loc[row_index, "四级问题"] = ""
                df_comment.loc[row_index, "五级描述"] = ""
                df_comment.loc[row_index, "AI原始返回"] = str(e)

            progress_bar.progress(idx / total)
            time.sleep(0.5)

    st.subheader("完整评论结果")
    st.dataframe(df_comment.head(20), use_container_width=True)

    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df_comment.to_excel(writer, sheet_name="评论", index=False)
        df_sales.to_excel(writer, sheet_name="销量", index=False)
        df_level.to_excel(writer, sheet_name="层级表", index=False)
        df_product.to_excel(writer, sheet_name="产品描述", index=False)
        df_examples.to_excel(writer, sheet_name="分类案例", index=False)

    output.seek(0)

    st.download_button(
        label="下载AI分析结果Excel",
        data=output,
        file_name="AI分析结果.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    st.markdown("---")
    st.header("数据分析")

    try:
        analyzed_df = df_comment.copy()
        analyzed_df = analyzed_df[analyzed_df["一级场景"].apply(is_valid_comment)]

        if analyzed_df.empty:
            st.info("当前暂无已分析的评论数据，无法生成数据分析图表。")
        else:
            st.caption("说明：旭日图、帕累托图展示问题结构和问题数量；趋势图、热力图、气泡图、SKU对比图展示问题率。")

            st.subheader("1. 问题分类结构旭日图")
            try:
                st.plotly_chart(build_sunburst_chart(analyzed_df), use_container_width=True)
            except Exception as e:
                st.info(f"旭日图暂不可用：{e}")

            st.subheader("2. 四级问题月度问题率趋势")
            try:
                st.plotly_chart(build_monthly_trend_chart(analyzed_df, df_sales), use_container_width=True)
            except Exception as e:
                st.info(f"月度问题率趋势图暂不可用：{e}")

            st.subheader("3. SKU × 问题层级问题率热力图")
            try:
                st.plotly_chart(build_sku_heatmap(analyzed_df, df_sales), use_container_width=True)
            except Exception as e:
                st.info(f"SKU问题率热力图暂不可用：{e}")

            st.subheader("4. SKU销量 × 问题率气泡图")
            try:
                st.plotly_chart(build_sku_bubble_chart(analyzed_df, df_sales), use_container_width=True)
            except Exception as e:
                st.info(f"SKU气泡图暂不可用：{e}")

            st.subheader("5. SKU主要问题率对比")
            try:
                st.plotly_chart(build_sku_compare_chart(analyzed_df, df_sales), use_container_width=True)
            except Exception as e:
                st.info(f"SKU问题率对比图暂不可用：{e}")

            st.subheader("6. 四级问题帕累托分析")
            try:
                st.plotly_chart(build_pareto_chart(analyzed_df), use_container_width=True)
            except Exception as e:
                st.info(f"帕累托图暂不可用：{e}")

            st.subheader("7. 评论词云")
            try:
                wordcloud_fig = build_wordcloud_figure(analyzed_df)
                st.pyplot(wordcloud_fig, use_container_width=True)
            except Exception as e:
                st.info(f"词云暂不可用：{e}")

            st.subheader("8. SKU主要问题明细表")
            try:
                sku_table = build_sku_issue_table(analyzed_df, df_sales, top_n=5)
                st.dataframe(sku_table, use_container_width=True)
            except Exception as e:
                st.info(f"SKU主要问题明细表暂不可用：{e}")

    except KeyError as e:
        st.error(str(e))
    except Exception as e:
        st.error(f"生成数据分析图表时出错：{e}")