"""
检查点管理模块 - 支持断点续爬
"""
import json
import os
from pathlib import Path
from typing import Dict, Any, Optional


class CheckpointManager:
    """检查点管理器"""

    def __init__(self, checkpoint_file: str):
        self.checkpoint_file = Path(checkpoint_file)
        self.data = self._load()

    def _load(self) -> Dict[str, Any]:
        """加载检查点数据"""
        if self.checkpoint_file.exists():
            try:
                with open(self.checkpoint_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                print(f"警告: 检查点文件加载失败: {e}")
                return {}
        return {}

    def save(self):
        """保存检查点数据"""
        try:
            self.checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.checkpoint_file, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except IOError as e:
            print(f"错误: 检查点保存失败: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """获取检查点值"""
        return self.data.get(key, default)

    def set(self, key: str, value: Any):
        """设置检查点值"""
        self.data[key] = value
        self.save()

    def update_progress(self, user: str, offset: int, total: int):
        """更新爬取进度"""
        self.set(f"{user}_progress", {
            "offset": offset,
            "total": total,
            "percentage": round(offset / total * 100, 2) if total > 0 else 0
        })
