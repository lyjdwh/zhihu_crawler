#!/usr/bin/env python3
"""
图片下载工具模块 - 支持异步批量下载知乎图片
"""
import asyncio
import hashlib
import os
import re
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from urllib.parse import urlparse

import aiohttp
from aiohttp import ClientTimeout


class ImageDownloader:
    """图片下载器"""

    def __init__(
        self,
        base_path: str = "output/images",
        quality: str = "hd",
        max_concurrent: int = 5,
        timeout: int = 30,
        retry_times: int = 3,
    ):
        """
        初始化图片下载器

        Args:
            base_path: 图片存储根路径
            quality: 图片质量 (raw/hd/normal/thumbnail)
            max_concurrent: 最大并发下载数
            timeout: 下载超时时间（秒）
            retry_times: 失败重试次数
        """
        self.base_path = Path(base_path).resolve()
        self.quality = quality
        self.max_concurrent = max_concurrent
        self.timeout = ClientTimeout(total=timeout)
        self.retry_times = retry_times
        self.session: Optional[aiohttp.ClientSession] = None

        # 质量参数映射
        self.quality_suffix = {
            "raw": "_r",      # 原图
            "hd": "_hd",      # 高清
            "normal": "_720w",  # 普通
            "thumbnail": "_300w"  # 缩略图
        }

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(timeout=self.timeout)
        return self

    async def __aexit__(self, *args):
        if self.session:
            await self.session.close()

    def _process_image_url(self, url: str) -> str:
        """处理图片URL，替换为指定质量的版本"""
        if not url:
            return url

        # 知乎图片CDN格式: https://picx.zhimg.com/[hash]_r.jpg
        # 移除现有质量后缀
        url = re.sub(r'_(r|hd|720w|300w)\.(jpg|jpeg|png|gif|webp)$', r'.\2', url)

        # 添加指定质量后缀
        suffix = self.quality_suffix.get(self.quality, "_hd")
        ext = url.split('.')[-1].lower() if '.' in url else 'jpg'
        if ext in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
            url = f"{url.rsplit('.', 1)[0]}{suffix}.{ext}"

        return url

    def _get_url_hash(self, url: str) -> str:
        """获取URL的哈希值，用于去重"""
        return hashlib.md5(url.encode('utf-8')).hexdigest()

    def _get_save_path(self, sub_dir: str, answer_id: str, index: int, url: str) -> Tuple[Path, Path]:
        """
        获取图片存储路径

        Args:
            sub_dir: 子目录（用户ID或收藏夹ID）
            answer_id: 回答ID
            index: 图片序号
            url: 图片URL

        Returns:
            (绝对路径, 相对路径)
        """
        # 从URL获取文件扩展名
        parsed = urlparse(url)
        path = parsed.path
        ext = path.split('.')[-1].lower() if '.' in path else 'jpg'
        if ext not in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
            ext = 'jpg'

        # 构建路径
        filename = f"{answer_id}_{index}.{ext}"
        relative_path = Path(sub_dir) / filename
        absolute_path = self.base_path / relative_path

        # 确保目录存在
        absolute_path.parent.mkdir(parents=True, exist_ok=True)

        return absolute_path, relative_path

    async def _download_single_image(
        self,
        url: str,
        save_path: Path,
        skip_existing: bool = True
    ) -> bool:
        """
        下载单张图片

        Args:
            url: 图片URL
            save_path: 保存路径
            skip_existing: 如果文件已存在是否跳过

        Returns:
            是否下载成功
        """
        if not self.session:
            return False

        # 检查文件是否已存在
        if skip_existing and save_path.exists():
            return True

        url = self._process_image_url(url)

        for attempt in range(self.retry_times):
            try:
                async with self.session.get(url) as response:
                    if response.status == 200:
                        content = await response.read()
                        with open(save_path, 'wb') as f:
                            f.write(content)
                        return True
                    else:
                        print(f"      图片下载失败 (状态码: {response.status}): {url}")
            except Exception as e:
                if attempt < self.retry_times - 1:
                    await asyncio.sleep(1)
                    continue
                print(f"      图片下载失败 (尝试 {attempt + 1} 次): {type(e).__name__}: {url}")

        return False

    async def download_images(
        self,
        images: List[Dict],
        sub_dir: str,
        answer_id: str,
        skip_existing: bool = True
    ) -> List[Dict]:
        """
        批量下载图片

        Args:
            images: 图片列表，每个包含url, alt等字段
            sub_dir: 子目录（用户ID或收藏夹ID）
            answer_id: 回答ID
            skip_existing: 是否跳过已存在的文件

        Returns:
            更新后的图片列表，包含local_path和relative_path字段
        """
        if not images:
            return []

        semaphore = asyncio.Semaphore(self.max_concurrent)
        tasks = []

        # 准备下载任务
        for i, img in enumerate(images):
            url = img.get('url', '')
            if not url:
                continue

            save_path, relative_path = self._get_save_path(sub_dir, answer_id, i, url)
            img['local_path'] = str(save_path)
            img['relative_path'] = str(relative_path)
            img['position'] = i

            async def download_task(img_data, path):
                async with semaphore:
                    success = await self._download_single_image(img_data['url'], path, skip_existing)
                    img_data['download_success'] = success
                    return img_data

            tasks.append(download_task(img, save_path))

        # 执行下载
        if tasks:
            results = await asyncio.gather(*tasks)
            return results

        return images

    def insert_images_into_content(self, content: str, images: List[Dict]) -> str:
        """
        将文本中的临时图片标记替换为实际的本地路径

        Args:
            content: 原始文本内容，包含临时标记[图片：index]
            images: 图片列表，包含relative_path字段

        Returns:
            替换后的文本
        """
        if not images:
            return content

        # 替换临时标记为实际路径
        for i, img in enumerate(images):
            temp_tag = f"[图片：{i}]"
            rel_path = img.get('relative_path', '')
            if rel_path:
                content = content.replace(temp_tag, f"[图片：{rel_path}]")

        return content
