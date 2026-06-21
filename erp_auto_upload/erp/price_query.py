from __future__ import annotations

from dataclasses import dataclass
import json
import re

from loguru import logger
from playwright.sync_api import Page

from parser.sku_parser import ParsedSku


@dataclass(frozen=True)
class PriceQueryResult:
    sku: ParsedSku
    price: str
    spec_code: str
    raw: dict | None = None


def _extract_json_payload(text: str) -> dict:
    stripped = text.strip()
    json_start = stripped.find("{")
    if json_start < 0:
        raise RuntimeError(f"ERP 成本接口未返回 JSON：{re.sub(r'<[^>]+>', ' ', stripped)[:200]}")
    return json.loads(stripped[json_start:])


def query_price_and_spec_code(page: Page, sku: ParsedSku) -> PriceQueryResult:
    logger.info("查成本：型号={} 颜色={} 外显={}", sku.erp_base_model, sku.erp_color, sku.display_name)
    result = page.evaluate(
        """async ({model, color}) => {
            const params = new URLSearchParams({p: model, c: color});
            const resp = await fetch('/leedis/index.php/autocomplete/getcost4product?' + params.toString(), {
                method: 'GET',
                headers: {'Content-Type': 'application/x-www-form-urlencoded'}
            });
            return {status: resp.status, text: await resp.text()};
        }""",
        {"model": sku.erp_base_model, "color": sku.erp_color},
    )
    if result["status"] != 200:
        raise RuntimeError(f"ERP 成本接口失败：HTTP {result['status']} {sku.erp_base_model} {sku.erp_color}")

    payload = _extract_json_payload(result["text"])
    first = payload.get("0") or {}
    price = str(first.get("单品成本") or first.get("成本") or "")
    if not price:
        raise RuntimeError(f"ERP 成本为空：{sku.erp_base_model} {sku.erp_color}")

    logger.info("成本结果：{} {} cost={}", sku.erp_base_model, sku.erp_color, price)
    return PriceQueryResult(sku=sku, price=price, spec_code="", raw=first)
