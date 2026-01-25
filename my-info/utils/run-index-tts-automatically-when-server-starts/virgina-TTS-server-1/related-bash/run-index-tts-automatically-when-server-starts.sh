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

# 等待Docker服务启动
sleep 10

echo "$(date): 开始启动Index-TTS服务..."

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
# 步骤3: 在容器内后台启动api_server.py
# ============================================================================
echo "$(date): 在容器内后台启动api_server.py..."

# 生成日志文件名
LOG_TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# 在后台运行api_server.py并保存日志到文件
docker exec -d ${server_name} /bin/bash -c "cd /mnt/index-tts-vllm && nohup /root/miniconda3/envs/index-tts-vllm/bin/python api_server.py --port 6006 --model_dir /mnt/index-tts-vllm/checkpoints/Index-TTS-1.5-vLLM --gpu_memory_utilization 0.25 > /mnt/index-tts-vllm/logs/api_server_py_${LOG_TIMESTAMP}.log 2>&1 &"

# 等待api_server.py启动
echo "$(date): 等待api_server.py启动..."
sleep 30

# 检查api_server.py是否在运行
if docker exec ${server_name} /bin/bash -c "ps aux | grep api_server.py | grep -v grep" > /dev/null 2>&1; then
    echo "$(date): api_server.py 已成功启动"
else
    echo "$(date): 警告: api_server.py 可能未成功启动，但将继续尝试启动api.py"
fi

# ============================================================================
# 步骤4: 在容器内后台启动api.py
# ============================================================================
echo "$(date): 在容器内后台启动api.py..."

# 在后台运行api.py并保存日志到文件
docker exec -d ${server_name} /bin/bash -c "cd /mnt/index-tts-vllm && nohup /root/miniconda3/envs/index-tts-vllm/bin/python api.py --port 9001 > /mnt/index-tts-vllm/logs/api_py_${LOG_TIMESTAMP}.log 2>&1 &"

# 等待api.py启动
echo "$(date): 等待api.py启动..."
sleep 5

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