# Harness 修复真实回放

`replay.py` 只读取给定真实任务的输入、初始清单、分区 proof、候选账本和最终 review。
源绑定、分区及账本必须满足当前合同；脚本不会转换旧 proof，不会修改原任务，也不读取 Gold。

```sh
PYTHONPATH=. uv run python tests/manual-diagnostics/template-harness-repair/replay.py \
  --body-task temp/span-skill-e2e-20260922-87710163/body-task \
  --table-task temp/full-flow-id-20260922/pku-cover-live \
  --output temp/harness-repair-20260923/phase1-replay
```

证据区分：

- `real_replay`：原正文候选仍报告范围错误；原 PKU 表格判断归执行能力阻塞，直接物化不写候选；原任务 hash 不变。
- `injected_revision_contract_check`：主动改变一条已有候选用途，证明候选可以重判且文字错误仍被拒绝。
  新用途由测试注入，不是新的 Agent 输出，不证明学校语义正确。
- 本脚本不运行 Agent，不证明 E2E 或产品验收。原始输入是任务内真实 DOCX，不使用 synthetic 来冒充 real replay。

长期 CI 不能依赖这里的临时 task 路径；若提升为 CI，需将输入及原始判断作为明确来源的 fixture 保存，
不能删掉绑定校验以适配旧资产。

阶段 2 的账本回放将原始真实候选逐批写入新的诊断账本，核对恢复结果与原候选完全一致。
每次运行需要新的 `--output` 目录。新账本全部标为 `evidence_mode=replay`，当前 prompt
仅为回放构造，未发送给 Agent；这不是缺失的历史消息，也不是新的 E2E。runtime 必须拒绝恢复该账本。


`shape_cleanup_replay.py --task <真实任务> --source-entry <原始判断中的 ID> --output <新诊断目录>`
读取原始完整候选，验证 source inventory、分区、词表、判断摘要及 Word 映射，然后仅回放指定
正文 VML shape 的已接受 cleanup 操作。它保留完整候选的其他阻塞，不调用 Agent，不走完整物化或发布。
输出 `diagnostic-shape-deletion.docx` 与 `replay.json`；断言只有目标 XML 节点被删，其余 XML、
包内其他部件和原 task 均不变。这是 `real replay` 的 Tool 执行切片，不是最终模板或产品验收。


`body_interface_replay.py --task <真实任务> --output <新诊断目录>` 使用完整原始清单和未修改的原判断，
选择删除说明后可连续合并的正文接口，仅回放这些接口的 Tool 执行。它核对每个贡献/删除范围、
一个接口只生成一个控件、其他段落及段落属性保持不变、原 task 与其他包部件不变。
完整候选的其他 blocker 保留；诊断 DOCX 不是完整物化、Agent E2E 或可发布产物。
