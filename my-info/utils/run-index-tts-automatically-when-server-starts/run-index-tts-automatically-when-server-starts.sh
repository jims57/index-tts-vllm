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
# 查看tmux会话: tmux ls
# 进入tmux会话: tmux attach -t indextts-server 或 tmux attach -t indextts
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
# 步骤1: 在tmux会话(indextts-server)中启动Docker容器和api_server.py
# ============================================================================
echo "$(date): 创建tmux会话 indextts-server 并启动Docker容器..."

# 先删除已存在的tmux会话(如果有)
tmux kill-session -t indextts-server 2>/dev/null

# 创建新的tmux会话并运行Docker容器
tmux new-session -d -s indextts-server

# 方法1: 在tmux会话中启动容器，然后在同一会话中运行命令
# 发送命令到tmux会话: 删除旧容器并启动新容器(使用-d后台模式)
tmux send-keys -t indextts-server "docker rm \"${server_name}\" -f 2>/dev/null; docker run -d --gpus all -p 9001:9001 --shm-size=4g -w /mnt/index-tts-vllm -v /mnt/index-tts-vllm/checkpoints:/mnt/index-tts-vllm/checkpoints -v /mnt/index-tts-vllm/assets:/mnt/index-tts-vllm/assets -v /mnt/index-tts-vllm/logs:/mnt/index-tts-vllm/logs -v /mnt/index-tts-vllm/savedAudioFiles:/mnt/index-tts-vllm/savedAudioFiles -e API_PORT=9001 --name \"${server_name}\" \"${image_name}:${tag}\" tail -f /dev/null" Enter

# 等待容器启动
sleep 5

# 在容器中安装Python
echo "$(date): 在容器中安装Python..."
tmux send-keys -t indextts-server "docker exec \"${server_name}\" apt-get update -y && docker exec \"${server_name}\" apt-get install -y python3 python3-pip && docker exec \"${server_name}\" ln -sf /usr/bin/python3 /usr/bin/python" Enter

# 等待Python安装完成
sleep 20

# 使用docker exec在容器内运行api_server.py
echo "$(date): 启动api_server.py..."
tmux send-keys -t indextts-server "docker exec -it \"${server_name}\" python api_server.py --port 6006 --model_dir /mnt/index-tts-vllm/checkpoints/Index-TTS-1.5-vLLM --gpu_memory_utilization 0.25" Enter

echo "$(date): Docker容器启动命令已发送到 indextts-server 会话"

# ============================================================================
# 步骤2: 等待Docker容器启动并检查状态
# ============================================================================
echo "$(date): 等待Docker容器启动..."
sleep 10

# 检查容器是否正在运行
max_retries=30
retry_count=0
while [ $retry_count -lt $max_retries ]; do
    if docker ps --format '{{.Names}}' | grep -q "^${server_name}$"; then
        echo "$(date): Docker容器 ${server_name} 已启动"
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

# 等待api_server.py完全启动(检查端口6006)
echo "$(date): 等待api_server.py启动(端口6006)..."
max_retries=60
retry_count=0
while [ $retry_count -lt $max_retries ]; do
    if docker exec ${server_name} bash -c 'netstat -tlnp 2>/dev/null | grep -q ":6006" || ss -tlnp 2>/dev/null | grep -q ":6006"' 2>/dev/null; then
        echo "$(date): api_server.py 已在端口6006启动"
        break
    fi
    echo "$(date): 等待api_server.py启动... (${retry_count}/${max_retries})"
    sleep 5
    retry_count=$((retry_count + 1))
done

if [ $retry_count -eq $max_retries ]; then
    echo "$(date): 警告: api_server.py启动超时，继续尝试启动api.py..."
fi

# ============================================================================
# 步骤3: 在tmux会话(indextts)中运行api.py
# ============================================================================
echo "$(date): 创建tmux会话 indextts 并运行api.py..."

# 先删除已存在的tmux会话(如果有)
tmux kill-session -t indextts 2>/dev/null

# 创建新的tmux会话
tmux new-session -d -s indextts

# 发送命令到tmux会话: 进入Docker容器并运行api.py
tmux send-keys -t indextts "docker exec -it ${server_name} python api.py --port 9001" Enter

echo "$(date): api.py启动命令已发送到 indextts 会话"

echo "$(date): Index-TTS服务启动完成!"
echo "$(date): 使用 'tmux attach -t indextts-server' 查看Docker容器状态"
echo "$(date): 使用 'tmux attach -t indextts' 查看api.py状态"