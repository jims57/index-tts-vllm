#!/bin/bash
# ============================================================================
# 脚本名称: run-index-tts-automatically-when-server-starts.sh
# 功能: 阿里云ECS服务器启动时自动运行Index-TTS服务
# 
# 使用方法:
# 1. 将此脚本复制到服务器: /root/run-index-tts-automatically-when-server-starts.sh
# 2. 添加执行权限: chmod +x /root/run-index-tts-automatically-when-server-starts.sh
# 3. 编辑crontab: crontab -e
# 4. 添加以下行实现开机自启:
#    @reboot /root/run-index-tts-automatically-when-server-starts.sh >> /var/log/index-tts-startup.log 2>&1
# 5. 重启服务器测试
#
# 手动运行: bash /root/run-index-tts-automatically-when-server-starts.sh
# 查看日志: tail -f /var/log/index-tts-startup.log
# 查看进程: docker exec index-tts-vllm /bin/bash -c "ps aux | grep python"
# 查看api_server.py日志: docker exec -it index-tts-vllm /bin/bash -c "tail -f /mnt/index-tts-vllm/logs/api_server_py_*.log"
# 查看api.py日志: docker exec -it index-tts-vllm /bin/bash -c "tail -f /mnt/index-tts-vllm/logs/api_py_*.log"
# ============================================================================

# 等待系统完全启动(包括Docker和NVIDIA驱动)
echo "$(date): 等待系统启动..."
sleep 30

echo "$(date): 开始启动Index-TTS服务..."

# ============================================================================
# 步骤0: 等待NVIDIA GPU/CUDA和Docker服务完全就绪
# ============================================================================
echo "$(date): 检查NVIDIA GPU是否就绪..."

max_gpu_retries=60
gpu_retry_count=0
while [ $gpu_retry_count -lt $max_gpu_retries ]; do
    if nvidia-smi > /dev/null 2>&1; then
        echo "$(date): NVIDIA GPU 已就绪"
        nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv
        break
    fi
    echo "$(date): 等待NVIDIA GPU就绪... (${gpu_retry_count}/${max_gpu_retries})"
    sleep 5
    gpu_retry_count=$((gpu_retry_count + 1))
done

if [ $gpu_retry_count -eq $max_gpu_retries ]; then
    echo "$(date): 警告: NVIDIA GPU检测超时，但将继续尝试启动服务"
fi

# 等待Docker服务就绪
echo "$(date): 检查Docker服务是否就绪..."
max_docker_retries=30
docker_retry_count=0
while [ $docker_retry_count -lt $max_docker_retries ]; do
    if docker info > /dev/null 2>&1; then
        echo "$(date): Docker服务已就绪"
        break
    fi
    echo "$(date): 等待Docker服务就绪... (${docker_retry_count}/${max_docker_retries})"
    sleep 5
    docker_retry_count=$((docker_retry_count + 1))
done

if [ $docker_retry_count -eq $max_docker_retries ]; then
    echo "$(date): 错误: Docker服务启动超时!"
    exit 1
fi

# 验证CUDA是否可用(只检查nvidia-smi能否正常工作)
echo "$(date): 验证CUDA是否可用..."
if nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader > /dev/null 2>&1; then
    echo "$(date): CUDA已就绪"
    # 显示当前GPU进程信息
    gpu_processes=$(nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null | wc -l)
    if [ "$gpu_processes" -gt 0 ]; then
        echo "$(date): 注意: GPU有 ${gpu_processes} 个进程在运行(可能是之前的服务)"
    fi
else
    echo "$(date): 警告: CUDA检测失败，但将继续尝试启动服务"
fi

# 等待5秒
echo "$(date): 等待5秒..."
sleep 5

# 配置变量
version="1.4.9"
server_name="index-tts-vllm"
image_prefix="d.watchfun.cn/jims57"
image_name="${image_prefix}/${server_name}"
tag="v${version}"

# ============================================================================
# 步骤1: 启动Docker容器(后台运行)
# ============================================================================
echo "$(date): 启动Docker容器..."

# 删除旧容器(如果存在)
docker rm "${server_name}" -f 2>/dev/null

# 启动新容器(在后台运行)
echo "$(date): 运行Docker容器 ${server_name}..."
docker run --gpus all -d -p 9001:9001 --shm-size=4g -w /mnt/index-tts-vllm \
  -v /mnt/index-tts-vllm/checkpoints:/mnt/index-tts-vllm/checkpoints \
  -v /mnt/index-tts-vllm/assets:/mnt/index-tts-vllm/assets \
  -v /mnt/index-tts-vllm/logs:/mnt/index-tts-vllm/logs \
  -v /mnt/index-tts-vllm/savedAudioFiles:/mnt/index-tts-vllm/savedAudioFiles \
  -e API_PORT=9001 --name "${server_name}" "${image_name}:${tag}" tail -f /dev/null

# 等待容器启动
sleep 5

# ============================================================================
# 步骤2: 检查Docker容器状态
# ============================================================================
echo "$(date): 检查Docker容器状态..."

# 检查容器是否正在运行
max_retries=30
retry_count=0
while [ $retry_count -lt $max_retries ]; do
    if docker ps --format '{{.Names}}' | grep -q "^${server_name}$"; then
        echo "$(date): Docker容器 ${server_name} 已启动成功"
        break
    fi
    echo "$(date): 等待Docker容器启动... (${retry_count}/${max_retries})"
    sleep 5
    retry_count=$((retry_count + 1))
done

if [ $retry_count -eq $max_retries ]; then
    echo "$(date): 错误: Docker容器启动超时!"
    exit 1
fi

# ============================================================================
# 步骤3: 在容器内后台启动api_server.py (带重试机制)
# ============================================================================
echo "$(date): 在容器内后台启动api_server.py..."

# 重试启动api_server.py最多5次
max_api_server_retries=5
api_server_retry_count=0
api_server_started=false

while [ $api_server_retry_count -lt $max_api_server_retries ]; do
    echo "$(date): 尝试启动api_server.py (第$((api_server_retry_count + 1))次)..."
    
    # 生成新的日志文件名
    LOG_TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    
    # 清理之前可能残留的api_server.py进程
    docker exec ${server_name} /bin/bash -c "pkill -9 -f api_server.py" 2>/dev/null
    sleep 3
    
    # 在后台运行api_server.py并保存日志到文件
    docker exec -d ${server_name} /bin/bash -c "cd /mnt/index-tts-vllm && nohup /root/miniconda3/envs/index-tts-vllm/bin/python api_server.py --port 6006 --model_dir /mnt/index-tts-vllm/checkpoints/Index-TTS-1.5-vLLM --gpu_memory_utilization 0.25 > /mnt/index-tts-vllm/logs/api_server_py_${LOG_TIMESTAMP}.log 2>&1 &"
    
    # 等待api_server.py启动(需要足够时间加载模型)
    echo "$(date): 等待api_server.py启动和加载模型(最多120秒)..."
    
    # 循环检查进程状态和日志，最多等待120秒
    check_count=0
    max_checks=24
    while [ $check_count -lt $max_checks ]; do
        sleep 5
        check_count=$((check_count + 1))
        
        # 检查日志是否有CUDA错误或启动失败
        if docker exec ${server_name} /bin/bash -c "grep -q 'CUDA error\|CUDA-capable device\|Application startup failed' /mnt/index-tts-vllm/logs/api_server_py_${LOG_TIMESTAMP}.log 2>/dev/null"; then
            echo "$(date): 检测到CUDA错误或启动失败，日志内容:"
            docker exec ${server_name} /bin/bash -c "tail -20 /mnt/index-tts-vllm/logs/api_server_py_${LOG_TIMESTAMP}.log" 2>/dev/null
            break
        fi
        
        # 检查进程是否还在运行
        if ! docker exec ${server_name} /bin/bash -c "ps aux | grep api_server.py | grep -v grep" > /dev/null 2>&1; then
            echo "$(date): api_server.py进程已退出，检查日志..."
            docker exec ${server_name} /bin/bash -c "tail -20 /mnt/index-tts-vllm/logs/api_server_py_${LOG_TIMESTAMP}.log" 2>/dev/null
            break
        fi
        
        # 检查端口6006是否已经在监听(表示启动成功) - 使用curl测试连接
        if docker exec ${server_name} /bin/bash -c "curl -s --connect-timeout 2 http://localhost:6006/ > /dev/null 2>&1 || curl -s --connect-timeout 2 http://localhost:6006/health > /dev/null 2>&1" 2>/dev/null; then
            echo "$(date): api_server.py 端口6006已开始监听，启动成功!"
            api_server_started=true
            break
        fi
        # 备用方法：检查/proc/net/tcp
        if docker exec ${server_name} /bin/bash -c "grep -q ':1776' /proc/net/tcp 2>/dev/null" 2>/dev/null; then
            echo "$(date): api_server.py 端口6006已开始监听(通过/proc检测)，启动成功!"
            api_server_started=true
            break
        fi
        
        echo "$(date): 等待api_server.py... (${check_count}/${max_checks})"
    done
    
    if [ "$api_server_started" = true ]; then
        break
    fi
    
    # 如果没有成功启动，等待一段时间后重试
    echo "$(date): api_server.py 启动失败，等待60秒后重试..."
    docker exec ${server_name} /bin/bash -c "pkill -9 -f api_server.py" 2>/dev/null
    sleep 60
    
    api_server_retry_count=$((api_server_retry_count + 1))
done

if [ "$api_server_started" = false ]; then
    echo "$(date): 错误: api_server.py 在${max_api_server_retries}次尝试后仍未成功启动，退出脚本"
    exit 1
fi

# ============================================================================
# 步骤4: 验证api_server.py TTS服务完全就绪(发送真实TTS请求)
# ============================================================================
echo "$(date): 验证api_server.py TTS服务完全就绪(发送测试TTS请求)..."

# 使用真实TTS请求验证服务是否完全就绪(与api.py的健康检查逻辑一致)
max_tts_retries=60
tts_retry_count=0
tts_ready=false

while [ $tts_retry_count -lt $max_tts_retries ]; do
    # 同时检查进程是否还在运行
    if ! docker exec ${server_name} /bin/bash -c "ps aux | grep api_server.py | grep -v grep" > /dev/null 2>&1; then
        echo "$(date): 错误: api_server.py进程已退出!"
        docker exec ${server_name} /bin/bash -c "tail -30 /mnt/index-tts-vllm/logs/api_server_py_${LOG_TIMESTAMP}.log" 2>/dev/null
        exit 1
    fi
    
    # 发送真实TTS请求测试(与api.py的check_tts_server_ready逻辑一致)
    # 使用/tts_url端口发送测试请求
    tts_response=$(docker exec ${server_name} /bin/bash -c "curl -s -w '%{http_code}' --connect-timeout 60 -X POST http://localhost:6006/tts_url -H 'Content-Type: application/json' -d '{\"text\":\"你好\",\"audio_paths\":[\"assets/jay_promptvn.wav\"],\"seed\":42}' -o /tmp/tts_test.wav 2>/dev/null" 2>/dev/null)
    
    if [ "$tts_response" = "200" ]; then
        # 检查返回的WAV文件大小(至少44字节的WAV头)
        wav_size=$(docker exec ${server_name} /bin/bash -c "stat -c%s /tmp/tts_test.wav 2>/dev/null || echo 0" 2>/dev/null)
        if [ "$wav_size" -gt 44 ]; then
            echo "$(date): api_server.py TTS服务已完全就绪! 收到${wav_size}字节的WAV数据"
            tts_ready=true
            break
        else
            echo "$(date): TTS返回数据过小: ${wav_size}字节，继续等待..."
        fi
    else
        echo "$(date): 等待TTS服务就绪... (${tts_retry_count}/${max_tts_retries}, HTTP状态码: ${tts_response})"
    fi
    
    sleep 3
    tts_retry_count=$((tts_retry_count + 1))
done

if [ "$tts_ready" = false ]; then
    echo "$(date): 警告: TTS服务验证超时，但将继续尝试启动api.py..."
fi

# ============================================================================
# 步骤5: 在容器内后台启动api.py
# ============================================================================
echo "$(date): 在容器内后台启动api.py..."

# 在后台运行api.py并保存日志到文件
docker exec -d ${server_name} /bin/bash -c "cd /mnt/index-tts-vllm && nohup /root/miniconda3/envs/index-tts-vllm/bin/python api.py --port 9001 > /mnt/index-tts-vllm/logs/api_py_${LOG_TIMESTAMP}.log 2>&1 &"

# 等待api.py启动
echo "$(date): 等待api.py启动..."
sleep 10

# 检查api.py是否在运行
if docker exec ${server_name} /bin/bash -c "ps aux | grep 'api.py' | grep -v grep" > /dev/null 2>&1; then
    echo "$(date): api.py 已成功启动"
else
    echo "$(date): 警告: api.py 可能未成功启动"
fi

echo "$(date): Index-TTS服务启动完成!"
echo "$(date): 查看进程: docker exec ${server_name} /bin/bash -c \"ps aux | grep python\""
echo "$(date): 查看api_server.py日志: docker exec -it ${server_name} /bin/bash -c \"tail -f /mnt/index-tts-vllm/logs/api_server_py_*.log\""
echo "$(date): 查看api.py日志: docker exec -it ${server_name} /bin/bash -c \"tail -f /mnt/index-tts-vllm/logs/api_py_*.log\""