---
name: pet-forge
description: >-
  生成可动画的像素风 SVG 桌宠主题包(base.svg + states.json + theme.json)。
  当用户要求创建/生成/设计桌宠、宠物皮肤、SVG pet、换肤主题、或「给我做一个小猫/小狗桌宠」时使用。
  也适用于校验 rig、打包主题、修整天外观。默认画风是像素画(192x208 像素画板 = 帧本身,整数坐标逐格填色)。
---

# Pet Forge — SVG 桌宠主题锻造

把自然语言描述变成**可校验、可动画**的桌宠主题包。**你自己就是生成器**:在对话里直接产出 SVG / JSON,脚本只负责校验、补镜像、打包。

**默认画风 = 像素画**:`viewBox 0 0 192 208` 就是帧 cell 本身(1 格 = 1 像素),整数坐标 = 像素格,
只走直线与直角、只用 `var(--pet-*)` 纯色块、无渐变/半透明。契约见 `references/rig-spec.md` §6,
合规样例见 `assets/fixtures/pixel-base.svg`。

## 产出物

一个主题目录包含:

| 文件 | 说明 |
|------|------|
| `base.svg` | 部件化 rig(`<g id="...">` + CSS 变量上色) |
| `states.json` | 6 个必需状态的动画规则 |
| `theme.json` | 元数据 + capabilities + 默认 palette(由脚本生成) |

## 何时使用

- 用户要「做一个桌宠 / 生成宠物皮肤 / 设计 SVG pet」
- 需要按描述产出可播放的 idle / happy / sleeping 等状态
- 已有主题但某一状态坏了,需要**只修该状态**

## 何时不要使用

- 纯聊天、不涉及桌宠外观/动画
- 用户只要位图/精灵图(从零自己画位图,不走 SVG rig)
- 已有合法主题包且仅需前端播放

## 工作流(你直接产出,脚本兜底校验)

```
1. 读规范(必要时):references/rig-spec.md、references/keyframe-spec.md
1.5. 可选草稿模式:形象描述模糊/用户在犹豫时,用内置 MCP pixeldraw 画像素草稿给用户看,
      满意后转录成 base.svg —— 协议见 references/pixeldraw-draft.md;描述明确则跳过
2. 自己产出 base.svg(部件化 rig)→ 可用 references/prompt-templates.md 的模板作参考
3. 自己产出 states.json(6 状态动画规则)→ 参考 keyframe-spec 白名单
4. 脚本校验:
   python scripts/validate_rig.py <base.svg>            # 有错 → 自己改,再跑,直到通过
   python scripts/derive_mirrors.py <states.json> -o <tmp>  # 补 left 镜像
   python scripts/validate_states.py <tmp> --rig <base.svg> # 有错 → 自己改,再跑
   # validate_rig 默认按「像素画板契约」校验(整数格 / 只走直线 / 禁渐变半透明)。
   # 输出里的 WARN 行不影响退出码,但必须修掉或向用户说明。老主题重烘焙才加 --smooth。
5. 脚本一键打包+烘焙(输出目录由脚本自己推导,不要写死盘符):
   python "<skill 根目录>/scripts/build_theme.py" -n "<名字>" --rig "<base.svg 绝对路径>" --states "<tmp 绝对路径>" -d "<一句话外观描述>"
   # <skill 根目录> 见 skill 工具返回的 [Skill root] 一行;
   # 输出目录 = <项目根>/Symbix_frontend/public/pixiv_pet/<名字>(可用 -o / 环境变量 SYMBIX_PIXIV_PET_DIR 覆盖)
   # 校验连续失败 ≥3 次时,加 --template-fallback 兜底打包(占位模板,务必告知用户)
6. 复查:确认目标目录下有 base.svg / states.json / theme.json / **spritesheet.webp** / pet.json
7. 清理:删除你创建的临时文件(如 /tmp 下的 states.mirrored.json / 临时目录),还原 skill 目录
```

### 产出即落盘

- 你**直接在对话/文件中写** `base.svg` 与 `states.json`,不要调用任何「生成脚本」去调 LLM——你自己就是 LLM。
- 写好后用 `validate_rig.py` / `validate_states.py` 校验,**校验失败就把错误列回给你自己**,改完再跑,直到通过(至多几次)。
- 校验通过后用 **`build_theme.py`** 一键完成打包+烘焙,输出到 **`<项目根>/Symbix_frontend/public/pixiv_pet/<名字>/`**(路径由脚本自己推导,**不要写死盘符,也不要用 `--out` 指定绝对路径**)。
- **必须跑 build_theme.py,不要只跑 pack_theme.py**:后者只产 rig 三件套(base.svg / states.json / theme.json),而 Home.vue 只认 8×9 的 spritesheet。只有 rig 的皮肤在前端皮肤窗口里既没动画、也切不过去(「存在但不可见」)。
- 成功标志:命令行最后一行 `OK: {...}` 且 JSON 里 `baked: true`、`missing_frames: []`、`fallback: false`、`warnings: []`;目录下出现 `spritesheet.webp` 与 `pet.json`。
- 边缘平滑:**历史画风**才用 `--scale 2`(2× 超采样后缩放,线条无锯齿)。
- **像素风是默认画风**:viewBox 192x208 = 帧本身,整数坐标 = 像素格。烘焙自动走像素模式(整数格栅格化 + 调色板量化 + 无抗锯齿),**你不需要加任何参数**;确实想做平滑矢量老皮肤才加 `--style smooth`。
- `pet.json` / `theme.json` 里的 `style` 字段(`pixel` / `smooth`)决定画风;重烘培会自动沿用主题原有风格。
- **`fallback: true` / `warnings` 非空时必须如实转告用户**(例如「这版用的是占位模板,外形是临时的」),不要当成完整成功汇报。

### 镜像规则(重要)

- 你 **只写** `-right` / 中心部件(`body` / `mouth` / `tail` / `accessory`)。
- **不要**写 `-left` 镜像侧;由 `derive_mirrors.py` 自动补全。
- 若你显式写了 left 与 right 不同规则,脚本**不会覆盖**你的 left。

### 失败面隔离

| 失败点 | 动作 |
|--------|------|
| rig 校验失败 | **自己改** base.svg,重跑 validate(最多几次) |
| states 校验失败 | **自己改** states.json,重跑 validate |
| 校验连续失败 ≥3 次 | 最后一次用 `--template-fallback` 兜底打包,然后**明确告知用户「外形是占位模板,可以再让我重画」**(宁可给一个能动可切换的,也不要产出为零) |
| pack 失败 | 看校验错误,改对应文件,不要静默写出 |
| `warnings` 非空 | 逐条读给用户(缺失帧/动画没作用到部件),这是「校验全过但画面不动」的唯一暴露窗口 |

## 脚本一览

路径均相对于本 skill 根目录 `scripts/`。

| 脚本 | 作用 | 是否调 LLM |
|------|------|------------|
| `validate_rig.py` | 严格校验 rig | 否 |
| `derive_mirrors.py` | right→left 镜像补全 | 否 |
| `validate_states.py` | 校验 states + keyframes 预设契约 | 否 |
| `pack_theme.py` | 打包 rig 三件套 | 否 |
| `build_theme.py` | **一键**校验+烘焙+拼 spritesheet+pet.json(推荐入口) | 否 |
| `bake_snapshots.py` | rig+states → 逐帧 PNG(被 build_theme 调用) | 否 |
| `pack_spritesheet.py` | 逐帧 PNG → 8×9 spritesheet.webp(被 build_theme 调用) | 否 |
| `_selftest_render.py` | **渲染级回归自测**(A~G 类缺陷,改动画/rig 后请跑一遍) | 否 |
| `_selftest.py` | **逻辑级回归自测**(像素契约正/负例、镜像、白名单、打包三件套;改脚本后请跑一遍) | 否 |

> 已移除旧的 `generate_rig.py` / `generate_states_batch.py` / `repair_state.py`(它们内嵌第二层 LLM 调用)。生成完全由你(Agent)完成。

### 推荐 CLI(离线校验 / 打包)

```bash
# 校验 rig
python scripts/validate_rig.py assets/fixtures/base.svg

# 镜像补全后校验 states(--keyframes 默认 config/keyframes.json,校验预设契约)
python scripts/derive_mirrors.py assets/fixtures/states.json -o /tmp/states.mirrored.json
python scripts/validate_states.py /tmp/states.mirrored.json --rig assets/fixtures/base.svg

# 逻辑级自测(像素契约正/负例 + 镜像 + 白名单 + 打包三件套)
python scripts/_selftest.py

# 渲染级自测(A~F:变换顺序/全身带动/部件范围/采样/等比/palette+契约)
python scripts/_selftest_render.py

# 打包(一键:校验 + 烘焙 spritesheet + pet.json)
python scripts/build_theme.py \
  -n "Fixture Cat" \
  --rig assets/fixtures/base.svg \
  --states /tmp/states.mirrored.json \
  -o /tmp/pet-theme-out

# 兑底打包:校验失败也能出一个「占位但可用」的皮肤(输出里 fallback=true)
python scripts/build_theme.py \
  -n "My Pet" \
  --rig "<你反复改不好的 base.svg>" \
  --states "<states.json>" \
  --template-fallback

# 只要 rig 三件套(不烘焙,产物不可直接播放)
python scripts/pack_theme.py \
  --rig assets/fixtures/base.svg \
  --states /tmp/states.mirrored.json \
  -n "Fixture Cat" \
  -o /tmp/pet-theme-out \
  --schema assets/theme.schema.json
```

## Agent 执行清单

1. **读规范**(需要时):`references/rig-spec.md`、`references/keyframe-spec.md`;形象模糊时读 `references/pixeldraw-draft.md` 走草稿模式
2. **自己写 base.svg**(部件化 rig,`<g id="...">` + `var(--pet-*)` 颜色,viewBox `0 0 192 208`)
3. **自己写 states.json**(6 状态:idle/listening/happy/concerned/sleeping/waking,动画名白名单)
4. **跑 `validate_rig`**;失败 → 把错误塞回自己思路改,重试(≤3 次)
5. **从 base.svg 提取 part ids**(确认自己写的部件 id 全在)
6. **跑 `derive_mirrors`** 补 left
7. **跑 `validate_states`**;失败 → 自己改 state 再跑
8. **跑 `build_theme.py`** 一键输出到 **`<项目根>/Symbix_frontend/public/pixiv_pet/<名字>/`**(路径由脚本推导,不写盘符),产出 spritesheet.webp + pet.json
   - 它返回的 `fallback` / `warnings` 必须如实汇报(见上表)
   - 真的改不好(≥3 次)就加 `--template-fallback` 先交付可用的占位宠物
9. **(改动过脚本/rig/动画预设时)跑 `_selftest.py` + `_selftest_render.py`**;有红灯就修脚本而不是硬烘(前者查契约/镜像/打包,后者把 A~F 类「校验全过画面坏」变红灯)
10. **清理**临时文件,报告输出路径与 capabilities 给用户
11. 进度话术:「正在勾勒样子...」「正在编排动作...」「烘焙精灵图并打包主题中...」

## 硬约束(摘要)

- viewBox **精确** `"0 0 192 208"`(画板 = 帧尺寸,1 格 = 1 像素;老 rig 的 `"0 0 200 200"` 仍兼容但会 0.96 缩放)
- 颜色**必须**用 `var(--pet-primary/secondary/accent/eye/pupil/line)`;根 `<svg>` 的 `style` **要声明这些变量**——没声明的话渲染器会整只落兜底黑(烘焙入口会自动补默认值,但自己写清楚才对)
- 必需部件:`body, eye-left, eye-right, pupil-left, pupil-right, mouth`
- 颜色只用 `var(--pet-*)`,禁止写死 hex/rgb
- 动画名白名单:见 `references/keyframe-spec.md`
- 禁止 script / foreignObject / 外部 image / on* 事件
- LLM **只写 -right / 中心部件**;left 由脚本镜像

## 参考文档

- `references/rig-spec.md` — SVG 几何与安全
- `references/pixeldraw-draft.md` — pixeldraw MCP 草稿模式(画草稿→用户确认→转录成 rig)
- `references/keyframe-spec.md` — 状态与动画白名单
- `references/prompt-templates.md` — 模板(供你参考,不再由脚本调 LLM)
- `references/qa-rubric.md` — 人类维护者检查清单
- `assets/theme.schema.json` — theme.json schema
- `assets/fixtures/` — 合法样例(自测用)