# DocFit Student Content Placement Debug Active Capsule

- Capsule status: PARTIAL DEBUG CANDIDATE PRODUCED
- Source plan: `docs/plans/docfit-student-content-placement-debug.md`
- Baseline commit: `0c3f292c2005722a8019c3bb32864829258f8da9`
- Branch/worktree: `codex/student-content-placement` / independent worktree
- User intent: 把真实学生内容提取与指定模板填写作为独立模块调试，不与当前模板提取 r2 联调
- Current slice: deterministic inventory、read-only Agent extraction、Placement、safe fill 与真实样本验收
- Fixed student hash: `fc39ac02efd152ddf609199615256393e3077b49629e1cca48e1f437b2e44a9b`
- Fixed template hash: `70b13aecf084816a5ff5abc879c00d26c63552c0c36623060b17cbae3d775f50`
- Template qualification: candidate / Human acceptance pending；本切片不得输出 COMPLETE
- Input evidence: student 360 dump paragraphs、1 table、6 drawings/media、4 math objects；
  template 31 content controls、5 sections、3 header/footer parts；两份 DOCX ZIP 检查通过
- Implementation evidence: 新增独立 `docfit.content` 模块和内部 app API；不增加 CLI、public Tool、
  Skill 或自定义 Agent runtime；15 个 synthetic tests 通过
- Real extraction: MiniMax + `convert-thesis` + `docx_inspect` structured output；368 个 source object
  均被记账，211 mapped、92 随父对象复制、65 unmapped；正文 166 个顶层对象，参考文献 36 个
- Real placement: 8 个文本槽和 2 个 block slot 写入；11 个 required 槽缺失；6 张图、1 个表、
  已选 1 个公式和 202 个顶层 block 经 dependency closure 进入候选
- Candidate evidence: `PARTIAL`，SHA-256
  `ad2d6985d4a758839f9b09b0dbb6e49f71930942c9e6031afa2ec919c1b1f332`；canonical
  LibreOffice 25.2.3.2 为 47 页，逐页检查完成
- Current blockers: template/Human Gold 未验收；11 required 缺失；目录未生成；65 source object
  和 3/4 source equations 未 placement；致谢/附录占位符可见；第 28 页稀疏；template 与 candidate
  均被固定 OfficeCLI 无诊断拒绝，新增回归状态为 UNKNOWN
- Next gate: 先由产品决定未映射 source 的处置策略和缺失字段输入方式，再处理目录、可选空槽清理、
  分页归一化与 template OfficeCLI/Human Gold 基线；不得把当前候选升级为 COMPLETE
- Regression evidence: root Ruff PASS；mypy 65 files PASS；root pytest `340 passed, 1 warning`；
  independent template-extraction Eval 在持有未跟踪人工候选目录的原工作区 `151 passed`
- Stop condition: 任何猜测必填值、源内容静默丢失、candidate 冒充 accepted、公开 CLI/Tool
  增长、第三 Skill 或第二 Agent loop
- No-touch scope: 当前 `prepare-template` r2、template extraction Eval 评分、三校 Human Gold
