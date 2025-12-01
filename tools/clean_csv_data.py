"""
CSV 数据清理工具
================

清理旧格式的 CSV 数据，保留新格式数据

用法:
    python tools/clean_csv_data.py           # 预览要清理的文件
    python tools/clean_csv_data.py --execute # 执行清理
    python tools/clean_csv_data.py --delete  # 删除所有旧数据文件
"""

import argparse
import shutil
from pathlib import Path
from datetime import datetime

# 新格式的 CSV 表头
NEW_HEADER = "timestamp,open,high,low,close,volume,funding_rate,open_interest"
OLD_HEADER = "timestamp,price,open_interest,funding_rate"


def analyze_csv_files(data_dir: Path) -> dict:
    """分析数据目录中的 CSV 文件"""
    stats = {
        "new_format": [],
        "old_format": [],
        "mixed_format": [],
        "unknown": [],
        "total_files": 0,
    }
    
    if not data_dir.exists():
        print(f"❌ 数据目录不存在: {data_dir}")
        return stats
    
    csv_files = list(data_dir.glob("*.csv"))
    stats["total_files"] = len(csv_files)
    
    for csv_file in csv_files:
        try:
            with open(csv_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            if not lines:
                continue
            
            header = lines[0].strip()
            
            if header == NEW_HEADER:
                stats["new_format"].append(csv_file.name)
            elif header == OLD_HEADER:
                # 检查是否有混合数据
                has_new_rows = any(len(line.split(',')) == 8 for line in lines[1:])
                if has_new_rows:
                    stats["mixed_format"].append(csv_file.name)
                else:
                    stats["old_format"].append(csv_file.name)
            else:
                stats["unknown"].append(csv_file.name)
                
        except Exception as e:
            print(f"⚠️ 读取 {csv_file.name} 失败: {e}")
            stats["unknown"].append(csv_file.name)
    
    return stats


def clean_mixed_files(data_dir: Path, execute: bool = False) -> int:
    """
    清理混合格式的 CSV 文件
    
    策略：删除旧格式行，只保留新格式数据
    """
    cleaned_count = 0
    csv_files = list(data_dir.glob("*.csv"))
    
    for csv_file in csv_files:
        try:
            with open(csv_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            if not lines:
                continue
            
            header = lines[0].strip()
            
            # 只处理旧表头但有新数据的文件
            if header == OLD_HEADER:
                # 找出新格式的行（8列）
                new_rows = [line for line in lines[1:] if len(line.strip().split(',')) == 8]
                
                if new_rows:
                    if execute:
                        # 备份原文件
                        backup_path = csv_file.with_suffix('.csv.bak')
                        shutil.copy2(csv_file, backup_path)
                        
                        # 写入新格式数据
                        with open(csv_file, 'w', encoding='utf-8', newline='') as f:
                            f.write(NEW_HEADER + '\n')
                            f.writelines(new_rows)
                        
                        print(f"✅ 已清理: {csv_file.name} ({len(new_rows)} 行新数据)")
                    else:
                        print(f"📝 将清理: {csv_file.name} ({len(new_rows)} 行新数据)")
                    
                    cleaned_count += 1
                    
        except Exception as e:
            print(f"❌ 处理 {csv_file.name} 失败: {e}")
    
    return cleaned_count


def delete_old_format_files(data_dir: Path, execute: bool = False) -> int:
    """删除旧格式的 CSV 文件"""
    deleted_count = 0
    csv_files = list(data_dir.glob("*.csv"))
    
    for csv_file in csv_files:
        try:
            with open(csv_file, 'r', encoding='utf-8') as f:
                header = f.readline().strip()
            
            if header == OLD_HEADER:
                if execute:
                    csv_file.unlink()
                    print(f"🗑️ 已删除: {csv_file.name}")
                else:
                    print(f"📝 将删除: {csv_file.name}")
                deleted_count += 1
                
        except Exception as e:
            print(f"❌ 删除 {csv_file.name} 失败: {e}")
    
    return deleted_count


def main():
    parser = argparse.ArgumentParser(
        description="CSV 数据清理工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python tools/clean_csv_data.py           # 预览分析
  python tools/clean_csv_data.py --execute # 执行清理 (保留新数据)
  python tools/clean_csv_data.py --delete  # 删除旧格式文件
        """
    )
    
    parser.add_argument(
        "--execute",
        action="store_true",
        help="执行清理操作 (清理混合文件，保留新格式数据)"
    )
    
    parser.add_argument(
        "--delete",
        action="store_true",
        help="删除所有旧格式文件"
    )
    
    parser.add_argument(
        "--data-dir",
        type=str,
        default="data",
        help="数据目录路径 (默认: data)"
    )
    
    args = parser.parse_args()
    data_dir = Path(args.data_dir)
    
    print("\n" + "=" * 60)
    print("📊 CSV 数据格式分析")
    print("=" * 60)
    
    stats = analyze_csv_files(data_dir)
    
    print(f"\n总文件数: {stats['total_files']}")
    print(f"  ✅ 新格式 (8列): {len(stats['new_format'])}")
    print(f"  ⚠️ 混合格式: {len(stats['mixed_format'])}")
    print(f"  ❌ 旧格式 (4列): {len(stats['old_format'])}")
    print(f"  ❓ 未知格式: {len(stats['unknown'])}")
    
    if args.delete:
        print("\n" + "-" * 60)
        print("🗑️ 删除旧格式文件...")
        count = delete_old_format_files(data_dir, execute=args.execute)
        if not args.execute and count > 0:
            print(f"\n⚠️ 预览模式。添加 --execute 来执行删除。")
    
    elif args.execute or stats['mixed_format']:
        print("\n" + "-" * 60)
        print("🔧 清理混合格式文件...")
        count = clean_mixed_files(data_dir, execute=args.execute)
        if not args.execute and count > 0:
            print(f"\n⚠️ 预览模式。添加 --execute 来执行清理。")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()

