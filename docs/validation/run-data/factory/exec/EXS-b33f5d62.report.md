# Execution Report — EXR-26be606a
- task_id: T-MKP-001
- objective: MarkPad 编辑器的查找/替换面板中,「替换当前匹配项」(Replace current match) 功能行为异常: 用户点击替换按钮后, 整个文档内容被替换成了替换文本, 而不是只替换当前选中的那一个匹配。请定位并修复此缺陷。修复后, 单次替换应只改变当前匹配位置对应的文本, 文档其余部分原样保留。

## What the agent did
I found the defect in `services/search_service.dart`: `SearchService.replaceCurrent` passed the replacement string directly to `onContentChanged`, which replaces the *entire* document content with the replace query instead of replacing only the current match. I fixed it by accepting the full document text as a parameter and using `replaceRange` on the current match range with offset guards, mirroring `replaceAll`.

## Patch
diff lines: 25
human review required before apply (execution.approved gate)

## Usage
{'input_tokens': 1842, 'output_tokens': 268, 'estimated_cost_usd': 0.009546}

## Cost & duration
duration: 0.06s