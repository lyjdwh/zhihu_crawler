#!/usr/bin/env python3
"""
奥特之父知乎数据爬取脚本

使用方法:
    python scripts/crawl_aote.py

功能:
    - 爬取奥特之父的所有知乎回答
    - 支持断点续爬
    - 自动分批保存数据
    - 生成爬取报告
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime

# 添加项目根目录到路径
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from core.config import ZHIHU_CONFIG, CRAWLER_CONFIG, TARGET_USERS, OUTPUT_DIR
from core.zhihu_api import ZhihuAPI
from utils.checkpoint import CheckpointManager
from utils.storage import BatchStorage


async def crawl_user_answers(
    api: ZhihuAPI,
    user_name: str,
    url_token: str,
    expected_count: int = 0
) -> int:
    """
    爬取用户的所有回答

    Args:
        api: ZhihuAPI 实例
        user_name: 用户名
        url_token: 用户URL token
        expected_count: 预期的回答数量

    Returns:
        实际爬取的回答数量
    """
    print(f"\n{'='*60}")
    print(f"开始爬取用户: {user_name}")
    print(f"{'='*60}\n")

    # 初始化检查点管理器
    checkpoint = CheckpointManager(ZHIHU_CONFIG["checkpoint_file"])

    # 获取用户信息
    print("正在获取用户信息...")
    user_info = await api.get_user_info(url_token)

    if not user_info:
        print(f"❌ 无法获取用户 {user_name} 的信息")
        return 0

    print(f"✓ 用户信息:")
    print(f"  - 名称: {user_info.name}")
    print(f"  - 回答数: {user_info.answer_count}")
    print(f"  - 文章数: {user_info.article_count}")
    print(f"  - 关注者: {user_info.follower_count}\n")

    # 初始化存储
    storage = BatchStorage(
        output_dir=OUTPUT_DIR,
        user_name=user_name,
        data_type="answers",
        batch_size=CRAWLER_CONFIG["batch_size"]
    )

    # 恢复进度
    progress_key = f"{user_name}_progress"
    saved_progress = checkpoint.get(progress_key, {})
    offset = saved_progress.get("offset", 0)
    total_collected = saved_progress.get("collected", 0)

    if total_collected > 0:
        print(f"📌 从检查点恢复: 已收集 {total_collected} 条，偏移量 {offset}\n")

    # 定义进度回调
    def progress_callback(collected: int, expected: int):
        if expected > 0:
            percentage = (collected / expected) * 100
            print(f"  进度: {collected}/{expected} ({percentage:.1f}%)")

    # 开始爬取
    print("🚀 开始爬取回答数据...\n")
    start_time = datetime.now()

    try:
        total = await api.crawl_all_answers(
            user_id=user_info.id,
            user_name=user_name,
            expected_count=expected_count or user_info.answer_count,
            checkpoint_manager=checkpoint,
            storage=storage,
            progress_callback=progress_callback
        )

        elapsed = (datetime.now() - start_time).total_seconds()

        print(f"\n{'='*60}")
        print(f"✅ 爬取完成!")
        print(f"{'='*60}")
        print(f"  - 用户: {user_name}")
        print(f"  - 总计: {total} 条回答")
        print(f"  - 耗时: {elapsed:.1f} 秒")
        print(f"  - 平均: {total/elapsed:.1f} 条/秒" if elapsed > 0 else "  - 平均: N/A")
        print(f"{'='*60}\n")

        return total

    except Exception as e:
        print(f"\n❌ 爬取过程中出错: {e}")
        raise


async def main():
    """主函数"""
    print("\n" + "="*60)
    print("知乎数据爬取工具 - 奥特之父专用版")
    print("="*60 + "\n")

    # 获取目标用户配置
    user_config = TARGET_USERS.get("奥特之父")

    if not user_config:
        print("❌ 未找到用户配置")
        return

    # 初始化 API 客户端
    async with ZhihuAPI(
        auth_file=ZHIHU_CONFIG["auth_file"],
        headless=CRAWLER_CONFIG["headless"],
        request_delay=CRAWLER_CONFIG["request_delay"]
    ) as api:
        # 爬取用户回答
        total = await crawl_user_answers(
            api=api,
            user_name="奥特之父",
            url_token=user_config["url_token"],
            expected_count=user_config.get("expected_answers", 0)
        )

        if total > 0:
            print("\n✨ 爬取任务全部完成!")
            print(f"📊 数据保存在: {OUTPUT_DIR}/")
        else:
            print("\n⚠️ 未能获取到数据，请检查登录状态")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n用户中断，程序已退出")
    except Exception as e:
        print(f"\n程序出错: {e}")
        import traceback
        traceback.print_exc()
