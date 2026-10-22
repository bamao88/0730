# 全流程对象身份专项诊断

只验证原始对象身份和范围，不进行学校语义或版式产品验收。正常自动测试在
`tests/contract/test_full_flow_source_identity.py`；本目录是需显式运行的真实输入诊断。

从仓库根运行，使用项目锁定的 OfficeCLI 1.0.143。2026-09-22 证据根固定为
`temp/full-flow-id-20260922`，学校原始 DOCX 位于
`temp/manual-gold-preparation/gold/00-inputs/schools`。只读原始输入，不读取 Gold 判断。

```sh
export PATH="$PWD/temp/id-closure-20260911/bin:$PATH"
uv run python tests/manual-diagnostics/template-full-flow-identity/verify_initial.py
uv run python tests/manual-diagnostics/template-full-flow-identity/verify_unit_projection.py
uv run python tests/manual-diagnostics/template-full-flow-identity/verify_word_mapping.py
uv run python tests/manual-diagnostics/template-full-flow-identity/verify_identity.py \
  temp/full-flow-id-20260922/<fresh-agent-task> \
  --output temp/full-flow-id-20260922/<fresh-agent-task>-identity.json
```

- `verify_initial.py`：新建三校准备任务，比较每页 3/17/200 项读取的完整 ID 顺序和原始输入。
  输出目录已存在时准备入口可能拒绝；需要新证据时先改脚本的实验根，不覆盖旧证据。
- `verify_unit_projection.py`：在一个原对象内部构造两个相接区间，核对仍为原 ID。
  边界由测试编写，属于真实输入上的机械探针，不是 Agent 语义 replay。
- `verify_word_mapping.py`：从初始清单逐一解析 Word 片段，检查正式包部件映射和原文。
  不运行 Agent，不修改 Word，不构成写入成功。
- `verify_identity.py`：要求新 Agent 的 V2 分区、完整判断、实际发布 Word 和 Fill Contract。
  重新解析初始绑定，验证发布来源，真实判断重新物化，与发布 Word 的所有 XML 部件比较；
  检查未选中段落的 XML 和未选中包部件字节；按内容控件透明的 XML 结构路径核对
  填写段落中的保留原文与槽顺序，不依赖可选的 Word paraId。拒绝旧 proof 与改 offsets 后重算摘要的 proof。
  结构路径无法建立完整对应时诊断失败，不能靠全文文字搜索通过。
  若输出与原始文件字节相同，明确记录 `source_noop_preservation`，不宣称有实际写入。

2026-09-22 收口补证：

```sh
uv run python tests/manual-diagnostics/template-full-flow-identity/audit_failures.py \
  --output temp/full-flow-id-20260922/identity-closure/failure-audit-new.json
uv run python tests/manual-diagnostics/template-full-flow-identity/verify_split_write.py \
  --output temp/full-flow-id-20260922/identity-closure/split-write-new
```

- `audit_failures.py`：复核明确列出的 5 次 fresh 失败和 2 条历史记录，校验实际达到的初始绑定、
  分区、候选原文、最终范围与源 Word 映射。候选范围错误被拒与已接受链偷换对象分开；未到阶段
  保持未知。输出路径必须未存在，不修改原运行证据；不是成功写入或新 E2E。
- `verify_split_write.py`：复用 NJAU 原始清单与原 Agent 判断，在已有 part 边界构造两个分区，
  经正式投影和 Harness review 后重复实际写入。同一 ID 两侧填写范围与原位置、全部输出部件、
  未选中段落和原证据 hash 均检查。属于真实输入上的机械分区与实际 DOCX 写入补证；
  **不是 Agent 自主分区 E2E，不是原分区 real replay**。输出目录必须未存在。
- `verify_identity.py` 补核 `body.table` 结构槽仍包住原表格，保留表格骨架与未选中子段落；
  非槽段落的精确片段清理也独立核验。目前仅支持可保持结构对应的这类产物检查，
  对其他结构类别明确失败，不以跳过检查冒充通过。
- `closure-evidence-20260922.json`：已提交的精简收口证据与原报告路径/摘要，明确各自验证层级。
  原始完整证据留在 `temp/full-flow-id-20260922/identity-closure/`。

`collect_runs.py` 汇总实验根内的新任务 trace；运行中、失败及无发布文件的状态分别保留。

Word 核验直接重读实际 DOCX 的 OOXML；不代表 Microsoft Word UI 或视觉版式验收。
任何断言失败都须保留失败，不能改 Agent 判断、替换定位或拼接旧阶段证据让诊断通过。
