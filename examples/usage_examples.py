"""
示例脚本 - 演示如何使用 metadata_fixer 库

这个脚本展示了如何使用该库来修复损坏的 global-metadata.dat 文件
"""

import os
import sys

# 确保可以导入 metadata_fixer
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from metadata_fixer import MetadataFixer, quick_fix, list_strategies
from metadata_fixer.utils import validate_file


def example_basic_usage():
    """基本使用示例"""
    print("=" * 60)
    print("示例 1: 基本使用")
    print("=" * 60)
    
    # 假设有一个损坏的文件
    damaged_file = "examples/damaged_metadata.dat"
    
    if not os.path.exists(damaged_file):
        print(f"提示：示例文件 {damaged_file} 不存在")
        print("创建一个测试文件来演示...")
        
        # 创建测试文件
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.dat', delete=False) as f:
            data = bytearray(2000)
            data[0:4] = (0x00000000).to_bytes(4, 'little')  # 损坏的魔数
            data[4:8] = (99).to_bytes(4, 'little')  # 损坏的版本
            for i in range(6):
                offset = 56 + (i * 100)
                pos = 8 + (i * 4)
                data[pos:pos+4] = offset.to_bytes(4, 'little')
            f.write(data)
            damaged_file = f.name
    
    # 方法 1: 使用快速修复函数
    print("\n方法 1: 使用 quick_fix() 函数")
    output_file = damaged_file.replace('.dat', '.fixed.dat')
    result = quick_fix(damaged_file, output_file, create_backup=False)
    
    print(f"  输入：{damaged_file}")
    print(f"  输出：{result.output_path}")
    print(f"  成功：{result.success}")
    print(f"  策略：{result.strategy_used}")
    
    # 清理
    if os.path.exists(output_file):
        os.unlink(output_file)
    if damaged_file.startswith('/tmp'):
        os.unlink(damaged_file)


def example_analyze_file():
    """分析文件示例"""
    print("\n" + "=" * 60)
    print("示例 2: 分析文件")
    print("=" * 60)
    
    import tempfile
    
    # 创建测试文件
    with tempfile.NamedTemporaryFile(suffix='.dat', delete=False) as f:
        data = bytearray(2000)
        data[0:4] = (0xDEADBEEF).to_bytes(4, 'little')
        data[4:8] = (50).to_bytes(4, 'little')
        f.write(data)
        test_file = f.name
    
    # 创建分析器
    fixer = MetadataFixer(test_file)
    
    # 获取基本信息
    info = fixer.get_info()
    print("\n文件信息:")
    for key, value in info.items():
        print(f"  {key}: {value}")
    
    # 执行详细分析
    report = fixer.analyze()
    print(f"\n分析报告:")
    print(f"  文件有效：{report.is_valid}")
    print(f"  建议策略：{report.suggested_strategy}")
    print(f"  置信度：{report.confidence * 100:.1f}%")
    print(f"  检测到的问题：{len(report.damage_reports)}")
    
    for damage in report.damage_reports:
        print(f"    - [{damage.severity}] {damage.description}")
    
    # 清理
    os.unlink(test_file)


def example_multiple_strategies():
    """多策略修复示例"""
    print("\n" + "=" * 60)
    print("示例 3: 多策略修复")
    print("=" * 60)
    
    import tempfile
    import shutil
    
    # 创建测试文件
    with tempfile.NamedTemporaryFile(suffix='.dat', delete=False) as f:
        data = bytearray(5000)
        data[0:4] = (0xBADBAD00).to_bytes(4, 'little')
        data[4:8] = (99).to_bytes(4, 'little')
        f.write(data)
        test_file = f.name
    
    # 创建输出目录
    output_dir = tempfile.mkdtemp()
    
    try:
        # 尝试所有策略
        fixer = MetadataFixer(test_file)
        results = fixer.fix_multiple_strategies(output_dir, create_backup_flag=False)
        
        print("\n策略对比:")
        for result in results:
            status = "✓" if result.success else "✗"
            confidence = 0.0
            if result.repair_attempts:
                confidence = max(a.get('confidence', 0) for a in result.repair_attempts)
            print(f"  {status} {result.strategy_used:15} 置信度：{confidence*100:5.1f}%")
        
        # 找到最佳结果
        best = results[0]
        if best.success:
            print(f"\n推荐输出：{best.output_path}")
            
            # 验证修复后的文件
            validation = validate_file(best.output_path)
            print(f"验证结果：{'有效' if validation.is_valid else '无效'}")
    
    finally:
        # 清理
        shutil.rmtree(output_dir)
        os.unlink(test_file)


def example_list_strategies():
    """列出所有策略"""
    print("\n" + "=" * 60)
    print("示例 4: 可用策略")
    print("=" * 60)
    
    strategies = list_strategies()
    for i, strategy in enumerate(strategies, 1):
        print(f"\n{i}. {strategy['name']}")
        print(f"   {strategy['description']}")


def example_as_library():
    """作为库使用的完整示例"""
    print("\n" + "=" * 60)
    print("示例 5: 作为库集成到其他项目")
    print("=" * 60)
    
    code_example = '''
# 在你的项目中导入
from metadata_fixer import MetadataFixer, quick_fix

# 方式 1: 简单修复
result = quick_fix("damaged.dat", "fixed.dat")
if result.success:
    print("修复成功!")
else:
    print(f"修复失败：{result.error_message}")

# 方式 2: 使用更多选项
fixer = MetadataFixer("damaged.dat", strategy="standard")

# 先分析
analysis = fixer.analyze()
print(f"检测到 {len(analysis.damage_reports)} 个问题")

# 执行修复
result = fixer.fix(
    output_path="fixed.dat",
    create_backup_flag=True,  # 创建备份
    report_path="report.json"  # 保存报告
)

# 方式 3: 尝试多种策略
results = fixer.fix_multiple_strategies("./output_dir")
best_result = results[0]  # 已按成功率排序
'''
    print(code_example)


def main():
    """运行所有示例"""
    print("\n" + "=" * 60)
    print("  Metadata Fixer 使用示例")
    print("=" * 60 + "\n")
    
    example_basic_usage()
    example_analyze_file()
    example_multiple_strategies()
    example_list_strategies()
    example_as_library()
    
    print("\n" + "=" * 60)
    print("  所有示例运行完成!")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
