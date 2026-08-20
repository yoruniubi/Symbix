看了hello-agent这个项目有感，简单写一下现在的认知，以及项目未来的方向
1. 关于agent和workflow
agent最重要的一个特质就是自主性，可以自行决定通过何种方式、工具来达成用户下达的要求
而workflow要求工业级的标准，所以每一步都是严格要求使用什么函数，什么工具来完成的
2. 关于幻觉
因为本身大语言模型都是从transformer训练而来的，其中的核心机制就是注意力机制，注意力机制关注头和尾，容易忽略中间的部分，所以上下文越长，越容易出现幻觉，幻觉换句话说就是预测能力的失衡，毕竟大模型的输出本质上也是概率，所以我们需要上下文压缩和继承（后面再说）。
3. 关于agent的行动架构
核心原理都是thought -> action（行动到思考）的底层行动逻辑, 简单来说，分为两种：
 - reAct: 也就是一边行动一边决策，适用于写代码，或者是需要复杂思考的环境，这样能保证任务的准确性
 - plan and solve: 也就是我们在cline里面看到的todolist，会事先计划好，然后再依据这个todolist去做
最后会有一个reflection，就是反思，然后可以再检查一下是否符合用户的需求
4. 关于框架和低代码平台
所以经常用于企业级AI
 - 常见的框架：AutoGen,langGraph， 框架顾名思义就是方便你开发的，它里面给你配置好了，你只需要在此基- 础上开发就好了，省时间和精力
 - 低代码平台：dify，Coze（扣子），就是纯粹的追求效率，工作流
5. 关于RAG和memory
 - RAG：我们之前也用过，就是向量数据库检索，特定知识库，同时我们也可以用RAG给memory专门建一个知识库来检索
 - memory:分为三种，短期的就是上下文，一般存在内存中；长期的就存在md文件里；非常久远的，就需要建一个知识库了
6. 关于上下文工程、提示词工程
我们之前也提到，这个上下文过长会导致幻觉，所以我们需要压缩总结，每轮对话结束后，总结成一段文本给下一轮对话使用；其次，系统提示词是最优先的，比如说你是某某角色，要用什么语言回复我
7. 关于协议
 - mcp: model context protocol, 这个我们很熟悉了，过程是这样的，client先请求远程服务器，同时附上一些json字段，表示可以调用的工具，然后ai会发送回来文本，以及它的选择（选择什么工具），然后client向本地起的一个mcp server发送对应的字段，然后mcp server执行对应的本地脚本，命令什么的；mcp.json文件里面是给客户端看的，让client知道如何启动mcp server
 - A2A: 就是agent之间的通信，然后我们就顺便说说agent间的关系，有三种：
   (1): 父子agent，最常用的，子agent完成小人物，父agent确保完成的没有问题 
   (2): agent同事，简单来说就是不同职位的agent，开发的，测试的
   (3): 反驳型的，一般用于大项目的重构，可以大幅度减少幻觉发生的可能性
8. 评估
有专门的评估框架，来测试agent的能力，之后可以测试一下；其实本质思想就是benchmark使用你的Agent，然后看看输出是否符合预期，常见的有：
## 工具调用能力

- **BFCL（Berkeley Function-Calling Leaderboard）** —— 目前最主流的工具调用评测集，专门测模型/Agent 在给定一堆函数定义时，能不能选对函数、传对参数（包括单函数调用、并行调用、多轮多步调用、错误参数处理）。如果你的 harness 是自己写的工具路由/参数解析逻辑，这个能直接测出你 harness 层的问题，而不是模型本身的问题。
- **ToolBench** —— 覆盖更大规模、更真实的 API 场景（16000+ 真实 API），偏向"多工具组合调用完成复杂任务"，比 BFCL 更贴近真实业务场景。
- **τ-bench (tau-bench)** —— 模拟客服/电商这类需要**多轮工具调用 + 遵守业务规则**的场景，专门测 Agent 在真实约束下（比如不能乱退款）调用工具的可靠性，比较适合测你 harness 的"纪律性"（会不会瞎调用工具、会不会不按规则来）。

## 代码生成/修复能力

- **SWE-bench（推荐先跑 Verified 子集）** —— 目前业界最认可的代码 Agent 硬指标。输入是真实 GitHub 仓库的 issue，Agent 需要自己读代码、定位问题、生成 patch，跑测试验证是否修复成功。这个非常适合测你 harness 编排"读代码 → 定位 → 改代码 → 验证"这一整条链路的能力，跟你之前帮我排查那次 log 问题的流程很像。
- **Terminal-bench** —— 更贴近"在真实命令行环境里干活"的场景（跑命令、装依赖、调试报错），如果你的 harness 有 shell 执行能力，这个能测出很多 BFCL/SWE-bench 测不出的问题（比如环境处理、异常恢复）。

9. 关于SEO和GEO
SEO就是搜索引擎优化(search engine optimization),简单来说就是怎样让你的项目排在搜索结果比较前面的位置，然后GEO就是生成引擎优化(generative engine optimization), 主要是就是AI搜索相关的优化，如何让自己的项目能比较容易让AI检索的到，其实这一块跟这个推广有关了，之后再说。
SEO的文章：https://developers.google.com/search/docs/fundamentals/seo-starter-guide?hl=zh-cn
GEO，该怎么说，有所风险，看看吧 https://linux.do/t/topic/2596934/24
10. 关于Harness
**Harness 具体做什么**
- 维护对话/任务的循环（loop）：模型输出 → harness 解析出工具调用 → harness 真正执行该工具（跑 bash、改文件、调 HTTP、点浏览器）→ 把执行结果重新塞回给模型 → 模型继续下一步，如此循环
- 上下文管理：控制窗口大小、做压缩/摘要、决定哪些历史要留哪些要丢
- 权限与安全：比如危险操作要不要先问用户确认、沙箱隔离
- 错误处理与重试：工具调用失败了怎么办、要不要换个方式重试
-  提供"世界"接口：文件系统、终端、浏览器、各种 API 之类的具体工具实现
-  可观测性：日志、trace，方便调试模型每一步在想什么
然后现在似乎没有完全能够控制model的Harness，要么就是干一般就不干了，要么就是永无止境地做事情。
然后上面是Harness的基本概念，接下来就是设计架构：
**Harness 的设计架构**
- Provider abstraction layer：一个统一的接口，用于连接不同的 LLM 应用程序接口（如 Anthropic、OpenAI、Google 等）。该接口能够规范化流媒体事件的传输方式、工具调用的格式、思维逻辑块的表达方式以及使用情况的记录方式，这样系统的其他部分就无需关心具体使用的是哪个模型了。
- Agent loop： 实际的“轮转”机制：发送上下文信息→生成响应流→解析工具调用→执行工具功能→添加结果→重复上述过程，直到达到终止状态。 tool_execution_start/end 、 message_update （流式差异数据）、 turn_end 、 agent_end 等事件就发生在这里。
- AgentHarness（编排层）：位于循环层的上方，负责处理各种功能，包括持久性、资源解析（文件、技能、MCP 服务器）、操作锁定，以及钩子系统的实现。
- Context/session management：包括压缩操作、分支/分叉功能，以及（在 Pi 的情况下）一个基于 JSON 的只读会话存储，以确保数据的持久性。
- Surface layer：TUI/CLI/RPC、扩展功能、斜杠命令——这些正是用户实际可以操作的组件。
**其他值得提的小概念**
- Thinking levels/budgets — providers expose reasoning effort as either a discrete level (minimal/low/medium/high) or a raw token budget. Higher budgets improve quality on hard steps but cost latency+tokens on every turn, so a harness usually wants to vary this per-task rather than fixing it globally (e.g. low for simple tool-routing turns, high for planning turns).
考虑等级/预算问题——提供方将推理的投入表现为不同的等级，例如 minimal 、 low 、 medium 、 high 等，或者以原始代币数量来表示。较高的预算可以提高复杂步骤的运算质量，但每轮游戏都会增加延迟和代币消耗。因此，系统通常希望根据任务需求来调整这些参数，而不是全局性地固定数值（例如，在简单的工具调度回合中可以使用较低的预算，在规划回合中则可以使用较高的预算）。
Thinking signatures / redacted thinking — some providers require you to pass back a signature or opaque blob alongside thinking content in the next turn to validate/reuse that reasoning; dropping it can break continuity. If you support multiple providers, you need to store this per-message rather than assume it round-trips.
思维签名/已编辑的思维内容——一些服务供应商要求在下一轮对话中提供签名或不透明的标记，以验证并重复使用该推理过程；如果省略这一步骤，就会破坏连贯性。如果你支持多个服务供应商，就需要为每条消息分别存储这些信息，而不是假设它们会自动包含在其中。
Tool execution mode (parallel vs sequential) — parallel tool execution is a real latency win when the model calls multiple independent tools in one turn, but results still need to be reassembled in the original requested order for the transcript to make sense to the model.
工具执行模式（并行与顺序）——当模型在一条指令中调用多个独立工具时，并行工具执行确实能显著降低延迟。不过，这些结果仍需按照原始的顺序重新组合，才能让模型能够理解这些输出结果。
Steering vs. follow-up messages — worth distinguishing if you ever want to support "the user types while the agent is mid-tool-call": steering messages get injected before the next LLM call within the current run, follow-up messages get injected after the run would otherwise have ended. Different queues, different semantics.
引导性消息与跟进消息——如果希望支持“用户在代理进行工具调用期间仍能继续输入”的功能，那么区分这两种消息是很有必要的。引导性消息会在当前会话中的下一次 LLM 调用之前被注入，而跟进消息则会在会话结束之后被注入。这两种消息的处理顺序是不同的，它们的含义也有所不同。
Context overflow detection — normalizing provider-specific "prompt too long" errors into one internal signal, so your compaction/retry logic doesn't need provider-specific error parsing.
上下文溢出检测——将各提供商特有的“提示字符串过长”错误统一处理为一种内部信号，这样你的压缩/重试逻辑就无需再处理各提供商特定的错误解析了。
Total token accounting across providers — input + output + cacheRead + cacheWrite, computed uniformly, is what lets you do context-window management independent of which provider you're currently on — relevant if you ever do cross-provider handoff mid-session.
所有提供商的代币总量统计结果—— input + output + cacheRead + cacheWrite ——是统一计算得出的。这一功能使得你可以独立于当前使用的提供商会进行上下文管理。如果你在会话过程中需要跨提供商进行切换，这一点就非常有用。
11. 关于Sandbox
沙盒简单来说有点像是隔离室，Agent在其中做的任何修改，都不会影响到真实的环境，所以说之前有很多AI公司说自己的模型太强大了，突破了沙盒，攻击了外部服务器
12. 关于supervisor模式
是multi Agent的一种方式，简单来说就是一个模块，一个主Agent作为supervisor，然后子Agent负责每一个模块，就比如说下面的结构
Root Router Agent（鉴权/角色识别，决定路由到哪条线）
├── 报告助手 Supervisor（插件包）
│   ├── 子Agent: 报告书写/集成
│   ├── 子Agent: 质控（报告+影像）
│   └── 子Agent: 影像分析
├── 岗位助理 Supervisor
│   ├── 子Agent: 登记台
│   ├── 子Agent: 预约
│   └── 子Agent: 科室秘书（排班/绩效/统计）
├── 科研助手 Supervisor
│   ├── 子Agent: 课题管理
│   ├── 子Agent: 论文协作
│   └── 子Agent: 数据挖掘
└── 科室客服 Supervisor
    ├── 子Agent: 智能客服
    └── 子Agent: 随访客服
**关于设计原则**
每个 Supervisor 对应 harness 的一个插件包，各自持有独立的 tool 集合、权限 scope、system prompt/skills。Root Agent 只做路由+鉴权，不碰业务逻辑——这样权限边界清晰，出问题也好审计定位到具体插件。

关键设计原则：子 Agent 不是越多越好。子 Agent 的存在理由应该是"职责边界+权限边界不同"，而不是"功能点不同"。比如"报告质控"和"影像质控"完全可以是同一个子 Agent 下的两个 tool，而不必拆成两个子 Agent——拆分过细会增加路由损耗和上下文丢失的风险。
13. 关于SSE
SSE是 Server-Sent Events (SSE) 是一种基于 HTTP 的服务器推送技术，它允许服务器将实时更新主动发送到客户端（通常是 Web 浏览器），而无需客户端重复发起请求，与传统的 Web 应用模式不同，在传统模式下，客户端需要主动向服务器发送请求以获取新数据，而 SSE 则反转了这一模式，使得服务器可以在数据可用时立即将其推送给客户端。
所以可以显著地减少这个等待的焦虑，大大增加了实时性