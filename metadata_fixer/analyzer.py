"""
文件分析模块
深入分析 metadata 文件的结构和损坏情况
"""

import os
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum

from .utils import (
    validate_file, read_uint32, METADATA_MAGIC,
    estimate_header_size, get_common_versions
)


class DamageType(Enum):
    """损坏类型枚举"""
    NONE = "none"
    MAGIC_CORRUPTED = "magic_corrupted"
    VERSION_CORRUPTED = "version_corrupted"
    OFFSET_INVALID = "offset_invalid"
    OFFSET_ORDER_WRONG = "offset_order_wrong"
    SIZE_MISMATCH = "size_mismatch"
    UNKNOWN = "unknown"


@dataclass
class HeaderInfo:
    """头部信息数据结构"""
    magic: int = 0
    version: int = 0
    string_offset: int = 0
    events_offset: int = 0
    properties_offset: int = 0
    methods_offset: int = 0
    parameters_offset: int = 0
    fields_offset: int = 0
    parameter_defaults_offset: int = 0
    field_defaults_offset: int = 0
    declared_types_offset: int = 0
    exported_types_offset: int = 0
    custom_attributes_offset: int = 0
    unresolved_virtual_call_parameter_offset: int = 0
    generic_container_table_offset: int = 0
    generic_method_table_offset: int = 0
    vtable_count: int = 0
    rgctx_entries_count: int = 0
    images_count: int = 0
    assembly_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {k: v for k, v in self.__dict__.items()}


@dataclass
class DamageReport:
    """损坏报告"""
    damage_type: DamageType
    description: str
    offset: int = -1
    expected_value: Optional[int] = None
    actual_value: Optional[int] = None
    severity: str = "low"  # low, medium, high, critical
    repairable: bool = True


@dataclass
class AnalysisReport:
    """分析报告"""
    file_path: str
    file_size: int
    is_valid: bool
    header: Optional[HeaderInfo] = None
    damage_reports: List[DamageReport] = field(default_factory=list)
    suggested_strategy: str = "standard"
    confidence: float = 0.0
    notes: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'file_path': self.file_path,
            'file_size': self.file_size,
            'is_valid': self.is_valid,
            'header': self.header.to_dict() if self.header else None,
            'damage_reports': [
                {
                    'type': dr.damage_type.value,
                    'description': dr.description,
                    'offset': dr.offset,
                    'expected': dr.expected_value,
                    'actual': dr.actual_value,
                    'severity': dr.severity,
                    'repairable': dr.repairable
                }
                for dr in self.damage_reports
            ],
            'suggested_strategy': self.suggested_strategy,
            'confidence': self.confidence,
            'notes': self.notes
        }


class MetadataAnalyzer:
    """元数据文件分析器"""
    
    # 头部字段偏移量定义（基于版本 21+）
    HEADER_LAYOUT = {
        'magic': 0,
        'version': 4,
        'string_offset': 8,
        'events_offset': 12,
        'properties_offset': 16,
        'methods_offset': 20,
        'parameters_offset': 24,
        'fields_offset': 28,
        'parameter_defaults_offset': 32,
        'field_defaults_offset': 36,
        'declared_types_offset': 40,
        'exported_types_offset': 44,
        'custom_attributes_offset': 48,
        'unresolved_virtual_call_parameter_offset': 52,
        'generic_container_table_offset': 56,
        'generic_method_table_offset': 60,
        'vtable_count': 64,
        'rgctx_entries_count': 68,
        'images_count': 72,
        'assembly_count': 76,
    }
    
    def __init__(self, file_path: str):
        """
        初始化分析器
        
        Args:
            file_path: metadata 文件路径
        """
        self.file_path = file_path
        self.file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
        self.data: Optional[bytearray] = None
        self._load_file()
    
    def _load_file(self) -> None:
        """加载文件到内存"""
        if os.path.exists(self.file_path):
            with open(self.file_path, 'rb') as f:
                self.data = bytearray(f.read())
    
    def analyze(self) -> AnalysisReport:
        """
        执行完整分析
        
        Returns:
            AnalysisReport 对象
        """
        report = AnalysisReport(
            file_path=self.file_path,
            file_size=self.file_size,
            is_valid=False
        )
        
        # 基础验证
        validation = validate_file(self.file_path)
        
        if not validation.is_valid:
            # 尝试提取部分信息
            header = self._parse_header_partial()
            report.header = header
            
            # 生成损坏报告
            self._generate_damage_reports(report, validation)
            
            # 建议修复策略
            report.suggested_strategy = self._suggest_strategy(report)
            report.confidence = self._calculate_confidence(report)
        else:
            # 文件有效，仍然进行详细分析
            header = self._parse_header_full()
            report.header = header
            report.is_valid = True
            report.confidence = 1.0
            report.notes.append("文件验证通过，无需修复")
        
        return report
    
    def _parse_header_partial(self) -> HeaderInfo:
        """部分解析头部（即使文件损坏）"""
        header = HeaderInfo()
        
        if self.data and len(self.data) >= 8:
            try:
                header.magic = read_uint32(self.data, 0)
                header.version = read_uint32(self.data, 4)
            except:
                pass
        
        return header
    
    def _parse_header_full(self) -> HeaderInfo:
        """完整解析头部"""
        header = HeaderInfo()
        
        if not self.data or len(self.data) < 80:
            return header
        
        try:
            for field_name, offset in self.HEADER_LAYOUT.items():
                if offset + 4 <= len(self.data):
                    value = read_uint32(self.data, offset)
                    setattr(header, field_name, value)
        except Exception as e:
            pass
        
        return header
    
    def _generate_damage_reports(self, report: AnalysisReport, 
                                  validation: Any) -> None:
        """生成损坏报告"""
        
        if report.header:
            # 检查魔数
            if report.header.magic != METADATA_MAGIC:
                damage = DamageReport(
                    damage_type=DamageType.MAGIC_CORRUPTED,
                    description="魔数损坏或不正确",
                    offset=0,
                    expected_value=METADATA_MAGIC,
                    actual_value=report.header.magic,
                    severity="critical",
                    repairable=True
                )
                report.damage_reports.append(damage)
            
            # 检查版本号
            if report.header.version < 16 or report.header.version > 27:
                damage = DamageReport(
                    damage_type=DamageType.VERSION_CORRUPTED,
                    description="版本号超出合理范围",
                    offset=4,
                    expected_value=None,  # 需要推断
                    actual_value=report.header.version,
                    severity="high",
                    repairable=True
                )
                report.damage_reports.append(damage)
        
        # 添加验证错误
        if validation.error_message:
            if "偏移量" in validation.error_message:
                damage = DamageReport(
                    damage_type=DamageType.OFFSET_INVALID,
                    description=validation.error_message,
                    severity="high",
                    repairable=True
                )
                report.damage_reports.append(damage)
        
        # 如果没有检测到具体损坏但验证失败
        if not report.damage_reports:
            damage = DamageReport(
                damage_type=DamageType.UNKNOWN,
                description=f"文件验证失败：{validation.error_message}",
                severity="medium",
                repairable=False
            )
            report.damage_reports.append(damage)
    
    def _suggest_strategy(self, report: AnalysisReport) -> str:
        """根据损坏情况建议修复策略"""
        if not report.damage_reports:
            return "conservative"
        
        critical_count = sum(1 for d in report.damage_reports if d.severity == "critical")
        high_count = sum(1 for d in report.damage_reports if d.severity == "high")
        
        if critical_count > 1 or (critical_count > 0 and high_count > 2):
            return "aggressive"
        elif critical_count > 0 or high_count > 0:
            return "standard"
        else:
            return "conservative"
    
    def _calculate_confidence(self, report: AnalysisReport) -> float:
        """计算修复成功的置信度"""
        if not report.damage_reports:
            return 1.0
        
        # 基于损坏类型和数量计算置信度
        base_confidence = 1.0
        
        for damage in report.damage_reports:
            if damage.severity == "critical":
                base_confidence -= 0.3
            elif damage.severity == "high":
                base_confidence -= 0.2
            elif damage.severity == "medium":
                base_confidence -= 0.1
            
            if not damage.repairable:
                base_confidence -= 0.2
        
        return max(0.0, min(1.0, base_confidence))
    
    def scan_for_patterns(self) -> Dict[str, Any]:
        """
        扫描文件中可能有助于修复的模式
        
        Returns:
            包含发现模式的字典
        """
        patterns = {
            'valid_magic_locations': [],
            'potential_version_values': [],
            'offset_sequences': []
        }
        
        if not self.data:
            return patterns
        
        # 扫描可能的魔数位置
        for i in range(0, min(len(self.data) - 4, 1024), 4):
            try:
                value = read_uint32(self.data, i)
                if value == METADATA_MAGIC:
                    patterns['valid_magic_locations'].append(i)
            except:
                pass
        
        # 扫描可能的版本号（16-27）
        for i in range(0, min(len(self.data) - 4, 1024), 4):
            try:
                value = read_uint32(self.data, i)
                if 16 <= value <= 27:
                    patterns['potential_version_values'].append((i, value))
            except:
                pass
        
        return patterns
    
    def get_header_bytes(self, count: int = 80) -> bytes:
        """获取原始头部字节"""
        if not self.data:
            return b''
        return bytes(self.data[:min(count, len(self.data))])
