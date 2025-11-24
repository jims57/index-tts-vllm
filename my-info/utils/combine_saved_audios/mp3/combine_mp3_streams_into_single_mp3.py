#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MP3文件合并工具 - 使用ffmpeg合并MP3音频流
作者: Jimmy Gan
日期: Nov 24, 2025
功能: 将savedAudioFiles目录中的所有MP3文件按顺序合并为单个MP3文件

使用示例:
  python combine_mp3_streams_into_single_mp3.py              # 不清理旧文件
  python combine_mp3_streams_into_single_mp3.py --clean      # 合并前清理输出目录
  python combine_mp3_streams_into_single_mp3.py -c           # 合并前清理输出目录（简写）
"""

import os
import sys
import subprocess
import glob
import argparse
import shutil
from pathlib import Path
from datetime import datetime
import re

# ANSI颜色代码
class Colors:
    GREEN = '\033[0;32m'
    BLUE = '\033[0;34m'
    YELLOW = '\033[1;33m'
    RED = '\033[0;31m'
    NC = '\033[0m'  # No Color

def print_color(text, color):
    """打印彩色文本"""
    print(f"{color}{text}{Colors.NC}")

def natural_sort_key(s):
    """自然排序键函数，用于正确排序chunk_1, chunk_2, ..., chunk_10, chunk_11"""
    return [int(text) if text.isdigit() else text.lower()
            for text in re.split('([0-9]+)', str(s))]

def check_ffmpeg():
    """检查ffmpeg是否可用"""
    try:
        subprocess.run(['ffmpeg', '-version'], 
                      stdout=subprocess.PIPE, 
                      stderr=subprocess.PIPE, 
                      check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

def get_file_size(filepath):
    """获取文件大小（字节）"""
    return os.path.getsize(filepath)

def format_size(size_bytes):
    """格式化文件大小"""
    size_mb = size_bytes / (1024 * 1024)
    return f"{size_bytes} 字节 ({size_mb:.2f} MB)"

def combine_mp3_files_with_ffmpeg(mp3_files, output_file):
    """
    使用ffmpeg合并MP3文件
    
    Args:
        mp3_files: MP3文件路径列表
        output_file: 输出文件路径
    """
    print_color(f"\n使用ffmpeg合并MP3文件...", Colors.YELLOW)
    print_color(f"格式: MP3, 声道: 单声道", Colors.YELLOW)
    
    # 方法：使用ffmpeg的concat filter来合并MP3文件
    # 为每个MP3文件创建输入参数
    input_args = []
    filter_inputs = []
    
    for idx, mp3_file in enumerate(mp3_files):
        # 为每个MP3文件添加输入参数
        input_args.extend([
            '-i', mp3_file      # 输入文件
        ])
        filter_inputs.append(f'[{idx}:a]')
    
    # 构建concat filter
    # 例如: [0:a][1:a][2:a]concat=n=3:v=0:a=1[out]
    concat_filter = f"{''.join(filter_inputs)}concat=n={len(mp3_files)}:v=0:a=1[out]"
    
    # 完整的ffmpeg命令
    cmd = [
        'ffmpeg',
        *input_args,           # 所有输入文件参数
        '-filter_complex', concat_filter,  # concat filter
        '-map', '[out]',       # 映射输出
        '-b:a', '128k',        # 比特率
        '-y',                  # 覆盖输出文件
        output_file
    ]
    
    # 执行ffmpeg命令
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    if result.returncode != 0:
        print_color(f"ffmpeg错误: {result.stderr}", Colors.RED)
        return False
    
    print_color("ffmpeg合并成功!", Colors.GREEN)
    return True

def clean_output_directory(output_dir):
    """
    清理输出目录中的所有文件
    
    Args:
        output_dir: 输出目录路径
    """
    if output_dir.exists():
        files = list(output_dir.glob('*'))
        if files:
            print_color(f"\n清理输出目录: {output_dir}", Colors.YELLOW)
            for file in files:
                if file.is_file():
                    file.unlink()
                    print_color(f"  已删除: {file.name}", Colors.GREEN)
            print_color(f"已删除 {len(files)} 个文件", Colors.GREEN)
        else:
            print_color(f"输出目录为空，无需清理", Colors.BLUE)
    else:
        print_color(f"输出目录不存在，将创建新目录", Colors.BLUE)

def main():
    """主函数"""
    # 解析命令行参数
    parser = argparse.ArgumentParser(
        description='MP3文件合并工具 - 使用ffmpeg合并MP3音频流',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
使用示例:
  python combine_mp3_streams_into_single_mp3.py              # 不清理旧文件
  python combine_mp3_streams_into_single_mp3.py --clean      # 合并前清理输出目录
  python combine_mp3_streams_into_single_mp3.py -c           # 合并前清理输出目录（简写）
        '''
    )
    parser.add_argument(
        '-c', '--clean',
        action='store_true',
        help='合并前清理输出目录中的所有文件'
    )
    
    args = parser.parse_args()
    
    print_color("="*50, Colors.BLUE)
    print_color("MP3文件合并工具 (使用ffmpeg)", Colors.BLUE)
    print_color("="*50, Colors.BLUE)
    
    # 检查ffmpeg
    if not check_ffmpeg():
        print_color("错误: 未找到ffmpeg，请先安装ffmpeg", Colors.RED)
        print_color("macOS安装: brew install ffmpeg", Colors.YELLOW)
        sys.exit(1)
    
    # 获取脚本所在目录
    script_dir = Path(__file__).parent.absolute()
    # 从 mp3 目录向上4级到达项目根目录
    # mp3 -> combine_saved_audios -> utils -> my-info -> index-tts-vllm
    project_root = script_dir.parent.parent.parent.parent
    
    # 设置源目录和输出目录
    source_dir = project_root / "savedAudioFiles"
    output_dir = script_dir / "combined_mp3_files"
    
    # 确保输出目录存在
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print_color(f"源目录: {source_dir}", Colors.YELLOW)
    print_color(f"输出目录: {output_dir}", Colors.YELLOW)
    
    # 检查源目录
    if not source_dir.exists():
        print_color(f"错误: 源目录不存在: {source_dir}", Colors.RED)
        sys.exit(1)
    
    # 创建输出目录
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 如果指定了--clean参数，清理输出目录
    if args.clean:
        clean_output_directory(output_dir)
    
    print_color("已创建/验证输出目录", Colors.GREEN)
    
    # 查找所有MP3文件
    mp3_pattern = str(source_dir / "chunk_*.mp3")
    mp3_files = glob.glob(mp3_pattern)
    
    if not mp3_files:
        print_color(f"错误: 在 {source_dir} 中未找到任何 chunk_*.mp3 文件", Colors.RED)
        sys.exit(1)
    
    # 自然排序
    mp3_files.sort(key=natural_sort_key)
    
    print_color(f"找到 {len(mp3_files)} 个MP3文件", Colors.BLUE)
    
    # 生成输出文件名（带时间戳）
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_mp3 = output_dir / f"combined_{timestamp}.mp3"
    
    print_color(f"\n输出MP3文件: {output_mp3}", Colors.YELLOW)
    
    # 显示合并顺序
    print_color("\n合并顺序:", Colors.YELLOW)
    for idx, mp3_file in enumerate(mp3_files, 1):
        filename = os.path.basename(mp3_file)
        filesize = get_file_size(mp3_file)
        print_color(f"  [{idx}/{len(mp3_files)}] {filename} ({filesize} 字节)", Colors.GREEN)
    
    # 使用ffmpeg合并MP3文件
    if combine_mp3_files_with_ffmpeg(mp3_files, str(output_mp3)):
        final_size = get_file_size(output_mp3)
        
        print_color("\n" + "="*50, Colors.BLUE)
        print_color("合并完成!", Colors.GREEN)
        print_color(f"合并的文件数量: {len(mp3_files)}", Colors.YELLOW)
        print_color(f"输出MP3文件: {output_mp3}", Colors.YELLOW)
        print_color(f"最终文件大小: {format_size(final_size)}", Colors.YELLOW)
        print_color("="*50, Colors.BLUE)
        
        # 播放提示
        print_color("\n播放提示:", Colors.BLUE)
        print_color(f"播放MP3: ffplay {output_mp3}", Colors.GREEN)
        
    else:
        print_color("\n合并失败!", Colors.RED)
        sys.exit(1)

if __name__ == "__main__":
    main()
