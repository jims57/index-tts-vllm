#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WAV转PCM工具 - 使用ffmpeg将WAV文件转换为PCM格式
作者: Jimmy Gan
日期: Nov 24, 2025
功能: 将input_wav_files目录中的所有WAV文件转换为PCM格式并保存到converted_pcm_files目录

使用示例:
  python convert_wav_to_pcm_file.py              # 转换所有WAV文件
  python convert_wav_to_pcm_file.py --clean      # 转换前清理输出目录
  python convert_wav_to_pcm_file.py -c           # 转换前清理输出目录（简写）
"""

import os
import sys
import subprocess
import glob
import argparse
import shutil
from pathlib import Path
from datetime import datetime

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

def convert_wav_to_pcm(wav_file, pcm_file, sample_rate=16000):
    """
    使用ffmpeg将WAV文件转换为PCM格式
    
    Args:
        wav_file: 输入WAV文件路径
        pcm_file: 输出PCM文件路径
        sample_rate: 采样率（默认16000Hz）
    
    Returns:
        bool: 转换成功返回True，失败返回False
    """
    # 构建ffmpeg命令
    cmd = [
        'ffmpeg',
        '-i', wav_file,        # 输入WAV文件
        '-f', 's16le',         # 输出格式：16位小端PCM
        '-ar', str(sample_rate),  # 输出采样率
        '-ac', '1',            # 输出单声道
        '-y',                  # 覆盖输出文件
        pcm_file
    ]
    
    # 执行ffmpeg命令
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    if result.returncode != 0:
        print_color(f"  转换失败: {result.stderr}", Colors.RED)
        return False
    
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
        description='WAV转PCM工具 - 使用ffmpeg将WAV文件转换为PCM格式',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
使用示例:
  python convert_wav_to_pcm_file.py              # 转换所有WAV文件
  python convert_wav_to_pcm_file.py --clean      # 转换前清理输出目录
  python convert_wav_to_pcm_file.py -c           # 转换前清理输出目录（简写）
        '''
    )
    parser.add_argument(
        '-c', '--clean',
        action='store_true',
        help='转换前清理输出目录中的所有文件'
    )
    parser.add_argument(
        '-r', '--sample-rate',
        type=int,
        default=16000,
        help='输出PCM采样率（默认: 16000Hz）'
    )
    
    args = parser.parse_args()
    
    print_color("="*60, Colors.BLUE)
    print_color("WAV转PCM工具 (使用ffmpeg)", Colors.BLUE)
    print_color("="*60, Colors.BLUE)
    
    # 检查ffmpeg
    if not check_ffmpeg():
        print_color("错误: 未找到ffmpeg，请先安装ffmpeg", Colors.RED)
        print_color("macOS安装: brew install ffmpeg", Colors.YELLOW)
        sys.exit(1)
    
    # 获取脚本所在目录
    script_dir = Path(__file__).parent.absolute()
    
    # 设置输入和输出目录
    input_dir = script_dir / "input_wav_files"
    output_dir = script_dir / "converted_pcm_files"
    
    print_color(f"\n输入目录: {input_dir}", Colors.YELLOW)
    print_color(f"输出目录: {output_dir}", Colors.YELLOW)
    print_color(f"采样率: {args.sample_rate}Hz", Colors.YELLOW)
    
    # 检查输入目录
    if not input_dir.exists():
        print_color(f"\n错误: 输入目录不存在: {input_dir}", Colors.RED)
        print_color(f"请创建目录并放入WAV文件", Colors.YELLOW)
        sys.exit(1)
    
    # 创建输出目录
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 如果指定了--clean参数，清理输出目录
    if args.clean:
        clean_output_directory(output_dir)
    
    print_color("\n已创建/验证输出目录", Colors.GREEN)
    
    # 查找所有WAV文件
    wav_pattern = str(input_dir / "*.wav")
    wav_files = glob.glob(wav_pattern)
    
    if not wav_files:
        print_color(f"\n错误: 在 {input_dir} 中未找到任何 .wav 文件", Colors.RED)
        sys.exit(1)
    
    # 排序
    wav_files.sort()
    
    print_color(f"\n找到 {len(wav_files)} 个WAV文件", Colors.BLUE)
    print_color("="*60, Colors.BLUE)
    
    # 转换统计
    success_count = 0
    failed_count = 0
    
    # 转换每个WAV文件
    for idx, wav_file in enumerate(wav_files, 1):
        filename = os.path.basename(wav_file)
        # 使用相同的文件名，只改扩展名
        pcm_filename = os.path.splitext(filename)[0] + '.pcm'
        pcm_file = output_dir / pcm_filename
        
        input_size = get_file_size(wav_file)
        
        print_color(f"\n[{idx}/{len(wav_files)}] 转换: {filename}", Colors.YELLOW)
        print_color(f"  输入大小: {format_size(input_size)}", Colors.BLUE)
        
        # 执行转换
        if convert_wav_to_pcm(wav_file, str(pcm_file), args.sample_rate):
            output_size = get_file_size(str(pcm_file))
            print_color(f"  转换成功!", Colors.GREEN)
            print_color(f"  输出文件: {pcm_filename}", Colors.GREEN)
            print_color(f"  输出大小: {format_size(output_size)}", Colors.GREEN)
            success_count += 1
        else:
            print_color(f"  转换失败!", Colors.RED)
            failed_count += 1
    
    # 显示总结
    print_color("\n" + "="*60, Colors.BLUE)
    print_color("转换完成!", Colors.GREEN)
    print_color(f"成功: {success_count} 个文件", Colors.GREEN)
    if failed_count > 0:
        print_color(f"失败: {failed_count} 个文件", Colors.RED)
    print_color(f"输出目录: {output_dir}", Colors.YELLOW)
    print_color("="*60, Colors.BLUE)
    
    # 播放提示
    if success_count > 0:
        print_color("\n播放提示:", Colors.BLUE)
        first_pcm = list(output_dir.glob("*.pcm"))[0]
        print_color(f"播放PCM: ffplay -f s16le -ar {args.sample_rate} -ac 1 {first_pcm}", Colors.GREEN)

if __name__ == "__main__":
    main()
