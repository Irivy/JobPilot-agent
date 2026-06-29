# AGENTS.md

本文件定义 Codex 进入本仓库后必须优先遵守的开发规则。

## 开始任务前

- 先阅读 `README.md`、`docs/PRD.md`、`docs/AGENT_SPEC.md`、`docs/TOOL_CONTRACTS.md`、`docs/ARCHITECTURE.md`、`docs/DECISIONS.md`。
- 先查看 Git 状态与待修改文件，确认本次任务范围。

## 目录职责

- `README.md`：项目概览与文档索引。
- `docs/`：需求、架构、Agent 规范、工具契约、ADR。
- 后续代码目录应按 `docs/ARCHITECTURE.md` 的统一建议结构规划：
  `app/`、`frontend/`、`data/`、`tests/`、`evals/`、`docs/`。
- `app/agent`：LangGraph 编排、State、Prompt 和策略。
- `app/tools`：六个 Agent Tool。
- `app/schemas`：Pydantic 数据模型。
- `app/providers`：LLM 与未来外部服务适配器。
- `app/api`：FastAPI 路由。
- `app/services`：不属于 Agent Tool 的确定性内部服务。
- 未经明确要求，不要提前创建上述目录或其中的代码文件。

## 编码与设计规则

- Python 代码必须使用类型注解。
- 网络调用必须封装在 `Provider` 或 `Adapter` 中，不得散落在业务流程里。
- 不得硬编码 API Key、Token、密码或其他密钥。
- 不得吞掉异常；需要保留上下文并显式处理或上抛。
- 未经用户明确要求，不得添加生产依赖。
- 所有用户经历、简历表述、技能结论都必须关联 `evidence_id`。
- 具有外部副作用的操作必须先得到用户确认，例如发请求、写外部系统、发送邮件、批量改写文件。

## 测试与质量

- 单元测试禁止访问真实网络。
- 一次任务只修改与当前需求直接相关的文件。
- 完成任务前应运行与当前阶段相匹配的检查。
- 当前仓库尚未初始化工程配置，具体测试、格式化、类型检查命令暂不固定；待工程初始化后补充到本文件与 `README.md`。

## 最终回复要求

- 报告本次修改的文件。
- 报告执行过的检查及结果。
- 报告当前已知限制、未覆盖项和风险。
