#!/bin/bash
# 启动 api.py 和 api_server.py 服务

cd /mnt/index-tts-vllm

# 启动 api.py
nohup /root/miniconda3/envs/index-tts-vllm/bin/python api.py --port 9001 --index-tts-url http://localhost:6006 >> /mnt/index-tts-vllm/logs/api-py.log 2>&1 &

# 启动 api_server.py
nohup /root/miniconda3/envs/index-tts-vllm/bin/python api_server.py --model_dir ./checkpoints/Index-TTS-1.5-vLLM >> /mnt/index-tts-vllm/logs/api-server-py.log 2>&1 &

# 显示日志
tail -f /mnt/index-tts-vllm/logs/api-py.log
