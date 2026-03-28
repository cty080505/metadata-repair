#!/usr/bin/env python3
"""
Unity global-metadata.dat 启发式修复工具 - 命令行入口

使用方法:
    python main.py <input_file> [选项]

示例:
    python main.py global-metadata.dat
    python main.py damaged.dat -o fixed.dat --strategy aggressive
    python main.py file.dat --report report.json --all-strategies
"""

import sys
import os
import argparse
import json
from typing import Optional

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from metadata_fixer import (
    MetadataFixer, FixResult,
    list_strategies, __version__
)
from metadata_fixer.utils import validate_file, METADATA_MAGIC


def print_banner():
    """打印程序横幅"""
    print("=" * 60)
    print("  Unity Global-Metadata.dat 启发式修复工具")
    print(f"  Version: {__version__}")
    print("=" * 60)
    print()


def print_file_info(file_path: str):
    """打印文件基本信息"""
    validation = validate_file(file_path)
    
    print(f"文件：{file_path}")
    print(f"大小：{validation.file_size:,} 字节")
    
    if validation.magic_number is not None:
        magic_hex = f"0x{validation.magic_number:08X}"
        expected_hex = f"0x{METADATA_MAGIC:08X}"
        status = "✓" if validation.magic_number == METADATA_MAGIC else "✗"
        print(f"魔数：{status} {magic_hex} (期望：{expected_hex})")
    
    if validation.version is not None:
        status = "✓" if 16 <= validation.version <= 27 else "✗"
        print(f"版本：{status} {validation.version}")
    
    print(f"状态：{'有效' if validation.is_valid else '无效/损坏'}")
    
    if validation.error_message:
        print(f"错误：{validation.error_message}")
    
    print()


def print_analysis_report(report: dict, indent: int = 0):
    """打印分析报告"""
    prefix = "  " * indent
    
    if report.get('damage_reports'):
        print(f"{prefix}检测到的损坏:")
        for i, damage in enumerate(report['damage_reports'], 1):
            severity_icon = {
                'critical': '🔴',
                'high': '🟠',
                'medium': '🟡',
                'low': '🟢'
            }.get(damage['severity'], '⚪')
            
            print(f"{prefix}  {i}. {severity_icon} [{damage['severity'].upper()}]")
            print(f"{prefix}     类型：{damage['type']}")
            print(f"{prefix}     描述：{damage['description']}")
            if damage.get('offset') >= 0:
                print(f"{prefix}     偏移量：{damage['offset']}")
            if damage.get('actual') is not None:
                actual_str = f"0x{damage['actual']:08X}" if isinstance(damage['actual'], int) else str(damage['actual'])
                print(f"{prefix}     实际值：{actual_str}")
            if damage.get('expected') is not None:
                expected_str = f"0x{damage['expected']:08X}" if isinstance(damage['expected'], int) else str(damage['expected'])
                print(f"{prefix}     期望值：{expected_str}")
            print(f"{prefix}     可修复：{'是' if damage['repairable'] else '否'}")
            print()
    
    if report.get('suggested_strategy'):
        print(f"{prefix}建议策略：{report['suggested_strategy']}")
    
    if report.get('confidence') is not None:
        confidence_pct = report['confidence'] * 100
        print(f"{prefix}置信度：{confidence_pct:.1f}%")
    
    print()


def print_repair_result(result: FixResult, verbose: bool = False):
    """打印修复结果"""
    print("\n" + "=" * 60)
    print("修复结果")
    print("=" * 60)
    
    if result.success:
        print("✅ 修复成功!")
        print(f"   输出文件：{result.output_path}")
        if result.backup_path:
            print(f"   备份文件：{result.backup_path}")
        print(f"   使用策略：{result.strategy_used}")
        
        if result.repair_attempts and verbose:
            print("\n   修改详情:")
            for attempt in result.repair_attempts:
                if attempt.get('modifications'):
                    for mod in attempt['modifications']:
                        offset = mod.get('offset', '?')
                        field = mod.get('field', '?')
                        old_val = mod.get('old_value')
                        new_val = mod.get('new_value')
                        
                        if old_val is not None and new_val is not None:
                            if isinstance(old_val, int) and isinstance(new_val, int):
                                old_str = f"0x{old_val:08X}"
                                new_str = f"0x{new_val:08X}"
                            else:
                                old_str = str(old_val)
                                new_str = str(new_val)
                            
                            print(f"     - 偏移量 {offset} ({field}): {old_str} → {new_str}")
    else:
        print("❌ 修复失败")
        print(f"   错误：{result.error_message}")
        if result.backup_path:
            print(f"   备份文件：{result.backup_path}")
    
    print()


def cmd_analyze(args):
    """分析命令"""
    print_banner()
    print("【文件分析】\n")
    
    print_file_info(args.input)
    
    # 执行详细分析
    fixer = MetadataFixer(args.input)
    report = fixer.analyze()
    
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    else:
        print_analysis_report(report.to_dict())


def cmd_fix(args):
    """修复命令"""
    print_banner()
    print("【文件修复】\n")
    
    # 显示输入文件信息
    print_file_info(args.input)
    
    # 创建修复器
    fixer = MetadataFixer(args.input, strategy=args.strategy)
    
    # 如果不是自动策略，先进行分析
    if args.strategy != 'auto':
        print(f"使用策略：{args.strategy}\n")
    
    # 执行修复
    result = fixer.fix(
        output_path=args.output,
        create_backup_flag=not args.no_backup,
        report_path=args.report
    )
    
    # 打印结果
    print_repair_result(result, verbose=args.verbose)
    
    # 如果指定了报告路径
    if args.report and result.success:
        print(f"详细报告已保存到：{args.report}\n")
    
    return 0 if result.success else 1


def cmd_fix_all(args):
    """尝试所有策略修复"""
    print_banner()
    print("【多策略修复】\n")
    
    print_file_info(args.input)
    
    # 创建输出目录
    output_dir = args.output_dir or os.path.dirname(args.input)
    if not output_dir:
        output_dir = "."
    
    print(f"输出目录：{output_dir}\n")
    
    # 执行多策略修复
    fixer = MetadataFixer(args.input, strategy='auto')
    results = fixer.fix_multiple_strategies(
        output_dir=output_dir,
        create_backup_flag=not args.no_backup
    )
    
    # 打印汇总
    print("\n" + "=" * 60)
    print("策略对比")
    print("=" * 60)
    
    success_count = sum(1 for r in results if r.success)
    
    for result in results:
        status = "✅" if result.success else "❌"
        confidence = 0.0
        if result.repair_attempts:
            confidence = max(a.get('confidence', 0) for a in result.repair_attempts)
        
        print(f"{status} {result.strategy_used:15} 置信度：{confidence*100:5.1f}%")
    
    print(f"\n总计：{success_count}/{len(results)} 策略成功")
    
    if success_count > 0:
        best_result = results[0]  # 已经排序，第一个是最好的
        print(f"\n推荐输出：{best_result.output_path}")
    
    print()
    
    return 0 if success_count > 0 else 1


def cmd_list_strategies(args):
    """列出所有策略"""
    print_banner()
    print("【可用策略】\n")
    
    strategies = list_strategies()
    
    for i, strategy in enumerate(strategies, 1):
        print(f"{i}. {strategy['name']}")
        print(f"   {strategy['description']}")
        print()


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="Unity global-metadata.dat 启发式修复工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s analyze damaged.dat              # 分析文件
  %(prog)s fix damaged.dat                  # 修复文件（自动策略）
  %(prog)s fix damaged.dat -o fixed.dat     # 修复并指定输出
  %(prog)s fix damaged.dat -s aggressive    # 使用激进策略
  %(prog)s fix-all damaged.dat              # 尝试所有策略
        """
    )
    
    parser.add_argument('-v', '--version', action='version', 
                       version=f'%(prog)s {__version__}')
    parser.add_argument('--verbose', '-V', action='store_true',
                       help='显示详细信息')
    
    subparsers = parser.add_subparsers(dest='command', help='命令')
    
    # analyze 命令
    analyze_parser = subparsers.add_parser('analyze', help='分析文件')
    analyze_parser.add_argument('input', help='输入文件路径')
    analyze_parser.add_argument('--json', '-j', action='store_true',
                               help='以 JSON 格式输出')
    analyze_parser.set_defaults(func=cmd_analyze)
    
    # fix 命令
    fix_parser = subparsers.add_parser('fix', help='修复文件')
    fix_parser.add_argument('input', help='输入文件路径')
    fix_parser.add_argument('--output', '-o', help='输出文件路径')
    fix_parser.add_argument('--strategy', '-s', default='auto',
                           choices=['auto', 'conservative', 'standard', 'aggressive'],
                           help='修复策略（默认：auto）')
    fix_parser.add_argument('--no-backup', action='store_true',
                           help='不创建备份')
    fix_parser.add_argument('--report', '-r', help='保存报告到指定文件')
    fix_parser.set_defaults(func=cmd_fix)
    
    # fix-all 命令
    fix_all_parser = subparsers.add_parser('fix-all', help='尝试所有策略')
    fix_all_parser.add_argument('input', help='输入文件路径')
    fix_all_parser.add_argument('--output-dir', '-d', help='输出目录')
    fix_all_parser.add_argument('--no-backup', action='store_true',
                               help='不创建备份')
    fix_all_parser.set_defaults(func=cmd_fix_all)
    
    # list 命令
    list_parser = subparsers.add_parser('list', help='列出可用策略')
    list_parser.set_defaults(func=cmd_list_strategies)
    
    # 兼容旧用法：直接提供文件路径时默认执行 fix
    parser.add_argument('input', nargs='?', help='输入文件路径（快捷方式）')
    
    args = parser.parse_args()
    
    # 如果没有指定命令但有 input，默认为 fix
    if not args.command and args.input:
        args.strategy = 'auto'
        args.output = None
        args.no_backup = False
        args.report = None
        args.func = cmd_fix
    
    # 如果没有指定任何参数，显示帮助
    if not hasattr(args, 'func'):
        parser.print_help()
        return 1
    
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())
