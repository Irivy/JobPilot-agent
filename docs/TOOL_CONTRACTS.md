# Tool Contracts

本文件定义 JobPilot MVP 的六个核心 Tool。这里的 Tool 指 Agent 可调用的能力单元；所有 Tool 都应返回结构化数据，避免将关键结果藏在不受约束的长文本中。

## 公共 Schema

未来至少需要以下公共 Schema，用于在 Tool 之间共享统一的数据结构：

- `CandidateExperience`：候选人经历条目，承载时间范围、角色、项目、事实摘要和关联 `evidence_id`。
- `CandidateSkill`：候选人技能条目，承载技能名、熟悉度标签、证据引用和备注。
- `JobRequirement`：岗位要求条目，承载要求文本、要求类型、优先级和可评分标记。
- `EvidenceItem`：证据条目，承载 `evidence_id`、来源、摘录、定位信息和置信标签。
- `RequirementMatch`：岗位要求与证据的匹配条目，承载匹配状态、命中证据、缺口说明和评分贡献。
- `ToolWarning`：可恢复提醒，承载 `code`、`message` 和可选 `context`。
- `ToolError`：结构化错误对象，承载 `code`、`message`、`recoverable` 和可选 `context`。

## 1. `load_candidate_profile`

### 作用

从本地简历文本或文件中提取结构化候选人画像，并为后续证据绑定提供基础素材。

### Schema

- Input: `LoadCandidateProfileInput`
- Output: `CandidateProfileResult`

### 使用时机

- `candidate_profile` 尚未建立。
- 用户提供了 `resume_text` 或 `resume_path`。

### 不应使用的情况

- 没有任何简历输入。
- `candidate_profile` 已存在且本轮没有新的简历内容。

### 输入字段

- `resume_text: str | null`
- `resume_path: str | null`
- `parsing_mode: str`
- `target_role_hint: str | null`

### 输出字段

- `candidate_profile_id: str`
- `summary_facts: list[CandidateFact]`
- `skills: list[CandidateSkill]`
- `experiences: list[CandidateExperience]`
- `education: list[EducationItem]`
- `certifications: list[CertificationItem]`
- `evidence_items: list[EvidenceItem]`
- `missing_fields: list[str]`
- `warnings: list[ToolWarning]`
- `errors: list[ToolError]`

### 可能的错误

- `resume_input_missing`
- `resume_file_not_found`
- `resume_parse_failed`
- `resume_content_empty`

### 是否存在外部副作用

无外部副作用。

### 安全约束

- 只读取用户明确提供的本地简历内容。
- 不得把推测内容写成事实。
- 输出中的每条经历和技能都应可回溯到 `evidence_items`。

## 2. `search_jobs`

### 作用

根据关键词和求职偏好搜索本地 `jobs.json`，返回候选岗位摘要。

### Schema

- Input: `SearchJobsInput`
- Output: `JobSearchResult`

### 使用时机

- 用户没有提供完整 JD。
- 当前缺少足以进入评分阶段的岗位上下文。

### 不应使用的情况

- `provided_jd` 已存在且内容完整。
- 已经确定目标岗位且无需继续搜索。

### 输入字段

- `query: str`
- `location_preferences: list[str]`
- `keywords: list[str]`
- `seniority: str | null`
- `work_mode: str | null`
- `limit: int`

### 输出字段

- `results: list[JobSummary]`
- `result_count: int`
- `applied_filters: dict`
- `search_source: str`
- `warnings: list[ToolWarning]`
- `errors: list[ToolError]`

### 可能的错误

- `jobs_dataset_missing`
- `jobs_dataset_invalid`
- `search_query_empty`

### 是否存在外部副作用

无外部副作用。

### 安全约束

- 仅允许访问本地岗位数据源。
- 不得访问真实招聘网站或外部网络。
- 返回摘要时避免泄露不必要的内部字段。

## 3. `read_job_detail`

### 作用

根据 `job_id` 读取某个岗位的完整信息，用于要求提取和评分。

### Schema

- Input: `ReadJobDetailInput`
- Output: `JobDetail`

### 使用时机

- 已从搜索结果中选定岗位。
- 用户提供了目标岗位 ID 或需补全岗位详情。

### 不应使用的情况

- 已有完整岗位详情且版本未变化。
- `job_id` 不明确或未被选定。

### 输入字段

- `job_id: str`
- `source: str`

### 输出字段

- `job_id: str`
- `title: str`
- `company: str`
- `location: str | null`
- `employment_type: str | null`
- `responsibilities: list[str]`
- `requirements: list[JobRequirement]`
- `preferred_qualifications: list[JobRequirement]`
- `raw_text: str`
- `warnings: list[ToolWarning]`
- `errors: list[ToolError]`

### 可能的错误

- `job_id_missing`
- `job_not_found`
- `job_record_invalid`

### 是否存在外部副作用

无外部副作用。

### 安全约束

- 只能读取本地岗位库中存在的记录。
- 不得伪造不存在的岗位字段。
- 不用于解析用户直接提供的原始 JD 文本；该路径属于 Agent 内部结构化节点。

## 4. `inspect_project_evidence`

### 作用

在用户指定的本地项目目录中搜索技能、模块、成果和上下文证据，为能力判断提供补充证明。

### Schema

- Input: `InspectProjectEvidenceInput`
- Output: `EvidenceScanResult`

### 使用时机

- 简历证据不足。
- 用户明确提供了 `project_path`。
- 需要验证某项岗位要求是否能在项目中找到事实支持。

### 不应使用的情况

- 用户未提供 `project_path`。
- 简历证据已足够支撑当前判断。
- 目标仅是生成自然语言总结而非补证据。

### 输入字段

- `project_path: str`
- `skills_to_verify: list[str]`
- `keywords: list[str]`
- `max_files: int`
- `allowed_extensions: list[str]`

### 输出字段

- `project_path: str`
- `evidence_hits: list[EvidenceItem]`
- `files_scanned: int`
- `truncated: bool`
- `warnings: list[ToolWarning]`
- `errors: list[ToolError]`

### 可能的错误

- `project_path_missing`
- `project_path_not_found`
- `project_path_not_accessible`
- `scan_limit_exceeded`

### 是否存在外部副作用

无外部副作用。

### 安全约束

- 只读取用户明确授权的本地目录。
- 不执行项目代码，不安装依赖，不写入项目文件。
- 对扫描范围和文件数量设置上限，避免越界读取或资源滥用。

## 5. `score_job_fit`

### 作用

根据岗位要求与已验证证据计算确定性的匹配分数，并输出可解释的分项结果。

### Schema

- Input: `ScoreJobFitInput`
- Output: `FitReport`

### 使用时机

- 已有岗位详情。
- 已有候选人画像和至少一部分证据。

### 不应使用的情况

- 缺少岗位要求。
- 完全没有可用证据。
- 仅需要搜索岗位而非比较匹配度。

### 输入字段

- `target_job: JobDetail`
- `candidate_profile: CandidateProfile`
- `evidence_ledger: list[EvidenceItem]`
- `scoring_version: str`
- `weights: dict | null`

### 输出字段

- `fit_report_id: str`
- `overall_score: float`
- `score_band: str`
- `dimension_scores: list[RequirementMatch]`
- `matched_evidence_ids: list[str]`
- `missing_requirements: list[JobRequirement]`
- `uncertain_claims: list[RequirementMatch]`
- `rationale_codes: list[str]`
- `warnings: list[ToolWarning]`
- `errors: list[ToolError]`

### 可能的错误

- `target_job_missing`
- `candidate_profile_missing`
- `evidence_ledger_missing`
- `scoring_input_invalid`

### 是否存在外部副作用

无外部副作用。

### 安全约束

- 评分逻辑必须可重复、可测试。
- 不得根据未验证事实加分。
- 输出应区分“已匹配”“部分匹配”“证据不足”。
- 只消费结构化 `target_job`，不直接消费原始 JD 文本。

## 6. `generate_application_pack`

### 作用

基于已验证事实与评分结果生成最终投递材料包，供用户复核和后续人工使用。

### Schema

- Input: `GenerateApplicationPackInput`
- Output: `ApplicationPack`

### 使用时机

- 已完成岗位理解与证据收集。
- 已有 `fit_report` 或明确的目标岗位上下文。

### 不应使用的情况

- 关键事实仍未验证。
- 目标岗位上下文不足。
- 用户只要求分析，不要求生成投递材料。

### 输入字段

- `candidate_profile: CandidateProfile`
- `target_job: JobDetail`
- `fit_report: FitReport`
- `evidence_ledger: list[EvidenceItem]`
- `output_language: str`
- `tone: str`

### 输出字段

- `application_pack_id: str`
- `candidate_summary: list[EvidenceBackedStatement]`
- `role_fit_summary: list[EvidenceBackedStatement]`
- `resume_adjustment_suggestions: list[ResumeAdjustmentSuggestion]`
- `cover_letter_points: list[EvidenceBackedStatement]`
- `fact_check_items: list[FactCheckItem]`
- `warnings: list[ToolWarning]`
- `errors: list[ToolError]`

### 可能的错误

- `target_job_missing`
- `fit_report_missing`
- `evidence_ledger_missing`
- `generation_input_invalid`

### 是否存在外部副作用

无外部副作用。

### 安全约束

- 只能基于已验证事实生成内容。
- 每条候选人经历、技能和亮点都必须能追溯到 `evidence_id`。
- 不得直接修改用户原始简历文件，不得自动投递。
- 只消费结构化 `target_job`，不直接消费原始 JD 文本。

字段命名约定、State 集成方式和模块边界见 `docs/ARCHITECTURE.md`。
