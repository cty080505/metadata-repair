"""
工具函数模块
提供文件操作、验证等辅助功能
"""

import os
import shutil
import hashlib
from datetime import datetime
from typing import Optional, Tuple
from dataclasses import dataclass


# Unity IL2CPP global-metadata.dat 的魔数
METADATA_MAGIC = 0x3AFB7A4C

# 支持的版本范围（根据实际情况调整）
MIN_SUPPORTED_VERSION = 16
MAX_SUPPORTED_VERSION = 27


@dataclass
class FileValidation:
    """文件验证结果"""
    is_valid: bool
    file_size: int
    magic_number: Optional[int] = None
    version: Optional[int] = None
    error_message: Optional[str] = None


def create_backup(file_path: str, backup_dir: Optional[str] = None) -> str:
    """
    创建文件备份
    
    Args:
        file_path: 原始文件路径
        backup_dir: 备份目录，默认为原始文件所在目录的 _backups 子目录
        
    Returns:
        备份文件的路径
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"文件不存在：{file_path}")
    
    # 确定备份目录
    if backup_dir is None:
        original_dir = os.path.dirname(os.path.abspath(file_path))
        backup_dir = os.path.join(original_dir, "_backups")
    
    os.makedirs(backup_dir, exist_ok=True)
    
    # 生成备份文件名
    filename = os.path.basename(file_path)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"{filename}.{timestamp}.bak"
    backup_path = os.path.join(backup_dir, backup_name)
    
    # 复制文件
    shutil.copy2(file_path, backup_path)
    
    return backup_path


def validate_file(file_path: str) -> FileValidation:
    """
    验证 metadata 文件的有效性
    
    Args:
        file_path: 文件路径
        
    Returns:
        FileValidation 对象，包含验证结果
    """
    if not os.path.exists(file_path):
        return FileValidation(
            is_valid=False,
            file_size=0,
            error_message="文件不存在"
        )
    
    file_size = os.path.getsize(file_path)
    
    # 检查最小文件大小（头部至少需要 56 字节）
    if file_size < 56:
        return FileValidation(
            is_valid=False,
            file_size=file_size,
            error_message="文件太小，无法包含有效的元数据头部"
        )
    
    try:
        with open(file_path, 'rb') as f:
            # 读取头部信息
            # 偏移量 0-3: 魔数 (uint32)
            magic_bytes = f.read(4)
            if len(magic_bytes) < 4:
                return FileValidation(
                    is_valid=False,
                    file_size=file_size,
                    error_message="无法读取魔数"
                )
            
            magic_number = int.from_bytes(magic_bytes, byteorder='little')
            
            # 偏移量 4-7: 版本号 (uint32)
            version_bytes = f.read(4)
            version = int.from_bytes(version_bytes, byteorder='little')
            
            # 验证魔数
            if magic_number != METADATA_MAGIC:
                return FileValidation(
                    is_valid=False,
                    file_size=file_size,
                    magic_number=magic_number,
                    version=version,
                    error_message=f"魔数无效：期望 0x{METADATA_MAGIC:08X}, 实际 0x{magic_number:08X}"
                )
            
            # 验证版本号
            if version < MIN_SUPPORTED_VERSION or version > MAX_SUPPORTED_VERSION:
                return FileValidation(
                    is_valid=False,
                    file_size=file_size,
                    magic_number=magic_number,
                    version=version,
                    error_message=f"版本号不支持：{version} (支持范围：{MIN_SUPPORTED_VERSION}-{MAX_SUPPORTED_VERSION})"
                )
            
            # 读取更多头部信息进行基本验证
            f.seek(8)
            string_offset = int.from_bytes(f.read(4), byteorder='little')
            events_offset = int.from_bytes(f.read(4), byteorder='little')
            properties_offset = int.from_bytes(f.read(4), byteorder='little')
            methods_offset = int.from_bytes(f.read(4), byteorder='little')
            parameters_offset = int.from_bytes(f.read(4), byteorder='little')
            fields_offset = int.from_bytes(f.read(4), byteorder='little')
            
            # 检查偏移量是否合理（应该小于文件大小）
            offsets = [string_offset, events_offset, properties_offset, 
                      methods_offset, parameters_offset, fields_offset]
            
            for offset in offsets:
                if offset > file_size:
                    return FileValidation(
                        is_valid=False,
                        file_size=file_size,
                        magic_number=magic_number,
                        version=version,
                        error_message=f"偏移量超出文件大小：{offset} > {file_size}"
                    )
            
            # 检查偏移量的相对顺序（后面的偏移量应该大于前面的）
            for i in range(len(offsets) - 1):
                if offsets[i] > offsets[i + 1] and offsets[i + 1] != 0:
                    # 允许某些偏移量为 0，但非零偏移量应该递增
                    if offsets[i] != 0:
                        return FileValidation(
                            is_valid=False,
                            file_size=file_size,
                            magic_number=magic_number,
                            version=version,
                            error_message=f"偏移量顺序异常：offset[{i}]={offsets[i]} > offset[{i+1}]={offsets[i+1]}"
                        )
            
            return FileValidation(
                is_valid=True,
                file_size=file_size,
                magic_number=magic_number,
                version=version
            )
            
    except Exception as e:
        return FileValidation(
            is_valid=False,
            file_size=file_size if 'file_size' in locals() else 0,
            error_message=f"读取文件时出错：{str(e)}"
        )


def calculate_file_hash(file_path: str, algorithm: str = 'sha256') -> str:
    """
    计算文件的哈希值
    
    Args:
        file_path: 文件路径
        algorithm: 哈希算法 (md5, sha1, sha256)
        
    Returns:
        十六进制哈希字符串
    """
    hash_func = getattr(hashlib, algorithm)()
    
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            hash_func.update(chunk)
    
    return hash_func.hexdigest()


def read_uint32(data: bytes, offset: int) -> int:
    """从字节数据中读取 uint32 值（小端序）"""
    if offset + 4 > len(data):
        raise ValueError(f"偏移量 {offset} 超出数据范围")
    return int.from_bytes(data[offset:offset+4], byteorder='little')


def write_uint32(data: bytearray, offset: int, value: int) -> None:
    """向字节数据中写入 uint32 值（小端序）"""
    if offset + 4 > len(data):
        raise ValueError(f"偏移量 {offset} 超出数据范围")
    data[offset:offset+4] = value.to_bytes(4, byteorder='little')


def estimate_header_size(version: int) -> int:
    """
    根据版本号估算头部大小
    
    不同版本的 Unity 使用不同的头部结构
    """
    # 基础头部大小（版本 16-20）
    base_size = 56
    
    # 版本 21+ 增加了额外的字段
    if version >= 21:
        base_size += 8  # 额外的大小字段
    
    # 版本 24+ 又有变化
    if version >= 24:
        base_size += 4
    
    return base_size


def get_common_versions() -> list:
    """返回常见的 Unity IL2CPP 版本号列表"""
    return [16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27]
