# JobPilot Agent Specification

## 1. Agent 最终目标

JobPilot Agent 的目标是：基于用户提供的求职目标、简历、可选 JD 和可选项目代码，选择合适的 Tool 完成岗位理解、证据收集、匹配评分和投递材料生成，并在证据不足时诚实暴露不确定性。

## 2. Agent 与固定 Workflow 的区别

这里的 Workflow 指预定义、分支有限的固定流程；Agent 指能基于当前 State 自主决定“下一步是否需要调用某个 Tool”。JobPilot 不是永远执行“读简历 -> 搜岗位 -> 读 JD -> 评分 -> 生成报告”的固定链路，而是根据输入差异选择路径。

## 3. 可用工具

- `load_candidate_profile`
- `search_jobs`
- `read_job_detail`
- `inspect_project_evidence`
- `score_job_fit`
- `generate_application_pack`

各工具的输入输出与安全约束以 `docs/TOOL_CONTRACTS.md` 为准。

说明：用户直接提供的 `provided_jd` 需要先在 Agent 内部节点中经由 LLM 结构化为 `JobDetail`，该内部节点不构成第七个外部 Tool。只有本地 `jobs.json` 中已存在 `job_id` 的岗位，才通过 `read_job_detail` 读取。两种来源最终都汇总到统一的 `target_job`。

## 4. 决策原则

- 先利用已提供信息，避免无意义搜索。
- `provided_jd` 缺失且用户明确要求寻找或推荐岗位时，必须搜索岗位。
- `provided_jd` 缺失但用户只要求解析简历、建立画像或总结经历时，不应搜索岗位。
- 优先收集事实证据，再生成结论。
- 对高风险结论保持保守，缺证据时明确标记。
- 能用确定性代码完成的逻辑，不交给 LLM 自由发挥。
- 每一步调用都应服务于最终报告生成或缺口消除。

## 5. Agent Loop

建议的 Agent Loop 如下：

1. 读取当前 `State`，识别是否已有简历、原始 `provided_jd`、结构化 `target_job`、项目路径和历史工具结果。
2. 若存在 `provided_jd` 但 `target_job` 尚未建立，则在 Agent 内部节点中把原始 JD 结构化为 `JobDetail` 并写入 `target_job`。
3. 判断当前主要缺口：候选人画像缺失、目标岗位缺失、证据缺失、评分缺失或最终材料缺失。
4. 选择一个最合适的 Tool。
5. 调用 Tool，写回结构化结果到 `State`；当岗位来自本地岗位库时，应把读取结果写入 `target_job`。
6. 增加 `tool_call_count`，并判断是否满足终止条件；若未满足且未超过 `max_tool_calls`，则继续下一轮。

## 6. 终止条件

满足任一条件即可终止：

- 已成功生成 `final_report`。
- 关键信息缺失且当前版本没有进一步可调用的 Tool。
- 工具连续返回不可恢复错误，继续调用无收益。
- 达到最大工具调用次数。

## 7. 最大工具调用次数

MVP 建议设置全局上限 `max_tool_calls = 12`。执行过程中应使用 `tool_call_count` 专门记录外部 Tool 调用次数，并据此执行上限控制；不再使用含义模糊的 `step_count`。该值用于防止循环调用，同时保留适度探索空间。后续可依据真实评测数据微调。

## 8. 事实依据规则

- 所有写入候选人能力、项目经历、投递材料的结论都必须绑定 `evidence_id`。
- 证据来源必须可追溯到简历原文、结构化 `target_job` 中的岗位要求或项目检查结果。
- LLM 可以做语义归纳，但不能伪造新事实。
- 若证据只能支持“可能相关”，输出中必须标记为待确认，而非已掌握。

## 9. 信息不足时的行为

- 如果缺少 JD，且用户明确要求寻找或推荐岗位，必须搜索岗位。
- 如果缺少 JD，但用户只要求解析简历、建立画像或总结经历，不应搜索岗位。
- 如果缺少关键能力证据，且存在 `project_path`，允许检查项目代码。
- 如果仍然缺证据，当前版本应输出“证据不足”并结束，后续版本再引入暂停提问。
- 不得为了完成报告而自动补写未经验证的经历。

## 10. Human-in-the-loop 计划

MVP 先记录 HITL 设计，不强制实现完整交互暂停。计划中的介入点包括：

- 用户确认是否采用某个岗位作为目标岗位。
- 用户补充未在简历或项目中出现的真实经历。
- 用户确认最终投递材料是否可用于外发。

## 11. 错误处理策略

- Tool 错误必须结构化返回，包含错误类型和可恢复性标记。
- 可恢复错误应允许 Agent 改用其他路径，例如搜索无结果后直接说明限制。
- 不可恢复错误应终止并输出失败状态。
- 不得吞掉异常或伪装成成功结果。

## 12. 成功和失败状态

### 成功状态

- `completed_with_report`：已生成最终报告与投递材料。
- `completed_with_gap_notice`：已输出报告，但明确标注部分证据不足。

### 失败状态

- `failed_missing_required_input`：缺少简历等必要输入。
- `failed_no_job_context`：既无 JD，也无法从岗位库中找到可用岗位。
- `failed_tool_error`：关键工具异常且不可恢复。
- `failed_tool_call_limit`：达到最大工具调用次数仍未收敛。

State 字段与模块边界见 `docs/ARCHITECTURE.md`。
