#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
TOOL_SCRIPT="$SCRIPT_DIR/scripts/code_change_check.py"
PYTHON_CMD=""

if command -v python3 >/dev/null 2>&1; then
    if python3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >/dev/null 2>&1; then
        PYTHON_CMD="python3"
    fi
fi

if [ -z "$PYTHON_CMD" ] && command -v python >/dev/null 2>&1; then
    if python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >/dev/null 2>&1; then
        PYTHON_CMD="python"
    fi
fi

if [ -z "$PYTHON_CMD" ]; then
    echo "未检测到 Python 3.10+。"
    echo "请先安装 Python 3.10 或更高版本：https://www.python.org/downloads/"
    echo "安装后请确认 python3 或 python 命令可用。"
    exit 1
fi

NEED_INTERACTIVE=1
for arg in "$@"; do
    case "$arg" in
        --interactive|--no-interactive|--base-ref|--base-ref=*|--target-ref|--target-ref=*|--svn-revision|--svn-revision=*|--baseline|--baseline=*|--scan-all)
            NEED_INTERACTIVE=0
            ;;
    esac
done

if [ "$NEED_INTERACTIVE" = "1" ]; then
    exec "$PYTHON_CMD" "$TOOL_SCRIPT" --interactive "$@"
fi

exec "$PYTHON_CMD" "$TOOL_SCRIPT" "$@"
