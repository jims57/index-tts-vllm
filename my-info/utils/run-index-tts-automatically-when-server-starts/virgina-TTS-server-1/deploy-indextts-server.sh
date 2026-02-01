#!/bin/bash
# ============================================================================
# 脚本名称: deploy-indextts-server.sh
# 功能: 部署Index-TTS自动启动脚本到目标服务器
# 
# 使用方法:
# ./deploy-indextts-server.sh <服务器IP> <私钥路径>
# 
# 示例:
# chmod +x deploy-indextts-server.sh
# ./deploy-indextts-server.sh 8.221.124.14 /Users/mac/.ssh/aliyun/Jimmy-US-Virginia-Private-Key.pem
# ============================================================================

# 检查参数
if [ $# -ne 2 ]; then
    echo "错误: 需要提供两个参数 - 服务器IP和私钥路径"
    echo "用法: $0 <服务器IP> <私钥路径>"
    echo "示例: $0 8.221.124.14 /Users/mac/.ssh/aliyun/Jimmy-US-Virginia-Private-Key.pem"
    exit 1
fi

SERVER_IP=$1
PRIVATE_KEY=$2

# 检查私钥文件是否存在
if [ ! -f "$PRIVATE_KEY" ]; then
    echo "错误: 私钥文件 '$PRIVATE_KEY' 不存在"
    exit 1
fi

# 脚本路径
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_SCRIPT="$SCRIPT_DIR/related-bash/run-index-tts-automatically-when-server-starts.sh"

# 检查运行脚本是否存在
if [ ! -f "$RUN_SCRIPT" ]; then
    echo "错误: 运行脚本 '$RUN_SCRIPT' 不存在"
    exit 1
fi

echo "============================================================"
echo "开始部署Index-TTS自动启动脚本到服务器: $SERVER_IP"
echo "============================================================"

# 上传脚本到服务器
echo "正在上传脚本到服务器..."
scp -i "$PRIVATE_KEY" -o StrictHostKeyChecking=no "$RUN_SCRIPT" "root@$SERVER_IP:/root/run-index-tts-automatically-when-server-starts.sh"

if [ $? -ne 0 ]; then
    echo "错误: 上传脚本失败"
    exit 1
fi

echo "脚本上传成功"

# 设置执行权限
echo "正在设置执行权限..."
ssh -i "$PRIVATE_KEY" -o StrictHostKeyChecking=no "root@$SERVER_IP" "chmod +x /root/run-index-tts-automatically-when-server-starts.sh"

if [ $? -ne 0 ]; then
    echo "错误: 设置执行权限失败"
    exit 1
fi

echo "执行权限设置成功"

# 配置开机自启动
echo "正在配置开机自启动..."
ssh -i "$PRIVATE_KEY" -o StrictHostKeyChecking=no "root@$SERVER_IP" "crontab -l 2>/dev/null | grep -v 'run-index-tts-automatically-when-server-starts.sh' | { cat; echo '@reboot /root/run-index-tts-automatically-when-server-starts.sh >> /var/log/index-tts-startup.log 2>&1'; } | crontab -"

if [ $? -ne 0 ]; then
    echo "错误: 配置开机自启动失败"
    exit 1
fi

echo "开机自启动配置成功"

# 创建日志文件
echo "正在创建日志文件..."
ssh -i "$PRIVATE_KEY" -o StrictHostKeyChecking=no "root@$SERVER_IP" "touch /var/log/index-tts-startup.log && chmod 644 /var/log/index-tts-startup.log"

if [ $? -ne 0 ]; then
    echo "警告: 创建日志文件失败，但不影响部署"
fi

echo "============================================================"
echo "部署完成！"
echo "============================================================"
echo "脚本已上传到: /root/run-index-tts-automatically-when-server-starts.sh"
echo "启动日志位置: /var/log/index-tts-startup.log"
echo "服务器重启后将自动启动Index-TTS服务"
echo ""
echo "============================================================"
echo "常用命令:"
echo "============================================================"
echo ""
echo "1. 手动运行脚本:"
echo "   ssh -i \"$PRIVATE_KEY\" root@$SERVER_IP \"bash /root/run-index-tts-automatically-when-server-starts.sh\""
echo ""
echo "2. 查看启动日志:"
echo "   ssh -i \"$PRIVATE_KEY\" root@$SERVER_IP \"tail -f /var/log/index-tts-startup.log\""
echo ""
echo "3. 查看容器状态:"
echo "   ssh -i \"$PRIVATE_KEY\" root@$SERVER_IP \"docker ps\""
echo ""
echo "4. 查看Python进程:"
echo "   ssh -i \"$PRIVATE_KEY\" root@$SERVER_IP \"docker exec index-tts-vllm ps aux | grep python\""
echo ""
echo "============================================================"
echo "查看应用日志 (日志路径格式: /mnt/index-tts-vllm/logs/{创建时间}/{服务器IP}/):"
echo "============================================================"
echo ""
echo "5. 查看api.py实时日志:"
echo "   ssh -i \"$PRIVATE_KEY\" root@$SERVER_IP \"docker exec index-tts-vllm /bin/bash -c 'tail -f /mnt/index-tts-vllm/logs/\\\$(ls -t /mnt/index-tts-vllm/logs/ | head -1)/\\\$(curl -s ifconfig.me)/api_py_current.log'\""
echo ""
echo "6. 查看api_server.py实时日志:"
echo "   ssh -i \"$PRIVATE_KEY\" root@$SERVER_IP \"docker exec index-tts-vllm /bin/bash -c 'tail -f /mnt/index-tts-vllm/logs/\\\$(ls -t /mnt/index-tts-vllm/logs/ | head -1)/\\\$(curl -s ifconfig.me)/api_server_py_current.log'\""
echo ""
echo "7. 列出所有日志目录:"
echo "   ssh -i \"$PRIVATE_KEY\" root@$SERVER_IP \"ls -la /mnt/index-tts-vllm/logs/\""
echo ""
echo "8. 查看归档日志:"
echo "   ssh -i \"$PRIVATE_KEY\" root@$SERVER_IP \"ls -la /mnt/index-tts-vllm/logs/\\\$(ls -t /mnt/index-tts-vllm/logs/ | head -1)/\\\$(curl -s ifconfig.me)/archived-logs/\""
echo ""
echo "============================================================"