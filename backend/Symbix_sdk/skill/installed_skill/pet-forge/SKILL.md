---
name: pet-forge
description: >-
  生成可动画的 SVG 桌宠主题包（base.svg + states.json + theme.json）。
  当用户要求创建/生成/设计桌宠、宠物皮肤、SVG pet、换肤主题、或「给我做一个小猫/小狗桌宠」时使用。
  也适用于修复单个动画状态、校验 rig、打包主题。
---

# Pet Forge — SVG 桌宠主题锻造

把自然语言描述变成**可校验、可动画**的桌宠主题包。

## 产出物

一个主题目录包含：

| 文件 | 说明 |
|------|------|
| `base.svg` | 部件化 rig（`<g id="...">` + CSS 变量上色） |
| `states.json` | 6 个必需状态的动画规则 |
| `theme.json` | 元数据 + capabilities + 默认 palette |

## 何时使用

- 用户要「做一个桌宠 / 生成宠物皮肤 / 设计 SVG pet」
- 需要按描述产出可播放的 idle / happy / sleeping 等状态
- 已有主题但某一状态坏了，需要**只修该状态**

## 何时不要使用

- 纯聊天、不涉及桌宠外观/动画
- 用户只要位图/精灵图（本 skill 产出 SVG rig，不是 spritesheet）
- 已有合法主题包且仅需前端播放

## 流水线（必须按序）

```
描述 → generate_rig → validate_rig
     → generate_states_batch（3 批）→ derive_mirrors → validate_states
     → （可选）repair_state 修单个状态
     → pack_theme
```

### 失败面隔离

| 失败点 | 动作 |
|--------|------|
| rig 校验失败 | **只**重试 `generate_rig`（最多 3 次） |
| 某一批 states 失败 | **只**重试该批 `generate_states_batch` |
| 单个状态仍坏 | 调 `repair_state`，**不要**整包重跑 |
| pack 失败 | 检查 validate 错误，不要静默写出 |

## 脚本一览

路径均相对于本 skill 根目录 `scripts/`。

| 脚本 | 作用 | 是否调 LLM |
|------|------|------------|
| `generate_rig.py` | 生成 base.svg | 是 |
| `validate_rig.py` | 严格校验 rig | 否 |
| `generate_states_batch.py` | 分 3 批生成 states | 是 |
| `derive_mirrors.py` | right→left 镜像补全 | 否 |
| `validate_states.py` | 校验 states | 否 |
| `repair_state.py` | 只修一个状态 | 是 |
| `pack_theme.py` | 打包三件套 | 否 |

### 推荐 CLI（离线校验 / 打包）

```bash
# 校验 fixture rig
python scripts/validate_rig.py assets/fixtures/base.svg

# 镜像补全后校验 states
python scripts/derive_mirrors.py assets/fixtures/states.json -o /tmp/states.mirrored.json
python scripts/validate_states.py /tmp/states.mirrored.json --rig assets/fixtures/base.svg

# 打包
python scripts/pack_theme.py \
  --rig assets/fixtures/base.svg \
  --states /tmp/states.mirrored.json \
  -n "Fixture Cat" \
  -o /tmp/pet-theme-out \
  --schema assets/theme.schema.json
```

### 生成（需要 Symbix backend LLM）

```bash
# 在 backend 环境中，且已配置 provider
python scripts/generate_rig.py -d "圆润的橙色小猫，有尖耳朵和细尾巴" -n "Mochi" -o /tmp/base.svg
python scripts/generate_states_batch.py --rig /tmp/base.svg -n "Mochi" -d "..." -o /tmp/states.json
python scripts/pack_theme.py --rig /tmp/base.svg --states /tmp/states.json -n "Mochi" -o /tmp/mochi-theme
```

也可在 Python 中注入 `llm_complete(system, user) -> str` 回调，避免依赖 backend import。

## Agent 执行清单

1. **读规范**（需要时）：`references/rig-spec.md`、`references/keyframe-spec.md`
2. **生成 rig** → 跑 `validate_rig`；失败则把错误列表塞回 prompt 重试（≤3）
3. **从 SVG 提取 part ids**（脚本内自动）
4. **分 3 批生成 states**：`(idle,listening)` → `(happy,concerned)` → `(sleeping,waking)`
5. **`derive_mirrors`** 补 left
6. **`validate_states`**；单状态失败 → `repair_state`
7. **`pack_theme`** 写出目录，向用户报告路径与 capabilities
8. 进度话术示例：「正在勾勒样子…」「正在编排动作…」「打包主题中…」

## 硬约束（摘要）

- viewBox **精确** `"0 0 200 200"`
- 必需部件：`body, eye-left, eye-right, pupil-left, pupil-right, mouth`
- 颜色只用 `var(--pet-*)`，禁止写死 hex/rgb
- 动画名白名单：见 `references/keyframe-spec.md`
- 禁止 script / foreignObject / 外部 image / on* 事件
- LLM **只写 -right / 中心部件**；left 由脚本镜像

## 参考文档

- `references/rig-spec.md` — SVG 几何与安全
- `references/keyframe-spec.md` — 状态与动画白名单
- `references/prompt-templates.md` — 写死的 system/user 模板
- `references/qa-rubric.md` — 人类维护者检查清单
- `assets/theme.schema.json` — theme.json schema
- `assets/fixtures/` — 合法样例（自测用）
