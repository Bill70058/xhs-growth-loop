# VENDOR PATCHES

更新时间：2026-03-09

## 已应用补丁
1. `vendors/XiaohongshuSkills/scripts/feed_explorer.py`
   - 修改：`@dataclass(slots=True)` -> `@dataclass`
   - 原因：兼容低版本 Python（3.9）运行环境。

## 风险说明
1. 该补丁属于 vendor 源码修改，后续升级 `XiaohongshuSkills` 可能被覆盖。
2. 推荐在后续固定 Python>=3.10 后回滚该补丁，减少 vendor 偏差。

## 维护建议
1. 每次更新 vendor 后执行：
   - `rg -n "dataclass\\(slots=True\\)" vendors/XiaohongshuSkills/scripts -S`
2. 若补丁被覆盖且运行环境仍为 Python 3.9，需要重新应用兼容改动。
