# download model from modelscope

# upload files in assets to server

# upload mount-nas-to-ecs.sh to root of server

# chmod +x /root/mount-nas-to-ecs.sh

# bash /root/mount-nas-to-ecs.sh 13b67948707-hme76.us-east-1.nas.aliyuncs.com

# check if mounted
ls /mnt/index-tts-vllm/assets

# upload run-index-tts-automatically-when-server-starts.shh to root of server

# login wq repository:
docker login --username=jimmy d.watchfun.cn

# chmod +x run-index-tts-automatically-when-server-starts.sh
# ./run-index-tts-automatically-when-server-starts.sh


crontab -e
# Add this line:
@reboot /root/run-index-tts-automatically-when-server-starts.sh >> /var/log/index-tts-startup.log 2>&1

