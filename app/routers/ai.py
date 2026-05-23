import json
import re
from difflib import SequenceMatcher
from datetime import date, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.database import get_db
from app.models import User, Category
from app.schemas import AIParseRequest, AIQueryRequest
from app.auth import get_current_user, require_admin
from app.utils.minimax import chat_completion
from app.utils.encryption import decrypt


def _fix_category_names(sql: str, real_names: list[str]) -> str:
    """把 SQL 里所有单引号字符串与真实分类名做模糊匹配，相似度>0.4 则替换。"""
    def best_match(word: str) -> str:
        scored = [(SequenceMatcher(None, word, n).ratio(), n) for n in real_names]
        score, name = max(scored, key=lambda x: x[0])
        return name if score > 0.4 else word

    def replace(m: re.Match) -> str:
        inner = m.group(1)
        fixed = best_match(inner)
        return f"'{fixed}'"

    return re.sub(r"'([^']+)'", replace, sql)

router = APIRouter()

_DANGEROUS_SQL = ["DROP", "DELETE", "UPDATE", "INSERT", "CREATE", "ALTER", "TRUNCATE", "REPLACE"]


def _check_ai_license():
    from app.routers.settings import read_settings
    from app.utils.license import validate_license
    s = read_settings()
    result = validate_license(s.get("license_key", ""))
    if not result["valid"]:
        raise HTTPException(status_code=403, detail=f"AI 功能未授权：{result['message']}")


@router.post("/parse-transaction")
async def parse_transaction(
    req: AIParseRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    _check_ai_license()
    today = date.today()
    yesterday = today - timedelta(days=1)
    categories = db.query(Category).all()
    cat_list = "、".join(c.name for c in categories)
    handlers = [u.username for u in db.query(User).all()]
    handler_list = "、".join(handlers) if handlers else "任意人名"

    system_prompt = f"""你是财务记账助手，从中文自然语言中提取记账信息。
今天：{today.isoformat()}，昨天：{yesterday.isoformat()}
系统用户（经手人参考）：{handler_list}
可选分类：{cat_list}

严格返回 JSON（不含其他文字）：
{{
  "amount": 数字,
  "category": "分类名",
  "handler": "经手人姓名或null",
  "date": "YYYY-MM-DD",
  "description": "简短备注"
}}

规则：
- amount 必须是纯数字
- date 必须 YYYY-MM-DD，"今天"={today.isoformat()}，"昨天"={yesterday.isoformat()}
- category 从可选分类中匹配，匹配不到用"其他"
- handler 从用户描述中提取姓名，无法判断时为 null"""

    try:
        response = await chat_completion(
            [{"role": "system", "content": system_prompt}, {"role": "user", "content": req.text}],
            max_tokens=512,
        )
        m = re.search(r"\{.*\}", response, re.DOTALL)
        if not m:
            raise ValueError("AI 未返回有效 JSON")
        parsed = json.loads(m.group())

        cat_name = parsed.get("category", "其他")
        cat = db.query(Category).filter(Category.name == cat_name).first()
        if not cat:
            cat = db.query(Category).filter(Category.name == "其他").first()

        return {
            "amount": float(parsed.get("amount", 0)),
            "category_id": cat.id if cat else None,
            "category_name": cat.name if cat else "其他",
            "handler": parsed.get("handler"),
            "date": parsed.get("date", today.isoformat()),
            "description": parsed.get("description", req.text),
            "original_text": req.text,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 解析失败：{e}")


@router.post("/query")
async def ai_query(
    req: AIQueryRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    _check_ai_license()
    today = date.today()
    categories = db.query(Category).all()
    cat_list = "、".join(c.name for c in categories)
    handlers = [u.username for u in db.query(User).all()]
    handler_list = "、".join(handlers) if handlers else "任意人名"

    system_prompt = f"""你是财务数据库 SQL 助手。
今天：{today.isoformat()}，年：{today.year}，月：{today.month}

表结构：
- transactions(id, amount REAL, category_id INTEGER, handler TEXT, description TEXT, transaction_date DATE, created_by INTEGER, is_deleted BOOLEAN, created_at DATETIME)
- categories(id INTEGER, name TEXT)
- users(id INTEGER, username TEXT)

可用分类名（SQL 中必须使用完全一致的名称）：{cat_list}
系统用户（经手人参考）：{handler_list}

规则：
1. 只生成 SELECT 语句
2. is_deleted=0 才是有效记录
3. JOIN categories 获取分类名
4. 只返回 SQL，不要任何解释
5. 用 SQLite 日期函数
6. 用户用自然语言描述分类时，从可用分类名中找语义最接近的一个，例如"招待客户"→"客户招待费"、"推广"→"市场推广费"、"垫资"→"内部垫资"

示例：
- "H上个月花了多少" → SELECT SUM(t.amount) total FROM transactions t WHERE t.handler='H' AND strftime('%Y-%m',t.transaction_date)=strftime('%Y-%m',date('now','-1 month')) AND t.is_deleted=0
- "本月各分类支出" → SELECT c.name,SUM(t.amount) total FROM transactions t JOIN categories c ON t.category_id=c.id WHERE strftime('%Y-%m',t.transaction_date)=strftime('%Y-%m','now') AND t.is_deleted=0 GROUP BY c.name ORDER BY total DESC
- "今年招待客户花了多少" → SELECT SUM(t.amount) total FROM transactions t JOIN categories c ON t.category_id=c.id WHERE c.name='客户招待费' AND strftime('%Y',t.transaction_date)='2026' AND t.is_deleted=0"""

    try:
        sql = (await chat_completion(
            [{"role": "system", "content": system_prompt}, {"role": "user", "content": req.question}],
            max_tokens=512,
        )).strip()

        # 去掉 markdown 代码块包裹（```sql ... ``` 或 ``` ... ```）
        sql = re.sub(r"^```(?:sql)?\s*", "", sql, flags=re.IGNORECASE)
        sql = re.sub(r"\s*```$", "", sql)
        sql = sql.strip()

        # 只保留第一条 SQL（防止多语句注入）
        sql = sql.split(";")[0].strip()

        if not sql.upper().startswith("SELECT"):
            raise ValueError("只允许 SELECT 查询")
        for kw in _DANGEROUS_SQL:
            if re.search(rf"\b{kw}\b", sql, re.IGNORECASE):
                raise ValueError(f"不允许的 SQL 关键词：{kw}")

        # 自动把 SQL 里猜错的分类名纠正为数据库真实名称
        real_cat_names = [c.name for c in categories]
        sql = _fix_category_names(sql, real_cat_names)

        result = db.execute(text(sql))
        columns = list(result.keys())
        rows = result.fetchmany(200)
        data = [dict(zip(columns, row)) for row in rows]

        # 解密 description，补充 category_name 和 created_by_name
        cat_map = {c.id: c.name for c in categories}
        user_map = {u.id: u.username for u in db.query(User).all()}
        for row in data:
            if "description" in row and row["description"]:
                row["description"] = decrypt(row["description"])
            if "category_id" in row and "category_name" not in row:
                row["category_name"] = cat_map.get(row["category_id"], "")
            if "created_by" in row and "created_by_name" not in row:
                row["created_by_name"] = user_map.get(row["created_by"], "")

        return {"question": req.question, "sql": sql, "columns": columns, "data": data}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询失败：{e}")
