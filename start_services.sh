#!/bin/bash
# 启动 api.py 和 api_server.py 服务

cd /mnt/index-tts-vllm

# 添加conda环境的bin目录到PATH（确保ninja可执行）
export PATH="/root/miniconda3/envs/index-tts-vllm/bin:$PATH"

# 启动 api.py（使用环境变量API_PORT，默认9001）
API_PORT=${API_PORT:-9001}
nohup /root/miniconda3/envs/index-tts-vllm/bin/python api.py --port ${API_PORT} --index-tts-url http://localhost:6006 >> /mnt/index-tts-vllm/logs/api-py.log 2>&1 &

# 启动 api_server.py
nohup /root/miniconda3/envs/index-tts-vllm/bin/python api_server.py --model_dir ./checkpoints/Index-TTS-1.5-vLLM >> /mnt/index-tts-vllm/logs/api-server-py.log 2>&1 &

# 显示日志
# tail -f /mnt/index-tts-vllm/logs/api-py.log

# 启动交互式bash（可以输入命令）
exec /bin/bash