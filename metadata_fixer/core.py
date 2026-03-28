"""
核心修复模块
提供主要的修复功能和接口
"""

import os
import json
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict
from datetime import datetime

from .utils import create_backup, validate_file, calculate_file_hash
from .analyzer import MetadataAnalyzer, AnalysisReport
from .strategies import (
    RepairStrategy, RepairAttempt, RepairResult,
    get_strategy, list_strategies, AutoStrategy
)


@dataclass
class FixResult:
    """修复操作的结果"""
    success: bool
    input_path: str
    output_path: Optional[str]
    backup_path: Optional[str]
    strategy_used: str
    analysis_report: Optional[Dict[str, Any]] = None
    repair_attempts: List[Dict[str, Any]] = None
    error_message: Optional[str] = None
    timestamp: str = ""
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)
    
    def save_report(self, path: str) -> None:
        """将报告保存为 JSON 文件"""
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)


class MetadataFixer:
    """
    Unity global-metadata.dat 修复器
    
    提供完整的修复流程：分析 -> 选择策略 -> 执行修复 -> 验证
    """
    
    def __init__(self, input_path: str, strategy: str = "auto"):
        """
        初始化修复器
        
        Args:
            input_path: 输入文件路径
            strategy: 修复策略名称 (auto, conservative, standard, aggressive)
        """
        self.input_path = input_path
        self.strategy_name = strategy
        self.analyzer: Optional[MetadataAnalyzer] = None
        self.analysis_report: Optional[AnalysisReport] = None
        self._validate_input()
    
    def _validate_input(self) -> None:
        """验证输入文件"""
        if not os.path.exists(self.input_path):
            raise FileNotFoundError(f"输入文件不存在：{self.input_path}")
        
        if os.path.getsize(self.input_path) < 56:
            raise ValueError("文件太小，无法包含有效的 metadata 头部")
    
    def analyze(self) -> AnalysisReport:
        """
        分析文件并生成报告
        
        Returns:
            AnalysisReport 对象
        """
        self.analyzer = MetadataAnalyzer(self.input_path)
        self.analysis_report = self.analyzer.analyze()
        return self.analysis_report
    
    def fix(self, output_path: Optional[str] = None, 
            create_backup_flag: bool = True,
            report_path: Optional[str] = None) -> FixResult:
        """
        执行修复操作
        
        Args:
            output_path: 输出文件路径，默认为输入文件路径.fix
            create_backup_flag: 是否创建备份
            report_path: 可选的报告保存路径
            
        Returns:
            FixResult 对象
        """
        # 设置默认输出路径
        if output_path is None:
            base, ext = os.path.splitext(self.input_path)
            output_path = f"{base}.fixed{ext}"
        
        # 确保输出目录存在
        output_dir = os.path.dirname(os.path.abspath(output_path))
        os.makedirs(output_dir, exist_ok=True)
        
        backup_path = None
        
        try:
            # 创建备份
            if create_backup_flag:
                backup_path = create_backup(self.input_path)
            
            # 分析文件（如果尚未分析）
            if self.analysis_report is None:
                self.analyze()
            
            # 读取文件数据
            with open(self.input_path, 'rb') as f:
                data = bytearray(f.read())
            
            # 获取策略并执行修复
            strategy = get_strategy(self.strategy_name)
            repair_attempt = strategy.repair(data, self.analysis_report)
            
            # 检查修复结果
            if not repair_attempt.success:
                return FixResult(
                    success=False,
                    input_path=self.input_path,
                    output_path=None,
                    backup_path=backup_path,
                    strategy_used=self.strategy_name,
                    analysis_report=self.analysis_report.to_dict() if self.analysis_report else None,
                    repair_attempts=[asdict(repair_attempt)],
                    error_message=repair_attempt.error_message or "修复失败"
                )
            
            # 写入修复后的文件
            with open(output_path, 'wb') as f:
                f.write(data)
            
            # 准备结果
            repair_attempts = [asdict(repair_attempt)]
            
            result = FixResult(
                success=True,
                input_path=self.input_path,
                output_path=output_path,
                backup_path=backup_path,
                strategy_used=self.strategy_name,
                analysis_report=self.analysis_report.to_dict() if self.analysis_report else None,
                repair_attempts=repair_attempts
            )
            
            # 保存报告（如果指定了路径）
            if report_path:
                result.save_report(report_path)
            
            return result
            
        except Exception as e:
            return FixResult(
                success=False,
                input_path=self.input_path,
                output_path=None,
                backup_path=backup_path,
                strategy_used=self.strategy_name,
                error_message=str(e)
            )
    
    def fix_multiple_strategies(self, output_dir: str,
                                strategies: Optional[List[str]] = None,
                                create_backup_flag: bool = True) -> List[FixResult]:
        """
        尝试多种策略进行修复
        
        Args:
            output_dir: 输出目录
            strategies: 要尝试的策略列表，默认为所有策略
            create_backup_flag: 是否创建备份
            
        Returns:
            FixResult 列表，按成功率排序
        """
        if strategies is None:
            strategies = ['conservative', 'standard', 'aggressive']
        
        results = []
        os.makedirs(output_dir, exist_ok=True)
        
        for strategy_name in strategies:
            try:
                # 为每个策略生成输出文件名
                base = os.path.basename(self.input_path)
                name, ext = os.path.splitext(base)
                output_path = os.path.join(output_dir, f"{name}.{strategy_name}{ext}")
                
                # 创建新的修复器实例（重置分析状态）
                fixer = MetadataFixer(self.input_path, strategy=strategy_name)
                result = fixer.fix(output_path=output_path, 
                                  create_backup_flag=create_backup_flag)
                results.append(result)
                
            except Exception as e:
                results.append(FixResult(
                    success=False,
                    input_path=self.input_path,
                    output_path=None,
                    backup_path=None,
                    strategy_used=strategy_name,
                    error_message=str(e)
                ))
        
        # 按成功率和置信度排序
        results.sort(key=lambda r: (
            r.success,
            max([a.get('confidence', 0) for a in (r.repair_attempts or [])], default=0)
        ), reverse=True)
        
        return results
    
    def get_info(self) -> Dict[str, Any]:
        """
        获取文件基本信息
        
        Returns:
            包含文件信息的字典
        """
        validation = validate_file(self.input_path)
        
        info = {
            'file_path': self.input_path,
            'file_size': os.path.getsize(self.input_path),
            'is_valid': validation.is_valid,
        }
        
        if validation.magic_number is not None:
            info['magic_number'] = f"0x{validation.magic_number:08X}"
        
        if validation.version is not None:
            info['version'] = validation.version
        
        if validation.error_message:
            info['error'] = validation.error_message
        
        return info


def quick_fix(input_path: str, output_path: Optional[str] = None,
              strategy: str = "auto", create_backup: bool = True) -> FixResult:
    """
    快速修复函数的便捷接口
    
    Args:
        input_path: 输入文件路径
        output_path: 输出文件路径（可选）
        strategy: 修复策略
        create_backup: 是否创建备份
        
    Returns:
        FixResult 对象
    """
    fixer = MetadataFixer(input_path, strategy=strategy)
    return fixer.fix(output_path=output_path, create_backup_flag=create_backup)
