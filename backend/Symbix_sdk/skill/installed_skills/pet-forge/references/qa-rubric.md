# Pet Forge — QA Rubric（开发者检查清单）

> 给人类维护者用，不是给 LLM。规则与 `validate_rig.py` / `validate_states.py` 一一对应。

## Rig 几何检查

- [ ] viewBox 精确等于 `"0 0 192 208"`(画板 = 帧尺寸;老 rig 的 `"0 0 200 200"` 仍可用,但会降级为 `pixel_board_legacy` warning)
- [ ] 必需部件 id 全部存在：`body`, `eye-left`, `eye-right`, `pupil-left`, `pupil-right`, `mouth`
- [ ] 每个必需部件是 `<g id="...">`，不是裸露 path/circle
- [ ] 每个必需部件有显式 `transform-origin`（属性或 style）
- [ ] 颜色使用 `var(--pet-*)` CSS 变量，无写死 hex/rgb/hsl
- [ ] 无 `<script>` / `<foreignObject>`
- [ ] 无外部 `<image href|xlink:href="http(s)://...">`
- [ ] 无任何 `on*` 事件属性
- [ ] 无 `javascript:` URL

## 像素画板契约检查(`validate_rig.py --pixel`,默认开启)

- [ ] 坐标全为整数(几何属性 / `path` 的 `d` / `transform-origin` / `transform` 的 translate)
- [ ] `path` 只用 `M L H V Z`,无 `C S Q T A`
- [ ] 无 `<linearGradient>` / `<radialGradient>` / `<pattern>` / `<filter>` / `<mask>` / `<image>`
- [ ] 最小特征 ≥ 2×2 格(瞳孔 2×2 起)
- [ ] 无半透明(`opacity`/`fill-opacity`/`stroke-opacity` < 1)
- [ ] `stroke-width` 为整数;无 `stroke-dasharray`
- [ ] 没用 `<circle>` / `<ellipse>` / 圆角 `rect`(或有充分理由)
- [ ] 图形不超出画板(`0..192` × `0..208`;老 rig 为 `0..200`)
- [ ] 烘焙后帧内**不得出现半透明像素**(`_selftest_render.py` R11a 自动拦)
- [ ] 烘焙后帧内颜色数 ≤ 调色板色数(受限调色板,R11b)

## States 引用检查

- [ ] 6 个必需状态全部存在：`idle`, `listening`, `happy`, `concerned`, `sleeping`, `waking`
- [ ] 每个状态是对象（map of part → animation declaration）
- [ ] 引用的部件 id 都在 rig 里实际存在
- [ ] 动画名都在白名单内：
  `breathe`, `breathe-slow`, `blink`, `bounce`, `wave`, `frown`,
  `close`, `open-startled`, `lean-in`, `perk`, `sway-slow`
- [ ] 动画声明格式为：`动画名 时长 缓动 次数`（次数为正整数或 `infinite`）

## 镜像一致性检查

- [ ] 镜像对（right → left）在同一状态中要么同时出现，要么同时不出现
- [ ] 若仅有 right 规则，`derive_mirrors.py` 已补全 left
- [ ] 若 left/right 均显式写出，以 LLM 显式为准（不强制覆盖）

## 打包检查

- [ ] 产出 `base.svg`、`states.json`、`theme.json`
- [ ] `pet.json` / `theme.json` 带 `style` 字段(`pixel` / `smooth`);老产物无该字段 = 平滑矢量
- [ ] 重烘焙沿用原 `style`(不会被默默改成像素风)
- [ ] `theme.json` 含 `name`、`version`、`rig`、`states_file`、`capabilities`
- [ ] `capabilities` 根据可选部件动态生成（如有 limb → `limb_animation`）
- [ ] 可选：对 `theme.schema.json` 做最终 schema 校验

## 失败面隔离

- [ ] rig 失败只重试 rig
- [ ] 某一批 states 失败只重试该批
- [ ] 单个状态校验失败只修复该状态(改 states.json 后重新校验)
- [ ] 错误信息定位到：状态 / 部件 / 规则
