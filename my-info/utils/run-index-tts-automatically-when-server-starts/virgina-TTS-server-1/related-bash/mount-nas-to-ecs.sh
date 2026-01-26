#!/bin/bash
 
 # 挂载NAS到ECS (NFS)
 # 用法: 
 # bash /root/mount-nas-to-ecs.sh 13b67948707-hme76.us-east-1.nas.aliyuncs.com
 
 if [ $# -ne 1 ]; then
     echo "错误: 需要提供nasUrl参数"
     echo "用法: $0 <nasUrl>"
     echo "示例: $0 13b67948707-hme76.us-east-1.nas.aliyuncs.com"
     exit 1
 fi
 
 NAS_URL="$1"
 
 # 避免因一次mount失败直接退出，使用重试机制保证挂载成功
 
 set -e
 
 sudo apt-get update && sudo apt-get install -y nfs-common
 
 sudo mkdir -p /mnt/index-tts-vllm/assets
 sudo mkdir -p /mnt/index-tts-vllm/logs
 sudo mkdir -p /mnt/index-tts-vllm/savedAudioFiles
 
 mount_with_retry() {
     local remote="$1"
     local target="$2"
     local name="$3"
     local max_retry=30
     local retry=0
 
     while [ $retry -lt $max_retry ]; do
         if mountpoint -q "$target"; then
             echo "$(date): ${name} 已挂载: ${target}"
             return 0
         fi
 
         echo "$(date): 正在挂载${name}... (${retry}/${max_retry})"
         sudo mount -t nfs "$remote" "$target" >/dev/null 2>&1 || true
         sleep 2
         retry=$((retry + 1))
     done
 
     echo "$(date): 错误: 挂载${name}超时: ${remote} -> ${target}"
     return 1
 }
 
 mount_with_retry "${NAS_URL}:/index-tts-vllm/assets" /mnt/index-tts-vllm/assets "assets"
 mount_with_retry "${NAS_URL}:/index-tts-vllm/logs" /mnt/index-tts-vllm/logs "logs"
 mount_with_retry "${NAS_URL}:/index-tts-vllm/savedAudioFiles" /mnt/index-tts-vllm/savedAudioFiles "savedAudioFiles"