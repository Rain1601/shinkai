"""Canonical supply-chain strata vocabulary.

A small, opinionated bucket of 16 layers covers the supply-chain depth that
matters for V0 visualization and reasoning. The mapping is used in two places:

1. **Write path**: ``IndustryGraphStore.upsert_entity`` calls
   :func:`derive_supply_layer` to populate ``facets.supply_layer`` whenever
   the caller (agent or ingestion script) leaves it blank. This means every
   stored entity carries a canonical layer that downstream queries can rely on.
2. **Read path / export**: ``api/industry_graph.py`` consults the same module
   so projections stay consistent with what is on disk.

The keyword rules cover the Chinese-named ``chain_layers`` values produced by
the supply_chain_graph_seed ingestion (~90 unique strings). Extending the
mapping is just appending to ``LAYER_RULES``.
"""

from __future__ import annotations

from typing import Any

# Canonical strata order — top of list = closest to end buyer,
# bottom = deepest upstream. Frontend uses the same order to lay out
# the supplier band; agent prompt quotes this verbatim.
LAYER_ORDER: list[str] = [
    "buyer",
    "ai_model",
    "designer",
    "assembly",
    "advanced_packaging",
    "memory",
    "testing",
    "foundry",
    "optical",
    "robotics",
    "battery",
    "power",
    "cooling",
    "infrastructure",
    "passive",
    "materials",
    "theme",
]

# (layer, keyword substrings) — match in order; first hit wins. Case-insensitive.
# Keep specific rules above more generic ones (e.g. ``cowos`` before ``封装``).
LAYER_RULES: list[tuple[str, list[str]]] = [
    ("foundry", ["晶圆代工", "logic foundry", "advanced foundry", "硅光子芯片代工", "前道设备"]),
    ("advanced_packaging", [
        "先进封装", "cowos", "soic", "aip", "sip 封装", "光学封装", "cpo/光学",
        "ic基板", "ic substrate", "pcb", "后道设备",
    ]),
    ("memory", ["hbm", "内存", "dram", "nand"]),
    ("testing", ["芯片测试", "chip testing", "osat"]),
    ("optical", [
        "光学收发", "光收发", "光纤阵列", "fau coupling", "光通信", "激光光源",
        "laser source", "optical transceiver", "铜互连", "aec", "active electrical",
        "networking infrastructure", "数据中心网络",
    ]),
    ("assembly", [
        "ems", "odm", "整机组装", "服务器组装", "pc oem", "ar/vr",
        "oled", "摄像头", "ois", "vcm", "haptic", "hinge", "铰链",
        "casing", "casing & frame", "结构件", "gigacasting",
        "ic substrates (abf)",
    ]),
    ("robotics", [
        "人形机器人", "dexterous hand", "灵巧手", "motors & actuator", "电机",
        "actuator", "reducer", "减速器", "screws", "精密丝杠", "bearing", "轴承",
        "sensors (lidar", "传感器 / sensors", "外部 actuator", "harmonic reducer",
    ]),
    ("battery", [
        "battery cell", "battery pack", "电池芯", "电池 (battery",
        "电池 / batteries", "megapack", "bess", "energy storage",
        "锂原材料", "battery energy storage",
    ]),
    ("power", [
        "power distribution", "ups", "nuclear", "gas turbine",
        "transformer", "grid equipment", "dc backup", "dc power",
        "数据中心电源", "datacenter power", "power semiconductor",
        "化合物半导体", "电源管理",
    ]),
    ("cooling", ["cooling", "冷却"]),
    ("materials", ["raw material", "rare earth", "稀土", "critical mineral"]),
    ("infrastructure", [
        "数据中心基础设施", "dc infrastructure", "external hyperscale",
        "云算力", "物流", "data center construction", "colocation",
    ]),
    ("passive", ["mlcc", "被动元件"]),
    ("ai_model", [
        "ai模型", "ai 模型", "ai 脑模型", "ai foundation model",
        "strategic ai model", "physical ai foundation",
    ]),
    ("designer", [
        "asic", "soc", "gpu", "tpu", "芯片设计", "ai加速", "ai 加速",
        "compute silicon", "半导体计算", "modem", "bmc", "图像传感器",
        "image sensor", "driver ic", "驱动 ic", "ai 训练算力",
        "design services", "应用处理器", "application processor",
        "5g 调制",
    ]),
]

DEFAULT_LAYER_BY_KIND: dict[str, str | None] = {
    "SubTheme": "theme",
    "Product": "designer",
    "Component": "designer",
    "Bottleneck": None,
    "InvestmentThesis": None,
    "KeyDataPoint": None,
    "Source": None,
}

VALID_LAYERS: frozenset[str] = frozenset(LAYER_ORDER)


def map_chain_layer(value: str) -> str | None:
    """Best-effort substring match of a raw chain_layers string to a layer.

    Returns ``None`` if no rule matches — the caller decides what to do
    (fall back to kind-default, leave unset, etc).
    """
    lower = value.lower()
    for layer, keywords in LAYER_RULES:
        for kw in keywords:
            if kw in lower:
                return layer
    return None


def derive_supply_layer(
    facets: dict[str, Any] | None,
    kind: str | None = None,
) -> str | None:
    """Pick a canonical strata for an entity.

    Precedence:
    1. ``facets.supply_layer`` if already set (str or first item of list).
    2. Keyword match against ``facets.chain_layers``.
    3. Kind-derived default (e.g. ``SubTheme`` → ``theme``).
    """
    if isinstance(facets, dict):
        sl = facets.get("supply_layer")
        if isinstance(sl, list) and sl:
            v = str(sl[0])
            return v if v else None
        if isinstance(sl, str) and sl:
            return sl
        cl = facets.get("chain_layers")
        cl_list = cl if isinstance(cl, list) else ([cl] if isinstance(cl, str) else [])
        for raw in cl_list:
            mapped = map_chain_layer(str(raw))
            if mapped:
                return mapped
    if kind:
        return DEFAULT_LAYER_BY_KIND.get(kind)
    return None


__all__ = [
    "DEFAULT_LAYER_BY_KIND",
    "LAYER_ORDER",
    "LAYER_RULES",
    "VALID_LAYERS",
    "derive_supply_layer",
    "map_chain_layer",
]
