# Pet Forge — Rig Spec（部件规范）

> 一切的地基。`validate_rig.py` / `derive_mirrors.py` 都以此为权威。

## 1. 画布

| 项 | 值 |
|---|---|
| viewBox | **推荐精确** `"0 0 192 208"`(= 帧 cell 本身,1 格 = 1 帧像素,零重采样);老 rig 的 `"0 0 200 200"` 仍兼容(会 0.96 倍缩进) |
| 推荐导出尺寸 | 192×208 |
| 坐标系 | 左上角原点，Y 向下 |

## 2. 必需部件（缺一即失败）

每个必须是 `<g id="...">` 分组，**不能**是裸露的 `<path>` / `<circle>` 顶层节点。

| id | 说明 | transform-origin（建议） |
|---|---|---|
| `body` | 身体主体 | `100px 120px` |
| `eye-left` | 左眼外轮廓/白眼 | `80px 90px` |
| `eye-right` | 右眼外轮廓/白眼 | `120px 90px` |
| `pupil-left` | 左瞳孔 | `80px 90px` |
| `pupil-right` | 右瞳孔 | `120px 90px` |
| `mouth` | 嘴巴 | `100px 130px` |

> 角色朝向约定：**角色面朝观众**时，`left` = 画面左侧（角色的右眼）。与镜像表一致即可。

## 3. 可选部件（用户描述提到才生成）

| id | 触发关键词示例 |
|---|---|
| `limb-left` / `limb-right` | 手、臂、爪、肢 |
| `ear-left` / `ear-right` | 耳、角 |
| `tail` | 尾 |
| `accessory` | 眼镜、帽子、围巾、蝴蝶结 |

## 4. 镜像对照表（`derive_mirrors.py` 权威来源）

```
eye-right    → eye-left
pupil-right  → pupil-left
limb-right   → limb-left
ear-right    → ear-left
```

规则：

- 右侧是 **canonical**（LLM 优先写 right / 中心件）。
- 若状态里只有 right、没有 left → 脚本复制同一动画规则给 left。
- 若 left/right **都**被 LLM 显式写出不同规则 → **以 LLM 显式为准，不覆盖**。

## 5. 结构约束

1. **根节点**：单个 `<svg ... viewBox="0 0 192 208">`，可含 `xmlns="http://www.w3.org/2000/svg"`。
   - 帧 cell 是 192×208(Home.vue 契约)。画板写成 192×208 时**正好等于帧**:1 格 = 1 帧像素,零重采样。
     老 rig 的 `0 0 200 200` 仍能用,脚本会**等比 contain + 居中**处理(0.96 倍 → 内容 192×192、上下各留 8px 透明边),但会有约 4% 行列被丢/重复。
   - 无论哪种画板,主体都**不要画到画板外**(x<0 / x>画板宽 / y>画板高),否则会被裁掉。
   - 根 `<svg>` 的 `style` 里**要声明** `--pet-*`(见下表);没声明时渲染器无法解析 `var()`,会整只落兜底黑。
2. **部件容器**：每个部件必须是 `<g id="部件id">`；其内部可用 path/circle/ellipse/rect/line/polyline/polygon。
3. **颜色**：统一 CSS 变量占位，**禁止写死**具体 hex/rgb（`#fff` / `rgb()` 等）。推荐：
   - `var(--pet-primary)` 主色
   - `var(--pet-secondary)` 辅色
   - `var(--pet-accent)` 点缀
   - `var(--pet-eye)` 眼白/眼眶
   - `var(--pet-pupil)` 瞳孔
   - `var(--pet-line)` 描边
4. **transform-origin**：每个必需部件 `<g>` 必须显式声明（属性或 style）：
   - `transform-origin="80px 90px"` 或
   - `style="transform-origin: 80px 90px"`
5. **禁止**：
   - `<script>`
   - `<foreignObject>`
   - 外部资源：`<image>` 的 `href` / `xlink:href` 以 `http://` `https://` `//` 开头
   - 任何 `on*` 事件属性（`onclick`、`onload`…）
   - 内联 JS / `javascript:` URL

## 6. 像素画板契约(默认画风,`validate_rig.py` 强制)

**`viewBox="0 0 192 208"` 就是帧本身:每个整数坐标 = 一个像素格,逐格填色。**
渲染链路:先在画板上按整数格 1:1 栅格化(无抗锯齿) → 颜色吸附到根 `style` 的 `--pet-*` 调色板
→ 直接落进 192×208 帧(**不缩放**)。

格语义:**坐标 = 格索引,首末格都填**。`<rect x="40" width="120">` 与同跨度的 `<path d="M40 40 L160 40 …">`
一样占 40..160 共 121 格——写形状时按「从哪画到哪」理解即可(想要正好 120 格就把 width 写 119)。

| # | 规则 | 级别 | 为什么 |
|---|---|---|---|
| P1 | 所有坐标必须是**整数**:`rect`(x/y/width/height/rx/ry)、`circle`/`ellipse`(cx/cy/r/rx/ry)、`line`(x1..y2)、`polygon`/`polyline` 的 `points`、`path` 的 `d`、`transform-origin` 的 px 值、`transform` 的 `translate` | error | 落在半格上 → 边缘抖成两级台阶,动画时还会闪 |
| P2 | `path` 只允许 `M L H V Z`(含小写),**禁止** `C S Q T A` 曲线 | error | 曲线在像素画板上画不出干净的阶梯 |
| P3 | 禁止 `<linearGradient>` / `<radialGradient>` / `<pattern>` / `<filter>` / `<mask>` / `<image>` | error | 渲染器不实现,用了就是空白/黑块 |
| P4 | 最小特征 ≥ **2×2 格**(推荐 4×4;瞳孔最小 2×2) | error | 1 格宽的特征缩到 96px 显示时直接消失 |
| P5 | 尽量不用 `<circle>` / `<ellipse>` / 圆角 `rect`,改用整数格矩形+折线拼圆 | warning | 会被栅格成 32 边形台阶,观感毛糙 |
| P6 | 禁止半透明(`opacity` / `fill-opacity` / `stroke-opacity` < 1) | warning | 破坏受限调色板(像素风是纯色块) |
| P7 | 描边宽度用整数(`stroke-width="2"`,不要 `1.5`) | warning | 非整数会被取整,相邻帧可能差 1px → 抖动 |
| P8 | 别用 `stroke-dasharray` | warning | 虚线在像素风里会断成碎点 |
| P9 | 图形不要超出画板(默认 `0..192` × `0..208`) | warning | 超出部分会被裁掉 |

补充说明:

- 颜色仍只准 `var(--pet-*)`(见 §5.3)。像素风最多 6–8 色,烘焙时会把所有颜色吸附到这几色上。
- **画板 = 帧尺寸**:1 格 = 1 帧像素,不存在缩放。老式 200×200 画板会被降级为 warning(`pixel_board_legacy`),
  因为它要 0.96 倍缩进帧、约丢 4% 行列(块宽 120 格 → 约 115px)。
- 自查命令:`python scripts/validate_rig.py base.svg`(像素契约默认开启,`--smooth` 才关)。**WARN 行必须修掉或向用户说明**,它不影响退出码。
- 合规参考实现:`assets/fixtures/pixel-base.svg`(画板 = 192×208 + 整数格 + 只走直线,同时也是兜底模板)。

## 7. 平滑矢量(历史画风,仅老主题)

老主题(产物 `pet.json` 里没有 `style` 字段)仍按原来的平滑矢量渲染:`--scale 2` 超采样抗锯齿,
可以用 `circle`/`ellipse`/曲线/小数坐标。重烘焙会自动沿用原风格,不会被改成像素风。

## 8. 样例约定

- 合规样例：`fixtures/rig_valid.svg`
- 违规样例：`fixtures/rig_invalid.svg`（缺部件、写死颜色、含 script 等）
