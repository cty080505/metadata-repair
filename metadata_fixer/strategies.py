"""
修复策略模块
实现不同的启发式修复策略
"""

from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass

from .utils import (
    METADATA_MAGIC, read_uint32, write_uint32,
    estimate_header_size, get_common_versions
)
from .analyzer import AnalysisReport, HeaderInfo, DamageReport, DamageType


@dataclass
class RepairAttempt:
    """单次修复尝试的结果"""
    strategy_name: str
    success: bool
    modifications: List[Dict[str, Any]]
    confidence: float
    error_message: Optional[str] = None


@dataclass
class RepairResult:
    """修复结果"""
    success: bool
    output_data: bytearray
    attempts: List[RepairAttempt]
    best_attempt: Optional[RepairAttempt] = None


class RepairStrategy(ABC):
    """修复策略基类"""
    
    name: str = "base"
    description: str = "基础修复策略"
    
    @abstractmethod
    def repair(self, data: bytearray, analysis: AnalysisReport) -> RepairAttempt:
        """
        执行修复
        
        Args:
            data: 原始数据（可修改的 bytearray）
            analysis: 分析报告
            
        Returns:
            RepairAttempt 对象
        """
        pass
    
    def validate_repair(self, data: bytearray) -> bool:
        """
        验证修复后的数据是否有效
        
        Args:
            data: 修复后的数据
            
        Returns:
            是否有效
        """
        if len(data) < 56:
            return False
        
        # 检查魔数
        magic = read_uint32(data, 0)
        if magic != METADATA_MAGIC:
            return False
        
        # 检查版本号
        version = read_uint32(data, 4)
        if version < 16 or version > 27:
            return False
        
        # 检查关键偏移量
        file_size = len(data)
        offsets_to_check = [8, 12, 16, 20, 24, 28]
        
        for offset in offsets_to_check:
            try:
                value = read_uint32(data, offset)
                if value > file_size:
                    return False
            except:
                return False
        
        return True


class ConservativeStrategy(RepairStrategy):
    """
    保守修复策略
    仅修复明显错误的最小改动，风险最低
    """
    
    name = "conservative"
    description = "保守策略：仅修复明确的魔数和版本号错误"
    
    def repair(self, data: bytearray, analysis: AnalysisReport) -> RepairAttempt:
        modifications = []
        original_data = bytearray(data)
        
        try:
            # 只修复魔数
            current_magic = read_uint32(data, 0)
            if current_magic != METADATA_MAGIC:
                write_uint32(data, 0, METADATA_MAGIC)
                modifications.append({
                    'offset': 0,
                    'field': 'magic',
                    'old_value': current_magic,
                    'new_value': METADATA_MAGIC
                })
            
            # 如果版本号明显错误，尝试推断正确的版本
            current_version = read_uint32(data, 4)
            if current_version < 16 or current_version > 27:
                # 尝试从常见版本中找到最接近的
                inferred_version = self._infer_version(data, analysis)
                if inferred_version:
                    write_uint32(data, 4, inferred_version)
                    modifications.append({
                        'offset': 4,
                        'field': 'version',
                        'old_value': current_version,
                        'new_value': inferred_version
                    })
            
            # 验证修复结果
            is_valid = self.validate_repair(data)
            
            return RepairAttempt(
                strategy_name=self.name,
                success=is_valid,
                modifications=modifications,
                confidence=0.9 if is_valid else 0.3,
                error_message=None if is_valid else "修复后验证失败"
            )
            
        except Exception as e:
            # 恢复原始数据
            data[:] = original_data
            return RepairAttempt(
                strategy_name=self.name,
                success=False,
                modifications=modifications,
                confidence=0.0,
                error_message=str(e)
            )
    
    def _infer_version(self, data: bytearray, analysis: AnalysisReport) -> Optional[int]:
        """推断最可能的版本号"""
        # 简单策略：使用最常见的版本
        # 可以根据文件大小、偏移量模式等进行更复杂的推断
        file_size = len(data)
        
        # 较大的文件可能对应较新的版本
        if file_size > 10 * 1024 * 1024:  # > 10MB
            return 24
        elif file_size > 5 * 1024 * 1024:  # > 5MB
            return 22
        else:
            return 21


class StandardStrategy(RepairStrategy):
    """
    标准修复策略
    平衡修复成功率和安全性，修复魔数、版本号和基本偏移量
    """
    
    name = "standard"
    description = "标准策略：修复魔数、版本号和明显的偏移量错误"
    
    def repair(self, data: bytearray, analysis: AnalysisReport) -> RepairAttempt:
        modifications = []
        original_data = bytearray(data)
        
        try:
            # 修复魔数
            current_magic = read_uint32(data, 0)
            if current_magic != METADATA_MAGIC:
                write_uint32(data, 0, METADATA_MAGIC)
                modifications.append({
                    'offset': 0,
                    'field': 'magic',
                    'old_value': current_magic,
                    'new_value': METADATA_MAGIC
                })
            
            # 修复版本号
            current_version = read_uint32(data, 4)
            if current_version < 16 or current_version > 27:
                inferred_version = self._infer_version(data, analysis)
                if inferred_version:
                    write_uint32(data, 4, inferred_version)
                    modifications.append({
                        'offset': 4,
                        'field': 'version',
                        'old_value': current_version,
                        'new_value': inferred_version
                    })
            
            # 修复明显的偏移量错误
            version = read_uint32(data, 4)
            header_size = estimate_header_size(version)
            
            # 确保第一个偏移量（string_offset）在合理位置
            string_offset = read_uint32(data, 8)
            if string_offset < header_size or string_offset > len(data):
                # 将 string_offset 设置为头部之后
                new_string_offset = header_size
                write_uint32(data, 8, new_string_offset)
                modifications.append({
                    'offset': 8,
                    'field': 'string_offset',
                    'old_value': string_offset,
                    'new_value': new_string_offset
                })
            
            # 验证修复结果
            is_valid = self.validate_repair(data)
            
            return RepairAttempt(
                strategy_name=self.name,
                success=is_valid,
                modifications=modifications,
                confidence=0.8 if is_valid else 0.5,
                error_message=None if is_valid else "修复后验证失败"
            )
            
        except Exception as e:
            data[:] = original_data
            return RepairAttempt(
                strategy_name=self.name,
                success=False,
                modifications=modifications,
                confidence=0.0,
                error_message=str(e)
            )
    
    def _infer_version(self, data: bytearray, analysis: AnalysisReport) -> Optional[int]:
        """推断版本号"""
        file_size = len(data)
        
        # 基于文件大小推断
        if file_size > 20 * 1024 * 1024:
            return 25
        elif file_size > 10 * 1024 * 1024:
            return 24
        elif file_size > 5 * 1024 * 1024:
            return 22
        elif file_size > 2 * 1024 * 1024:
            return 21
        else:
            return 20


class AggressiveStrategy(RepairStrategy):
    """
    激进修复策略
    尝试多种可能性，包括重建整个头部结构
    """
    
    name = "aggressive"
    description = "激进策略：尝试多种修复方案，包括重建头部"
    
    def repair(self, data: bytearray, analysis: AnalysisReport) -> RepairAttempt:
        modifications = []
        original_data = bytearray(data)
        
        try:
            # 首先应用标准修复
            standard_result = self._apply_standard_fixes(data, modifications)
            
            if not standard_result:
                # 如果标准修复失败，尝试更激进的方案
                aggressive_result = self._apply_aggressive_fixes(data, modifications, analysis)
                
                if not aggressive_result:
                    # 最后尝试重建头部
                    rebuild_result = self._rebuild_header(data, modifications, analysis)
            
            # 验证修复结果
            is_valid = self.validate_repair(data)
            
            # 计算置信度
            confidence = 0.7 if is_valid else 0.4
            if len(modifications) > 10:
                confidence -= 0.1  # 修改越多，置信度越低
            
            return RepairAttempt(
                strategy_name=self.name,
                success=is_valid,
                modifications=modifications,
                confidence=max(0.0, confidence),
                error_message=None if is_valid else "修复后验证失败"
            )
            
        except Exception as e:
            data[:] = original_data
            return RepairAttempt(
                strategy_name=self.name,
                success=False,
                modifications=modifications,
                confidence=0.0,
                error_message=str(e)
            )
    
    def _apply_standard_fixes(self, data: bytearray, 
                              modifications: List[Dict]) -> bool:
        """应用标准修复"""
        # 修复魔数
        write_uint32(data, 0, METADATA_MAGIC)
        modifications.append({
            'offset': 0,
            'field': 'magic',
            'new_value': METADATA_MAGIC
        })
        
        # 设置合理的版本号
        version = 21
        write_uint32(data, 4, version)
        modifications.append({
            'offset': 4,
            'field': 'version',
            'new_value': version
        })
        
        return True
    
    def _apply_aggressive_fixes(self, data: bytearray,
                                modifications: List[Dict],
                                analysis: AnalysisReport) -> bool:
        """应用激进修复"""
        version = read_uint32(data, 4)
        header_size = estimate_header_size(version)
        
        # 重置所有偏移量为合理的默认值
        offset_fields = [
            (8, 'string_offset', header_size),
            (12, 'events_offset', header_size + 100),
            (16, 'properties_offset', header_size + 200),
            (20, 'methods_offset', header_size + 300),
            (24, 'parameters_offset', header_size + 400),
            (28, 'fields_offset', header_size + 500),
        ]
        
        for offset, field_name, default_value in offset_fields:
            current_value = read_uint32(data, offset)
            if current_value > len(data) or current_value < header_size:
                write_uint32(data, offset, default_value)
                modifications.append({
                    'offset': offset,
                    'field': field_name,
                    'old_value': current_value,
                    'new_value': default_value
                })
        
        return True
    
    def _rebuild_header(self, data: bytearray,
                       modifications: List[Dict],
                       analysis: AnalysisReport) -> bool:
        """重建整个头部"""
        # 完全重建头部结构
        version = 21
        header_size = estimate_header_size(version)
        
        # 写入魔数和版本
        write_uint32(data, 0, METADATA_MAGIC)
        write_uint32(data, 4, version)
        
        # 设置递增的偏移量序列
        base_offset = header_size
        offsets = [
            8,   # string_offset
            12,  # events_offset
            16,  # properties_offset
            20,  # methods_offset
            24,  # parameters_offset
            28,  # fields_offset
            32,  # parameter_defaults_offset
            36,  # field_defaults_offset
            40,  # declared_types_offset
            44,  # exported_types_offset
            48,  # custom_attributes_offset
        ]
        
        for i, offset in enumerate(offsets):
            value = base_offset + (i * 1000)
            write_uint32(data, offset, value)
            modifications.append({
                'offset': offset,
                'field': f'offset_{i}',
                'new_value': value
            })
        
        return True


class AutoStrategy(RepairStrategy):
    """
    自动修复策略
    根据损坏程度自动选择合适的策略
    """
    
    name = "auto"
    description = "自动策略：根据分析结果选择最佳修复方法"
    
    def __init__(self):
        self.conservative = ConservativeStrategy()
        self.standard = StandardStrategy()
        self.aggressive = AggressiveStrategy()
    
    def repair(self, data: bytearray, analysis: AnalysisReport) -> RepairAttempt:
        """自动选择并执行最佳策略"""
        
        # 根据损坏情况选择策略
        strategy = self._select_strategy(analysis)
        
        # 执行选定的策略
        result = strategy.repair(data, analysis)
        result.strategy_name = f"auto ({strategy.name})"
        
        return result
    
    def _select_strategy(self, analysis: AnalysisReport) -> RepairStrategy:
        """根据分析报告选择策略"""
        if not analysis.damage_reports:
            return self.conservative
        
        critical_count = sum(1 for d in analysis.damage_reports 
                            if d.severity == "critical")
        high_count = sum(1 for d in analysis.damage_reports 
                        if d.severity == "high")
        
        if critical_count > 1 or (critical_count > 0 and high_count > 2):
            return self.aggressive
        elif critical_count > 0 or high_count > 0:
            return self.standard
        else:
            return self.conservative


# 策略注册表
STRATEGY_REGISTRY = {
    'conservative': ConservativeStrategy,
    'standard': StandardStrategy,
    'aggressive': AggressiveStrategy,
    'auto': AutoStrategy,
}


def get_strategy(name: str) -> RepairStrategy:
    """获取指定名称的策略实例"""
    if name not in STRATEGY_REGISTRY:
        raise ValueError(f"未知策略：{name}")
    return STRATEGY_REGISTRY[name]()


def list_strategies() -> List[Dict[str, str]]:
    """列出所有可用策略"""
    return [
        {'name': cls.name, 'description': cls.description}
        for cls in STRATEGY_REGISTRY.values()
    ]
