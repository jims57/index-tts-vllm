#!/bin/bash

# ============================================================================
# Index-TTS-vLLM 自动启动脚本
# 功能: 服务器启动时自动挂载NAS并启动Index-TTS服务
# 用法: 通过crontab @reboot运行
# ============================================================================

set -e

# ============================================================================
# 配置参数
# ============================================================================
NAS_URL="13b67948707-hme76.us-east-1.nas.aliyuncs.com"
version="1.5.0"
server_name="index-tts-vllm"
image_prefix="d.watchfun.cn/jims57"
image_name="${image_prefix}/${server_name}"
tag="v${version}"
API_PORT=9001
LOG_FILE="/var/log/index-tts-startup.log"
LOG_TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# 日志函数
log() {
    echo "$(date): $1" | tee -a "$LOG_FILE"
}

log "=========================================="
log "Index-TTS-vLLM 自动启动脚本开始执行"
log "=========================================="

# ============================================================================
# 步骤1: 检查并挂载NAS目录
# ============================================================================
log "步骤1: 检查NAS挂载状态..."

# 创建挂载目录
sudo mkdir -p /mnt/index-tts-vllm/assets
sudo mkdir -p /mnt/index-tts-vllm/logs
sudo mkdir -p /mnt/index-tts-vllm/savedAudioFiles

# 挂载函数(带重试)
mount_with_retry() {
    local remote="$1"
    local target="$2"
    local name="$3"
    local max_retry=30
    local retry=0

    while [ $retry -lt $max_retry ]; do
        if mountpoint -q "$target"; then
            log "${name} 已挂载: ${target}"
            return 0
        fi

        log "正在挂载${name}... (${retry}/${max_retry})"
        sudo mount -t nfs "$remote" "$target" >/dev/null 2>&1 || true
        sleep 2
        retry=$((retry + 1))
    done

    log "错误: 挂载${name}超时: ${remote} -> ${target}"
    return 1
}

# 挂载所有NAS目录
mount_with_retry "${NAS_URL}:/index-tts-vllm/assets" /mnt/index-tts-vllm/assets "assets"
mount_with_retry "${NAS_URL}:/index-tts-vllm/logs" /mnt/index-tts-vllm/logs "logs"
mount_with_retry "${NAS_URL}:/index-tts-vllm/savedAudioFiles" /mnt/index-tts-vllm/savedAudioFiles "savedAudioFiles"

# 验证所有目录都已挂载
all_mounted=true
for dir in /mnt/index-tts-vllm/assets /mnt/index-tts-vllm/logs /mnt/index-tts-vllm/savedAudioFiles; do
    if ! mountpoint -q "$dir"; then
        log "错误: ${dir} 未成功挂载"
        all_mounted=false
    fi
done

if [ "$all_mounted" = false ]; then
    log "错误: NAS挂载失败，脚本退出"
    exit 1
fi

log "所有NAS目录挂载成功"

# ============================================================================
# 步骤2: 启动Docker容器
# ============================================================================
log "步骤2: 启动Docker容器..."

# 等待Docker服务就绪
docker_retry=0
max_docker_retry=30
while [ $docker_retry -lt $max_docker_retry ]; do
    if docker info >/dev/null 2>&1; then
        log "Docker服务已就绪"
        break
    fi
    log "等待Docker服务... (${docker_retry}/${max_docker_retry})"
    sleep 2
    docker_retry=$((docker_retry + 1))
done

if [ $docker_retry -eq $max_docker_retry ]; then
    log "错误: Docker服务启动超时"
    exit 1
fi

# 删除旧容器(如果存在)
docker rm "${server_name}" -f 2>/dev/null || true
sleep 2

# 启动新容器
log "启动容器: ${image_name}:${tag}"
docker run --gpus all -d -p ${API_PORT}:${API_PORT} --shm-size=4g -w /mnt/index-tts-vllm \
    -v /mnt/index-tts-vllm/checkpoints:/mnt/index-tts-vllm/checkpoints \
    -v /mnt/index-tts-vllm/assets:/mnt/index-tts-vllm/assets \
    -v /mnt/index-tts-vllm/logs:/mnt/index-tts-vllm/logs \
    -v /mnt/index-tts-vllm/savedAudioFiles:/mnt/index-tts-vllm/savedAudioFiles \
    -e API_PORT=${API_PORT} \
    --name "${server_name}" "${image_name}:${tag}" tail -f /dev/null

# 等待容器启动
sleep 5

# 验证容器运行状态
if ! docker ps | grep -q "${server_name}"; then
    log "错误: 容器启动失败"
    exit 1
fi

log "容器启动成功"

# ============================================================================
# 步骤3: 启动api.py
# ============================================================================
log "步骤3: 启动api.py..."

docker exec -d ${server_name} /bin/bash -c "cd /mnt/index-tts-vllm && nohup /root/miniconda3/envs/index-tts-vllm/bin/python api.py --port ${API_PORT} > /mnt/index-tts-vllm/logs/api_py_${LOG_TIMESTAMP}.log 2>&1 &"

sleep 3

# 验证api.py进程
if docker exec ${server_name} /bin/bash -c "ps aux | grep 'api.py' | grep -v grep" > /dev/null 2>&1; then
    log "api.py 启动成功"
else
    log "警告: api.py 进程未检测到"
fi

# ============================================================================
# 步骤4: 启动api_server.py
# ============================================================================
log "步骤4: 启动api_server.py..."

docker exec -d ${server_name} /bin/bash -c "cd /mnt/index-tts-vllm && nohup /root/miniconda3/envs/index-tts-vllm/bin/python api_server.py --port 6006 --model_dir /mnt/index-tts-vllm/checkpoints/Index-TTS-1.5-vLLM --gpu_memory_utilization 0.25 > /mnt/index-tts-vllm/logs/api_server_py_${LOG_TIMESTAMP}.log 2>&1 &"

sleep 3

# 验证api_server.py进程
if docker exec ${server_name} /bin/bash -c "ps aux | grep 'api_server.py' | grep -v grep" > /dev/null 2>&1; then
    log "api_server.py 启动成功"
else
    log "警告: api_server.py 进程未检测到"
fi

# ============================================================================
# 完成
# ============================================================================
log "=========================================="
log "Index-TTS-vLLM 自动启动脚本执行完成"
log "api.py 日志: /mnt/index-tts-vllm/logs/api_py_${LOG_TIMESTAMP}.log"
log "api_server.py 日志: /mnt/index-tts-vllm/logs/api_server_py_${LOG_TIMESTAMP}.log"
log "=========================================="

exit 0