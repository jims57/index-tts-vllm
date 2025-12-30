#!/bin/bash

# 同步本地文件到远程服务器Docker容器的脚本
# 只同步指定的文件，提高性能
# 支持同步到容器内部，而不是宿主机

# Usage:
# cd /Users/mac/Documents/GitHub/index-tts-vllm/my-info/utils/sync_files_to_server && ./sync_files_to_server.sh

# 默认配置
LOCAL_BASE_DIR="/Users/mac/Documents/GitHub/index-tts-vllm"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RECORDS_FILE="$SCRIPT_DIR/last_changes_records.json"
SSH_KEY="/Users/mac/.ssh/aliyun/WQ/Jimmy-TTS-Private-Key-SH.pem"
SSH_HOST="root@8.153.108.254"
SSH_PORT="22"
CONTAINER_NAME="index-tts-vllm"
CONTAINER_DEST="/mnt/index-tts-vllm"
TEMP_DIR="/tmp/sync_to_index_tts"

# 指定要同步的文件列表（相对于LOCAL_BASE_DIR的路径）
SYNC_FILE_LIST=(
    "api.py"
    "api_documentation.html"
)

# 解析命令行参数
while [[ $# -gt 0 ]]; do
    case $1 in
        --container)
            CONTAINER_NAME="$2"
            shift 2
            ;;
        --dest)
            CONTAINER_DEST="$2"
            shift 2
            ;;
        --host)
            SSH_HOST="$2"
            shift 2
            ;;
        --port)
            SSH_PORT="$2"
            shift 2
            ;;
        --help)
            echo "Usage: $0 [options]"
            echo "Options:"
            echo "  --container NAME   Docker container name (default: index-tts-vllm)"
            echo "  --dest PATH        Destination path inside container (default: /mnt/index-tts-vllm)"
            echo "  --host USER@HOST   SSH host (default: root@8.153.108.254)"
            echo "  --port PORT        SSH port (default: 22)"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}=== 开始同步文件到远程Docker容器 ===${NC}"
echo -e "服务器: $SSH_HOST:$SSH_PORT"
echo -e "容器: $CONTAINER_NAME"
echo -e "目标路径: $CONTAINER_DEST"

# 检查SSH密钥是否存在
if [ ! -f "$SSH_KEY" ]; then
    echo -e "${RED}错误: SSH密钥不存在: $SSH_KEY${NC}"
    exit 1
fi

# 检查本地目录是否存在
if [ ! -d "$LOCAL_BASE_DIR" ]; then
    echo -e "${RED}错误: 本地目录不存在: $LOCAL_BASE_DIR${NC}"
    exit 1
fi

# 初始化记录文件（如果不存在或为空）
if [ ! -f "$RECORDS_FILE" ] || [ ! -s "$RECORDS_FILE" ]; then
    echo '{}' > "$RECORDS_FILE"
fi

# 读取现有记录
RECORDS=$(cat "$RECORDS_FILE")

# 用于存储需要同步的文件
SYNC_FILES=()
NEW_RECORDS="{}"

# 遍历指定的文件列表
echo -e "${YELLOW}检查文件变化...${NC}"
for REL_PATH in "${SYNC_FILE_LIST[@]}"; do
    file="$LOCAL_BASE_DIR/$REL_PATH"
    
    # 检查文件是否存在
    if [ ! -f "$file" ]; then
        echo -e "  ${RED}[不存在]${NC} $REL_PATH"
        continue
    fi
    
    # 获取文件修改时间（秒级时间戳）
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        MTIME=$(stat -f "%m" "$file")
    else
        # Linux
        MTIME=$(stat -c "%Y" "$file")
    fi
    
    # 从记录中获取上次同步时间
    LAST_SYNC=$(echo "$RECORDS" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('$REL_PATH', 0))" 2>/dev/null || echo "0")
    
    # 如果文件有变化或是新文件，添加到同步列表
    if [ "$MTIME" -gt "$LAST_SYNC" ]; then
        SYNC_FILES+=("$REL_PATH")
        echo -e "  ${GREEN}[变化]${NC} $REL_PATH"
    else
        echo -e "  ${YELLOW}[无变化]${NC} $REL_PATH"
    fi
    
    # 更新记录（使用当前修改时间）
    NEW_RECORDS=$(echo "$NEW_RECORDS" | python3 -c "import sys,json; d=json.load(sys.stdin); d['$REL_PATH']=$MTIME; print(json.dumps(d, indent=2, ensure_ascii=False))")
    
done

# 如果没有文件需要同步
if [ ${#SYNC_FILES[@]} -eq 0 ]; then
    echo -e "${GREEN}所有文件都是最新的，无需同步${NC}"
    exit 0
fi

echo -e "${YELLOW}共 ${#SYNC_FILES[@]} 个文件需要同步${NC}"

# 创建临时目录
rm -rf "$TEMP_DIR"
mkdir -p "$TEMP_DIR"

# 复制需要同步的文件到临时目录（保持目录结构）
for REL_PATH in "${SYNC_FILES[@]}"; do
    SRC_FILE="$LOCAL_BASE_DIR/$REL_PATH"
    DEST_FILE="$TEMP_DIR/$REL_PATH"
    DEST_DIR=$(dirname "$DEST_FILE")
    mkdir -p "$DEST_DIR"
    cp "$SRC_FILE" "$DEST_FILE"
done

# 使用rsync同步到远程服务器临时目录
echo -e "${YELLOW}正在同步到远程服务器...${NC}"
REMOTE_TEMP="/tmp/sync_from_local"

# 先在远程创建临时目录
ssh -i "$SSH_KEY" -p "$SSH_PORT" "$SSH_HOST" "rm -rf $REMOTE_TEMP && mkdir -p $REMOTE_TEMP"

# rsync到远程服务器
rsync -avz --progress -e "ssh -i $SSH_KEY -p $SSH_PORT" "$TEMP_DIR/" "$SSH_HOST:$REMOTE_TEMP/"

if [ $? -ne 0 ]; then
    echo -e "${RED}错误: rsync同步失败${NC}"
    rm -rf "$TEMP_DIR"
    exit 1
fi

# 在远程服务器上将文件复制到Docker容器
echo -e "${YELLOW}正在复制到Docker容器 $CONTAINER_NAME...${NC}"
ssh -i "$SSH_KEY" -p "$SSH_PORT" "$SSH_HOST" << EOF
    # 遍历临时目录中的所有文件并复制到容器
    cd $REMOTE_TEMP
    for file in \$(find . -type f); do
        # 获取相对路径（去掉开头的./）
        rel_path=\${file#./}
        # 获取目标目录
        dest_dir=\$(dirname "$CONTAINER_DEST/\$rel_path")
        # 在容器中创建目录
        docker exec $CONTAINER_NAME mkdir -p "\$dest_dir"
        # 复制文件到容器
        docker cp "\$file" "$CONTAINER_NAME:$CONTAINER_DEST/\$rel_path"
        echo "  已复制: \$rel_path"
    done
    # 清理临时目录
    rm -rf $REMOTE_TEMP
EOF

if [ $? -ne 0 ]; then
    echo -e "${RED}错误: 复制到Docker容器失败${NC}"
    rm -rf "$TEMP_DIR"
    exit 1
fi

# 清理本地临时目录
rm -rf "$TEMP_DIR"

# 保存新的记录
echo "$NEW_RECORDS" > "$RECORDS_FILE"

echo -e "${GREEN}=== 同步完成! ===${NC}"
echo -e "已同步 ${#SYNC_FILES[@]} 个文件到 $CONTAINER_NAME:$CONTAINER_DEST"