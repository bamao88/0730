# 完成与视觉复核

完成是主 Agent 的证据结论，不是应用状态机走到最后一个 region。

## 修改后局部复核

每次重要 edit 后：

- 重新 inspect 新 snapshot，确认目标效果存在且 ref/field/tag 正确；
- 查看受影响页面或区域，确认固定标签、容器、边框、样式、分页和相邻职责仍在；
- 检查说明/样例已消失而真实填写位置没有一起丢失；
- 对分节、字段、表格、图片、书签、题注等风险查看 Tool 的机械回执与视觉结果；
- 回到全局 inventory 检查重复接口、孤立标题和跨区依赖。

局部图证明当前修改，不能代替最终全页覆盖。

## 最终全页检查

1. 对精确最终候选调用 `docx_render`，记录 document hash、render ref 和 page count。
2. 实际打开每一页原生 PNG；可以按你选择的批次查看，但最终页码集合必须完整。
3. 检查裁切、重叠、缺字/错字形、表格断裂或越界、图片/题注错位、明显间距漂移、页眉页脚/页码
   错位和内容控件布局损坏。
4. `【字段名】` 是合法填写界面，不是残留；空白页本身不能证明语义错误，但异常分页关系需要回到
   结构证据判断。
5. 发现 blocking 缺陷时定位并修改。任何修改都会产生新 hash，使旧 render 和全部页结论失效；
   对新版本重新渲染并从全页覆盖开始。

不能因“渲染成功”、文本可提取、Office 校验通过、缩略图看起来正常或其他页面正常而跳过目视判断。

## 独立验证

最后调用 `docx_validate`，把结构化视觉证据直接绑定到最终 document hash/render：

- `reviewed_pages` 等于最终 `1..page_count`；
- findings 中没有 blocking 项；
- source hash 未变、DOCX package 可重开、OfficeCLI 校验通过；
- Registry-bound 内容控件可被最终发布重新读取；
- validation、Word、最终 render 和后续 Fill Contract 使用同一 hash。

## 宣布完成

只有全局责任闭合、最终视觉覆盖完整、blocking 问题为零且独立验证通过，才返回 `complete`。返回精确
候选路径、candidate render ref、完整 reviewed pages、findings 和总结。仍有会改变最终文档的证据
缺口时返回 `needs_input`；一般 warning 应明确披露，但不要把可继续解决的问题交还用户。
