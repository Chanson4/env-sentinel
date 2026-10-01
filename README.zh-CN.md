# Env Sentinel

**检查环境配置是否缺项、重复或仍是占位值，报告不输出配置值。**

[English](README.md) · [下载](https://github.com/Chanson4/env-sentinel/releases/latest)

![预览](docs/preview.svg)

适用于上线前检查、环境迁移和 CI：用 `.env.example` 定义必须具备的键，检查真实配置是否满足约定。零运行依赖，Python 3.10 及以上可直接使用。

```sh
git clone https://github.com/Chanson4/env-sentinel.git
cd env-sentinel
python env_sentinel.py diff examples/contract.env examples/drift.env
python env_sentinel.py check .env --format json
python env_sentinel.py diff .env.example .env.production --allow-extra
python env_sentinel.py template .env > .env.example
```

也可在克隆后运行 `python -m pip install .`，再使用 `env-sentinel` 命令。目前未发布到 PyPI。

- `check`：检查语法、重复键、空值、常见占位值、未定义引用和循环引用。
- `diff`：检查缺少的键和多出的键，并检查目标配置的质量。参考文件中的值不参与比较。
- `template`：导出按名称排序的键，所有值置空；原文件语法错误或有重复键时拒绝生成。
- 退出码：`0` 通过，`1` 发现问题，`2` 输入或用法错误。

支持 UTF-8/BOM、CRLF、`export`、引号、多行值和注释。引用只能来自当前文件，不读取进程环境，不执行 shell，不解码转义，不支持嵌套变量表达式。默认值按字面文本处理。所有目标空值均会报告；占位值检测为启发式规则，不能验证凭据是否有效。

报告仅包含合法键名、问题类型、引用键名和行号，不包含配置值或原始错误行。键名也可能暴露内部信息，公开模板前请检查。本工具不是密钥扫描器。

```sh
python -m unittest discover -s tests -v
```

详见 [完整说明](README.md) 与 [贡献指南](CONTRIBUTING.md)。欢迎用虚构配置提交问题或改进建议。
