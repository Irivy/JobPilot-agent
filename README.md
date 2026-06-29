# JobPilot

JobPilot 是一个面向智能求职执行场景的 Python Agent 项目，目标是在用户提供求职目标、简历、可选 JD 和可选项目代码后，动态选择工具完成岗位理解、证据收集、匹配评分与投递材料生成。

## 核心场景

- 用户已提供完整 JD，系统直接做岗位理解、证据核验和匹配分析。
- 用户未提供 JD，系统可先搜索本地岗位库，再读取岗位详情继续分析。
- 简历证据不足时，系统可检查本地项目代码补充技能证据。
- 当证据仍不足时，系统必须明确说明限制，而不是把能力写成既成事实。

## 计划技术栈

- Python
- LangGraph
- FastAPI
- Streamlit
- 本地 `jobs.json` 数据源
- 自动化测试与 Golden Cases

## 当前开发状态

当前仓库处于文档与仓库规范建立阶段，已明确产品需求、Agent 约束、工具契约、架构边界和关键 ADR。

目前尚未实现任何 Python 业务代码、前后端功能、测试代码或工程初始化配置。

## 建议目录结构

未来代码结构统一规划为：

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

其中 `frontend` 计划用于 Streamlit，`data` 用于本地 `jobs.json`、示例简历和项目数据，`tests` 用于单元测试与集成测试，`evals` 用于 Agent Golden Cases 和轨迹评测。

## 文档索引

- `AGENTS.md`：仓库级开发规则。
- `docs/PRD.md`：产品需求文档。
- `docs/AGENT_SPEC.md`：Agent 行为规范。
- `docs/TOOL_CONTRACTS.md`：六个核心工具的契约定义。
- `docs/ARCHITECTURE.md`：系统分层、State 设计与测试边界。
- `docs/DECISIONS.md`：关键架构决策记录。

## MVP 范围

第一版计划覆盖以下能力：

- 单个求职 Agent
- 本地简历文本或文件
- 本地岗位库搜索与岗位详情读取
- 本地项目代码证据检索
- 确定性的岗位匹配评分
- LangGraph Agent Loop
- FastAPI 后端
- Streamlit 前端
- Agent 执行轨迹
- 自动化测试和 Golden Cases

第一版明确不包含：

- 多 Agent
- 真实招聘网站抓取
- 真实 GitHub API
- 自动投递或自动发信
- 自动修改用户原始简历
- 用户账户系统
- 云端部署
- 向量数据库或 RAG 知识库

## 说明

本阶段仅完成项目概览和设计文档，不提供尚未存在的运行命令，也不声称未实现的功能已经可用。
