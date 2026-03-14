"""
数据存储模块 - 批量保存JSON数据
"""
import json
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime


class BatchStorage:
    """批量数据存储器"""

    def __init__(self, output_dir: str, user_name: str, data_type: str, batch_size: int = 50):
        self.output_dir = Path(output_dir)
        self.user_name = user_name
        self.data_type = data_type
        self.batch_size = batch_size
        self.batch_index = 0
        self.buffer: List[Dict[str, Any]] = []
        self.total_saved = 0

        # 创建输出目录
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def add(self, item: Dict[str, Any]):
        """添加单条数据"""
        self.buffer.append(item)
        if len(self.buffer) >= self.batch_size:
            self.flush()

    def add_many(self, items: List[Dict[str, Any]]):
        """批量添加数据"""
        for item in items:
            self.add(item)

    def flush(self):
        """保存缓冲区数据到文件"""
        if not self.buffer:
            return

        filename = self.output_dir / f"{self.user_name}_{self.data_type}_batch_{self.batch_index}.json"

        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(self.buffer, f, ensure_ascii=False, indent=2)

            print(f"  [保存] {self.data_type} 批次 #{self.batch_index}: {len(self.buffer)} 条 "
                  f"(总计: {self.total_saved + len(self.buffer)})")

            self.total_saved += len(self.buffer)
            self.buffer = []
            self.batch_index += 1

        except IOError as e:
            print(f"  [错误] 保存失败: {e}")

    def close(self) -> Dict[str, int]:
        """关闭存储器并保存剩余数据"""
        self.flush()
        return {
            "total_saved": self.total_saved,
            "batch_count": self.batch_index
        }


class DataMerger:
    """数据合并工具"""

    def __init__(self, output_dir: str):
        self.output_dir = Path(output_dir)

    def merge_batches(self, pattern: str, output_file: str) -> int:
        """合并批次文件"""
        all_data = []

        for batch_file in sorted(self.output_dir.glob(pattern)):
            try:
                with open(batch_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        all_data.extend(data)
                    else:
                        all_data.append(data)
            except (json.JSONDecodeError, IOError) as e:
                print(f"警告: 读取 {batch_file.name} 失败: {e}")
                continue

        if all_data:
            output_path = self.output_dir / output_file
            try:
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(all_data, f, ensure_ascii=False, indent=2)
                print(f"✓ 合并完成: {output_file} ({len(all_data)} 条数据)")
                return len(all_data)
            except IOError as e:
                print(f"错误: 保存合并文件失败: {e}")

        return 0

    def generate_report(self, user_name: str, data_type: str) -> Dict[str, Any]:
        """生成数据报告"""
        pattern = f"{user_name}_{data_type}_batch_*.json"
        batches = list(self.output_dir.glob(pattern))

        total_items = 0
        total_size = 0

        for batch_file in batches:
            try:
                with open(batch_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    total_items += len(data) if isinstance(data, list) else 1
                total_size += batch_file.stat().st_size
            except (json.JSONDecodeError, IOError):
                continue

        return {
            "user": user_name,
            "data_type": data_type,
            "batches": len(batches),
            "total_items": total_items,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "output_dir": str(self.output_dir)
        }
