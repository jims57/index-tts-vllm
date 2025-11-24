# Index-TTS-vLLM API 使用指南

## 概述

这是一个为 Index-TTS-vLLM 项目创建的 API 包装器，提供与 Minimax API 兼容的接口，支持流式 TTS 响应。

## 架构

```
客户端 (iOS/Android) 
    ↓
api.py (端口 9001) - 公开的 API 接口
    ↓
api_server.py (端口 7860) - 内部 Index-TTS-vLLM 服务
```

## 启动服务

### 1. 启动 Index-TTS-vLLM 服务器 (api_server.py)

```bash
# 确保在 conda 环境中
conda activate index-tts-vllm

# 启动 Index-TTS-vLLM 服务器（端口 7860）
python api_server.py --model_dir ./checkpoints/Index-TTS-1.5-vLLM --port 7860
```

### 2. 启动 API 包装器 (api.py)

在另一个终端：

```bash
# 确保在 conda 环境中
conda activate index-tts-vllm

# 启动 API 包装器（端口 9001）
python api.py --port 9001 --index-tts-url http://localhost:7860
```

## API 端点

### 1. 健康检查

```bash
GET /
```

响应：
```json
{
  "errorCode": 0,
  "message": "Index-TTS-vLLM API is running"
}
```

### 2. WebSocket TTS 流式接口

```
WebSocket: ws://localhost:9001/tts
```

#### 请求参数

```json
{
  "text": "要合成的文本",
  "speakerId": "wm-sample-for-cosy",
  "language": "zh",
  "audioFormat": "pcm",
  "outputSampleRate": 16000,
  "saveAudioFiles": false,
  "startTimeId": 1234567890,
  "messageId": 12345,
  "seed": 42
}
```

参数说明：
- `text` (必需): 要合成的文本
- `speakerId` (可选): 说话人 ID，默认 "wm-sample-for-cosy"
  - 可以是文件名（如 "wm-sample-for-cosy"）
  - 可以是 MD5 ID（如 "e327cd589a5b99739ea21070a8529c46"）
- `language` (可选): 语言代码
  - `zh` 或 `zh-cn`: 中文
  - `en`: 英文
  - 不指定则自动检测
- `audioFormat` (可选): 音频格式，默认 "pcm"
  - `pcm`: PCM 格式（推荐）
  - `mp3`: MP3 格式（暂不支持）
- `outputSampleRate` (可选): 输出采样率，默认 16000
- `saveAudioFiles` (可选): 是否保存音频文件，默认 false
- `startTimeId` (可选): 开始时间 ID（用于消息头）
- `messageId` (可选): 消息 ID（用于消息头和停止控制）
- `seed` (可选): 随机种子，默认 42

#### 响应

API 会将文本按标点符号分割，然后逐段发送音频数据：

1. **音频数据**（二进制）：
   - 如果提供了 `startTimeId` 和 `messageId`，每个音频块会包含 8 字节头部：
     - 前 4 字节：startTimeId (uint32)
     - 后 4 字节：messageId (uint32)
   - 然后是 PCM 音频数据

2. **完成消息**（JSON）：
```json
{
  "errorCode": 0,
  "message": "TTS generation completed",
  "segments": 3
}
```

3. **错误消息**（JSON）：
```json
{
  "errorCode": 5000,
  "message": "错误描述"
}
```

#### 停止 TTS 生成

发送停止信号：
```json
{
  "action": "stop",
  "messageId": 12345
}
```

停止后，该 messageId 会被忽略 5 秒（可配置）。

### 3. 上传音频文件

```bash
POST /uploadAudio
Header: x-api-key: sk-5z6y7x8w9v0u1t2s3r4q5p6o7n8m9l0k1j2i3h4g
Content-Type: multipart/form-data

file: <audio file>
```

响应：
```json
{
  "errorCode": 0,
  "message": "Audio uploaded successfully",
  "data": {
    "filename": "abc123.wav",
    "path": "assets/uploaded/abc123.wav"
  }
}
```

### 4. 克隆声音

```bash
POST /cloneVoice
Header: x-api-key: sk-5z6y7x8w9v0u1t2s3r4q5p6o7n8m9l0k1j2i3h4g
Content-Type: multipart/form-data

audio_file: <audio file>
speaker_name: "My Voice"
```

响应：
```json
{
  "errorCode": 0,
  "message": "Voice cloned successfully",
  "data": {
    "speakerId": "abc123def456",
    "speakerName": "My Voice",
    "audioPath": "assets/cloned/My_Voice_abc123.wav"
  }
}
```

### 5. 获取说话人音频

```bash
GET /getSpeakerVoice/{filename}
```

返回音频文件。

### 6. API 文档

```bash
GET /apiDoc
```

返回 API 文档。

## 使用示例

### Python WebSocket 客户端

```python
import asyncio
import websockets
import json
import struct

async def test_tts():
    uri = "ws://localhost:9001/tts"
    
    async with websockets.connect(uri) as websocket:
        # 发送 TTS 请求
        request = {
            "text": "在这样一个阳光明媚、微风拂面的下午，我独自坐在公园的长椅上，看着孩子们欢快地追逐嬉戏。",
            "speakerId": "wm-sample-for-cosy",
            "language": "zh",
            "audioFormat": "pcm",
            "outputSampleRate": 16000,
            "startTimeId": 1234567890,
            "messageId": 12345
        }
        
        await websocket.send(json.dumps(request))
        print("请求已发送")
        
        # 接收响应
        audio_chunks = []
        while True:
            try:
                message = await websocket.recv()
                
                if isinstance(message, bytes):
                    # 音频数据
                    # 提取头部（如果有）
                    if len(message) >= 8:
                        start_time_id, msg_id = struct.unpack('<II', message[:8])
                        pcm_data = message[8:]
                        print(f"收到音频块: startTimeId={start_time_id}, messageId={msg_id}, 大小={len(pcm_data)}")
                        audio_chunks.append(pcm_data)
                    else:
                        audio_chunks.append(message)
                else:
                    # JSON 消息
                    response = json.loads(message)
                    print(f"收到消息: {response}")
                    
                    if response.get("errorCode") == 0 and "completed" in response.get("message", ""):
                        print("TTS 生成完成")
                        break
                    elif response.get("errorCode") != 0:
                        print(f"错误: {response.get('message')}")
                        break
            except Exception as e:
                print(f"错误: {e}")
                break
        
        # 保存音频
        if audio_chunks:
            with open("output.pcm", "wb") as f:
                for chunk in audio_chunks:
                    f.write(chunk)
            print(f"音频已保存到 output.pcm，共 {len(audio_chunks)} 个块")

asyncio.run(test_tts())
```

### JavaScript WebSocket 客户端

```javascript
const ws = new WebSocket('ws://localhost:9001/tts');

ws.onopen = () => {
    console.log('WebSocket 连接已建立');
    
    const request = {
        text: '在这样一个阳光明媚、微风拂面的下午，我独自坐在公园的长椅上，看着孩子们欢快地追逐嬉戏。',
        speakerId: 'wm-sample-for-cosy',
        language: 'zh',
        audioFormat: 'pcm',
        outputSampleRate: 16000,
        startTimeId: 1234567890,
        messageId: 12345
    };
    
    ws.send(JSON.stringify(request));
};

ws.onmessage = (event) => {
    if (event.data instanceof Blob) {
        // 音频数据
        console.log('收到音频块:', event.data.size, '字节');
        // 处理音频数据...
    } else {
        // JSON 消息
        const response = JSON.parse(event.data);
        console.log('收到消息:', response);
        
        if (response.errorCode === 0 && response.message.includes('completed')) {
            console.log('TTS 生成完成');
            ws.close();
        }
    }
};

ws.onerror = (error) => {
    console.error('WebSocket 错误:', error);
};

ws.onclose = () => {
    console.log('WebSocket 连接已关闭');
};
```

## 配置

### API 密钥

在 `api.py` 中修改：

```python
VALID_API_KEYS = {
    "sk-5z6y7x8w9v0u1t2s3r4q5p6o7n8m9l0k1j2i3h4g",
    "your-custom-api-key"
}
```

### 停止信号忽略时间

在 `api.py` 中修改（单位：毫秒）：

```python
ignoringDurationInMillisecondsAfterStopTTS = 5000  # 5 秒
```

### Index-TTS 服务器 URL

启动时指定：

```bash
python api.py --index-tts-url http://localhost:7860
```

或在代码中修改默认值：

```python
INDEX_TTS_SERVER_URL = "http://localhost:7860"
```

## 注意事项

1. **音频格式**：目前仅支持 PCM 格式，MP3 格式待实现
2. **采样率**：Index-TTS 默认输出 24000Hz，API 会自动重采样到指定的采样率
3. **流式响应**：通过分割文本实现伪流式，每个标点符号分割的段落会立即生成并发送
4. **性能**：确保 `api_server.py` 和 `api.py` 在同一服务器上以获得最佳性能
5. **说话人 ID**：
   - 使用默认说话人：`speakerId: "wm-sample-for-cosy"`
   - 使用自定义音频：`speakerId: "assets/your-audio.wav"`
   - 使用 MD5 ID：`speakerId: "e327cd589a5b99739ea21070a8529c46"`

## 错误代码

- `0`: 成功
- `4400`: 请求参数错误
- `4401`: API 密钥无效
- `4404`: 文件未找到
- `5000`: 服务器内部错误
- `5001`: 功能未实现

## 故障排除

### 1. 连接被拒绝

确保 `api_server.py` 正在运行：

```bash
curl http://localhost:7860/health
```

### 2. 音频质量问题

尝试调整采样率或使用更高质量的参考音频。

### 3. 生成速度慢

- 检查 GPU 是否可用
- 调整 `gpu_memory_utilization` 参数
- 确保安装了 ninja（用于 CUDA 加速）

## 生产部署建议

1. 使用 Nginx 作为反向代理
2. 配置 SSL/TLS 证书
3. 实施速率限制
4. 添加日志记录和监控
5. 使用 systemd 或 supervisor 管理进程
6. 配置防火墙规则
