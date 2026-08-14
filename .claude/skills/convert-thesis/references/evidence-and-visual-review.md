# 视觉证据与完成判定

视觉证据回答“当前 DOCX 在固定 LibreOffice 环境中呈现得怎样”，结构验证回答“文档
是否满足可程序检查的合同”。两者都需要，不能互相替代。所有 V2 视觉证据固定标记为
`approximate`，不声称与 Microsoft Word 像素一致。

## 建立当前快照

对需要观察的当前 DOCX 调用一次 `mcp__docfit__docx_render`：

```json
{"input_docx":"work/current.docx","overview":true}
```

不要传 intent、输出目录、provider、backend、parent ref 或对象 focus。Tool 返回
`render:v2:`、document hash、页数、renderer/container/font identity 和默认联系表。
相同文档与环境直接复用 cache；编辑后 document hash 变化，必须取得新 render。

## 按需选择视图

- `contact_sheet`：全局扫描指定页段；
- `pages`：查看完整页面，最终候选必须分批覆盖每一页；
- `regions`：用当前 `object_ref`、文字 selector 或已有图片 `image_bbox` 查看高清细节；
- `compare`：比较两个同 renderer/font 环境的 LibreOffice render。

先看联系表，再请求异常页和必要局部图。整页不足以辨认小字、域结果、图题编号、
下划线或边界时使用 `quality: detail` region。单次结果有图片数量和字节预算；有 cursor
时继续分批，不能把首批图片误认为全部页面。

`object_ref` 由 Tool 通过 OfficeCLI 语义锚点重新定位到 LibreOffice PDF。mapping 不唯一
或不可用时，Tool 返回候选完整页和 warning；不要把候选页当成精确 bbox，也不要使用
OfficeCLI 页码/HTML 坐标或图片 bbox 直接定位 OOXML 编辑对象。

## 视觉检查项目

- 内容是否截断、遮挡、重叠或溢出；
- 标题、段落、列表、表格和图片的层级与对齐；
- 页边距、页眉页脚、页码和节边界是否连续；
- 模板槽位是否填入正确事实，操作说明是否误留；
- 目录条目、编号和正文起始页是否一致；
- 是否出现异常空白页、孤行、寡行或跨页断裂。

可见的应用错误、损坏的域或交叉引用结果、未清理占位符和必需内容截断都属于阻断性发现。
裁剪图不能替代完整页面判断，因为它看不到跨区域关系。

## 完成判定

以下任一情况存在时，不得声称视觉完成：

- 当前最终 DOCX 没有绑定相同 hash 的 V2 render；
- renderer/container/font identity 缺失或与所审查证据不一致；
- 最终页面没有完整覆盖，或 evidence refs 无效；
- 文档在最终 render 后又被修改；
- 存在遮挡、截断、错页、异常空白页或明显层级错误；
- 当前固定 renderer 失败，无法观察关键页面。

非阻断性的近似差异也要在最终回复中说明，不能用验证成功掩盖视觉差异。
