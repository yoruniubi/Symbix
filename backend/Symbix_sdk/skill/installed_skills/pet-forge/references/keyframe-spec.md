# Pet Forge — Keyframe Spec（动画白名单）

> LLM **只能**从本文白名单选动画名，禁止自造 keyframes 名称。  
> 具体 `@keyframes` 实现在 presence-runtime 公共样式表；本文件只约定**名字与语义**。

## 1. 必需状态（陪伴场景）

生成 `states.json` 时，下列 6 个状态**必须全部存在**：

| 状态 | 场景 | 建议动画组合 |
|---|---|---|
| `idle` | 常态待机 | `breathe` + 偶尔 `blink` |
| `listening` | 用户说话 / 等待输入 | `lean-in` / `perk` |
| `happy` | 开心 / 完成任务 | `bounce` / `wave` |
| `concerned` | 担心 / 失败 / 抱歉 | `frown` |
| `sleeping` | 长时间空闲 | `breathe-slow` + `close` |
| `waking` | 从睡眠被唤醒 | `open-startled` |

## 2. 动画白名单（仅可选用）

| 动画名 | 适用场景 | 典型时长 |
|---|---|---|
| `breathe` | 常态呼吸起伏 | 2.4s ease-in-out infinite |
| `breathe-slow` | 睡眠/放松 | 3.6s ease-in-out infinite |
| `blink` | 眨眼 | 0.18s ease-in-out 1–2 |
| `bounce` | 开心轻跳 | 0.5s ease-out 1–2 |
| `wave` | 挥手打招呼 | 0.6s ease-in-out 2 |
| `frown` | 皱眉/难过 | 0.4s ease-out 1 |
| `close` | 闭眼入睡 | 0.5s ease-in 1 |
| `open-startled` | 惊醒睁眼 | 0.35s ease-out 1 |
| `lean-in` | 前倾倾听 | 0.45s ease-out 1 / alternate |
| `perk` | 竖耳/精神一振 | 0.4s ease-out 1 |
| `sway-slow` | 缓慢摇摆 | 2.8s ease-in-out infinite |

**硬约束语气（写给 LLM）：**

> 你只能从以上列表选择动画名。禁止发明任何未列出的动画名（如 `spin`、`shake`、`custom-foo`）。  
> 若不确定，优先选 `breathe` 或 `blink`。

## 3. `states.json` 字段格式

顶层对象：状态名 → 规则对象。

规则对象：

```json
{
  "body": "breathe 2.4s ease-in-out infinite",
  "eye-right,pupil-right": "blink 0.18s ease-in-out 2",
  "mouth": "bounce 0.5s ease-out 1"
}
```

### 键（part-id）

- 单个部件：`body`、`mouth`、`eye-right` …
- 多个部件共用同一动画：逗号分隔，**无空格或仅两侧 trim**  
  例：`eye-right,pupil-right`

### 值（动画声明）

格式：

```
动画名 时长 缓动 次数
```

- `动画名`：必须在白名单内  
- `时长`：如 `2.4s` / `400ms`  
- `缓动`：`ease` / `ease-in` / `ease-out` / `ease-in-out` / `linear`  
- `次数`：正整数或 `infinite`

## 3.5 preset 字段(config/keyframes.json,烘焙期)

| 字段 | 取值 | 说明 |
|---|---|---|
| `kind` | `translateY` / `translateX` / `rotateZ` / `frameSwap` | 变换种类 |
| `scope` | `rig` / `part`(默认) | `rig` = **角色整体动**(作用到 rig 全部部件);`breathe`/`breathe-slow`/`bounce`/`lean-in` 这类必须用 `rig`,否则只动 `body` 组 → 头动脸不动 |
| `parts` | 部件名数组 | **仅兜底**:states 里已写部件时以 states 为准 |
| `segments` | 数组 | `{t, dy|dx|deg|swap}`,t ∈ [0,1];烘焙时按帧数采样 |
| `must_hit` | `true`(仅 `frameSwap`) | 该事件必须在每一行里**真的出现一次**:窄窗口按帧数均匀采样常被整段跳过(如 `blink` 只占 t∈[0.5,0.6),6 帧的 idle 一只都不眨眼),烘焙时会挑最接近窗口中点的那一帧强制命中该事件 |

- `rotateZ` 的旋转中心取该部件自己的 `transform-origin`(rig-spec 强制要求),不在 preset 里写死。
- `frameSwap`(闭眼/睁眼)只作用于 `eye-*`/`pupil-*`,用 `scaleY=0.08` 压扁实现(不是消失:瞳孔要留一条线)。
- 只有「偶尔发生、不发生也看不出来」的事件才加 `must_hit`(`blink`);`close` / `open-startled` 这类由状态语义决定,不要加。

## 3.6 行模式(spritesheet_map.json 的 row.mode,烘焙期)

| mode | 含义 |
|---|---|
| `direct` | 按上面的方式均匀采样 |
| `mirror+scroll-x` / `mirror-back+scroll-x` | PNG 层镜像 + 水平往复(奔跑行) |
| `amplify-bounce` | 复用来源状态的 bounce 曲线,位移乘 `variants.<home>.amplitude_factor` |
| `cycle` | 把行内帧映射到 `variants.<home>.cycles` 个虚拟循环的相位上:同样来源的两行(如 `running` 思考中 / `waiting` 等待)必须长得不一样,否则前端两个状态画面完全一样 |
| `head-frames` | 只取来源状态前 `variants.<home>.head_frames` 帧缓动,其余帧复用最后一帧 |

## 4. 镜像策略（重要）

- LLM **只写** `-right`、单侧、中心部件（`body` / `mouth` / `tail` / `accessory`）。
- **不要**写 `-left` 镜像侧；由 `derive_mirrors.py` 自动补全。
- 若你显式写了 left 与 right 不同规则，脚本**不会覆盖**你的 left。

## 5. 批次划分(手工产出时的参考)

| Batch | 状态 |
|---|---|
| 1 | `idle`, `listening` |
| 2 | `happy`, `concerned` |
| 3 | `sleeping`, `waking` |

每批独立重试；一批失败不影响已成功批次。

## 6. 最小示例

```json
{
  "idle": {
    "body": "breathe 2.4s ease-in-out infinite",
    "eye-right,pupil-right": "blink 0.2s ease-in-out 2"
  },
  "listening": {
    "body": "lean-in 0.5s ease-out 1",
    "ear-right": "perk 0.4s ease-out 1"
  },
  "happy": {
    "body": "bounce 0.5s ease-out 2",
    "limb-right": "wave 0.6s ease-in-out 2"
  },
  "concerned": {
    "mouth": "frown 0.4s ease-out 1"
  },
  "sleeping": {
    "body": "breathe-slow 3.6s ease-in-out infinite",
    "eye-right,pupil-right": "close 0.5s ease-in 1"
  },
  "waking": {
    "eye-right,pupil-right": "open-startled 0.35s ease-out 1",
    "body": "perk 0.4s ease-out 1"
  }
}
```
