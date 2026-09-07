from typing import Literal


WardrobeStatus = Literal[
    "可穿",
    "待洗",
    "清洗中",
    "晾晒中",
    "收纳中",
    "季节性收纳",
    "借出",
    "已淘汰",
    "需要修补",
    "准备淘汰",
]

UNAVAILABLE_WARDROBE_STATUSES = {
    "待洗",
    "清洗中",
    "晾晒中",
    "收纳中",
    "季节性收纳",
    "借出",
    "已淘汰",
    "需要修补",
    "准备淘汰",
}
