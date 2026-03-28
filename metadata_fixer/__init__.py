"""
metadata_fixer - Unity global-metadata.dat 启发式修复工具
"""

from .core import MetadataFixer, FixResult, quick_fix
from .analyzer import MetadataAnalyzer, AnalysisReport
from .strategies import (
    RepairStrategy,
    ConservativeStrategy,
    StandardStrategy,
    AggressiveStrategy,
    AutoStrategy,
    get_strategy,
    list_strategies,
)
from .utils import create_backup, validate_file

__version__ = "1.0.0"
__author__ = "Metadata Fixer Team"
__all__ = [
    "MetadataFixer",
    "FixResult",
    "quick_fix",
    "MetadataAnalyzer",
    "AnalysisReport",
    "RepairStrategy",
    "ConservativeStrategy",
    "StandardStrategy",
    "AggressiveStrategy",
    "AutoStrategy",
    "get_strategy",
    "list_strategies",
    "create_backup",
    "validate_file",
]
