import json
import re
import pandas as pd
from openai import OpenAI


def table_to_text(df: pd.DataFrame, max_rows=None) -> str:
    if max_rows:
        df = df.head(max_rows)
    df = df.fillna("")
    return df.to_markdown(index=False)


def extract_json(text: str):
    text = text.strip()
    text = re.sub(r"^```json", "", text, flags=re.I).strip()
    text = re.sub(r"^```", "", text).strip()
    text = re.sub(r"```$", "", text).strip()

    try:
        return json.loads(text)
    except Exception:
        match = re.search(r"\[.*\]", text, re.S)
        if match:
            return json.loads(match.group(0))
        raise


def build_prompt(comment, product_text, level_text, examples_text):
    return f"""
你是亚马逊售后评论VOC分析专家，任务是把买家评论结构化分类，用于后续BI分析。

【产品资料】
{product_text}

【允许使用的分类框架】
{level_text}

【标准分类案例】
{examples_text}

【分类规则】
1. 必须优先参考“标准分类案例”的分类口径。
2. 一级场景、二级维度必须从“允许使用的分类框架”中选择，禁止新增。
3. 三级对象、四级问题优先从“允许使用的分类框架”中选择；如果没有合适项，可以根据评论合理新增。
4. 五级描述由AI根据评论生成，要求简短、具体。
5. 所有字段都不能为空；如果无法判断，必须填写：无法判断、信息不足、整体、信息不足。
6. 评论包含多个问题时，必须拆成多条结果。
7. 如果评论只是“Walmart”“NA”“No”等无有效内容，归为：无法判断 → 信息不足 → 整体 → 信息不足。
8. 只能返回标准JSON数组。
9. 禁止输出 ```json。
10. 禁止输出解释文字。
11. JSON字段必须固定为：一级场景、二级维度、三级对象、四级问题、五级描述。

【待分类评论】
{comment}

【返回格式】
[
  {{
    "一级场景": "",
    "二级维度": "",
    "三级对象": "",
    "四级问题": "",
    "五级描述": ""
  }}
]
""".strip()


def analyze_one_comment(api_key, comment, product_text, level_text, examples_text):
    client = OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com"
    )

    prompt = build_prompt(comment, product_text, level_text, examples_text)

    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "user", "content": prompt}
        ],
        temperature=0.1
    )

    raw_text = response.choices[0].message.content.strip()

    try:
        data = extract_json(raw_text)
    except Exception:
        data = [{
            "一级场景": "解析失败",
            "二级维度": "",
            "三级对象": "",
            "四级问题": "",
            "五级描述": raw_text
        }]

    if isinstance(data, dict):
        data = [data]

    return data, raw_text