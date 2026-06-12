# 工具运行时

运行时清单位于 `assets/runtime-manifest.json`。

- 优先使用系统 Java 17+。
- 系统 Java 不可用时，按平台下载固定版本便携运行时。
- CodeGraph 使用独立平台包，包内包含 Node.js。
- 下载文件必须校验摘要。
- 默认缓存目录为 `~/.code-change-check/tools/`。
- `--offline` 禁止下载，缺少缓存时明确报告不可用。

用户无需安装 Maven、Gradle、Node.js、npm 或全局 CodeGraph。
