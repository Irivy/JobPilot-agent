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
- `ToolFailure`：本次调用无法构造成功载荷时的统一失败分支，至少包含一个
  `ToolError`；其中错误可以全部为可恢复错误。

成功载荷中的 `errors` 只能包含可恢复错误。无法构造合法领域对象时，Tool
返回 `ToolFailure`，不得使用占位字段伪造 `CandidateProfile`、`JobDetail`、
`FitReport` 或 `ApplicationPack`。Agent 应依据每个 `ToolError.recoverable`
决定换用其他路径或终止，而不能仅根据结果是否为 `ToolFailure` 判断。

## 1. `load_candidate_profile`

### 作用

从本地简历文本或文件中提取结构化候选人画像，并为后续证据绑定提供基础素材。

### Schema

- Input: `LoadCandidateProfileInput`
- Success: `CandidateProfileSuccess`
- Output: `CandidateProfileResult = CandidateProfileSuccess | ToolFailure`

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

`resume_text` 与 `resume_path` 必须恰好提供一个；契约校验不读取或解析文件。

### 成功输出字段

- `candidate_profile: CandidateProfile`
- `evidence_items: list[EvidenceItem]`
- `warnings: list[ToolWarning]`
- `errors: list[ToolError]`

`candidate_profile_id`、`missing_fields`、技能、经历、教育和证书由
`CandidateProfile` 统一承载，不在成功载荷中重复保存。

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
- Success: `JobSearchSuccess`
- Output: `JobSearchResult = JobSearchSuccess | ToolFailure`

### 使用时机

- 用户没有提供完整 JD。
- 当前缺少足以进入评分阶段的岗位上下文。

### 不应使用的情况

- `provided_jd` 已存在且内容完整。
- 已经确定目标岗位且无需继续搜索。

### 输入字段

- `query: str | null`
- `location_preferences: list[str]`
- `keywords: list[str]`
- `seniority: str | null`
- `work_mode: str | null`
- `limit: int`

`query` 或 `keywords` 必须至少提供一项；`limit` 范围为 1 到 100。位置和关键词
按忽略大小写方式去重并保留首次出现顺序。

搜索使用 NFKC、`casefold`、标点转空格和连续空白合并进行规范化。query token
全部命中才符合条件；keywords 中任一完整短语命中即可。location preferences
内部为 OR，seniority 和 work mode 使用规范化精确匹配，各过滤组之间为 AND。
如果输入在规范化后不含有效搜索项，则返回可恢复的 `search_query_empty`。

固定字段权重为：title 8、requirements 5、preferred qualifications 4、
summary/responsibilities 3、company/location/employment type/seniority/work mode 1。
每个唯一搜索项只取命中字段的最高权重。结果按总分降序、标题命中数降序、
`job_id.casefold()` 和原始 `job_id` 升序排列，再应用 limit；内部得分不对外返回。

### 输出字段

- `results: list[JobSummary]`
- `result_count: int`
- `applied_filters: SearchJobsInput`
- `search_source: JobSourceType.JOBS_DATASET`
- `warnings: list[ToolWarning]`
- `errors: list[ToolError]`

### 可能的错误

- `jobs_dataset_missing`
- `jobs_dataset_invalid`
- `search_query_empty`

数据集缺失使用不可恢复的 `jobs_dataset_missing`；数据集不可读、格式错误、记录
无效或 `job_id` 重复使用不可恢复的 `jobs_dataset_invalid`。

### 是否存在外部副作用

无外部副作用。

### 安全约束

- 仅允许访问本地岗位数据源。
- 不得访问真实招聘网站或外部网络。
- 返回摘要时避免泄露不必要的内部字段。
- 数据源正常但没有匹配项时返回 `JobSearchSuccess(results=[])`，并附加
  `code=no_job_matches` 的可恢复 warning，不返回 `ToolFailure`。

## 3. `read_job_detail`

### 作用

根据 `job_id` 读取某个岗位的完整信息，用于要求提取和评分。

### Schema

- Input: `ReadJobDetailInput`
- Output: `ReadJobDetailResult = JobDetail | ToolFailure`

### 使用时机

- 已从搜索结果中选定岗位。
- 用户提供了目标岗位 ID 或需补全岗位详情。

### 不应使用的情况

- 已有完整岗位详情且版本未变化。
- `job_id` 不明确或未被选定。

### 输入字段

- `job_id: str`
- `source: JobSourceType.JOBS_DATASET`

### 输出字段

- `job_id: str`
- `title: str`
- `company: str`
- `location: str | null`
- `employment_type: str | null`
- `seniority: str | null`
- `work_mode: str | null`
- `summary: str | null`
- `responsibilities: list[str]`
- `requirements: list[JobRequirement]`
- `preferred_qualifications: list[JobRequirement]`
- `raw_text: str | null`
- `warnings: list[ToolWarning]`
- `errors: list[ToolError]`

### 可能的错误

- `job_id_missing`
- `job_not_found`
- `job_record_invalid`

`job_not_found` 返回 `recoverable=true` 的 `ToolFailure`。数据集缺失、不可读或
无效时返回不可恢复的 `ToolFailure`，分别使用 `jobs_dataset_missing` 或
`jobs_dataset_invalid`；记录校验失败使用 `job_record_invalid`。

### 是否存在外部副作用

无外部副作用。

### 安全约束

- 只能读取本地岗位库中存在的记录。
- 不得伪造不存在的岗位字段。
- 不用于解析用户直接提供的原始 JD 文本；该路径属于 Agent 内部结构化节点。
- `JobDetail` 是成功分支；无法构造合法岗位详情时返回 `ToolFailure`。

## 4. `inspect_project_evidence`

### 作用

在用户指定的本地项目目录中搜索技能、模块、成果和上下文证据，为能力判断提供补充证明。

### Schema

- Input: `InspectProjectEvidenceInput`
- Success: `EvidenceScanSuccess`
- Output: `EvidenceScanResult = EvidenceScanSuccess | ToolFailure`

### 使用时机

- 简历证据不足。
- 用户明确提供了 `project_path`。
- 需要验证某项岗位要求是否能在项目中找到事实支持。

### 不应使用的情况

- 用户未提供 `project_path`。
- 简历证据已足够支撑当前判断。
- 目标仅是生成自然语言总结而非补证据。

### 输入字段

- `project_path: LocalPathStr`
- `skills_to_verify: list[str]`
- `keywords: list[str]`
- `max_files: int`
- `allowed_extensions: list[str]`

`project_path` 只表示用户授权的本地路径，不允许网络 URI 或 UNC 网络路径。
扩展名统一转为小写并带前导点，例如 `py`、`.PY` 都规范化为 `.py`；禁止通配符和路径。
`skills_to_verify` 或 `keywords` 必须至少提供一项，`max_files` 范围为 1 到 1000。

### 输出字段

- `project_path: LocalPathStr`
- `evidence_hits: list[EvidenceItem]`
- `files_scanned: int`
- `truncated: bool`
- `warnings: list[ToolWarning]`
- `errors: list[ToolError]`

`files_scanned` 是成功解码并实际参与匹配的文件数；仅读取受限前缀的文件仍计入。
当文件数、目录项、总读取字节、单文件前缀、每目标 Evidence 数量或总 Evidence
数量达到限制时，`truncated=true`，并通过 warning 说明具体原因。

### 扫描与匹配规则

- Provider 独占真实文件系统访问。Tool 只消费 Provider 返回的内部 `ProjectFile`
  快照，不直接遍历或读取磁盘。
- Provider 解析授权根目录，并拒绝读取解析后位于根目录之外的文件。目录 symlink
  和 junction 不递归；文件 symlink 只有在指向根目录内普通文件时才可读取。
- 隐藏目录、常见依赖或构建目录、二进制文件、明显凭据文件及私钥内容会被跳过。
  文件读取使用 UTF-8 严格解码，支持 UTF-8 BOM，并受文件数、目录项、单文件字节
  和总字节限制。
- 文本依次执行 NFKC、camelCase/acronym 边界拆分、分隔符规范化、空白合并和
  `casefold`；保留 `+` 和 `#`，中文使用规范化子字符串匹配。
- 每个 skill 和 keyword 独立匹配；同一规范化目标同时出现时优先保留 skill。
  扩展名本身不作为技能证据。
- 命中优先级依次为：源码或配置完整 token/短语、README 或文档完整 token/短语、
  文件名或路径组件精确命中、普通内容子字符串命中。同一目标在同一文件中的重复
  命中合并，选择质量最高且行号最早的位置。
- 最终结果按命中等级、目标类型、规范化目标、相对路径、行号和 `evidence_id`
  稳定排序。每个目标最多 5 条 Evidence，总计最多 50 条。
- 项目 Evidence 的置信度仅使用 `MEDIUM` 和 `LOW`：源码或配置中的完整 token/短语
  为 `MEDIUM`，文档、路径和普通子字符串命中为 `LOW`。词法命中不产生 `HIGH`。
  词法命中只表示项目中出现了相关内容，不等同于候选人熟练掌握该技能。
- `evidence_id` 为带版本输入的 SHA-256 截断值，输入包含解析后根目录的摘要、
  相对路径、目标类型、规范化目标、命中类型、行号和命中行摘要。绝对路径不直接
  出现在 ID、Evidence 或错误上下文中；项目移动后 ID 可以变化。
- 内容摘录最多包含命中行前后各一行，总长度不超过 600 字符，并对常见秘密赋值
  做保守脱敏。

### 成功、警告与失败

- 无匹配返回成功，并附 `no_project_evidence` warning。
- 无可参与匹配的文件返回成功，并附 `no_scannable_project_files` warning。
- 达到扫描限制返回成功，并附 `scan_limit_exceeded` warning；不是
  `ToolFailure`。
- 单文件不可读或解码失败、但仍有其他文件成功时，返回成功并附聚合的可恢复
  `project_file_unreadable` 或 `project_file_decode_failed` error。
- 根路径不存在返回可恢复的 `ToolFailure(project_path_not_found)`。
- 根路径不是目录或无法访问返回可恢复的
  `ToolFailure(project_path_not_accessible)`。
- 存在读取候选但所有候选均不可读或不可解码时，返回可恢复的
  `ToolFailure(project_files_unreadable)`。
- `project_path_missing` 已由输入 Schema 阻止，不由 Tool 伪造。

同类 Provider issue 会聚合成单个 warning 或 error；context 只包含总计数、少量
相对路径样例和限制或安全类别。成功结果中的所有 error 都必须
`recoverable=true`。

### 是否存在外部副作用

无外部副作用。

### 安全约束

- 只读取用户明确授权的本地目录。
- 不执行项目代码，不安装依赖，不写入项目文件。
- 对扫描范围和文件数量设置上限，避免越界读取或资源滥用。
- 不输出解析后的绝对根路径、完整文件内容或检测到的秘密值。

## 5. `score_job_fit`

### 作用

根据岗位要求与已验证证据计算确定性的匹配分数，并输出可解释的分项结果。

### Schema

- Input: `ScoreJobFitInput`
- Output: `ScoreJobFitResult = FitReport | ToolFailure`

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
- `weights: ScoringWeights | null`

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
- `FitReport` 是成功分支；无法构造合法评分结果时返回 `ToolFailure`。

## 6. `generate_application_pack`

### 作用

基于已验证事实与评分结果生成最终投递材料包，供用户复核和后续人工使用。

### Schema

- Input: `GenerateApplicationPackInput`
- Output: `GenerateApplicationPackResult = ApplicationPack | ToolFailure`

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
- `ApplicationPack` 是成功分支；无法构造合法材料包时返回 `ToolFailure`。

字段命名约定、State 集成方式和模块边界见 `docs/ARCHITECTURE.md`。
