"""
# Author: Jimmy Gan
# Date: Nov 24, 2025
# Index-TTS-vLLM API Server - Wrapper for Index-TTS-vLLM
# Version: 1.0.0
# Changes number: 1
"""

import argparse
import asyncio
import json
import time
import os
import struct
import re
from typing import Optional
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Header, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
import uvicorn
import aiohttp
import uuid
import numpy as np

# 有效的API密钥
VALID_API_KEYS = {
    "sk-5z6y7x8w9v0u1t2s3r4q5p6o7n8m9l0k1j2i3h4g"
}

# 停止TTS信号发送后忽略相同messageId的TTS生成的持续时间（毫秒）
ignoringDurationInMillisecondsAfterStopTTS = 5000

# Index-TTS-vLLM服务器配置
INDEX_TTS_SERVER_URL = "http://localhost:7860"

def verify_api_key(x_api_key: Optional[str] = Header(None)):
    """验证API密钥"""
    if x_api_key not in VALID_API_KEYS:
        raise HTTPException(
            status_code=400,
            detail={
                "errorCode": 4401,
                "message": "Invalid API key"
            }
        )

# 初始化FastAPI应用
app = FastAPI()

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 从文件头获取版本信息
with open(__file__, 'r', encoding='utf-8') as f:
    version_line = ''
    changes_line = ''
    for line in f:
        if line.startswith('# Version:'):
            version_line = line.strip()
        elif line.startswith('# Changes number:'):
            changes_line = line.strip()
        if version_line and changes_line:
            break

# 启动时记录版本信息
print(f"\n{'-'*50}")
print(f"Index-TTS-vLLM API Server {version_line.split(':')[-1].strip()}")
print(f"{changes_line}")
print(f"{'-'*50}\n")

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """处理FastAPI验证错误，使用一致的格式"""
    return JSONResponse(
        status_code=400,
        content={
            "errorCode": 4400,
            "message": "Invalid request parameters"
        }
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """处理HTTPException，使用一致的格式"""
    if isinstance(exc.detail, dict) and "errorCode" in exc.detail:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.detail
        )
    else:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "errorCode": exc.status_code,
                "message": str(exc.detail) if exc.detail else "An error occurred"
            }
        )

@app.get("/")
async def root():
    """根路径健康检查"""
    return {
        "errorCode": 0,
        "message": "Index-TTS-vLLM API is running"
    }

@app.post("/uploadAudio")
async def upload_audio(
    file: UploadFile = File(...),
    x_api_key: Optional[str] = Header(None)
):
    """上传音频文件用于声音克隆"""
    verify_api_key(x_api_key)
    
    try:
        # 创建保存目录
        upload_dir = os.path.join(os.path.dirname(__file__), "assets", "uploaded")
        os.makedirs(upload_dir, exist_ok=True)
        
        # 生成唯一文件名
        file_extension = os.path.splitext(file.filename)[1]
        unique_filename = f"{uuid.uuid4().hex}{file_extension}"
        file_path = os.path.join(upload_dir, unique_filename)
        
        # 保存文件
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)
        
        return {
            "errorCode": 0,
            "message": "Audio uploaded successfully",
            "data": {
                "filename": unique_filename,
                "path": f"assets/uploaded/{unique_filename}"
            }
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "errorCode": 5000,
                "message": f"Failed to upload audio: {str(e)}"
            }
        )

@app.post("/cloneVoice")
async def clone_voice(
    audio_file: UploadFile = File(...),
    speaker_name: str = Form(...),
    x_api_key: Optional[str] = Header(None)
):
    """克隆声音并注册到系统"""
    verify_api_key(x_api_key)
    
    try:
        # 保存上传的音频文件
        upload_dir = os.path.join(os.path.dirname(__file__), "assets", "cloned")
        os.makedirs(upload_dir, exist_ok=True)
        
        file_extension = os.path.splitext(audio_file.filename)[1]
        unique_filename = f"{speaker_name}_{uuid.uuid4().hex}{file_extension}"
        file_path = os.path.join(upload_dir, unique_filename)
        
        content = await audio_file.read()
        with open(file_path, "wb") as f:
            f.write(content)
        
        # 生成speaker ID (MD5)
        import hashlib
        speaker_id = hashlib.md5(speaker_name.encode()).hexdigest()
        
        return {
            "errorCode": 0,
            "message": "Voice cloned successfully",
            "data": {
                "speakerId": speaker_id,
                "speakerName": speaker_name,
                "audioPath": f"assets/cloned/{unique_filename}"
            }
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "errorCode": 5000,
                "message": f"Failed to clone voice: {str(e)}"
            }
        )

@app.get("/getSpeakerVoice/{filename}")
async def get_speaker_voice(filename: str):
    """获取说话人音频文件"""
    try:
        # 检查多个可能的目录
        possible_dirs = [
            os.path.join(os.path.dirname(__file__), "assets", "uploaded"),
            os.path.join(os.path.dirname(__file__), "assets", "cloned"),
            os.path.join(os.path.dirname(__file__), "assets")
        ]
        
        for directory in possible_dirs:
            file_path = os.path.join(directory, filename)
            if os.path.exists(file_path):
                return FileResponse(file_path)
        
        return JSONResponse(
            status_code=404,
            content={
                "errorCode": 4404,
                "message": "Audio file not found"
            }
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "errorCode": 5000,
                "message": f"Failed to retrieve audio: {str(e)}"
            }
        )

@app.get("/apiDoc")
async def api_doc():
    """API文档"""
    doc = {
        "errorCode": 0,
        "message": "Index-TTS-vLLM API Documentation",
        "data": {
            "version": "1.0.0",
            "endpoints": {
                "/": "健康检查",
                "/tts": "WebSocket TTS流式接口",
                "/uploadAudio": "上传音频文件",
                "/cloneVoice": "克隆声音",
                "/getSpeakerVoice/{filename}": "获取说话人音频"
            },
            "websocket": {
                "url": "ws://host:port/tts",
                "parameters": {
                    "text": "要合成的文本",
                    "speakerId": "说话人ID (默认: wm-sample-for-cosy)",
                    "language": "语言 (zh/zh-cn/en, 可选)",
                    "audioFormat": "音频格式 (pcm/mp3, 默认: pcm)",
                    "outputSampleRate": "输出采样率 (默认: 16000)",
                    "saveAudioFiles": "是否保存音频文件 (默认: false)",
                    "startTimeId": "开始时间ID (可选)",
                    "messageId": "消息ID (可选)"
                }
            }
        }
    }
    return doc

def split_text_by_punctuation(text: str, language: str = None) -> list:
    """
    根据标点符号分割文本
    
    Args:
        text: 要分割的文本
        language: 语言代码 (zh/en)
    
    Returns:
        分割后的文本段列表
    """
    # 定义标点符号
    chinese_punctuation = ['。', '！', '？', '；', '，', '：', '、', '…']
    english_punctuation = ['.', '!', '?', ';', ',', ':']
    
    # 根据语言选择标点符号
    if language and language.lower() in ['zh', 'zh-cn']:
        punctuation_markers = chinese_punctuation + english_punctuation
    elif language and language.lower() == 'en':
        punctuation_markers = english_punctuation
    else:
        # 自动检测或使用所有标点
        punctuation_markers = chinese_punctuation + english_punctuation
    
    segments = []
    current_segment = ""
    
    for char in text:
        current_segment += char
        if char in punctuation_markers:
            if current_segment.strip():
                segments.append(current_segment.strip())
            current_segment = ""
    
    # 添加剩余文本
    if current_segment.strip():
        segments.append(current_segment.strip())
    
    # 如果没有分割（文本中没有标点），使用整个文本
    if not segments:
        segments = [text]
    
    # 合并过短的段落以提高质量
    combined_segments = []
    current_combined = ""
    
    for segment in segments:
        if len(segment) < 5 or not current_combined:
            current_combined += " " + segment if current_combined else segment
        else:
            combined_segments.append(current_combined)
            current_combined = segment
    
    if current_combined:
        combined_segments.append(current_combined)
    
    return combined_segments if combined_segments else segments

async def call_index_tts_api(text: str, speaker_id: str, seed: int = 42) -> bytes:
    """
    调用Index-TTS-vLLM API生成音频
    
    Args:
        text: 要合成的文本
        speaker_id: 说话人ID或音频文件路径
        seed: 随机种子
    
    Returns:
        音频数据（WAV格式）
    """
    url = f"{INDEX_TTS_SERVER_URL}/tts_url"
    
    # 构建请求数据
    # 如果speaker_id看起来像文件路径，使用它；否则使用默认路径
    if speaker_id.endswith('.wav') or '/' in speaker_id:
        audio_paths = [speaker_id]
    else:
        # 使用speaker_id作为文件名
        audio_paths = [f"assets/{speaker_id}.wav"]
    
    payload = {
        "text": text,
        "audio_paths": audio_paths,
        "seed": seed
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as response:
            if response.status == 200:
                return await response.read()
            else:
                error_text = await response.text()
                raise Exception(f"Index-TTS API error: {response.status} - {error_text}")

def pcm_to_wav_header(sample_rate: int, num_channels: int, bits_per_sample: int, data_size: int) -> bytes:
    """
    生成WAV文件头
    
    Args:
        sample_rate: 采样率
        num_channels: 声道数
        bits_per_sample: 位深度
        data_size: 数据大小
    
    Returns:
        WAV头部字节
    """
    byte_rate = sample_rate * num_channels * bits_per_sample // 8
    block_align = num_channels * bits_per_sample // 8
    
    header = struct.pack('<4sI4s', b'RIFF', 36 + data_size, b'WAVE')
    header += struct.pack('<4sIHHIIHH', b'fmt ', 16, 1, num_channels, sample_rate, byte_rate, block_align, bits_per_sample)
    header += struct.pack('<4sI', b'data', data_size)
    
    return header

def wav_to_pcm(wav_data: bytes) -> bytes:
    """
    从WAV数据中提取PCM数据
    
    Args:
        wav_data: WAV格式音频数据
    
    Returns:
        PCM格式音频数据
    """
    # WAV文件头通常是44字节
    # 跳过头部，返回PCM数据
    if len(wav_data) > 44:
        return wav_data[44:]
    return wav_data

async def resample_audio(audio_data: bytes, source_rate: int, target_rate: int) -> bytes:
    """
    重采样音频数据
    
    Args:
        audio_data: 原始音频数据（PCM）
        source_rate: 源采样率
        target_rate: 目标采样率
    
    Returns:
        重采样后的音频数据
    """
    if source_rate == target_rate:
        return audio_data
    
    # 使用numpy进行简单的重采样
    audio_array = np.frombuffer(audio_data, dtype=np.int16)
    
    # 计算重采样比率
    ratio = target_rate / source_rate
    new_length = int(len(audio_array) * ratio)
    
    # 线性插值重采样
    indices = np.linspace(0, len(audio_array) - 1, new_length)
    resampled = np.interp(indices, np.arange(len(audio_array)), audio_array)
    
    return resampled.astype(np.int16).tobytes()

@app.websocket("/tts")
async def websocket_tts(websocket: WebSocket):
    """
    WebSocket TTS流式接口
    模拟流式响应，通过分段处理文本
    """
    await websocket.accept()
    print(f"[Index-TTS-WS] WebSocket连接已建立")
    
    # 存储活动的TTS请求
    active_tts_requests = {}
    # 存储被忽略的messageId及其过期时间
    ignored_message_ids = {}
    # 连接状态
    connection_active = True
    # 消息队列
    message_queue = asyncio.Queue()
    
    async def message_receiver():
        """接收客户端消息的后台任务"""
        nonlocal connection_active
        try:
            while connection_active:
                try:
                    data = await websocket.receive_text()
                    request_data = json.loads(data)
                    
                    # 检查是否是停止信号
                    if request_data.get("action") == "stop":
                        message_id = request_data.get("messageId")
                        if message_id is not None:
                            print(f"[Index-TTS-WS] 收到停止信号，messageId: {message_id}")
                            # 标记该messageId的请求为停止
                            if message_id in active_tts_requests:
                                active_tts_requests[message_id]["stop_requested"] = True
                            # 将messageId添加到忽略列表
                            expiration_time = time.time() + (ignoringDurationInMillisecondsAfterStopTTS / 1000.0)
                            ignored_message_ids[message_id] = expiration_time
                            print(f"[Index-TTS-WS] messageId {message_id} 已添加到忽略列表，过期时间: {expiration_time:.3f}")
                    else:
                        # 正常的TTS请求，添加到队列
                        await message_queue.put(request_data)
                        
                except WebSocketDisconnect:
                    print(f"[Index-TTS-WS] WebSocket连接已断开")
                    connection_active = False
                    break
                except Exception as e:
                    print(f"[Index-TTS-WS] 消息接收错误: {str(e)}")
                    break
        finally:
            connection_active = False
            print(f"[Index-TTS-WS] 消息接收器已停止")
    
    # 启动后台消息接收任务
    receiver_task = asyncio.create_task(message_receiver())
    
    try:
        while connection_active:
            # 清理过期的忽略messageId
            current_time = time.time()
            expired_message_ids = [msg_id for msg_id, exp_time in ignored_message_ids.items() if current_time > exp_time]
            for msg_id in expired_message_ids:
                del ignored_message_ids[msg_id]
                print(f"[Index-TTS-WS] 已从忽略列表中移除过期的messageId {msg_id}")
            
            # 从队列获取下一个TTS请求
            try:
                request_data = await asyncio.wait_for(message_queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            
            # 提取参数
            text = request_data.get("text", "")
            speaker_id = request_data.get("speakerId", "wm-sample-for-cosy")
            output_sample_rate = request_data.get("outputSampleRate", 16000)
            audio_format = request_data.get("audioFormat", "pcm").lower()
            start_time_id = request_data.get("startTimeId")
            message_id = request_data.get("messageId")
            save_audio_files = request_data.get("saveAudioFiles", False)
            language = request_data.get("language")
            seed = request_data.get("seed", 42)
            
            # 检查messageId是否在忽略列表中
            if message_id is not None and message_id in ignored_message_ids:
                current_time = time.time()
                expiration_time = ignored_message_ids[message_id]
                if current_time < expiration_time:
                    print(f"[Index-TTS-WS] 忽略messageId {message_id}的TTS请求（在忽略列表中）")
                    continue
                else:
                    del ignored_message_ids[message_id]
            
            # 注册此TTS请求
            if message_id is not None:
                active_tts_requests[message_id] = {"stop_requested": False}
            
            # 验证语言参数
            if language:
                language_lower = language.lower()
                if language_lower not in ['zh', 'zh-cn', 'en']:
                    error_response = {
                        "errorCode": 4400,
                        "message": f"Unsupported language: {language}. Supported: zh, zh-cn, en"
                    }
                    await websocket.send_text(json.dumps(error_response))
                    continue
                # 标准化语言代码
                if language_lower == 'zh':
                    language = 'zh-cn'
                else:
                    language = language_lower
            
            # 验证参数
            if not text:
                await websocket.send_text(json.dumps({"errorCode": 4400, "message": "Text is required"}))
                continue
            
            if audio_format not in ["mp3", "pcm"]:
                await websocket.send_text(json.dumps({"errorCode": 4400, "message": "Audio format must be 'mp3' or 'pcm'"}))
                continue
            
            print(f"[Index-TTS-WS] 处理请求 - 文本: {text[:50]}{'...' if len(text) > 50 else ''}")
            print(f"[Index-TTS-WS] 说话人: {speaker_id}, 采样率: {output_sample_rate}Hz, 格式: {audio_format}")
            
            # 判断是否有消息头
            has_message_headers = start_time_id is not None and message_id is not None
            if has_message_headers:
                print(f"[Index-TTS-WS] 消息头 - startTimeId: {start_time_id}, messageId: {message_id}")
            
            # 设置保存音频块的文件夹
            chunk_save_folder = None
            chunk_file_counter = 0
            if save_audio_files:
                chunk_save_folder = os.path.join(os.path.dirname(__file__), "saved_audio_chunks")
                os.makedirs(chunk_save_folder, exist_ok=True)
                print(f"[Index-TTS-WS] 创建/验证音频块保存文件夹: {chunk_save_folder}")
            
            try:
                # 分割文本
                text_segments = split_text_by_punctuation(text, language)
                print(f"[Index-TTS-WS] 将文本分割为 {len(text_segments)} 个段落")
                for i, segment in enumerate(text_segments):
                    print(f"[Index-TTS-WS] 段落 {i+1}: {segment[:50]}{'...' if len(segment) > 50 else ''}")
                
                # 处理每个文本段落
                for segment_idx, segment_text in enumerate(text_segments):
                    # 检查是否收到停止请求
                    if message_id is not None and message_id in active_tts_requests:
                        if active_tts_requests[message_id]["stop_requested"]:
                            print(f"[Index-TTS-WS] TTS生成已停止，messageId: {message_id}")
                            break
                    
                    segment_start_time = time.time()
                    print(f"[Index-TTS-WS] 处理段落 {segment_idx+1}/{len(text_segments)}: {segment_text[:50]}{'...' if len(segment_text) > 50 else ''}")
                    
                    try:
                        # 调用Index-TTS-vLLM API生成音频
                        wav_data = await call_index_tts_api(segment_text, speaker_id, seed)
                        
                        # 提取PCM数据
                        pcm_data = wav_to_pcm(wav_data)
                        
                        # Index-TTS默认输出24000Hz，需要重采样
                        source_rate = 24000
                        if output_sample_rate != source_rate:
                            pcm_data = await resample_audio(pcm_data, source_rate, output_sample_rate)
                        
                        segment_time = (time.time() - segment_start_time) * 1000
                        print(f"[Index-TTS-WS] 段落 {segment_idx+1} 生成时间: {segment_time:.2f}ms")
                        
                        # 保存音频块（如果需要）
                        if save_audio_files and chunk_save_folder:
                            chunk_file_counter += 1
                            chunk_filename = f"chunk_{message_id}_{chunk_file_counter}.pcm"
                            chunk_path = os.path.join(chunk_save_folder, chunk_filename)
                            with open(chunk_path, "wb") as f:
                                f.write(pcm_data)
                            print(f"[Index-TTS-WS] 保存音频块: {chunk_path}")
                        
                        # 发送音频数据
                        if audio_format == "pcm":
                            # 如果需要消息头，添加头部
                            if has_message_headers:
                                # 消息头格式: startTimeId (4字节) + messageId (4字节) + PCM数据
                                header = struct.pack('<II', start_time_id, message_id)
                                audio_chunk = header + pcm_data
                            else:
                                audio_chunk = pcm_data
                            
                            await websocket.send_bytes(audio_chunk)
                            print(f"[Index-TTS-WS] 已发送PCM音频块 {segment_idx+1}, 大小: {len(audio_chunk)} 字节")
                        else:
                            # MP3格式（需要转换）
                            # 这里简化处理，实际应该使用ffmpeg等工具转换
                            await websocket.send_text(json.dumps({
                                "errorCode": 5001,
                                "message": "MP3 format not yet supported, please use PCM"
                            }))
                            break
                        
                    except Exception as e:
                        print(f"[Index-TTS-WS] 段落 {segment_idx+1} 生成失败: {str(e)}")
                        await websocket.send_text(json.dumps({
                            "errorCode": 5000,
                            "message": f"Failed to generate audio for segment {segment_idx+1}: {str(e)}"
                        }))
                        break
                
                # 发送完成信号
                completion_message = {
                    "errorCode": 0,
                    "message": "TTS generation completed",
                    "segments": len(text_segments)
                }
                await websocket.send_text(json.dumps(completion_message))
                print(f"[Index-TTS-WS] TTS生成完成")
                
            except Exception as e:
                print(f"[Index-TTS-WS] TTS生成错误: {str(e)}")
                await websocket.send_text(json.dumps({
                    "errorCode": 5000,
                    "message": f"TTS generation failed: {str(e)}"
                }))
            finally:
                # 清理活动请求
                if message_id is not None and message_id in active_tts_requests:
                    del active_tts_requests[message_id]
    
    except WebSocketDisconnect:
        print(f"[Index-TTS-WS] WebSocket连接已断开")
    except Exception as e:
        print(f"[Index-TTS-WS] WebSocket错误: {str(e)}")
    finally:
        connection_active = False
        receiver_task.cancel()
        print(f"[Index-TTS-WS] WebSocket连接已关闭")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Index-TTS-vLLM API Server')
    parser.add_argument('--port', type=int, default=9001, help='端口号 (默认: 9001)')
    parser.add_argument('--index-tts-url', type=str, default="http://localhost:6006", 
                        help='Index-TTS-vLLM服务器URL (默认: http://localhost:6006)')
    args = parser.parse_args()
    
    # 更新Index-TTS服务器URL
    INDEX_TTS_SERVER_URL = args.index_tts_url
    
    uvicorn.run(app, host="0.0.0.0", port=args.port)
