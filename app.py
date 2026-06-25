import os
import time
from io import BytesIO

import pandas as pd
import streamlit as st

from utils.ai_client import table_to_text, analyze_one_comment


st.set_page_config(
    page_title="评论AI分析工具",
    layout="wide"
)

st.title("评论AI分析工具")

# 模板文件下载功能
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

# 模板使用说明
with st.expander("📖 模板使用说明与AI分析逻辑", expanded=True):
    st.markdown("""
### 1. 这个工具怎么运作

用户下载模板 → 填写各个 Sheet → 上传 Excel → 输入 API Key → 设置每批分析数量 → AI 读取模板里的产品信息、分类层级、示例案例 → 逐条分析评论 → 输出分类结果和分析结果。

### 2. 各 Sheet 页作用

**评论数据**
- 用户放真正需要分析的评论数据
- 核心字段是评论内容
- 建议保留原行号、订单号、SKU、评分、评论时间等字段，用于后续结果回填和定位来源

**层级表**
- 用于定义 AI 的分类体系
- 例如一级分类、二级分类、三级分类
- AI 会优先按照这里的分类框架判断评论属于哪个问题类型，避免每次自由发挥，保证分类口径统一

**产品介绍**
- 用于告诉 AI 这个产品是什么
- 包括产品名称、功能、使用场景、适用人群、材质、尺寸、卖点、配件等
- 目的是让 AI 结合产品背景理解评论，不要脱离产品乱判断

**案例/修正/引导**
- 用于放人工示例
- 例如某条评论应该怎么分类、为什么这么分、哪些分法是错误的、应该如何修正
- 这相当于给 AI 做 few-shot 引导，提高准确率和一致性

### 3. 为什么要填这些

- 层级表 → 负责"分类标准"
- 产品介绍 → 负责"产品背景"
- 案例 → 负责"判断示范"
- 评论数据 → 负责"待分析内容"

AI 不是只看评论本身，而是综合这些 Sheet 后再判断。

### 4. 使用建议

- 第一次使用建议先放 20-50 条评论测试
- 确认分类口径正确后，再上传几千或几万条评论
- 如果分类不准，优先调整层级表和案例 Sheet
    """)

uploaded_file = st.file_uploader("上传Excel文件", type=["xlsx"])
api_key = st.text_input("请输入API Key", type="password")
batch_size = st.slider("每批发送给AI的评论数量", 1, 50, 5)

required_sheets = ["评论", "层级表", "产品描述", "分类举例"]

can_analyze = True

df_comment = None
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
        df_level = pd.read_excel(uploaded_file, sheet_name="层级表")
        df_product = pd.read_excel(uploaded_file, sheet_name="产品描述")
        df_examples = pd.read_excel(uploaded_file, sheet_name="分类举例")

        if "买家备注" not in df_comment.columns:
            st.error("评论sheet中未找到【买家备注】列")
            can_analyze = False
        elif "订单号" not in df_comment.columns:
            st.error("评论sheet中未找到【订单号】列")
            can_analyze = False
        else:
            st.success("文件结构校验通过")

            tab1, tab2, tab3, tab4 = st.tabs(["评论", "层级表", "产品描述", "分类举例"])

            with tab1:
                st.write(f"评论数据：{len(df_comment)} 行，{len(df_comment.columns)} 列")
                st.dataframe(df_comment.head(20), use_container_width=True)

            with tab2:
                st.write(f"层级表：{len(df_level)} 行，{len(df_level.columns)} 列")
                st.dataframe(df_level, use_container_width=True)

            with tab3:
                st.write(f"产品描述：{len(df_product)} 行，{len(df_product.columns)} 列")
                st.dataframe(df_product, use_container_width=True)

            with tab4:
                st.write(f"分类举例：{len(df_examples)} 行，{len(df_examples.columns)} 列")
                st.dataframe(df_examples.head(20), use_container_width=True)


if not api_key:
    st.warning("请填写API Key")
    can_analyze = False


if st.button("开始分析", disabled=not can_analyze):
    st.success("开始AI分析")

    product_text = table_to_text(df_product)
    level_text = table_to_text(df_level)
    examples_text = table_to_text(df_examples)

    df_comment = df_comment.copy()
    df_comment["订单号"] = df_comment["订单号"].fillna("").astype(str).str.strip()
    df_comment["买家备注"] = df_comment["买家备注"].fillna("").astype(str).str.strip()

    valid_df = df_comment[
        (df_comment["买家备注"] != "")
        & (df_comment["买家备注"].str.lower() != "nan")
        & (df_comment["买家备注"].str.lower() != "na")
        & (df_comment["买家备注"].str.lower() != "n/a")
    ].copy()

    st.write(f"总行数：{len(df_comment)}")
    st.write(f"有效评论数：{len(valid_df)}")
    st.write(f"每批发送数量：{batch_size}")

    rows = []
    progress_bar = st.progress(0)
    status_text = st.empty()

    total = len(valid_df)

    for idx, (_, row) in enumerate(valid_df.iterrows(), start=1):
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

            for item in data:
                rows.append({
                    "订单号": order_id,
                    "买家备注": comment,
                    "一级场景": item.get("一级场景", ""),
                    "二级维度": item.get("二级维度", ""),
                    "三级对象": item.get("三级对象", ""),
                    "四级问题": item.get("四级问题", ""),
                    "五级描述": item.get("五级描述", ""),
                    "AI原始返回": raw_text
                })

        except Exception as e:
            rows.append({
                "订单号": order_id,
                "买家备注": comment,
                "一级场景": "报错",
                "二级维度": "",
                "三级对象": "",
                "四级问题": "",
                "五级描述": "",
                "AI原始返回": str(e)
            })

        progress_bar.progress(idx / total)
        time.sleep(0.5)

    result_df = pd.DataFrame(rows)

    st.subheader("AI分析结果")
    st.dataframe(result_df, use_container_width=True)

    output_comment_df = result_df[
        [
            "订单号",
            "买家备注",
            "一级场景",
            "二级维度",
            "三级对象",
            "四级问题",
            "五级描述"
        ]
    ]

    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        output_comment_df.to_excel(writer, sheet_name="评论", index=False)
        df_level.to_excel(writer, sheet_name="层级表", index=False)
        df_product.to_excel(writer, sheet_name="产品描述", index=False)
        df_examples.to_excel(writer, sheet_name="分类举例", index=False)
        result_df.to_excel(writer, sheet_name="AI原始结果", index=False)

    output.seek(0)

    st.download_button(
        label="下载AI分析结果Excel",
        data=output,
        file_name="AI分析结果.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )