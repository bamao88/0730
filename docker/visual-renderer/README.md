# DocFit 视觉渲染器

该镜像是 DocFit 当前唯一页面渲染器，包含锁定的 LibreOffice 25.2.3.2、中国语言环境、
字体别名和 Poppler 工具。

构建命令：

```bash
docker build -t docfit-libreoffice-visual:25.2.3.2 docker/visual-renderer
```

应用每次转换都以无网络、只读根文件系统、无 Linux capability、`no-new-privileges`、
隔离临时 HOME/profile、只读 DOCX 挂载和独立可写输出挂载启动。构建时会检查
`packages.lock`；Debian 包集合变化时必须通过仓库提交显式更新。
