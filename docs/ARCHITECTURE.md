# JobPilot Architecture

## 1. 系统分层

JobPilot MVP 建议采用分层架构，把“界面展示”“API 编排”“Agent 决策”“Tool 执行”“Provider 适配”“Schema 定义”“评测验证”分开。这样做的目标是降低耦合，保证后续从本地 Mock 迁移到真实服务时，不需要重写 Agent 主逻辑。

建议层次如下：

- Frontend：展示输入表单、执行轨迹和输出报告。
- API：接收请求、校验输入、触发 Agent 运行、返回结构化结果。
- Agent：维护 State，决定下一步 Tool，控制 Loop 和终止。
- Tools：实现可调用能力，封装单个任务单元。
- Providers / Adapters：封装外部依赖或数据源访问。
- Schemas：统一输入输出数据结构和类型定义。
- Evaluation：承载自动化测试、Golden Cases、回归检查。

## 2. 建议目录结构

本阶段只给建议，不代表当前仓库已实现：

```text
jobpilot-agent/
  app/
    agent/
    tools/
    schemas/
    providers/
    api/
    services/
  main.py
  frontend/
  data/
  tests/
  evals/
  docs/
```

目录说明如下：

- `app/agent`：LangGraph 编排、State、Prompt 和策略。
- `app/tools`：六个 Agent Tool。
- `app/schemas`：Pydantic 数据模型。
- `app/providers`：LLM 与未来外部服务适配器。
- `app/api`：FastAPI 路由。
- `app/services`：不属于 Agent Tool 的确定性内部服务。
- `frontend`：Streamlit 前端。
- `data`：本地 `jobs.json`、示例简历和项目数据。
- `tests`：单元测试与集成测试。
- `evals`：Agent Golden Cases 和轨迹评测。
- `docs`：需求、架构、契约与 ADR 文档。

## 3. 模块职责

### Frontend

Frontend 指面向用户的交互界面。MVP 计划使用 Streamlit，负责收集用户输入、展示 Agent 轨迹和最终结果，不直接调用 Tool。

### API

API 指系统对外的程序入口。MVP 计划使用 FastAPI，负责请求校验、会话上下文传递、调用 Agent 服务并返回结构化响应。

### Agent

Agent 负责读取当前 State、决定下一步 Tool、控制最大步数、判断终止条件，并把结果汇总为最终报告。

### Tools

Tool 是可被 Agent 调用的原子能力，例如搜索岗位、读取岗位详情、检查项目证据、评分和生成材料。Tool 本身不负责全局流程决策。

### Providers / Adapters

Provider 或 Adapter 负责封装数据源和未来的外部服务，例如本地 `jobs.json`、未来的招聘网站接口、LLM 调用封装。所有网络访问都必须通过这一层。

### Schemas

Schema 负责统一定义 `State`、请求响应对象、工具输入输出、评分报告、证据记录等结构，避免跨层自由拼装字典。

### Evaluation

评测模块负责 Golden Cases、回归测试、轨迹断言、工具调用顺序验证和确定性评分结果验证。

## 4. Agent 执行流程

建议执行流程如下：

1. API 接收用户输入并构造初始 `State`。
2. Agent 判断是否先调用 `load_candidate_profile`。
3. 若存在原始 `provided_jd`，Agent 通过内部 LLM 节点把它结构化为 `JobDetail`，并写入统一的 `target_job`。
4. 若 `provided_jd` 缺失，且用户明确要求寻找或推荐岗位，Agent 必须调用 `search_jobs` 并选取候选岗位。
5. Agent 对选中的 `job_id` 调用 `read_job_detail`，将结果写入统一的 `target_job`。
6. 若证据不足且存在 `project_path`，Agent 调用 `inspect_project_evidence`。
7. Agent 调用 `score_job_fit`，基于 `target_job` 和证据生成确定性匹配报告。
8. Agent 调用 `generate_application_pack`，基于 `target_job`、`fit_report` 和证据输出最终材料。
9. API 返回结果，Frontend 展示轨迹和报告。

## 5. 数据流

- 用户输入先进入 API 层，不直接进入 Tool。
- API 将原始输入转换为结构化 `State`。
- Agent 基于 `State` 决策 Tool 调用。
- Tool 返回结构化结果，再写回 `State`。
- `State` 是一次执行过程的工作内存，不等同于数据库。
- 最终结果通过 API 返回给 Frontend；若未来需要持久化，再单独设计存储层。

## 6. Agent State 初步字段设计

### `messages`

保存 Agent 与系统提示、工具摘要、用户追问等消息序列。它存在的原因是帮助 LLM 理解上下文和最近的决策依据，但不应被当作长期事实数据库。

### `user_goal`

保存用户的开放式求职目标。它存在的原因是驱动岗位搜索和投递材料风格，避免 Agent 只围绕 JD 工作而忽略用户意图。

### `provided_jd`

保存用户直接给出的原始 JD 文本或文件解析结果。它存在的原因是让 Agent 判断是否可以跳过 `search_jobs`，并在 Agent 内部先把原始 JD 结构化为统一岗位对象。

### `resume_path`

保存简历文件路径。它存在的原因是让简历加载与后续审计具备可追溯入口。

### `project_path`

保存本地项目路径。它存在的原因是只有在证据不足时，Agent 才应考虑调用项目检查 Tool。

### `candidate_profile`

保存由简历解析得到的结构化候选人画像。它存在的原因是将简历原文转化为可复用的事实对象，供多个 Tool 共享。

### `job_candidates`

保存 `search_jobs` 返回的候选岗位摘要列表。它存在的原因是让 Agent 能比较和选择目标岗位，而不是只保留最终一个结果。

### `inspected_jobs`

保存已读取详情的岗位信息集合。它存在的原因是避免重复读取同一岗位，也为多岗位比较预留空间。

### `target_job`

保存统一的结构化目标岗位对象。它存在的原因是屏蔽岗位来源差异：无论岗位来自用户直接提供的 `provided_jd`，还是来自本地岗位库中的 `job_id`，最终都应归一成同一个 `JobDetail` 结构，供评分和材料生成复用。

### `evidence_ledger`

保存所有已登记的证据条目及其 `evidence_id`、来源、置信级别和关联能力。它存在的原因是支撑“所有结论必须绑定证据”的核心约束。

### `fit_reports`

保存一个或多个岗位匹配报告。它存在的原因是将评分结果从自然语言总结中独立出来，便于测试和回归比对。

### `final_report`

保存最终投递材料和输出摘要。它存在的原因是区分“过程状态”和“对用户可展示的最终产物”。

### `errors`

保存结构化、可诊断的工具或执行错误。它存在的原因是让 Agent、API 和测试可以区分可恢复错误与不可恢复错误，而不是只依赖自然语言报错。

### `tool_call_count`

保存当前外部 Tool 调用次数。它存在的原因是专门用于执行 `max_tool_calls` 限制，避免再使用含义模糊的 `step_count`。

### `status`

保存当前执行状态，例如运行中、完成、证据不足、失败。它存在的原因是让 API 和前端可以明确展示任务阶段与结束原因。

## 7. State、Messages、数据库的区别

- `State`：一次 Agent 运行期间的工作内存，服务于当前任务推进。
- `messages`：`State` 中的一部分，主要给 LLM 提供对话和步骤上下文。
- 数据库：未来若引入，用于跨会话持久化用户资料、历史任务和审计记录；MVP 当前不要求实现。

## 8. 哪些逻辑交给 LLM

- 理解开放式求职目标。
- 从简历或原始 `provided_jd` 中做语义归纳。
- 把用户直接提供的原始 JD 结构化为 `JobDetail`。
- 决定下一步优先调用哪个 Tool。
- 在已验证事实范围内组织最终输出表达。

## 9. 哪些逻辑必须使用普通代码

- 读取本地文件和本地岗位库。
- 目录扫描与证据命中收集。
- 确定性岗位匹配评分。
- 工具输入输出校验。
- `max_tool_calls` 控制、状态迁移和错误分类。

## 10. Mock 阶段和真实服务阶段如何替换

- 数据访问通过 Provider 接口抽象。
- MVP 用本地 `jobs.json` 与本地文件系统 Provider。
- 未来若接入真实招聘网站或 GitHub API，只替换对应 Provider，不改 Agent 决策接口和 Tool 契约。
- 所有真实网络调用都必须继续走 Provider / Adapter 层，测试中可用 Mock Provider 替换。

## 11. 安全边界

- Frontend 不直接调用 Tool，避免绕过 API 校验。
- Tool 只读取用户明确授权的本地路径。
- 外部副作用操作需要单独确认与隔离设计。
- 不修改用户原始简历文件。
- 不把未验证事实写入最终材料。

## 12. 测试分层

- 单元测试：验证 Tool 纯逻辑、评分逻辑、Schema 校验和错误分类。
- 集成测试：验证 API 到 Agent 到 Tool 的主链路。
- Golden Cases：验证典型输入下的调用路径、`target_job` 归一化、状态流转和输出约束。
- 回归测试：防止未来改动破坏“有 JD 不搜岗”“无证据不写成已掌握”等核心规则。

相关产品目标与验收条件见 `docs/PRD.md`，Agent 行为规则见 `docs/AGENT_SPEC.md`。
