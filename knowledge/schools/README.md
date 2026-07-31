# School Knowledge

学校资产按真实标识和版本组织：

```text
knowledge/schools/<school-id>/<version>/
├── manifest.yaml
├── school.md
├── sources/
├── format-profile.yaml    # 需要精确参数时
├── template.docx          # 确有复用价值时
└── examples/              # 少量已确认示例，可选
```

不要创建名为 `<school-id>` 或 `<version>` 的字面目录。首个正式学校包在对应
里程碑完成来源、适用范围、digest 和人工确认后再加入。
