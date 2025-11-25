#!/usr/bin/env python3
"""
MP3 Binary Combiner
Author: Jimmy Gan
Date: Nov 25, 2025

Combines all MP3 stream chunks from savedAudioFiles folder into a single MP3 file.
Uses direct binary-level concatenation without any processing.
Designed for IndexTTS MP3 streams.

Usage:
python combine_mp3_streams_into_single_mp3.py
"""

import os
import sys
import re
from datetime import datetime

def get_chunk_number(filename):
    """Extract chunk number from filename like 'chunk_0.mp3' -> 0"""
    match = re.search(r'chunk_(\d+)\.mp3', filename)
    return int(match.group(1)) if match else 0

def combine_mp3_files():
    """
    Combine all MP3 stream chunks in order from savedAudioFiles folder into a single MP3 file.
    Uses direct binary-level concatenation without any processing.
    """
    # 获取脚本所在目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # 从 mp3 目录向上4级到达项目根目录
    # mp3 -> combine_saved_audios -> utils -> my-info -> index-tts-vllm
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(script_dir))))
    
    # 定义目录
    mp3_folder = os.path.join(project_root, "savedAudioFiles")
    output_folder = os.path.join(script_dir, "combined_mp3_files")
    
    # 检查MP3文件夹是否存在
    if not os.path.exists(mp3_folder):
        print(f"Error: {mp3_folder} folder not found!")
        return False
    
    # 创建输出文件夹
    os.makedirs(output_folder, exist_ok=True)
    print(f"Created/verified output folder: {output_folder}")
    
    # 查找所有MP3文件并排序
    mp3_files = []
    for filename in os.listdir(mp3_folder):
        if filename.endswith(".mp3"):
            mp3_path = os.path.join(mp3_folder, filename)
            mp3_files.append((filename, mp3_path))
    
    if not mp3_files:
        print(f"No .mp3 files found in {mp3_folder}")
        return False
    
    # 按chunk编号排序(自然排序)确保正确顺序
    mp3_files.sort(key=lambda x: get_chunk_number(x[0]))
    
    print(f"\nFound {len(mp3_files)} MP3 files to combine")
    print(f"Files in order:")
    for idx, (filename, filepath) in enumerate(mp3_files, 1):
        file_size = os.path.getsize(filepath)
        print(f"  {idx}. {filename} ({file_size} bytes)")
    
    # 创建输出MP3文件
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_mp3 = os.path.join(output_folder, f"combined_{timestamp}.mp3")
    
    print(f"\nCombining MP3 files at binary level...")
    print(f"Note: Binary concatenation preserves original sample rate")
    
    # 合并所有MP3文件 - 直接二进制拼接
    try:
        total_bytes_written = 0
        
        with open(output_mp3, 'wb') as outfile:
            for idx, (filename, mp3_path) in enumerate(mp3_files):
                with open(mp3_path, 'rb') as infile:
                    data = infile.read()
                    print(f"  {filename}: Writing {len(data)} bytes")
                    outfile.write(data)
                    total_bytes_written += len(data)
        
        output_size_kb = total_bytes_written / 1024
        print(f"\nCombined MP3 file created: {output_size_kb:.1f}KB ({total_bytes_written} bytes)")
        
        print(f"\n" + "=" * 60)
        print(f"COMBINED MP3 FILE SAVED TO:")
        print(f"   {output_mp3}")
        print(f"=" * 60)
        
        return True
        
    except Exception as e:
        print(f"Failed to combine MP3 files: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("MP3 Binary Combiner")
    print("=" * 60)
    print("Direct binary concatenation of MP3 stream chunks")
    print("=" * 60)
    print()
    
    success = combine_mp3_files()
    
    if success:
        print("\nMP3 combination completed successfully!")
    else:
        print("\nMP3 combination failed!")
