import pandas as pd


def is_valid_comment(value) -> bool:
    text = str(value).strip().lower()
    invalid_values = {"", "nan", "none", "null", "na", "n/a", "无", "空", "-", "--"}
    return text not in invalid_values


def summarize_review_status(df_comments: pd.DataFrame) -> dict:
    required_columns = ["一级场景", "买家备注"]
    missing = [col for col in required_columns if col not in df_comments.columns]
    if missing:
        raise KeyError(f"缺少评论sheet必需列：{missing}")

    total_comments = len(df_comments)
    analyzed_comments = df_comments[~df_comments["一级场景"].astype(str).fillna("").str.strip().eq("")].shape[0]
    empty_comment_rows = df_comments[~df_comments["买家备注"].apply(is_valid_comment)].shape[0]
    pending_comments = df_comments[
        df_comments["一级场景"].astype(str).fillna("").str.strip().eq("")
        & df_comments["买家备注"].apply(is_valid_comment)
    ].shape[0]

    return {
        "total_comments": int(total_comments),
        "analyzed_comments": int(analyzed_comments),
        "pending_comments": int(pending_comments),
        "empty_comment_rows": int(empty_comment_rows),
    }


def prepare_comment_month(df_comments: pd.DataFrame) -> pd.DataFrame:
    result = df_comments.copy()
    if "退货时间" not in result.columns:
        result["退货月份"] = ""
        return result

    result["退货月份"] = pd.to_datetime(result["退货时间"], errors="coerce").dt.strftime("%Y-%m")
    result["退货月份"] = result["退货月份"].fillna("")
    return result


def summarize_kpi(df_comments: pd.DataFrame, df_sales: pd.DataFrame) -> dict:
    total_comments = len(df_comments)
    total_skus = 0
    if "亚马逊SKU" in df_comments.columns:
        total_skus = (
            df_comments["亚马逊SKU"]
            .astype(str)
            .fillna("")
            .str.strip()
            .replace("", pd.NA)
            .dropna()
            .unique()
            .shape[0]
        )
    total_sales = 0
    if "销量" in df_sales.columns:
        total_sales = pd.to_numeric(df_sales["销量"], errors="coerce").fillna(0).sum()
    overall_problem_rate = 0
    if total_sales and total_sales != 0:
        overall_problem_rate = float(total_comments) / float(total_sales)

    return {
        "total_comments": int(total_comments),
        "total_skus": int(total_skus),
        "total_sales": float(total_sales),
        "overall_problem_rate": float(overall_problem_rate),
    }


def build_sku_month_stats(df_comments: pd.DataFrame, df_sales: pd.DataFrame) -> pd.DataFrame:
    comments = df_comments.copy()
    if "退货时间" in comments.columns:
        comments = prepare_comment_month(comments)
    else:
        comments["退货月份"] = ""

    if "亚马逊SKU" not in comments.columns:
        raise KeyError("评论sheet缺少列：亚马逊SKU")
    if "退货月份" not in comments.columns:
        raise KeyError("评论sheet缺少列：退货月份")

    comments["亚马逊SKU"] = comments["亚马逊SKU"].astype(str).fillna("").str.strip()
    comments["退货月份"] = comments["退货月份"].astype(str).fillna("").str.strip()

    comments = comments[~comments["亚马逊SKU"].eq("") & ~comments["退货月份"].eq("")]
    comments["问题评论数"] = 1
    comment_stats = (
        comments.groupby(["亚马逊SKU", "退货月份"], dropna=False)
        ["问题评论数"]
        .count()
        .reset_index()
    )

    sales = df_sales.copy()
    if "亚马逊SKU" not in sales.columns or "月份" not in sales.columns or "销量" not in sales.columns:
        raise KeyError("销量sheet缺少列：亚马逊SKU、月份或销量")

    sales["亚马逊SKU"] = sales["亚马逊SKU"].astype(str).fillna("").str.strip()
    sales["月份"] = pd.to_datetime(sales["月份"], errors="coerce").dt.strftime("%Y-%m")
    sales["月份"] = sales["月份"].fillna("")
    sales["销量"] = pd.to_numeric(sales["销量"], errors="coerce").fillna(0)

    sales_stats = (
        sales.groupby(["亚马逊SKU", "月份"], dropna=False)["销量"].sum().reset_index()
        .rename(columns={"月份": "退货月份"})
    )

    merged = pd.merge(
        comment_stats,
        sales_stats,
        how="outer",
        left_on=["亚马逊SKU", "退货月份"],
        right_on=["亚马逊SKU", "退货月份"],
    )
    merged["问题评论数"] = merged["问题评论数"].fillna(0).astype(int)
    merged["销量"] = pd.to_numeric(merged["销量"], errors="coerce").fillna(0)
    merged["问题率"] = merged.apply(
        lambda row: float(row["问题评论数"]) / float(row["销量"]) if row["销量"] else 0,
        axis=1,
    )
    merged = merged[["亚马逊SKU", "退货月份", "问题评论数", "销量", "问题率"]].rename(columns={"退货月份": "月份"})
    return merged


def build_category_stats(df_comments: pd.DataFrame) -> pd.DataFrame:
    required_columns = ["一级场景", "二级维度", "三级对象", "四级问题", "五级描述"]
    missing = [col for col in required_columns if col not in df_comments.columns]
    if missing:
        raise KeyError(f"缺少评论sheet必需列：{missing}")

    stats = (
        df_comments.groupby(required_columns, dropna=False)
        .size()
        .reset_index(name="问题数")
    )
    return stats
def is_valid_comment(value):
    """
    判断评论是否有效：
    - 空值、NA、N/A、nan、none、无、- 等视为无效
    - 其他内容视为有效
    """
    if value is None:
        return False

    text = str(value).strip()

    if text == "":
        return False

    invalid_values = {
        "NA", "N/A", "NULL", "NONE", "NAN",
        "无", "暂无", "没有", "-", "--"
    }

    return text.upper() not in invalid_values