"""
# Author: Jimmy Gan
# Date: Nov 24, 2025
# Index-TTS-vLLM API Server - Wrapper for Index-TTS-vLLM
# Version: 1.4.6
# Changes number: 7
#
# Common cmd:
# head -n 10 /mnt/index-tts-vllm/api.py
# modelscope download --model kusuriuri/Index-TTS-1.5-vLLM --local_dir ./checkpoints/Index-TTS-1.5-vLLM
# python api_server.py --port 6006 --model_dir /mnt/index-tts-vllm/checkpoints/Index-TTS-1.5-vLLM --gpu_memory_utilization 0.25
# docker exec -it index-tts-vllm /bin/bash
# python api.py --port 9001
"""

import argparse
import asyncio
import json
import time
import os
import struct
import re
import shutil
import subprocess
import tempfile
from typing import Optional
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Header, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
import uvicorn
import aiohttp
import uuid
import numpy as np
import select

# 有效的API密钥
VALID_API_KEYS = {
    "sk-5z6y7x8w9v0u1t2s3r4q5p6o7n8m9l0k1j2i3h4g"
}

# 停止TTS信号发送后忽略相同messageId的TTS生成的持续时间（毫秒）
ignoringDurationInMillisecondsAfterStopTTS = 5000

# Index-TTS-vLLM服务器配置
INDEX_TTS_SERVER_URL = "http://localhost:6006"

# TTS服务就绪状态标志（用于健康检查）
tts_server_ready = False
tts_server_check_task = None

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

async def check_tts_server_ready():
    """后台任务：每5秒检查api_server.py是否就绪，直到能获取真实TTS流"""
    global tts_server_ready
    test_text = "你好"
    test_speaker = "jay_promptvn"
    
    while not tts_server_ready:
        try:
            print(f"[Health-Check] 正在检查TTS服务是否就绪...")
            url = f"{INDEX_TTS_SERVER_URL}/tts_url"
            payload = {
                "text": test_text,
                "audio_paths": [f"assets/{test_speaker}.wav"],
                "seed": 42
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=60)) as response:
                    if response.status == 200:
                        wav_data = await response.read()
                        # 检查是否为有效的WAV数据（至少有WAV头部）
                        if len(wav_data) > 44:  # WAV头部至少44字节
                            tts_server_ready = True
                            print(f"[Health-Check] TTS服务已就绪！收到{len(wav_data)}字节的WAV数据")
                            return
                        else:
                            print(f"[Health-Check] TTS服务返回数据过小: {len(wav_data)}字节")
                    else:
                        error_text = await response.text()
                        print(f"[Health-Check] TTS服务返回错误: {response.status} - {error_text[:100]}")
        except asyncio.TimeoutError:
            print(f"[Health-Check] TTS服务请求超时")
        except Exception as e:
            print(f"[Health-Check] TTS服务检查失败: {str(e)}")
        
        # 等待5秒后重试
        await asyncio.sleep(5)

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

@app.on_event("startup")
async def startup_event():
    """应用启动时开始后台检查TTS服务"""
    global tts_server_check_task
    tts_server_check_task = asyncio.create_task(check_tts_server_ready())

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

@app.api_route("/", methods=["GET", "HEAD"])
async def root():
    """根路径健康检查 - 只有当TTS服务就绪时才返回健康"""
    global tts_server_ready
    if not tts_server_ready:
        # 返回503表示TTS服务未就绪，ALB不会将用户请求转发到此实例
        return JSONResponse(
            status_code=503,
            content={
                "errorCode": 5003,
                "message": "TTS service is not ready yet, model is still loading"
            }
        )
    return {
        "errorCode": 0,
        "message": "Index-TTS-vLLM API is running"
    }

@app.post("/denoiseAudio")
async def denoise_audio(
    audio: UploadFile = File(...),
    sessionId: str = Form(...),
    inputSampleRate: int = Form(16000),
    outputSampleRate: int = Form(16000),
    x_api_key: Optional[str] = Header(None)
):
    """降噪音频API - 使用RNNoise降噪，支持自定义输入输出采样率
    
    参数:
        audio: PCM音频文件
        sessionId: 会话ID (UUID格式)
        inputSampleRate: 输入PCM的采样率 (默认: 16000)
        outputSampleRate: 输出WAV的采样率 (默认: 16000)
        x_api_key: API密钥
    
    注意: RNNoise内部使用48kHz处理，会自动进行重采样
    """
    # 验证API密钥
    verify_api_key(x_api_key)
    
    # 验证sessionId是有效的UUID
    try:
        uuid_obj = uuid.UUID(sessionId)
    except Exception:
        raise HTTPException(
            status_code=200,
            detail={
                "errorCode": 4608,
                "message": "sessionId must be a valid UUID string, e.g. 69361790-4120-49de-8c37-58c3e3eaf388"
            }
        )
    
    # 验证文件是PCM格式
    if not audio.filename.lower().endswith('.pcm'):
        raise HTTPException(
            status_code=200,
            detail={
                "errorCode": 4609,
                "message": "Only PCM files are allowed. Please upload a .pcm file."
            }
        )
    
    try:
        # 生成MD5作为speakerId
        import hashlib
        md5_generator = hashlib.md5()
        md5_generator.update(str(uuid.uuid4()).encode())
        md5_id = md5_generator.hexdigest()
        
        # 创建denoised目录下的sessionId子文件夹
        denoised_dir = os.path.join(os.path.dirname(__file__), "assets", "denoised")
        session_dir = os.path.join(denoised_dir, sessionId)
        os.makedirs(session_dir, exist_ok=True)
        print(f"[DenoiseAudio] Created session directory: {session_dir}")
        
        # 保存上传的PCM文件到session目录
        pcm_content = await audio.read()
        pcm_path = os.path.join(session_dir, f"{md5_id}.pcm")
        with open(pcm_path, 'wb') as f:
            f.write(pcm_content)
        print(f"[DenoiseAudio] Saved PCM file: {pcm_path}")
        
        # 转换PCM为WAV格式
        wav_path = os.path.join(session_dir, f"{md5_id}.wav")
        
        print(f"[DenoiseAudio] Input sample rate: {inputSampleRate} Hz, Output sample rate: {outputSampleRate} Hz")
        
        try:
            # 使用ffmpeg转换PCM到WAV (保持输入采样率)
            cmd = [
                'ffmpeg',
                '-f', 's16le',  # PCM 16位小端格式
                '-ar', str(inputSampleRate),  # 输入采样率
                '-ac', '1',      # 输入声道（单声道）
                '-i', pcm_path,
                '-ar', str(inputSampleRate),  # 输出采样率保持与输入一致
                '-ac', '1',      # 输出声道（单声道）
                '-y',            # 覆盖输出文件
                wav_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            print(f"[DenoiseAudio] Converted PCM to WAV: {wav_path}")
        except subprocess.CalledProcessError as e:
            raise HTTPException(
                status_code=200,
                detail={
                    "errorCode": 4610,
                    "message": f"Failed to convert PCM to WAV: {e.stderr}"
                }
            )
        except FileNotFoundError:
            raise HTTPException(
                status_code=200,
                detail={
                    "errorCode": 4611,
                    "message": "ffmpeg not found"
                }
            )
        
        # 验证WAV文件已创建
        if not os.path.exists(wav_path):
            raise HTTPException(
                status_code=200,
                detail={
                    "errorCode": 4614,
                    "message": "WAV file was not created"
                }
            )
        
        # 使用wqDenoiser进行降噪处理
        denoiser_path = os.path.join(os.path.dirname(__file__), "denoiseAudios", "wqDenoiser")
        denoised_wav_path = os.path.join(session_dir, f"{md5_id}_denoised.wav")
        
        try:
            # wqDenoiser参数: <input.wav> [output.wav] [inputSampleRate] [outputSampleRate]
            # wqDenoiser内部使用48kHz处理，会自动进行重采样
            denoise_cmd = [
                denoiser_path,
                wav_path,
                denoised_wav_path,
                str(inputSampleRate),   # 输入采样率
                str(outputSampleRate)   # 输出采样率
            ]
            result = subprocess.run(denoise_cmd, capture_output=True, text=True, check=True)
            print(f"[DenoiseAudio] Denoised audio: {denoised_wav_path} (input: {inputSampleRate}Hz, output: {outputSampleRate}Hz)")
            
            # 用降噪后的文件替换原文件
            if os.path.exists(denoised_wav_path):
                os.replace(denoised_wav_path, wav_path)
                print(f"[DenoiseAudio] Replaced original WAV with denoised version")
        except subprocess.CalledProcessError as e:
            print(f"[DenoiseAudio] Warning: Denoising failed: {e.stderr}, using original WAV")
            # 降噪失败时继续使用原始WAV文件
        except FileNotFoundError:
            print(f"[DenoiseAudio] Warning: wqDenoiser not found at {denoiser_path}, using original WAV")
            # 找不到降噪程序时继续使用原始WAV文件
        
        # 清理PCM文件
        if os.path.exists(pcm_path):
            os.unlink(pcm_path)
            print(f"[DenoiseAudio] Cleaned up PCM file")
        
        return {
            "errorCode": 0,
            "message": "Audio denoised successfully",
            "sessionId": sessionId,
            "speakerId": md5_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=200,
            detail={
                "errorCode": 4615,
                "message": f"Internal server error: {str(e)}"
            }
        )

class CloneVoiceRequest(BaseModel):
    text: str
    sessionId: str

@app.post("/cloneVoice")
async def clone_voice(request: Request, body: CloneVoiceRequest, x_api_key: Optional[str] = Header(None)):
    """克隆声音API - 使用TTS生成音频"""
    print(f"[CloneVoice] Request received: sessionId={body.sessionId}, text length={len(body.text)}")
    
    # 验证API密钥
    verify_api_key(x_api_key)
    
    # 验证sessionId是有效的UUID
    try:
        uuid_obj = uuid.UUID(body.sessionId)
    except Exception:
        raise HTTPException(
            status_code=200,
            detail={
                "errorCode": 4608,
                "message": "sessionId must be a valid UUID string, e.g. 69361790-4120-49de-8c37-58c3e3eaf388"
            }
        )
    
    try:
        # 在denoised目录的sessionId子文件夹中查找WAV文件
        denoised_dir = os.path.join(os.path.dirname(__file__), "assets", "denoised")
        session_dir = os.path.join(denoised_dir, body.sessionId)
        print(f"[CloneVoice] Looking for WAV files in: {session_dir}")
        
        found_wav_file = None
        speaker_id = None
        
        if os.path.exists(session_dir):
            # 查找WAV文件
            for filename in os.listdir(session_dir):
                if filename.endswith('.wav'):
                    # 提取speakerId（移除.wav扩展名）
                    speaker_id = os.path.splitext(filename)[0]
                    # 验证是有效的MD5（32字符十六进制）
                    if len(speaker_id) == 32 and all(c in "0123456789abcdef" for c in speaker_id.lower()):
                        found_wav_file = os.path.join(session_dir, filename)
                        print(f"[CloneVoice] Found WAV file: {found_wav_file}, speaker_id: {speaker_id}")
                        break
        
        if not found_wav_file or not speaker_id:
            print(f"[CloneVoice] ERROR: No WAV file found in session directory: {session_dir}")
            raise HTTPException(
                status_code=200,
                detail={
                    "errorCode": 4516,
                    "message": f"No denoised WAV file found for sessionId {body.sessionId}. Please ensure audio denoising is completed first."
                }
            )
        
        # 创建assets目录（如果不存在）
        assets_dir = os.path.join(os.path.dirname(__file__), "assets")
        os.makedirs(assets_dir, exist_ok=True)
        print(f"[CloneVoice] Created/verified assets directory: {assets_dir}")
        
        # 创建临时目录用于存储PCM chunks
        temp_dir = os.path.join(os.path.dirname(__file__), "temp_clone_audio", speaker_id)
        os.makedirs(temp_dir, exist_ok=True)
        print(f"[CloneVoice] Created temp directory: {temp_dir}")
        
        try:
            # 分割文本为段落
            text_segments = split_text_by_punctuation(body.text)
            print(f"[CloneVoice] Split text into {len(text_segments)} segments")
            
            # 存储所有PCM文件路径
            pcm_files = []
            
            # 为每个段落生成音频
            for segment_idx, segment_text in enumerate(text_segments):
                print(f"[CloneVoice] Generating audio for segment {segment_idx+1}/{len(text_segments)}: {segment_text[:50]}...")
                
                try:
                    # 调用Index-TTS API生成音频（使用找到的WAV文件作为参考）
                    wav_data = await call_index_tts_api(segment_text, found_wav_file, seed=42)
                    
                    # 提取PCM数据
                    pcm_data = wav_to_pcm(wav_data)
                    
                    # Index-TTS默认输出24000Hz，重采样到16000Hz
                    source_rate = 24000
                    target_rate = 16000
                    if source_rate != target_rate:
                        pcm_data = await resample_audio(pcm_data, source_rate, target_rate)
                    
                    # 保存PCM chunk
                    chunk_filename = f"chunk_{segment_idx+1}.pcm"
                    chunk_path = os.path.join(temp_dir, chunk_filename)
                    with open(chunk_path, 'wb') as f:
                        f.write(pcm_data)
                    pcm_files.append(chunk_path)
                    print(f"[CloneVoice] Saved PCM chunk: {chunk_filename} ({len(pcm_data)} bytes)")
                    
                except Exception as e:
                    print(f"[CloneVoice] ERROR generating audio for segment {segment_idx+1}: {e}")
                    raise HTTPException(
                        status_code=200,
                        detail={
                            "errorCode": 4518,
                            "message": f"Failed to generate audio for text segment: {str(e)}"
                        }
                    )
            
            # 使用ffmpeg合并所有PCM文件
            print(f"[CloneVoice] Combining {len(pcm_files)} PCM files using ffmpeg...")
            combined_pcm_path = os.path.join(temp_dir, "combined.pcm")
            
            # 构建ffmpeg命令
            input_args = []
            filter_inputs = []
            
            for idx, pcm_file in enumerate(pcm_files):
                input_args.extend([
                    '-f', 's16le',      # 输入格式：16位小端PCM
                    '-ar', '16000',     # 采样率
                    '-ac', '1',         # 单声道
                    '-i', pcm_file      # 输入文件
                ])
                filter_inputs.append(f'[{idx}:a]')
            
            # 构建concat filter
            concat_filter = f"{''.join(filter_inputs)}concat=n={len(pcm_files)}:v=0:a=1[out]"
            
            # 完整的ffmpeg命令
            cmd = [
                'ffmpeg',
                *input_args,
                '-filter_complex', concat_filter,
                '-map', '[out]',
                '-f', 's16le',
                '-ar', '16000',
                '-ac', '1',
                '-y',
                combined_pcm_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                print(f"[CloneVoice] ffmpeg error: {result.stderr}")
                raise HTTPException(
                    status_code=200,
                    detail={
                        "errorCode": 4519,
                        "message": f"Failed to combine PCM files: {result.stderr}"
                    }
                )
            
            print(f"[CloneVoice] Successfully combined PCM files")
            
            # 转换合并后的PCM为WAV
            target_wav_path = os.path.join(assets_dir, f"{speaker_id}.wav")
            wav_cmd = [
                'ffmpeg',
                '-f', 's16le',
                '-ar', '16000',
                '-ac', '1',
                '-i', combined_pcm_path,
                '-y',
                target_wav_path
            ]
            
            result = subprocess.run(wav_cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                print(f"[CloneVoice] WAV conversion error: {result.stderr}")
                raise HTTPException(
                    status_code=200,
                    detail={
                        "errorCode": 4520,
                        "message": f"Failed to convert PCM to WAV: {result.stderr}"
                    }
                )
            
            print(f"[CloneVoice] Successfully created WAV file: {target_wav_path}")
            
            # 将WAV转换为MP3（用于移动端下载，体积更小）
            target_mp3_path = os.path.join(assets_dir, f"{speaker_id}.mp3")
            mp3_cmd = [
                'ffmpeg',
                '-i', target_wav_path,
                '-b:a', '128k',  # 128kbps比特率
                '-y',
                target_mp3_path
            ]
            
            result = subprocess.run(mp3_cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                print(f"[CloneVoice] MP3 conversion error: {result.stderr}")
                raise HTTPException(
                    status_code=200,
                    detail={
                        "errorCode": 4521,
                        "message": f"Failed to convert WAV to MP3: {result.stderr}"
                    }
                )
            
            print(f"[CloneVoice] Successfully created MP3 file: {target_mp3_path}")
            
            # 保存文本到txt文件
            txt_path = os.path.join(assets_dir, f"{speaker_id}.txt")
            with open(txt_path, 'w', encoding='utf-8') as txt_file:
                txt_file.write(body.text)
            print(f"[CloneVoice] Saved text file: {txt_path}")
            
        finally:
            # 清理临时目录
            try:
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)
                    print(f"[CloneVoice] Cleaned up temp directory: {temp_dir}")
            except Exception as e:
                print(f"[CloneVoice] Warning: Failed to clean up temp directory: {e}")
        
        # 清理session目录（如果为空）
        try:
            if os.path.exists(session_dir) and not os.listdir(session_dir):
                os.rmdir(session_dir)
                print(f"[CloneVoice] Cleaned up empty session directory: {session_dir}")
        except Exception as e:
            print(f"[CloneVoice] Warning: Failed to clean up session directory: {e}")
        
        # 构建MP3 URL（移动端使用，体积更小）
        host = request.url.hostname
        port = request.url.port
        scheme = request.url.scheme
        if port is None or port == 80:
            mp3_url = f"{scheme}://{host}/resource/{speaker_id}.mp3"
        else:
            mp3_url = f"{scheme}://{host}:{port}/resource/{speaker_id}.mp3"
        
        return {
            "errorCode": 0,
            "message": "Voice cloned successfully",
            "speakerId": speaker_id,
            "mp3Url": mp3_url,
            "text": body.text
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[CloneVoice] ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=200,
            detail={
                "errorCode": 4517,
                "message": f"Failed to clone voice: {str(e)}"
            }
        )

@app.get("/resource/{resource_id}")
async def get_resource(resource_id: str, request: Request):
    """资源API - 获取音频文件（支持WAV和MP3）"""
    # 如果resource_id以.mp3结尾，直接提供MP3文件
    if resource_id.endswith(".mp3"):
        md5_part = resource_id[:-4]
        # 验证是有效的MD5（32字符十六进制）
        if len(md5_part) == 32 and all(c in "0123456789abcdef" for c in md5_part.lower()):
            # 在assets目录中查找MP3文件
            assets_dir = os.path.join(os.path.dirname(__file__), "assets")
            mp3_path = os.path.join(assets_dir, f"{md5_part}.mp3")
            
            if os.path.exists(mp3_path):
                # 提供MP3文件
                return FileResponse(mp3_path, media_type="audio/mpeg", filename=f"{md5_part}.mp3")
            else:
                raise HTTPException(
                    status_code=200,
                    detail={
                        "errorCode": 4533,
                        "message": "MP3 file not found"
                    }
                )
        else:
            raise HTTPException(
                status_code=200,
                detail={
                    "errorCode": 4534,
                    "message": "Invalid MD5 format for mp3 file"
                }
            )
    # 如果resource_id以.wav结尾，直接提供WAV文件
    elif resource_id.endswith(".wav"):
        md5_part = resource_id[:-4]
        # 验证是有效的MD5（32字符十六进制）
        if len(md5_part) == 32 and all(c in "0123456789abcdef" for c in md5_part.lower()):
            # 在assets目录中查找WAV文件
            assets_dir = os.path.join(os.path.dirname(__file__), "assets")
            wav_path = os.path.join(assets_dir, f"{md5_part}.wav")
            
            if os.path.exists(wav_path):
                # 提供WAV文件
                return FileResponse(wav_path, media_type="audio/wav", filename=f"{md5_part}.wav")
            else:
                raise HTTPException(
                    status_code=200,
                    detail={
                        "errorCode": 4530,
                        "message": "WAV file not found"
                    }
                )
        else:
            raise HTTPException(
                status_code=200,
                detail={
                    "errorCode": 4531,
                    "message": "Invalid MD5 format for wav file"
                }
            )
    else:
        # 如果resource_id是MD5，返回MP3资源URL（移动端使用）
        if len(resource_id) == 32 and all(c in "0123456789abcdef" for c in resource_id.lower()):
            # 构建MP3 URL
            host = request.url.hostname
            port = request.url.port
            scheme = request.url.scheme
            if port is None or port == 80:
                mp3_url = f"{scheme}://{host}/resource/{resource_id}.mp3"
            else:
                mp3_url = f"{scheme}://{host}:{port}/resource/{resource_id}.mp3"
            
            return {
                "errorCode": 0,
                "message": "success",
                "mp3Url": mp3_url
            }
        else:
            raise HTTPException(
                status_code=200,
                detail={
                    "errorCode": 4532,
                    "message": "Invalid resource ID format"
                }
            )

@app.get("/apiDoc")
async def api_doc():
    """API文档"""
    try:
        # 获取HTML文档文件路径
        html_file_path = os.path.join(os.path.dirname(__file__), "api_documentation.html")
        
        # 检查文件是否存在
        if not os.path.exists(html_file_path):
            raise HTTPException(
                status_code=200,
                detail={
                    "errorCode": 4540,
                    "message": "API documentation file not found"
                }
            )
        
        # 读取并返回HTML内容
        with open(html_file_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        return HTMLResponse(content=html_content, status_code=200)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=200,
            detail={
                "errorCode": 4541,
                "message": f"Failed to load API documentation: {str(e)}"
            }
        )

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
    
    # 使用正则表达式分割文本，保留标点符号
    # 构建正则表达式模式，匹配任意标点符号
    escaped_punctuation = [re.escape(p) for p in punctuation_markers]
    pattern = f"([{''.join(escaped_punctuation)}])"
    
    # 分割文本
    parts = re.split(pattern, text)
    
    # 重新组合：将标点符号附加到前面的文本段
    segments = []
    current_segment = ""
    
    for i, part in enumerate(parts):
        if not part:  # 跳过空字符串
            continue
        if part in punctuation_markers:
            # 这是一个标点符号，附加到当前段落
            current_segment += part
            if current_segment.strip():
                segments.append(current_segment.strip())
            current_segment = ""
        else:
            # 这是普通文本
            current_segment += part
    
    # 添加剩余文本（没有以标点结尾的部分）
    if current_segment.strip():
        segments.append(current_segment.strip())
    
    # 如果没有分割（文本中没有标点），使用整个文本
    if not segments:
        segments = [text]
    
    # 合并过短的段落以提高质量（阈值设为3，允许短中文短语保持独立）
    combined_segments = []
    current_combined = ""
    
    for segment in segments:
        if len(segment) < 3 or not current_combined:
            current_combined += " " + segment if current_combined else segment
        else:
            combined_segments.append(current_combined)
            current_combined = segment
    
    if current_combined:
        combined_segments.append(current_combined)
    
    result = combined_segments if combined_segments else segments
    print(f"[TextSplit] 最终段落数: {len(result)}, 段落: {result}", flush=True)
    
    return result

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
    # 确保speaker_id是字符串类型（兼容melo api发送int类型的情况）
    speaker_id = str(speaker_id)
    
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

async def pcm_to_mp3(pcm_data: bytes, sample_rate: int, bitrate: int = 128) -> bytes:
    """
    使用ffmpeg将PCM数据转换为MP3格式
    
    Args:
        pcm_data: PCM音频数据（s16le格式）
        sample_rate: 采样率
        bitrate: MP3比特率（kbps，默认128）
    
    Returns:
        MP3格式的音频数据
    """
    # 创建临时文件
    with tempfile.NamedTemporaryFile(suffix='.pcm', delete=False) as pcm_temp:
        pcm_temp.write(pcm_data)
        pcm_temp_path = pcm_temp.name
    
    with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as mp3_temp:
        mp3_temp_path = mp3_temp.name
    
    try:
        # 使用ffmpeg转换PCM为MP3
        cmd = [
            'ffmpeg',
            '-f', 's16le',           # 输入格式：16位小端PCM
            '-ar', str(sample_rate), # 采样率
            '-ac', '1',              # 单声道
            '-i', pcm_temp_path,     # 输入文件
            '-b:a', f'{bitrate}k',   # 比特率
            '-y',                    # 覆盖输出文件
            mp3_temp_path
        ]
        
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        if result.returncode != 0:
            raise Exception(f"ffmpeg conversion failed: {result.stderr}")
        
        # 读取MP3数据
        with open(mp3_temp_path, 'rb') as f:
            mp3_data = f.read()
        
        return mp3_data
        
    finally:
        # 清理临时文件
        try:
            os.unlink(pcm_temp_path)
            os.unlink(mp3_temp_path)
        except:
            pass


def calculate_mp3_frame_length(version, layer, bitrate_index, sample_rate_index, padding):
    """
    计算MP3帧长度
    
    Args:
        version: MPEG版本 (0=2.5, 2=2, 3=1)
        layer: Layer (1=III, 2=II, 3=I)
        bitrate_index: 比特率索引
        sample_rate_index: 采样率索引
        padding: 填充位
    
    Returns:
        帧长度（字节）
    """
    # 比特率表（kbps）
    # MPEG-1 Layer III
    bitrate_table_v1_l3 = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0]
    # MPEG-2/2.5 Layer III
    bitrate_table_v2_l3 = [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 0]
    
    # 采样率表（Hz）
    sample_rate_table = {
        3: [44100, 48000, 32000],  # MPEG-1
        2: [22050, 24000, 16000],  # MPEG-2
        0: [11025, 12000, 8000]    # MPEG-2.5
    }
    
    # 获取比特率
    if version == 3:  # MPEG-1
        bitrate = bitrate_table_v1_l3[bitrate_index] * 1000
    else:  # MPEG-2 or MPEG-2.5
        bitrate = bitrate_table_v2_l3[bitrate_index] * 1000
    
    # 获取采样率
    if version not in sample_rate_table:
        return 0
    if sample_rate_index >= len(sample_rate_table[version]):
        return 0
    sample_rate = sample_rate_table[version][sample_rate_index]
    
    if bitrate == 0 or sample_rate == 0:
        return 0
    
    # Layer III帧长度计算公式
    if version == 3:  # MPEG-1
        frame_length = (144 * bitrate) // sample_rate + padding
    else:  # MPEG-2 or MPEG-2.5
        frame_length = (72 * bitrate) // sample_rate + padding
    
    return frame_length


class GaplessMP3Encoder:
    """
    无缝MP3编码器 - 保持单一FFmpeg进程，实现真正的无缝MP3流
    
    关键特性:
    1. 保持单一编码器实例，维护内部状态一致性
    2. PCM缓冲区处理帧边界对齐（1152样本）
    3. 只输出纯净的MP3音频帧，无元数据
    """
    
    MP3_FRAME_SAMPLES = 1152  # MPEG-1 Layer III每帧样本数
    
    def __init__(self, sample_rate=24000, bitrate='128k'):
        self.sample_rate = sample_rate
        self.bitrate = bitrate
        self.process = None
        self.pcm_buffer = np.array([], dtype=np.float32)  # PCM缓冲区
        self.mp3_buffer = b''  # MP3输出缓冲区
        self.is_first_chunk = True
        self.frames_written = 0
        
    def start(self):
        """启动FFmpeg编码器进程"""
        if shutil.which('ffmpeg') is None:
            raise FileNotFoundError("FFmpeg not found")
        
        # 启动持久的FFmpeg进程
        self.process = subprocess.Popen(
            [
                'ffmpeg',
                '-f', 's16le',
                '-ar', str(self.sample_rate),
                '-ac', '1',
                '-i', 'pipe:0',
                '-c:a', 'libmp3lame',
                '-b:a', self.bitrate,
                '-q:a', '2',
                '-write_id3v1', '0',
                '-write_id3v2', '0',
                '-id3v2_version', '0',
                '-write_xing', '0',
                '-fflags', '+bitexact',
                '-f', 'mp3',
                'pipe:1'
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0  # 无缓冲，实时输出
        )
        print(f"[GaplessMP3] Encoder started: {self.sample_rate}Hz, {self.bitrate}")
        
    def feed_pcm(self, pcm_float, volume_multiplier=1.0):
        """
        输入PCM数据，返回可用的MP3帧
        
        Args:
            pcm_float: float32 PCM数据 [-1.0, 1.0]
            volume_multiplier: 音量倍数
        
        Returns:
            bytes: 纯净的MP3音频帧数据
        """
        if self.process is None:
            self.start()
        
        # 应用音量并裁剪
        audio = pcm_float * volume_multiplier
        audio = np.clip(audio, -1.0, 1.0)
        
        # 添加到PCM缓冲区
        self.pcm_buffer = np.concatenate([self.pcm_buffer, audio])
        
        # 计算可以编码的完整帧数
        complete_frames = len(self.pcm_buffer) // self.MP3_FRAME_SAMPLES
        
        if complete_frames == 0:
            return b''  # 缓冲区不足一帧
        
        # 取出完整帧的样本
        samples_to_encode = complete_frames * self.MP3_FRAME_SAMPLES
        pcm_to_encode = self.pcm_buffer[:samples_to_encode]
        self.pcm_buffer = self.pcm_buffer[samples_to_encode:]  # 保留剩余样本
        
        # 转换为16位PCM并写入编码器
        pcm_int16 = (pcm_to_encode * 32767).astype(np.int16)
        self.process.stdin.write(pcm_int16.tobytes())
        self.process.stdin.flush()
        
        # 非阻塞读取MP3输出
        mp3_output = b''
        
        while True:
            # 检查是否有数据可读（非阻塞）
            readable, _, _ = select.select([self.process.stdout], [], [], 0.01)
            if not readable:
                break
            
            chunk = self.process.stdout.read(4096)
            if not chunk:
                break
            mp3_output += chunk
        
        if mp3_output:
            # 提取纯净的MP3帧
            clean_frames = self._extract_audio_frames(mp3_output)
            self.frames_written += 1
            return clean_frames
        
        return b''
    
    def flush(self):
        """
        刷新编码器，获取剩余的MP3数据
        
        Returns:
            bytes: 剩余的MP3帧数据
        """
        if self.process is None:
            return b''
        
        # 如果缓冲区还有数据，用静音填充到完整帧
        if len(self.pcm_buffer) > 0:
            padding_needed = self.MP3_FRAME_SAMPLES - (len(self.pcm_buffer) % self.MP3_FRAME_SAMPLES)
            if padding_needed < self.MP3_FRAME_SAMPLES:
                self.pcm_buffer = np.concatenate([self.pcm_buffer, np.zeros(padding_needed, dtype=np.float32)])
            
            pcm_int16 = (self.pcm_buffer * 32767).astype(np.int16)
            self.process.stdin.write(pcm_int16.tobytes())
            self.pcm_buffer = np.array([], dtype=np.float32)
        
        # 关闭stdin触发编码器刷新
        self.process.stdin.close()
        
        # 读取所有剩余输出
        mp3_output = self.process.stdout.read()
        self.process.wait()
        
        if mp3_output:
            # 提取纯净帧，但跳过最后可能包含LAME标签的帧
            clean_frames = self._extract_audio_frames(mp3_output, skip_last=True)
            return clean_frames
        
        return b''
    
    def _extract_audio_frames(self, mp3_data, skip_last=False):
        """
        从MP3数据中提取纯净的音频帧
        
        Args:
            mp3_data: 原始MP3数据
            skip_last: 是否跳过最后一帧（可能包含LAME标签）
        
        Returns:
            bytes: 纯净的MP3音频帧
        """
        if len(mp3_data) < 4:
            return mp3_data
        
        data = bytes(mp3_data)
        pos = 0
        frames = []
        
        # 跳过ID3头部
        if data[:3] == b'ID3' and len(data) >= 10:
            id3_size = ((data[6] & 0x7F) << 21) | ((data[7] & 0x7F) << 14) | \
                       ((data[8] & 0x7F) << 7) | (data[9] & 0x7F)
            pos = 10 + id3_size
        
        while pos < len(data) - 4:
            if data[pos] == 0xFF and (data[pos + 1] & 0xE0) == 0xE0:
                header = (data[pos] << 24) | (data[pos + 1] << 16) | (data[pos + 2] << 8) | data[pos + 3]
                
                version = (header >> 19) & 0x03
                layer = (header >> 17) & 0x03
                bitrate_index = (header >> 12) & 0x0F
                sample_rate_index = (header >> 10) & 0x03
                padding = (header >> 9) & 0x01
                
                if layer == 0 or bitrate_index == 0 or bitrate_index == 15 or sample_rate_index == 3:
                    pos += 1
                    continue
                
                frame_length = calculate_mp3_frame_length(version, layer, bitrate_index, sample_rate_index, padding)
                
                if frame_length > 0 and pos + frame_length <= len(data):
                    # 检查是否为Xing/Info/LAME元数据帧
                    frame_content = data[pos:pos+200]
                    if b'Xing' in frame_content or b'Info' in frame_content or b'LAME' in frame_content:
                        pos += frame_length
                        continue
                    
                    frames.append((pos, frame_length))
                    pos += frame_length
                else:
                    pos += 1
            else:
                pos += 1
        
        # 如果需要跳过最后一帧
        if skip_last and len(frames) > 0:
            frames = frames[:-1]
        
        # 组装纯净帧
        result = b''
        for frame_pos, frame_len in frames:
            result += data[frame_pos:frame_pos + frame_len]
        
        return result
    
    def close(self):
        """关闭编码器"""
        if self.process:
            try:
                self.process.stdin.close()
                self.process.stdout.close()
                self.process.stderr.close()
                self.process.terminate()
                self.process.wait(timeout=1)
            except:
                pass
            self.process = None
        print(f"[GaplessMP3] Encoder closed, total writes: {self.frames_written}")

@app.websocket("/tts")
async def websocket_tts(websocket: WebSocket):
    """
    WebSocket TTS流式接口
    模拟流式响应，通过分段处理文本
    """
    await websocket.accept()
    ws_start_time = time.time()
    print(f"[Index-TTS-WS] ========== WebSocket连接已建立 ==========", flush=True)
    print(f"[Index-TTS-WS] 连接时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ws_start_time))}", flush=True)
    
    # 添加API密钥验证
    api_key = websocket.headers.get("x-api-key")
    if not api_key or api_key not in VALID_API_KEYS:
        print(f"[Index-TTS-WS] API密钥验证失败: api_key={api_key}", flush=True)
        await websocket.send_text(json.dumps({
            "errorCode": 4401,
            "message": "Missing or invalid x-api-key header"
        }))
        await websocket.close(code=4001, reason="Unauthorized")
        return
    print(f"[Index-TTS-WS] API密钥验证成功", flush=True)
    
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
                    # 设置超时以检测死连接
                    data = await asyncio.wait_for(websocket.receive_text(), timeout=120.0)
                    request_data = json.loads(data)
                    print(f"[Index-TTS-WS] 收到请求: {request_data}", flush=True)
                    
                    # 立即处理停止信号，不排队
                    if request_data.get("task") == "stopTTS" or request_data.get("action") == "stop":
                        message_id = request_data.get("messageId")
                        if message_id is not None:
                            print(f"[Index-TTS-WS] 收到停止信号，messageId: {message_id}", flush=True)
                            
                            # 标记活动请求为停止
                            if message_id in active_tts_requests:
                                active_tts_requests[message_id]["stop_requested"] = True
                                print(f"[Index-TTS-WS] 已标记messageId {message_id}为停止", flush=True)
                            else:
                                print(f"[Index-TTS-WS] messageId {message_id}未在活动请求中找到", flush=True)
                            
                            # 将messageId添加到忽略列表
                            current_time = time.time()
                            expiration_time = current_time + (ignoringDurationInMillisecondsAfterStopTTS / 1000.0)
                            ignored_message_ids[message_id] = expiration_time
                            print(f"[Index-TTS-WS] messageId {message_id}已添加到忽略列表，过期时间: {expiration_time:.3f}", flush=True)
                    else:
                        # 将TTS请求排队处理
                        await message_queue.put(request_data)
                
                except asyncio.TimeoutError:
                    # 等待消息超时 - 连接可能空闲但仍然活动
                    print(f"[Index-TTS-WS] 120秒内未收到消息，连接仍然活动", flush=True)
                    continue
                
                except WebSocketDisconnect as disconnect_error:
                    # 客户端正常或异常断开连接
                    print(f"[Index-TTS-WS] 客户端在接收器中断开连接: {disconnect_error}", flush=True)
                    connection_active = False
                    break
                
                except Exception as recv_error:
                    # 处理其他接收错误
                    print(f"[Index-TTS-WS] 接收消息错误: {recv_error}", flush=True)
                    connection_active = False
                    break
        
        except asyncio.CancelledError:
            print(f"[Index-TTS-WS] 消息接收器已取消", flush=True)
            connection_active = False
        
        except Exception as e:
            print(f"[Index-TTS-WS] 消息接收器致命错误: {e}", flush=True)
            connection_active = False
        
        finally:
            print(f"[Index-TTS-WS] 消息接收器已停止，清理活动请求", flush=True)
            # 标记所有活动TTS请求为停止
            for message_id in list(active_tts_requests.keys()):
                active_tts_requests[message_id]["stop_requested"] = True
                print(f"[Index-TTS-WS] 已标记messageId {message_id}进行清理", flush=True)
    
    # 启动后台消息接收任务
    receiver_task = asyncio.create_task(message_receiver())
    
    try:
        while connection_active:
            # 清理过期的忽略messageId
            current_time = time.time()
            expired_message_ids = [msg_id for msg_id, exp_time in ignored_message_ids.items() if current_time > exp_time]
            for msg_id in expired_message_ids:
                del ignored_message_ids[msg_id]
                print(f"[Index-TTS-WS] 已从忽略列表中移除过期的messageId {msg_id}", flush=True)
            
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
                    print(f"[Index-TTS-WS] 忽略messageId {message_id}的TTS请求（在忽略列表中）", flush=True)
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
            
            print(f"[Index-TTS-WS] 处理请求 - 文本: {text[:50]}{'...' if len(text) > 50 else ''}", flush=True)
            print(f"[Index-TTS-WS] 说话人: {speaker_id}, 采样率: {output_sample_rate}Hz, 格式: {audio_format}", flush=True)
            
            # 判断是否有消息头
            has_message_headers = start_time_id is not None and message_id is not None
            if has_message_headers:
                print(f"[Index-TTS-WS] 消息头 - startTimeId: {start_time_id}, messageId: {message_id}", flush=True)
            
            # 设置保存音频块的文件夹
            chunk_save_folder = None
            chunk_file_counter = 0
            if save_audio_files:
                chunk_save_folder = os.path.join(os.path.dirname(__file__), "savedAudioFiles")
                os.makedirs(chunk_save_folder, exist_ok=True)
                print(f"[Index-TTS-WS] 创建/验证音频块保存文件夹: {chunk_save_folder}", flush=True)
            
            try:
                # 分割文本
                text_segments = split_text_by_punctuation(text, language)
                print(f"[Index-TTS-WS] 将文本分割为 {len(text_segments)} 个段落", flush=True)
                for i, segment in enumerate(text_segments):
                    print(f"[Index-TTS-WS] 段落 {i+1}: {segment[:50]}{'...' if len(segment) > 50 else ''}", flush=True)
                
                # 跟踪是否被停止
                stop_requested = False
                chunk_counter = 0
                # 跟踪是否有音频成功发送（用于判断是否发送完成信号）
                has_audio_sent = False
                
                # 创建持久的MP3编码器（用于无缝MP3流）
                mp3_encoder = None
                if audio_format == "mp3":
                    mp3_encoder = GaplessMP3Encoder(sample_rate=output_sample_rate, bitrate='128k')
                    print(f"[Index-TTS-WS] 创建GaplessMP3Encoder用于无缝流式传输", flush=True)
                
                # 处理每个文本段落
                for segment_idx, segment_text in enumerate(text_segments):
                    # 检查是否收到停止请求
                    if message_id is not None and message_id in active_tts_requests:
                        if active_tts_requests[message_id]["stop_requested"]:
                            print(f"[Index-TTS-WS] TTS生成已停止，messageId: {message_id}", flush=True)
                            stop_requested = True
                            break
                    
                    segment_start_time = time.time()
                    print(f"[Index-TTS-WS] 处理段落 {segment_idx+1}/{len(text_segments)}: {segment_text[:50]}{'...' if len(segment_text) > 50 else ''}", flush=True)
                    
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
                        print(f"[Index-TTS-WS] 段落 {segment_idx+1} 生成时间: {segment_time:.2f}ms", flush=True)
                        
                        # 发送音频数据
                        if audio_format == "pcm":
                            # 如果需要消息头，添加头部
                            if has_message_headers:
                                # 消息头格式: startTimeId (8字节 unsigned long long) + messageId (4字节 unsigned int) = 12字节
                                header_bytes = struct.pack('>QI', start_time_id, message_id)
                                audio_bytes_with_headers = header_bytes + pcm_data
                            else:
                                audio_bytes_with_headers = pcm_data
                            
                            # 保存音频块（如果需要）- 保存时包含头部（如果有）
                            if save_audio_files and chunk_save_folder:
                                chunk_file_counter += 1
                                file_extension = "pcm"
                                chunk_filename = f"chunk_{chunk_file_counter}.{file_extension}"
                                chunk_path = os.path.join(chunk_save_folder, chunk_filename)
                                with open(chunk_path, "wb") as f:
                                    f.write(audio_bytes_with_headers)
                                if has_message_headers:
                                    print(f"[Index-TTS-WS] 已保存 {chunk_filename} ({len(audio_bytes_with_headers)} 字节，包含12字节头部)", flush=True)
                                else:
                                    print(f"[Index-TTS-WS] 已保存 {chunk_filename} ({len(audio_bytes_with_headers)} 字节，无头部)", flush=True)
                            
                            audio_chunk = audio_bytes_with_headers
                            
                            # 检查连接是否仍然活动
                            if connection_active:
                                try:
                                    await websocket.send_bytes(audio_chunk)
                                    chunk_counter += 1
                                    has_audio_sent = True
                                    print(f"[Index-TTS-WS] 已发送PCM音频块 {chunk_counter}, 大小: {len(audio_chunk)} 字节", flush=True)
                                except Exception as send_error:
                                    print(f"[Index-TTS-WS] 发送音频块错误: {send_error}", flush=True)
                                    connection_active = False
                                    break
                            else:
                                print(f"[Index-TTS-WS] 连接不再活动，停止音频传输", flush=True)
                                break
                        else:
                            # MP3格式 - 使用GaplessMP3Encoder进行无缝编码
                            try:
                                # 将PCM数据转换为float32格式用于编码器
                                pcm_int16 = np.frombuffer(pcm_data, dtype=np.int16)
                                pcm_float = pcm_int16.astype(np.float32) / 32767.0
                                
                                # 使用持久编码器进行无缝编码
                                mp3_data = mp3_encoder.feed_pcm(pcm_float, volume_multiplier=1.0)
                                
                                if mp3_data:
                                    print(f"[Index-TTS-WS] GaplessMP3: 输入 {len(pcm_float)} 样本, 输出 {len(mp3_data)} 字节", flush=True)
                                    
                                    # 如果需要消息头，添加头部
                                    if has_message_headers:
                                        header_bytes = struct.pack('>QI', start_time_id, message_id)
                                        audio_bytes_with_headers = header_bytes + mp3_data
                                    else:
                                        audio_bytes_with_headers = mp3_data
                                    
                                    # 保存音频块（如果需要）
                                    if save_audio_files and chunk_save_folder:
                                        chunk_file_counter += 1
                                        file_extension = "mp3"
                                        chunk_filename = f"chunk_{chunk_file_counter}.{file_extension}"
                                        chunk_path = os.path.join(chunk_save_folder, chunk_filename)
                                        with open(chunk_path, "wb") as f:
                                            f.write(audio_bytes_with_headers)
                                        if has_message_headers:
                                            print(f"[Index-TTS-WS] 已保存 {chunk_filename} ({len(audio_bytes_with_headers)} 字节，包含12字节头部)", flush=True)
                                        else:
                                            print(f"[Index-TTS-WS] 已保存 {chunk_filename} ({len(audio_bytes_with_headers)} 字节，无头部)", flush=True)
                                    
                                    audio_chunk = audio_bytes_with_headers
                                    
                                    # 检查连接是否仍然活动
                                    if connection_active:
                                        try:
                                            await websocket.send_bytes(audio_chunk)
                                            chunk_counter += 1
                                            has_audio_sent = True
                                            print(f"[Index-TTS-WS] 已发送MP3音频块 {chunk_counter}, 大小: {len(audio_chunk)} 字节", flush=True)
                                        except Exception as send_error:
                                            print(f"[Index-TTS-WS] 发送音频块错误: {send_error}", flush=True)
                                            connection_active = False
                                            break
                                    else:
                                        print(f"[Index-TTS-WS] 连接不再活动，停止音频传输", flush=True)
                                        break
                                else:
                                    print(f"[Index-TTS-WS] GaplessMP3: 输入 {len(pcm_float)} 样本, 缓冲中...", flush=True)
                                    
                            except Exception as mp3_error:
                                print(f"[Index-TTS-WS] MP3编码错误: {mp3_error}", flush=True)
                                await websocket.send_text(json.dumps({
                                    "errorCode": 5001,
                                    "message": f"MP3 encoding failed: {str(mp3_error)}"
                                }))
                                break
                        
                    except Exception as e:
                        print(f"[Index-TTS-WS] 段落 {segment_idx+1} 生成失败: {str(e)}", flush=True)
                        await websocket.send_text(json.dumps({
                            "errorCode": 5000,
                            "message": f"Failed to generate audio for segment {segment_idx+1}: {str(e)}"
                        }))
                        break
                
                # 刷新MP3编码器，获取剩余数据
                if mp3_encoder is not None and not stop_requested:
                    try:
                        final_mp3_data = mp3_encoder.flush()
                        if final_mp3_data and connection_active:
                            if has_message_headers:
                                header_bytes = struct.pack('>QI', start_time_id, message_id)
                                data_to_send = header_bytes + final_mp3_data
                                await websocket.send_bytes(data_to_send)
                                print(f"[Index-TTS-WS] GaplessMP3: 刷新最终 {len(final_mp3_data)} 字节（带头部）", flush=True)
                            else:
                                await websocket.send_bytes(final_mp3_data)
                                print(f"[Index-TTS-WS] GaplessMP3: 刷新最终 {len(final_mp3_data)} 字节", flush=True)
                            chunk_counter += 1
                            has_audio_sent = True
                        mp3_encoder.close()
                    except Exception as flush_error:
                        print(f"[Index-TTS-WS] GaplessMP3 刷新错误: {str(flush_error)}", flush=True)
                
                # 发送完成信号（空流）仅在未停止且有音频成功发送时
                if not stop_requested and connection_active and has_audio_sent:
                    try:
                        if has_message_headers:
                            # 发送带头部的空流 (12字节头部 + 0音频字节)
                            header_bytes = struct.pack('>QI', start_time_id, message_id)
                            completion_data = header_bytes + b''
                            await websocket.send_bytes(completion_data)
                            print(f"[Index-TTS-WS] 已发送完成信号: {len(completion_data)} 字节 (12字节头部 + 0音频字节)", flush=True)
                        else:
                            # 发送空流
                            await websocket.send_bytes(b'')
                            print(f"[Index-TTS-WS] 已发送完成信号: 0 字节 (空流)", flush=True)
                    except Exception as completion_error:
                        print(f"[Index-TTS-WS] 发送完成信号错误: {completion_error}", flush=True)
                        connection_active = False
                
                if stop_requested:
                    print(f"[Index-TTS-WS] TTS已停止，messageId: {message_id} - 在停止前发送了 {chunk_counter} 个音频块", flush=True)
                else:
                    print(f"[Index-TTS-WS] 完成流式响应 - 发送了 {chunk_counter} 个音频块", flush=True)
                if save_audio_files:
                    print(f"[Index-TTS-WS] 已保存 {chunk_file_counter} 个 {audio_format.upper()} 块文件到 {chunk_save_folder}", flush=True)
                
            except Exception as e:
                print(f"[Index-TTS-WS] TTS生成错误: {str(e)}", flush=True)
                # 只在连接仍然活动时发送错误消息
                if connection_active:
                    try:
                        await websocket.send_text(json.dumps({
                            "errorCode": 5000,
                            "message": f"TTS generation failed: {str(e)}"
                        }))
                    except:
                        pass
            finally:
                # 清理活动请求
                if message_id is not None and message_id in active_tts_requests:
                    del active_tts_requests[message_id]
    
    except WebSocketDisconnect:
        print(f"[Index-TTS-WS] WebSocket连接已断开", flush=True)
    except Exception as e:
        print(f"[Index-TTS-WS] WebSocket错误: {str(e)}", flush=True)
    finally:
        connection_active = False
        receiver_task.cancel()
        print(f"[Index-TTS-WS] WebSocket连接已关闭", flush=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Index-TTS-vLLM API Server')
    parser.add_argument('--port', type=int, default=9001, help='端口号 (默认: 9001)')
    parser.add_argument('--index-tts-url', type=str, default="http://localhost:6006", 
                        help='Index-TTS-vLLM服务器URL (默认: http://localhost:6006)')
    args = parser.parse_args()
    
    # 更新Index-TTS服务器URL
    INDEX_TTS_SERVER_URL = args.index_tts_url
    
    uvicorn.run(app, host="0.0.0.0", port=args.port)
