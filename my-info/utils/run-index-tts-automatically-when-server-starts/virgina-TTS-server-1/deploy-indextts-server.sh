#!/bin/bash
# ============================================================================
# 脚本名称: deploy-indextts-server.sh
# 功能: 部署Index-TTS自动启动脚本到目标服务器
# 
# 使用方法:
# ./deploy-indextts-server.sh <服务器IP> <私钥路径>
# 
# 示例:
# ./deploy-indextts-server.sh 47.85.102.125 /Users/mac/.ssh/aliyun/Jimmy-US-Virginia-Private-Key.pem
# ============================================================================

# 检查参数
if [ $# -ne 2 ]; then
    echo "错误: 需要提供两个参数 - 服务器IP和私钥路径"
    echo "用法: $0 <服务器IP> <私钥路径>"
    echo "示例: $0 47.85.102.125 /Users/mac/.ssh/aliyun/Jimmy-US-Virginia-Private-Key.pem"
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
echo "日志文件位置: /var/log/index-tts-startup.log"
echo "服务器重启后将自动启动Index-TTS服务"
echo ""
echo "手动运行脚本: ssh -i \"$PRIVATE_KEY\" root@$SERVER_IP \"bash /root/run-index-tts-automatically-when-server-starts.sh\""
echo "查看日志: ssh -i \"$PRIVATE_KEY\" root@$SERVER_IP \"tail -f /var/log/index-tts-startup.log\""
echo "查看tmux会话: ssh -i \"$PRIVATE_KEY\" root@$SERVER_IP \"tmux ls\""
echo "============================================================"