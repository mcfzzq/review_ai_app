import re

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from .statistics import is_valid_comment


COLOR_MAP = {
    "产品体验": "#2563EB",
    "用户需求": "#06B6D4",
    "市场竞争": "#8B5CF6",
    "履约过程": "#F97316",
    "无法判断": "#9CA3AF",
}


def _clean_text_series(s: pd.Series) -> pd.Series:
    return s.fillna("").astype(str).str.strip()


def _require_cols(df: pd.DataFrame, cols: list[str], table_name: str = "表"):
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise KeyError(f"{table_name}缺少列：{missing}")


def _normalize_month(s: pd.Series) -> pd.Series:
    raw = s.fillna("").astype(str).str.strip()

    parsed = pd.to_datetime(raw, errors="coerce")
    result = parsed.dt.strftime("%Y-%m")

    mask = result.isna() | (result == "NaT")
    extracted = raw.str.extract(r"(\d{4})[-/年\.](\d{1,2})")
    fallback = extracted[0] + "-" + extracted[1].str.zfill(2)

    result = result.where(~mask, fallback)
    return result.fillna("").astype(str).str.strip()


def _filter_analyzed_comments(df_comments: pd.DataFrame) -> pd.DataFrame:
    _require_cols(df_comments, ["一级场景"], "评论sheet")

    df = df_comments.copy()
    df["一级场景"] = _clean_text_series(df["一级场景"])
    df = df[df["一级场景"].apply(is_valid_comment)]
    return df


def prepare_issue_rate_data(df_comments: pd.DataFrame, df_sales: pd.DataFrame) -> pd.DataFrame:
    df = _filter_analyzed_comments(df_comments)
    _require_cols(df, ["亚马逊SKU", "退货时间", "一级场景", "二级维度", "四级问题"], "评论sheet")
    _require_cols(df_sales, ["亚马逊SKU", "月份", "销量"], "销量sheet")

    df["亚马逊SKU"] = _clean_text_series(df["亚马逊SKU"])
    df["一级场景"] = _clean_text_series(df["一级场景"])
    df["二级维度"] = _clean_text_series(df["二级维度"])
    df["四级问题"] = _clean_text_series(df["四级问题"])
    df["月份"] = _normalize_month(df["退货时间"])

    df = df[
        df["亚马逊SKU"].apply(is_valid_comment)
        & df["月份"].apply(is_valid_comment)
        & df["一级场景"].apply(is_valid_comment)
    ].copy()

    sales = df_sales.copy()
    sales["亚马逊SKU"] = _clean_text_series(sales["亚马逊SKU"])
    sales["月份"] = _normalize_month(sales["月份"])
    sales["销量"] = pd.to_numeric(sales["销量"], errors="coerce").fillna(0)
    sales = sales.groupby(["亚马逊SKU", "月份"], as_index=False)["销量"].sum()

    grouped = (
        df.groupby(["亚马逊SKU", "月份", "一级场景", "二级维度", "四级问题"])
        .size()
        .reset_index(name="问题数")
    )

    result = grouped.merge(sales, on=["亚马逊SKU", "月份"], how="left")
    result["销量"] = result["销量"].fillna(0)
    result = result[result["销量"] > 0].copy()
    result["问题率"] = result["问题数"] / result["销量"]

    return result


def build_sunburst_chart(df_comments: pd.DataFrame):
    df = _filter_analyzed_comments(df_comments)
    required_cols = ["一级场景", "二级维度", "三级对象", "四级问题"]
    _require_cols(df, required_cols, "评论sheet")

    for col in required_cols:
        df[col] = _clean_text_series(df[col])
        df[col] = df[col].where(df[col].apply(is_valid_comment), "未知")

    fig = px.sunburst(
        df,
        path=required_cols,
        color="一级场景",
        color_discrete_map=COLOR_MAP,
        title="问题分类结构旭日图",
    )
    fig.update_layout(height=720, margin=dict(t=60, l=20, r=20, b=20))
    return fig


def build_monthly_trend_chart(df_comments: pd.DataFrame, df_sales: pd.DataFrame, top_n: int = 5):
    rate_df = prepare_issue_rate_data(df_comments, df_sales)

    if rate_df.empty:
        raise ValueError("没有可用于月度问题率趋势的数据")

    top_issues = (
        rate_df.groupby("四级问题")["问题数"]
        .sum()
        .sort_values(ascending=False)
        .head(top_n)
        .index
        .tolist()
    )

    df = rate_df[rate_df["四级问题"].isin(top_issues)].copy()

    trend = (
        df.groupby(["月份", "四级问题"], as_index=False)
        .agg({"问题数": "sum", "销量": "sum"})
    )
    trend["问题率"] = trend["问题数"] / trend["销量"]
    trend = trend.sort_values("月份")

    fig = px.line(
        trend,
        x="月份",
        y="问题率",
        color="四级问题",
        markers=True,
        title=f"四级问题 TOP{top_n} 月度问题率趋势",
    )
    fig.update_xaxes(type="category", title="月份")
    fig.update_yaxes(tickformat=".2%", title="问题率")
    fig.update_layout(height=560, margin=dict(t=60, l=20, r=20, b=40))
    return fig


def build_sku_heatmap(df_comments: pd.DataFrame, df_sales: pd.DataFrame, top_sku_n: int = 10):
    rate_df = prepare_issue_rate_data(df_comments, df_sales)

    if rate_df.empty:
        raise ValueError("没有可用于 SKU 问题率热力图的数据")

    top_skus = (
        rate_df.groupby("亚马逊SKU")["问题数"]
        .sum()
        .sort_values(ascending=False)
        .head(top_sku_n)
        .index
        .tolist()
    )

    df = rate_df[rate_df["亚马逊SKU"].isin(top_skus)].copy()
    df["问题层级"] = df["一级场景"] + " / " + df["二级维度"]

    pivot_data = (
        df.groupby(["问题层级", "亚马逊SKU"], as_index=False)
        .agg({"问题数": "sum", "销量": "sum"})
    )
    pivot_data["问题率"] = pivot_data["问题数"] / pivot_data["销量"]

    rate_matrix = pivot_data.pivot(
        index="问题层级",
        columns="亚马逊SKU",
        values="问题率"
    ).fillna(0)

    issue_matrix = pivot_data.pivot(
        index="问题层级",
        columns="亚马逊SKU",
        values="问题数"
    ).fillna(0)

    sales_matrix = pivot_data.pivot(
        index="问题层级",
        columns="亚马逊SKU",
        values="销量"
    ).fillna(0)

    text_matrix = rate_matrix.copy()
    for col in text_matrix.columns:
        text_matrix[col] = text_matrix[col].map(lambda x: f"{x:.2%}" if x > 0 else "")

    customdata = []
    for row_key in rate_matrix.index:
        row_data = []
        for col_key in rate_matrix.columns:
            row_data.append([
                issue_matrix.loc[row_key, col_key],
                sales_matrix.loc[row_key, col_key],
                rate_matrix.loc[row_key, col_key],
            ])
        customdata.append(row_data)

    fig = px.imshow(
        rate_matrix,
        aspect="auto",
        color_continuous_scale=["#FFFFFF", "#FCA5A5", "#DC2626"],
        title=f"SKU × 问题层级问题率热力图（TOP{top_sku_n} SKU）",
    )

    fig.update_traces(
        text=text_matrix.values,
        texttemplate="%{text}",
        customdata=customdata,
        hovertemplate=(
            "问题层级：%{y}<br>"
            "亚马逊SKU：%{x}<br>"
            "问题数：%{customdata[0]:,.0f}<br>"
            "销量：%{customdata[1]:,.0f}<br>"
            "问题率：%{customdata[2]:.2%}<extra></extra>"
        ),
    )

    fig.update_layout(height=700, margin=dict(t=60, l=20, r=20, b=80))
    fig.update_coloraxes(colorbar_tickformat=".2%")
    return fig


def build_sku_bubble_chart(
    df_comments: pd.DataFrame,
    df_sales: pd.DataFrame,
    min_sales: int = 100,
    top_n: int = 20,
):
    rate_df = prepare_issue_rate_data(df_comments, df_sales)

    if rate_df.empty:
        raise ValueError("没有可用于 SKU 气泡图的数据")

    sku_total = (
        rate_df.groupby("亚马逊SKU", as_index=False)
        .agg({"问题数": "sum", "销量": "sum"})
    )
    sku_total["问题率"] = sku_total["问题数"] / sku_total["销量"]

    main_scene = (
        rate_df.groupby(["亚马逊SKU", "一级场景"])["问题数"]
        .sum()
        .reset_index()
        .sort_values(["亚马逊SKU", "问题数"], ascending=[True, False])
        .drop_duplicates("亚马逊SKU")
        [["亚马逊SKU", "一级场景"]]
    )

    bubble = sku_total.merge(main_scene, on="亚马逊SKU", how="left")
    bubble = bubble[bubble["销量"] >= min_sales].copy()
    bubble = bubble.sort_values("问题数", ascending=False).head(top_n)

    if bubble.empty:
        raise ValueError(f"没有销量大于等于 {min_sales} 的 SKU 可用于气泡图")

    fig = px.scatter(
        bubble,
        x="销量",
        y="问题率",
        size="问题数",
        color="一级场景",
        color_discrete_map=COLOR_MAP,
        hover_data={
            "亚马逊SKU": True,
            "一级场景": True,
            "问题数": True,
            "销量": ":,.0f",
            "问题率": ":.2%",
        },
        text="亚马逊SKU",
        title=f"SKU销量 × 问题率气泡图（销量≥{min_sales}，TOP{top_n}）",
    )

    fig.update_traces(textposition="top center")
    fig.update_yaxes(tickformat=".2%", title="问题率")
    fig.update_xaxes(title="销量")
    fig.update_layout(height=620, margin=dict(t=60, l=20, r=20, b=60))
    return fig


def build_sku_compare_chart(df_comments: pd.DataFrame, df_sales: pd.DataFrame, top_sku_n: int = 8, top_issue_n: int = 5):
    rate_df = prepare_issue_rate_data(df_comments, df_sales)

    if rate_df.empty:
        raise ValueError("没有可用于 SKU 问题率对比的数据")

    top_skus = (
        rate_df.groupby("亚马逊SKU")["问题数"]
        .sum()
        .sort_values(ascending=False)
        .head(top_sku_n)
        .index
        .tolist()
    )
    top_issues = (
        rate_df.groupby("四级问题")["问题数"]
        .sum()
        .sort_values(ascending=False)
        .head(top_issue_n)
        .index
        .tolist()
    )

    df = rate_df[
        rate_df["亚马逊SKU"].isin(top_skus)
        & rate_df["四级问题"].isin(top_issues)
    ].copy()

    compare = (
        df.groupby(["亚马逊SKU", "四级问题"], as_index=False)
        .agg({"问题数": "sum", "销量": "sum"})
    )
    compare["问题率"] = compare["问题数"] / compare["销量"]

    fig = px.bar(
        compare,
        x="亚马逊SKU",
        y="问题率",
        color="四级问题",
        barmode="group",
        title=f"SKU主要问题率对比（TOP{top_sku_n} SKU × TOP{top_issue_n} 问题）",
        text=compare["问题率"].map(lambda x: f"{x:.2%}"),
    )
    fig.update_yaxes(tickformat=".2%", title="问题率")
    fig.update_layout(height=600, margin=dict(t=60, l=20, r=20, b=100))
    return fig


def build_pareto_chart(df_comments: pd.DataFrame, top_n: int = 15):
    df = _filter_analyzed_comments(df_comments)
    _require_cols(df, ["四级问题"], "评论sheet")

    df["四级问题"] = _clean_text_series(df["四级问题"])
    df = df[df["四级问题"].apply(is_valid_comment)]

    if df.empty:
        raise ValueError("没有可用于帕累托分析的数据")

    counts = df["四级问题"].value_counts().head(top_n).reset_index()
    counts.columns = ["四级问题", "数量"]
    counts["累计占比"] = counts["数量"].cumsum() / counts["数量"].sum() * 100

    fig = go.Figure()

    fig.add_trace(
        go.Bar(
            x=counts["四级问题"],
            y=counts["数量"],
            name="问题数",
            marker_color="#2563EB",
            text=counts["数量"],
            textposition="auto",
        )
    )

    fig.add_trace(
        go.Scatter(
            x=counts["四级问题"],
            y=counts["累计占比"],
            name="累计占比",
            yaxis="y2",
            mode="lines+markers",
            line=dict(color="#EF4444", width=3),
        )
    )

    fig.add_hline(
        y=80,
        line_dash="dash",
        line_color="#EF4444",
        annotation_text="80%",
        annotation_position="top left",
        yref="y2",
    )

    fig.update_layout(
        title=f"四级问题帕累托分析 TOP{top_n}",
        height=580,
        yaxis=dict(title="问题数"),
        yaxis2=dict(
            title="累计占比",
            overlaying="y",
            side="right",
            range=[0, 105],
            ticksuffix="%",
        ),
        margin=dict(t=60, l=20, r=20, b=100),
    )
    return fig


def build_wordcloud_figure(df_comments: pd.DataFrame):
    try:
        from wordcloud import WordCloud
        import matplotlib.pyplot as plt
    except ImportError:
        raise ImportError("缺少 wordcloud 或 matplotlib，请先安装：pip install wordcloud matplotlib")

    text_cols = [c for c in ["买家备注", "五级描述"] if c in df_comments.columns]
    if not text_cols:
        raise KeyError("评论sheet缺少列：买家备注 或 五级描述")

    texts = []
    for col in text_cols:
        texts.extend(_clean_text_series(df_comments[col]).tolist())

    raw_text = " ".join([t for t in texts if is_valid_comment(t)])
    words = re.findall(r"[A-Za-z\u4e00-\u9fa5]+", raw_text)

    stopwords = {
        "the", "and", "is", "to", "it", "a", "of", "for", "in", "on", "not",
        "this", "that", "with", "was", "too", "very", "but", "have", "has",
        "None", "none", "产品", "问题", "用户", "没有", "无法", "使用"
    }

    words = [w for w in words if w not in stopwords and len(w) > 1]

    if not words:
        raise ValueError("没有可用于生成词云的文本")

    def red_color_func(word, font_size, position, orientation, random_state=None, **kwargs):
        if font_size > 120:
            return "rgb(153, 27, 27)"
        elif font_size > 70:
            return "rgb(185, 28, 28)"
        elif font_size > 40:
            return "rgb(220, 38, 38)"
        else:
            return "rgb(248, 113, 113)"

    wc = WordCloud(
        width=1400,
        height=600,
        background_color="white",
        max_words=120,
        prefer_horizontal=0.9,
        color_func=red_color_func,
    ).generate(" ".join(words))

    fig, ax = plt.subplots(figsize=(14, 6))
    ax.imshow(wc, interpolation="bilinear")
    ax.axis("off")
    return fig


def build_sku_issue_table(df_comments: pd.DataFrame, df_sales: pd.DataFrame | None = None, top_n: int = 5) -> pd.DataFrame:
    if df_sales is None:
        df = _filter_analyzed_comments(df_comments)
        _require_cols(df, ["亚马逊SKU", "四级问题"], "评论sheet")

        df["亚马逊SKU"] = _clean_text_series(df["亚马逊SKU"])
        df["四级问题"] = _clean_text_series(df["四级问题"])

        counts = (
            df.groupby(["亚马逊SKU", "四级问题"])
            .size()
            .reset_index(name="问题数")
            .sort_values(["亚马逊SKU", "问题数"], ascending=[True, False])
        )
        counts["排名"] = counts.groupby("亚马逊SKU").cumcount() + 1
        return counts[counts["排名"] <= top_n][["亚马逊SKU", "排名", "四级问题", "问题数"]]

    rate_df = prepare_issue_rate_data(df_comments, df_sales)

    result = (
        rate_df.groupby(["亚马逊SKU", "四级问题"], as_index=False)
        .agg({"问题数": "sum", "销量": "sum"})
    )
    result["问题率"] = result["问题数"] / result["销量"]
    result = result.sort_values(["亚马逊SKU", "问题率"], ascending=[True, False])
    result["排名"] = result.groupby("亚马逊SKU").cumcount() + 1
    result = result[result["排名"] <= top_n].copy()
    result["问题率"] = result["问题率"].map(lambda x: f"{x:.2%}")

    return result[["亚马逊SKU", "排名", "四级问题", "问题数", "销量", "问题率"]]