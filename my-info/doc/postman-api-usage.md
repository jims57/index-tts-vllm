# Index-TTS-vLLM API 使用文档 (Postman)

## 基础信息

- **Base URL**: `http://localhost:6006`
- **API Version**: Changes number: 5

---

## 1. 健康检查 (Health Check)

### GET /

**描述**: 检查API服务是否正常运行

**请求示例 (Postman)**:
```
GET http://localhost:6006/
```

**响应示例**:
```json
{
    "status": "ok",
    "message": "Index-TTS-vLLM API is running"
}
```

---

## 2. 上传音频文件 (Upload Audio)

### POST /uploadAudio

**描述**: 上传音频文件用于声音克隆

**请求类型**: `multipart/form-data`

**Headers**:
- `x-api-key`: (可选) API密钥

**Body (form-data)**:
- `file`: 音频文件 (File)

**Postman设置**:
1. Method: `POST`
2. URL: `http://localhost:6006/uploadAudio`
3. Headers:
   - `x-api-key`: `your-api-key` (可选)
4. Body → form-data:
   - Key: `file`
   - Type: File
   - Value: 选择音频文件

**响应示例 (成功)**:
```json
{
    "status": "success",
    "filename": "audio_20251124_162530.wav",
    "message": "Audio file uploaded successfully"
}
```

**响应示例 (失败)**:
```json
{
    "errorCode": 4400,
    "message": "No file uploaded"
}
```

---

## 3. 克隆声音 (Clone Voice)

### POST /cloneVoice

**描述**: 使用上传的音频文件克隆声音

**请求类型**: `multipart/form-data`

**Body (form-data)**:
- `audio_file`: 音频文件 (File)
- `speaker_name`: 说话人名称 (Text)

**Postman设置**:
1. Method: `POST`
2. URL: `http://localhost:6006/cloneVoice`
3. Body → form-data:
   - Key: `audio_file`, Type: File, Value: 选择音频文件
   - Key: `speaker_name`, Type: Text, Value: `my-speaker-name`

**响应示例 (成功)**:
```json
{
    "status": "success",
    "speaker_id": "my-speaker-name",
    "message": "Voice cloned successfully"
}
```

**响应示例 (失败)**:
```json
{
    "errorCode": 4400,
    "message": "Speaker name already exists"
}
```

---

## 4. 获取说话人音频 (Get Speaker Voice)

### GET /getSpeakerVoice/{filename}

**描述**: 获取已克隆的说话人音频文件

**路径参数**:
- `filename`: 音频文件名

**Postman设置**:
1. Method: `GET`
2. URL: `http://localhost:6006/getSpeakerVoice/my-speaker-name.wav`

**响应**: 音频文件流 (audio/wav)

**响应示例 (失败)**:
```json
{
    "errorCode": 4404,
    "message": "Speaker voice file not found"
}
```

---

## 5. API文档 (API Documentation)

### GET /apiDoc

**描述**: 获取API文档

**Postman设置**:
1. Method: `GET`
2. URL: `http://localhost:6006/apiDoc`

**响应示例**:
```json
{
    "title": "Index-TTS-vLLM API Documentation",
    "version": "1.0.0",
    "endpoints": [
        {
            "path": "/",
            "method": "GET",
            "description": "健康检查"
        },
        {
            "path": "/uploadAudio",
            "method": "POST",
            "description": "上传音频文件"
        },
        {
            "path": "/cloneVoice",
            "method": "POST",
            "description": "克隆声音"
        },
        {
            "path": "/getSpeakerVoice/{filename}",
            "method": "GET",
            "description": "获取说话人音频文件"
        },
        {
            "path": "/tts",
            "method": "WebSocket",
            "description": "WebSocket TTS流式接口"
        }
    ]
}
```

---

## 6. WebSocket TTS流式接口 (WebSocket TTS Streaming)

### WS /tts

**描述**: WebSocket实时TTS流式传输接口

**协议**: WebSocket

**连接URL**: `ws://localhost:6006/tts`

### 6.1 TTS请求消息格式

**发送消息 (JSON)**:
```json
{
    "text": "你好，这是一段测试文本。",
    "speakerId": "wm-sample-for-cosy",
    "outputSampleRate": 8000,
    "audioFormat": "pcm",
    "startTimeId": 1732435200000,
    "messageId": 12345,
    "saveAudioFiles": true,
    "language": "zh-cn",
    "seed": 42
}
```

**参数说明**:
- `text` (必填): 要转换的文本
- `speakerId` (可选): 说话人ID，默认 `wm-sample-for-cosy`
- `outputSampleRate` (可选): 输出采样率，默认 16000Hz
- `audioFormat` (可选): 音频格式，支持 `pcm` 或 `mp3`，默认 `pcm`
- `startTimeId` (可选): 开始时间ID (8字节 unsigned long long)
- `messageId` (可选): 消息ID (4字节 unsigned int)
- `saveAudioFiles` (可选): 是否保存音频文件，默认 false
- `language` (可选): 语言，支持 `zh`/`zh-cn`/`en`
- `seed` (可选): 随机种子，默认 42

### 6.2 停止TTS请求

**发送消息 (JSON)**:
```json
{
    "task": "stopTTS",
    "messageId": 12345
}
```

或

```json
{
    "action": "stop",
    "messageId": 12345
}
```

**参数说明**:
- `task` 或 `action`: 设置为 `stopTTS` 或 `stop`
- `messageId` (必填): 要停止的消息ID

### 6.3 接收消息格式

**音频数据 (Binary)**:
- 如果提供了 `startTimeId` 和 `messageId`:
  - 前12字节: 消息头 (startTimeId 8字节 + messageId 4字节，大端序)
  - 后续字节: PCM音频数据
- 如果未提供消息头:
  - 直接为PCM音频数据

**完成信号 (Binary)**:
- 如果提供了消息头: 12字节头部 + 0字节音频数据
- 如果未提供消息头: 空字节流

**错误消息 (JSON)**:
```json
{
    "errorCode": 4400,
    "message": "Text is required"
}
```

### 6.4 Postman WebSocket测试

**注意**: Postman需要使用支持WebSocket的版本

1. 新建请求
2. 选择 `WebSocket Request`
3. URL: `ws://localhost:6006/tts`
4. 点击 `Connect`
5. 在消息框中输入JSON请求
6. 点击 `Send`
7. 查看接收到的二进制音频数据

### 6.5 JavaScript WebSocket示例

```javascript
const ws = new WebSocket('ws://localhost:6006/tts');

ws.onopen = () => {
    console.log('WebSocket连接已建立');
    
    // 发送TTS请求
    const request = {
        text: '你好，这是一段测试文本。',
        speakerId: 'wm-sample-for-cosy',
        outputSampleRate: 8000,
        audioFormat: 'pcm',
        startTimeId: Date.now(),
        messageId: 12345,
        saveAudioFiles: true,
        language: 'zh-cn',
        seed: 42
    };
    
    ws.send(JSON.stringify(request));
};

ws.onmessage = (event) => {
    if (event.data instanceof Blob) {
        // 二进制音频数据
        console.log('收到音频数据:', event.data.size, '字节');
        
        // 处理音频数据
        event.data.arrayBuffer().then(buffer => {
            const view = new DataView(buffer);
            
            // 如果有消息头 (12字节)
            if (buffer.byteLength >= 12) {
                // 读取startTimeId (8字节，大端序)
                const startTimeId = view.getBigUint64(0, false);
                // 读取messageId (4字节，大端序)
                const messageId = view.getUint32(8, false);
                
                console.log('startTimeId:', startTimeId);
                console.log('messageId:', messageId);
                
                // 音频数据从第12字节开始
                const audioData = buffer.slice(12);
                console.log('音频数据大小:', audioData.byteLength, '字节');
                
                // 如果音频数据为0字节，表示完成信号
                if (audioData.byteLength === 0) {
                    console.log('收到完成信号');
                }
            }
        });
    } else {
        // JSON错误消息
        const response = JSON.parse(event.data);
        console.log('收到消息:', response);
    }
};

ws.onerror = (error) => {
    console.error('WebSocket错误:', error);
};

ws.onclose = () => {
    console.log('WebSocket连接已关闭');
};

// 停止TTS
function stopTTS(messageId) {
    const stopRequest = {
        task: 'stopTTS',
        messageId: messageId
    };
    ws.send(JSON.stringify(stopRequest));
}
```

### 6.6 Python WebSocket示例

```python
import asyncio
import websockets
import json
import struct

async def test_tts():
    uri = "ws://localhost:6006/tts"
    
    async with websockets.connect(uri) as websocket:
        # 发送TTS请求
        request = {
            "text": "你好，这是一段测试文本。",
            "speakerId": "wm-sample-for-cosy",
            "outputSampleRate": 8000,
            "audioFormat": "pcm",
            "startTimeId": 1732435200000,
            "messageId": 12345,
            "saveAudioFiles": True,
            "language": "zh-cn",
            "seed": 42
        }
        
        await websocket.send(json.dumps(request))
        print("已发送TTS请求")
        
        # 接收音频数据
        audio_chunks = []
        while True:
            try:
                message = await websocket.recv()
                
                if isinstance(message, bytes):
                    # 二进制音频数据
                    print(f"收到音频数据: {len(message)} 字节")
                    
                    # 如果有消息头 (12字节)
                    if len(message) >= 12:
                        # 解析消息头
                        start_time_id, message_id = struct.unpack('>QI', message[:12])
                        print(f"startTimeId: {start_time_id}, messageId: {message_id}")
                        
                        # 音频数据从第12字节开始
                        audio_data = message[12:]
                        print(f"音频数据大小: {len(audio_data)} 字节")
                        
                        # 如果音频数据为0字节，表示完成信号
                        if len(audio_data) == 0:
                            print("收到完成信号")
                            break
                        
                        audio_chunks.append(audio_data)
                    else:
                        audio_chunks.append(message)
                else:
                    # JSON消息
                    response = json.loads(message)
                    print(f"收到消息: {response}")
                    
                    if "errorCode" in response:
                        print(f"错误: {response['message']}")
                        break
            
            except websockets.exceptions.ConnectionClosed:
                print("连接已关闭")
                break
        
        # 保存音频文件
        if audio_chunks:
            with open("output.pcm", "wb") as f:
                for chunk in audio_chunks:
                    f.write(chunk)
            print(f"已保存 {len(audio_chunks)} 个音频块到 output.pcm")

# 运行测试
asyncio.run(test_tts())
```

---

## 错误代码说明

| 错误代码 | 说明 |
|---------|------|
| 4400 | 请求参数错误 (Bad Request) |
| 4404 | 资源未找到 (Not Found) |
| 5000 | 服务器内部错误 (Internal Server Error) |
| 5001 | 功能未实现 (Not Implemented) |

---

## 音频格式说明

### PCM格式
- **编码**: 16位有符号整数，小端序 (s16le)
- **采样率**: 可选 8000Hz, 16000Hz, 22050Hz, 24000Hz, 32000Hz, 44100Hz
- **声道**: 单声道 (mono)

### 消息头格式 (可选)
- **startTimeId**: 8字节无符号长整型 (unsigned long long)，大端序
- **messageId**: 4字节无符号整型 (unsigned int)，大端序
- **总长度**: 12字节

---

## 保存的音频文件

当 `saveAudioFiles` 设置为 `true` 时，音频块会保存到:
```
/Users/mac/Documents/GitHub/index-tts-vllm/savedAudioFiles/
```

文件命名格式:
```
chunk_1.pcm
chunk_2.pcm
chunk_3.pcm
...
```

**注意**: 保存的文件包含消息头（如果提供了 startTimeId 和 messageId）

---

## 合并保存的PCM文件

使用提供的Python脚本合并所有保存的PCM文件:

```bash
cd /Users/mac/Documents/GitHub/index-tts-vllm/my-info/utils/combine_saved_audios/pcm

# 不清理旧文件
python combine_pcm_streams_into_single_pcm.py

# 合并前清理输出目录
python combine_pcm_streams_into_single_pcm.py --clean
python combine_pcm_streams_into_single_pcm.py -c
```

合并后的文件保存在:
```
/Users/mac/Documents/GitHub/index-tts-vllm/my-info/utils/combine_saved_audios/pcm/combined_pcm_files/
```

---

## 播放PCM文件

使用 ffplay 播放PCM文件:

```bash
# 8000Hz采样率
ffplay -f s16le -ar 8000 -ac 1 output.pcm

# 16000Hz采样率
ffplay -f s16le -ar 16000 -ac 1 output.pcm

# 24000Hz采样率
ffplay -f s16le -ar 24000 -ac 1 output.pcm
```

转换PCM为WAV:

```bash
ffmpeg -f s16le -ar 8000 -ac 1 -i output.pcm output.wav
```

---

## 完整的Postman Collection JSON

```json
{
    "info": {
        "name": "Index-TTS-vLLM API",
        "description": "Index-TTS-vLLM API完整测试集合",
        "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
    },
    "item": [
        {
            "name": "1. 健康检查",
            "request": {
                "method": "GET",
                "header": [],
                "url": {
                    "raw": "http://localhost:6006/",
                    "protocol": "http",
                    "host": ["localhost"],
                    "port": "6006",
                    "path": [""]
                }
            }
        },
        {
            "name": "2. 上传音频文件",
            "request": {
                "method": "POST",
                "header": [
                    {
                        "key": "x-api-key",
                        "value": "your-api-key",
                        "type": "text"
                    }
                ],
                "body": {
                    "mode": "formdata",
                    "formdata": [
                        {
                            "key": "file",
                            "type": "file",
                            "src": "/path/to/audio.wav"
                        }
                    ]
                },
                "url": {
                    "raw": "http://localhost:6006/uploadAudio",
                    "protocol": "http",
                    "host": ["localhost"],
                    "port": "6006",
                    "path": ["uploadAudio"]
                }
            }
        },
        {
            "name": "3. 克隆声音",
            "request": {
                "method": "POST",
                "header": [],
                "body": {
                    "mode": "formdata",
                    "formdata": [
                        {
                            "key": "audio_file",
                            "type": "file",
                            "src": "/path/to/audio.wav"
                        },
                        {
                            "key": "speaker_name",
                            "value": "my-speaker-name",
                            "type": "text"
                        }
                    ]
                },
                "url": {
                    "raw": "http://localhost:6006/cloneVoice",
                    "protocol": "http",
                    "host": ["localhost"],
                    "port": "6006",
                    "path": ["cloneVoice"]
                }
            }
        },
        {
            "name": "4. 获取说话人音频",
            "request": {
                "method": "GET",
                "header": [],
                "url": {
                    "raw": "http://localhost:6006/getSpeakerVoice/my-speaker-name.wav",
                    "protocol": "http",
                    "host": ["localhost"],
                    "port": "6006",
                    "path": ["getSpeakerVoice", "my-speaker-name.wav"]
                }
            }
        },
        {
            "name": "5. API文档",
            "request": {
                "method": "GET",
                "header": [],
                "url": {
                    "raw": "http://localhost:6006/apiDoc",
                    "protocol": "http",
                    "host": ["localhost"],
                    "port": "6006",
                    "path": ["apiDoc"]
                }
            }
        }
    ]
}
```

---

## 注意事项

1. **WebSocket连接**: Postman的WebSocket功能可能有限，建议使用专门的WebSocket测试工具或编写代码测试
2. **音频格式**: 目前主要支持PCM格式，MP3格式尚未完全实现
3. **采样率**: Index-TTS默认输出24000Hz，会自动重采样到请求的采样率
4. **消息头**: 消息头是可选的，用于客户端追踪和管理音频流
5. **停止TTS**: 使用 `stopTTS` 任务可以中断正在进行的TTS生成
6. **保存文件**: 保存的PCM文件包含消息头（如果提供），需要在播放前处理或使用合并脚本

---

**文档更新日期**: 2025-11-24
**API版本**: Changes number: 5
