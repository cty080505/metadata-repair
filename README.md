# Unity Global-Metadata.dat 启发式修复工具

一个用于修复受损的 Unity `global-metadata.dat` 文件的 Python 工具集。该工具通过启发式方法分析并尝试修复头部损坏的元数据文件，使反编译工具（如 Il2CppDumper）能够正常处理这些文件。

## 功能特性

- **自动检测损坏**: 分析文件头部的有效性
- **启发式修复**: 基于已知有效模式推断正确的头部值
- **多种修复策略**: 支持不同的修复算法和策略
- **备份保护**: 自动创建原始文件备份
- **详细报告**: 生成修复过程和结果的详细报告
- **命令行和库接口**: 既可作为命令行工具使用，也可作为库集成

## 安装

```bash
pip install -r requirements.txt
```

## 使用方法

### 命令行使用

```bash
# 基本用法
python main.py path/to/damaged/global-metadata.dat

# 指定输出文件
python main.py input.dat -o output.dat

# 使用特定修复策略
python main.py input.dat --strategy aggressive

# 生成详细报告
python main.py input.dat --report repair_report.json

# 不创建备份
python main.py input.dat --no-backup
```

### 作为库使用

```python
from metadata_fixer import MetadataFixer

# 创建修复器实例
fixer = MetadataFixer("damaged_file.dat")

# 执行修复
result = fixer.fix()

if result.success:
    print(f"修复成功！文件已保存到：{result.output_path}")
    print(f"使用的策略：{result.strategy_used}")
else:
    print(f"修复失败：{result.error_message}")
    print(f"建议的修复参数：{result.suggestions}")
```

## 项目结构

```
.
├── main.py                 # 命令行入口
├── metadata_fixer/
│   ├── __init__.py        # 包初始化
│   ├── core.py            # 核心修复逻辑
│   ├── analyzer.py        # 文件分析模块
│   ├── strategies.py      # 修复策略实现
│   └── utils.py           # 工具函数
├── tests/                 # 测试用例
├── examples/              # 示例文件
├── requirements.txt       # 依赖项
└── README.md             # 说明文档
```

## 支持的修复策略

1. **conservative**: 保守策略，仅修复明显错误的最小改动
2. **standard**: 标准策略，平衡修复成功率和安全性
3. **aggressive**: 激进策略，尝试更多可能性以提高成功率
4. **auto**: 自动选择（默认），根据损坏程度选择合适的策略

## 注意事项

⚠️ **重要提示**: 
- 始终保留原始文件的备份
- 此工具仅供学习和研究使用
- 请确保您有合法的权利修改目标文件
- 修复结果可能因文件损坏程度而异

## 技术原理

`global-metadata.dat` 是 Unity IL2CPP 后端使用的元数据文件，包含类型、方法、字段等信息。文件头部包含关键的魔数、版本信息和偏移量表。

本工具通过分析以下特征来修复损坏的头部：
- 魔数验证 (0x3AFB7A4C)
- 版本号合理性检查
- 偏移量一致性验证
- 大小关系约束检查
- 与已知有效模式的比对

## 许可证

MIT License - 详见 LICENSE 文件

## 贡献

欢迎提交 Issue 和 Pull Request！
