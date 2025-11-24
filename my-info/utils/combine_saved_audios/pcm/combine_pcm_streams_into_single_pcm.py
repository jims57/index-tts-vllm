#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PCM文件合并工具 - 使用ffmpeg合并PCM音频流
作者: Jimmy Gan
日期: Nov 24, 2025
功能: 将savedAudioFiles目录中的所有PCM文件按顺序合并为单个PCM文件

使用示例:
  python combine_pcm_streams_into_single_pcm.py              # 不清理旧文件
  python combine_pcm_streams_into_single_pcm.py --clean      # 合并前清理输出目录
  python combine_pcm_streams_into_single_pcm.py -c           # 合并前清理输出目录（简写）
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

def combine_pcm_files_with_ffmpeg(pcm_files, output_file, sample_rate=8000):
    """
    使用ffmpeg合并PCM文件
    
    Args:
        pcm_files: PCM文件路径列表
        output_file: 输出文件路径
        sample_rate: 采样率（默认8000Hz）
    """
    print_color(f"\n使用ffmpeg合并PCM文件...", Colors.YELLOW)
    print_color(f"采样率: {sample_rate}Hz, 格式: s16le (16位小端), 声道: 单声道", Colors.YELLOW)
    
    # 方法：使用ffmpeg的concat filter来合并原始PCM文件
    # 为每个PCM文件创建输入参数
    input_args = []
    filter_inputs = []
    
    for idx, pcm_file in enumerate(pcm_files):
        # 为每个PCM文件添加输入参数
        input_args.extend([
            '-f', 's16le',      # 输入格式：16位小端PCM
            '-ar', str(sample_rate),  # 采样率
            '-ac', '1',         # 单声道
            '-i', pcm_file      # 输入文件
        ])
        filter_inputs.append(f'[{idx}:a]')
    
    # 构建concat filter
    # 例如: [0:a][1:a][2:a]concat=n=3:v=0:a=1[out]
    concat_filter = f"{''.join(filter_inputs)}concat=n={len(pcm_files)}:v=0:a=1[out]"
    
    # 完整的ffmpeg命令
    cmd = [
        'ffmpeg',
        *input_args,           # 所有输入文件参数
        '-filter_complex', concat_filter,  # concat filter
        '-map', '[out]',       # 映射输出
        '-f', 's16le',         # 输出格式：16位小端PCM
        '-ar', str(sample_rate),  # 输出采样率
        '-ac', '1',            # 输出单声道
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
        description='PCM文件合并工具 - 使用ffmpeg合并PCM音频流',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
使用示例:
  python combine_pcm_streams_into_single_pcm.py              # 不清理旧文件
  python combine_pcm_streams_into_single_pcm.py --clean      # 合并前清理输出目录
  python combine_pcm_streams_into_single_pcm.py -c           # 合并前清理输出目录（简写）
        '''
    )
    parser.add_argument(
        '-c', '--clean',
        action='store_true',
        help='合并前清理输出目录中的所有文件'
    )
    
    args = parser.parse_args()
    
    print_color("="*50, Colors.BLUE)
    print_color("PCM文件合并工具 (使用ffmpeg)", Colors.BLUE)
    print_color("="*50, Colors.BLUE)
    
    # 检查ffmpeg
    if not check_ffmpeg():
        print_color("错误: 未找到ffmpeg，请先安装ffmpeg", Colors.RED)
        print_color("macOS安装: brew install ffmpeg", Colors.YELLOW)
        sys.exit(1)
    
    # 获取脚本所在目录
    script_dir = Path(__file__).parent.absolute()
    project_root = script_dir.parent.parent.parent.parent
    
    # 设置源目录和输出目录
    source_dir = project_root / "savedAudioFiles"
    output_dir = script_dir / "combined_pcm_files"
    
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
    
    # 查找所有PCM文件
    pcm_pattern = str(source_dir / "chunk_*.pcm")
    pcm_files = glob.glob(pcm_pattern)
    
    if not pcm_files:
        print_color(f"错误: 在 {source_dir} 中未找到任何 chunk_*.pcm 文件", Colors.RED)
        sys.exit(1)
    
    # 自然排序
    pcm_files.sort(key=natural_sort_key)
    
    print_color(f"找到 {len(pcm_files)} 个PCM文件", Colors.BLUE)
    
    # 生成输出文件名（带时间戳）
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_pcm = output_dir / f"combined_{timestamp}.pcm"
    output_wav = output_dir / f"combined_{timestamp}.wav"
    
    print_color(f"\n输出PCM文件: {output_pcm}", Colors.YELLOW)
    print_color(f"输出WAV文件: {output_wav}", Colors.YELLOW)
    
    # 显示合并顺序
    print_color("\n合并顺序:", Colors.YELLOW)
    for idx, pcm_file in enumerate(pcm_files, 1):
        filename = os.path.basename(pcm_file)
        filesize = get_file_size(pcm_file)
        print_color(f"  [{idx}/{len(pcm_files)}] {filename} ({filesize} 字节)", Colors.GREEN)
    
    # 使用ffmpeg合并PCM文件
    if combine_pcm_files_with_ffmpeg(pcm_files, str(output_pcm)):
        final_size = get_file_size(output_pcm)
        
        print_color("\n" + "="*50, Colors.BLUE)
        print_color("合并完成!", Colors.GREEN)
        print_color(f"合并的文件数量: {len(pcm_files)}", Colors.YELLOW)
        print_color(f"输出PCM文件: {output_pcm}", Colors.YELLOW)
        print_color(f"最终文件大小: {format_size(final_size)}", Colors.YELLOW)
        
        # 转换为WAV格式
        print_color("\n转换为WAV格式...", Colors.YELLOW)
        wav_cmd = [
            'ffmpeg',
            '-f', 's16le',
            '-ar', '8000',
            '-ac', '1',
            '-i', str(output_pcm),
            '-y',
            str(output_wav)
        ]
        
        result = subprocess.run(
            wav_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        if result.returncode == 0:
            wav_size = get_file_size(output_wav)
            print_color(f"WAV文件已创建: {output_wav}", Colors.GREEN)
            print_color(f"WAV文件大小: {format_size(wav_size)}", Colors.YELLOW)
        else:
            print_color(f"WAV转换失败", Colors.RED)
        
        print_color("="*50, Colors.BLUE)
        
        # 播放提示
        print_color("\n播放提示:", Colors.BLUE)
        print_color(f"播放PCM (8000Hz): ffplay -f s16le -ar 8000 -ac 1 {output_pcm}", Colors.GREEN)
        print_color(f"播放PCM (16000Hz): ffplay -f s16le -ar 16000 -ac 1 {output_pcm}", Colors.GREEN)
        print_color(f"播放WAV: ffplay {output_wav}", Colors.GREEN)
        
    else:
        print_color("\n合并失败!", Colors.RED)
        sys.exit(1)

if __name__ == "__main__":
    main()
