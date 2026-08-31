#!/usr/bin/env bash
# Bear Code 启动脚本（Git Bash 使用：bash run.sh 或 ./run.sh）
cd "$(dirname "$0")"

if [ ! -f ".venv/Scripts/activate" ]; then
    echo "[错误] 未找到 .venv，请先创建虚拟环境并安装依赖。"
    exit 1
fi

source .venv/Scripts/activate
python -m agents.main
