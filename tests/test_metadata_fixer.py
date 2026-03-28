"""
测试模块
包含单元测试和集成测试

运行方式:
    python -m pytest tests/test_metadata_fixer.py -v
    或
    cd /workspace && PYTHONPATH=/workspace python tests/test_metadata_fixer.py
"""

import unittest
import os
import sys
import tempfile
import shutil
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 导入被测试的模块
from metadata_fixer.utils import (
    validate_file, create_backup, METADATA_MAGIC,
    read_uint32, write_uint32, FileValidation
)
from metadata_fixer.analyzer import MetadataAnalyzer, DamageType
from metadata_fixer.strategies import (
    ConservativeStrategy, StandardStrategy, 
    AggressiveStrategy, AutoStrategy, get_strategy
)
from metadata_fixer.core import MetadataFixer, FixResult, quick_fix


def create_test_metadata_file(path: str, magic: int = METADATA_MAGIC, 
                               version: int = 21, corrupt: bool = False) -> str:
    """
    创建一个测试用的 metadata 文件
    
    Args:
        path: 文件路径
        magic: 魔数值
        version: 版本号
        corrupt: 是否创建损坏的文件
        
    Returns:
        文件路径
    """
    # 创建一个最小有效的头部（56 字节）
    header_size = 56
    data = bytearray(header_size + 1000)  # 额外添加一些数据
    
    # 写入魔数
    data[0:4] = magic.to_bytes(4, byteorder='little')
    
    # 写入版本号
    data[4:8] = version.to_bytes(4, byteorder='little')
    
    # 写入合理的偏移量
    if not corrupt:
        # 正常的偏移量序列
        offsets = [
            header_size,           # string_offset
            header_size + 100,     # events_offset
            header_size + 200,     # properties_offset
            header_size + 300,     # methods_offset
            header_size + 400,     # parameters_offset
            header_size + 500,     # fields_offset
        ]
        
        for i, offset in enumerate(offsets):
            pos = 8 + (i * 4)
            data[pos:pos+4] = offset.to_bytes(4, byteorder='little')
    else:
        # 损坏的偏移量（超出文件大小）
        data[8:12] = (999999).to_bytes(4, byteorder='little')
    
    # 写入文件
    with open(path, 'wb') as f:
        f.write(data)
    
    return path


class TestUtils(unittest.TestCase):
    """工具函数测试"""
    
    def setUp(self):
        """设置测试环境"""
        self.test_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        """清理测试环境"""
        shutil.rmtree(self.test_dir)
    
    def test_validate_valid_file(self):
        """测试验证有效文件"""
        file_path = os.path.join(self.test_dir, 'valid.dat')
        create_test_metadata_file(file_path)
        
        result = validate_file(file_path)
        
        self.assertTrue(result.is_valid)
        self.assertEqual(result.magic_number, METADATA_MAGIC)
        self.assertEqual(result.version, 21)
        self.assertIsNone(result.error_message)
    
    def test_validate_invalid_magic(self):
        """测试验证无效魔数"""
        file_path = os.path.join(self.test_dir, 'invalid_magic.dat')
        create_test_metadata_file(file_path, magic=0x12345678)
        
        result = validate_file(file_path)
        
        self.assertFalse(result.is_valid)
        self.assertEqual(result.magic_number, 0x12345678)
        self.assertIn("魔数无效", result.error_message)
    
    def test_validate_invalid_version(self):
        """测试验证无效版本号"""
        file_path = os.path.join(self.test_dir, 'invalid_version.dat')
        create_test_metadata_file(file_path, version=99)
        
        result = validate_file(file_path)
        
        self.assertFalse(result.is_valid)
        self.assertEqual(result.version, 99)
        self.assertIn("版本号不支持", result.error_message)
    
    def test_validate_nonexistent_file(self):
        """测试验证不存在的文件"""
        result = validate_file('/nonexistent/path/file.dat')
        
        self.assertFalse(result.is_valid)
        self.assertIn("不存在", result.error_message)
    
    def test_create_backup(self):
        """测试创建备份"""
        original_path = os.path.join(self.test_dir, 'original.dat')
        create_test_metadata_file(original_path)
        
        backup_path = create_backup(original_path)
        
        self.assertTrue(os.path.exists(backup_path))
        self.assertTrue(backup_path.endswith('.bak'))
        
        # 验证备份内容
        with open(original_path, 'rb') as f1, open(backup_path, 'rb') as f2:
            self.assertEqual(f1.read(), f2.read())
    
    def test_read_write_uint32(self):
        """测试 uint32 读写"""
        data = bytearray(4)
        value = 0x12345678
        
        write_uint32(data, 0, value)
        read_value = read_uint32(data, 0)
        
        self.assertEqual(value, read_value)


class TestAnalyzer(unittest.TestCase):
    """分析器测试"""
    
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        shutil.rmtree(self.test_dir)
    
    def test_analyze_valid_file(self):
        """测试分析有效文件"""
        file_path = os.path.join(self.test_dir, 'valid.dat')
        create_test_metadata_file(file_path)
        
        analyzer = MetadataAnalyzer(file_path)
        report = analyzer.analyze()
        
        self.assertTrue(report.is_valid)
        self.assertEqual(len(report.damage_reports), 0)
        self.assertEqual(report.header.magic, METADATA_MAGIC)
        self.assertEqual(report.header.version, 21)
    
    def test_analyze_corrupted_file(self):
        """测试分析损坏文件"""
        file_path = os.path.join(self.test_dir, 'corrupt.dat')
        create_test_metadata_file(file_path, magic=0x00000000, corrupt=True)
        
        analyzer = MetadataAnalyzer(file_path)
        report = analyzer.analyze()
        
        self.assertFalse(report.is_valid)
        self.assertGreater(len(report.damage_reports), 0)
        
        # 应该检测到魔数损坏
        damage_types = [d.damage_type for d in report.damage_reports]
        self.assertIn(DamageType.MAGIC_CORRUPTED, damage_types)


class TestStrategies(unittest.TestCase):
    """修复策略测试"""
    
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        shutil.rmtree(self.test_dir)
    
    def test_conservative_strategy(self):
        """测试保守策略"""
        file_path = os.path.join(self.test_dir, 'test.dat')
        create_test_metadata_file(file_path, magic=0x00000000)
        
        analyzer = MetadataAnalyzer(file_path)
        analysis = analyzer.analyze()
        
        strategy = ConservativeStrategy()
        
        with open(file_path, 'rb') as f:
            data = bytearray(f.read())
        
        result = strategy.repair(data, analysis)
        
        self.assertTrue(result.success)
        self.assertEqual(read_uint32(data, 0), METADATA_MAGIC)
    
    def test_standard_strategy(self):
        """测试标准策略"""
        file_path = os.path.join(self.test_dir, 'test.dat')
        create_test_metadata_file(file_path, magic=0xBADBAD00, version=99)
        
        analyzer = MetadataAnalyzer(file_path)
        analysis = analyzer.analyze()
        
        strategy = StandardStrategy()
        
        with open(file_path, 'rb') as f:
            data = bytearray(f.read())
        
        result = strategy.repair(data, analysis)
        
        self.assertTrue(result.success)
    
    def test_get_strategy(self):
        """测试获取策略"""
        strategies = ['conservative', 'standard', 'aggressive', 'auto']
        
        for name in strategies:
            strategy = get_strategy(name)
            self.assertIsNotNone(strategy)
            self.assertEqual(strategy.name, name)


class TestMetadataFixer(unittest.TestCase):
    """主修复器测试"""
    
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        shutil.rmtree(self.test_dir)
    
    def test_quick_fix(self):
        """测试快速修复"""
        input_path = os.path.join(self.test_dir, 'input.dat')
        output_path = os.path.join(self.test_dir, 'output.dat')
        
        create_test_metadata_file(input_path, magic=0x00000000)
        
        result = quick_fix(input_path, output_path, create_backup=False)
        
        self.assertTrue(result.success)
        self.assertEqual(result.output_path, output_path)
        self.assertTrue(os.path.exists(output_path))
    
    def test_fix_with_backup(self):
        """测试带备份的修复"""
        input_path = os.path.join(self.test_dir, 'input.dat')
        create_test_metadata_file(input_path, magic=0x00000000)
        
        fixer = MetadataFixer(input_path)
        result = fixer.fix(create_backup_flag=True)
        
        self.assertTrue(result.success)
        self.assertIsNotNone(result.backup_path)
        self.assertTrue(os.path.exists(result.backup_path))
    
    def test_fix_multiple_strategies(self):
        """测试多策略修复"""
        input_path = os.path.join(self.test_dir, 'input.dat')
        output_dir = os.path.join(self.test_dir, 'output')
        
        create_test_metadata_file(input_path, magic=0x00000000, version=99)
        
        fixer = MetadataFixer(input_path)
        results = fixer.fix_multiple_strategies(output_dir, create_backup_flag=False)
        
        self.assertGreater(len(results), 0)
        
        # 至少有一个策略应该成功
        success_count = sum(1 for r in results if r.success)
        self.assertGreater(success_count, 0)


class TestIntegration(unittest.TestCase):
    """集成测试"""
    
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        shutil.rmtree(self.test_dir)
    
    def test_full_workflow(self):
        """测试完整工作流程"""
        # 1. 创建损坏的文件
        input_path = os.path.join(self.test_dir, 'damaged.dat')
        create_test_metadata_file(input_path, magic=0xDEADBEEF, version=99, corrupt=True)
        
        # 2. 分析文件
        fixer = MetadataFixer(input_path)
        analysis = fixer.analyze()
        
        self.assertFalse(analysis.is_valid)
        self.assertGreater(len(analysis.damage_reports), 0)
        
        # 3. 执行修复
        output_path = os.path.join(self.test_dir, 'fixed.dat')
        result = fixer.fix(output_path=output_path, create_backup_flag=True)
        
        # 4. 验证结果
        self.assertTrue(result.success)
        self.assertTrue(os.path.exists(output_path))
        self.assertTrue(os.path.exists(result.backup_path))
        
        # 5. 验证修复后的文件
        validation = validate_file(output_path)
        self.assertTrue(validation.is_valid)


if __name__ == '__main__':
    unittest.main(verbosity=2)
