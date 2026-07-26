# Pet Forge — Rig Spec（部件规范）

> 一切的地基。`validate_rig.py` / `generate_rig.py` / `derive_mirrors.py` 都以此为权威。

## 1. 画布

| 项 | 值 |
|---|---|
| viewBox | **精确** `"0 0 200 200"` |
| 推荐导出尺寸 | 200×200 |
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

1. **根节点**：单个 `<svg ... viewBox="0 0 200 200">`，可含 `xmlns="http://www.w3.org/2000/svg"`。
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

## 6. 风格（宠物安全）

- 简洁圆润，小尺寸（约 64–128px）仍可辨识。
- 避免过多细线、复杂渐变、文字。
- 部件边界清晰，便于单独做 CSS 动画。

## 7. 样例约定

- 合规样例：`fixtures/rig_valid.svg`
- 违规样例：`fixtures/rig_invalid.svg`（缺部件、写死颜色、含 script 等）
