# DocFit Student Content Placement Debug Active Capsule

- Capsule status: PARTIAL QUALITY CANDIDATE PRODUCED
- Source plan: `docs/plans/docfit-student-content-placement-debug.md`
- Baseline commit: `0c3f292c2005722a8019c3bb32864829258f8da9`
- Branch/worktree: `codex/student-content-placement` / independent worktree
- User intent: 把真实学生内容提取与指定模板填写作为独立模块调试，不与当前模板提取 r2 联调
- Current slice: deterministic inventory、read-only Agent extraction、Placement、safe fill、独立质量投影与真实样本验收
- Fixed student hash: `fc39ac02efd152ddf609199615256393e3077b49629e1cca48e1f437b2e44a9b`
- Fixed template hash: `70b13aecf084816a5ff5abc879c00d26c63552c0c36623060b17cbae3d775f50`
- Template qualification: candidate / Human acceptance pending；本切片不得输出 COMPLETE
- Input evidence: student 360 dump paragraphs、1 table、6 drawings/media、4 math objects；
  template 31 content controls、5 sections、3 header/footer parts；两份 DOCX ZIP 检查通过
- Style decision: 长期需要统一内置兜底样式库，但明确不在当前切片；当前只允许使用目标模板现有
  style 和对象安全 direct formatting，不创建公式等缺失样式
- Implementation evidence: 新增独立 `docfit.content.projection`；不增加 CLI、public Tool、Skill 或
  自定义 Agent runtime；inventory 以 OOXML 补齐 inspection 遗漏对象，fill 不复制学生源 style
- Real extraction: MiniMax + `convert-thesis` + `docx_inspect` structured output；371 个 source object
  均被记账（含 3 个 OOXML 恢复公式段），214 mapped、92 随父对象复制、65 unmapped；正文 169 个
  顶层对象，参考文献 36 个
- Real placement: 8 个文本槽和 2 个 block slot 写入；11 个 required 槽缺失；205 个顶层 block、
  6 张图、1 个学生表和 4/4 公式经 dependency closure 进入候选
- Quality evidence: 29 个安全空排版段移除；3/10/23 个一级/二级/三级标题投影；6/6 浮动图转
  inline 并绑定中英文题注；学生表 8958 dxa、17/17 行 `cantSplit`；无非模板 style；9 组批准文本修复
  各命中一次；174 个已选有文本对象、6 图、4 公式、1 学生表零丢失
- Candidate evidence: `PARTIAL`，SHA-256
  `39caaaffddf55d4749957e25610cd743a529fbe3b17c5f30093599ce8cf5d3f0`；canonical
  LibreOffice 25.2.3.2 为 47 页并完成全 47 页接触表复核
- Current blockers: template/Human Gold 未验收；11 required 缺失；65 source object 仍显式 unmapped；
  致谢/附录无来源；TOC 已标 dirty/update-on-open 但需 Microsoft Word 真实刷新；模板与 candidate 均被
  固定 OfficeCLI 无诊断拒绝，新增回归状态为 UNKNOWN
- Next gate: 用户复核质量候选；产品随后决定缺失字段输入和未映射 source 处置。目录 Word 更新证明、
  template OfficeCLI/Human Gold 基线仍是升级 COMPLETE 的外部门槛
- Regression evidence: root Ruff PASS；改动范围 Ruff format PASS；mypy 66 files PASS；root pytest
  `346 passed, 1 warning`；原工作区 independent template-extraction Eval `151 passed`
- Stop condition: 任何猜测必填值、源内容静默丢失、candidate 冒充 accepted、公开 CLI/Tool
  增长、第三 Skill 或第二 Agent loop
- No-touch scope: 当前 `prepare-template` r2、template extraction Eval 评分、三校 Human Gold
