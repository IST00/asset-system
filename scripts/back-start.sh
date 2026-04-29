#!/usr/bin/env bash
# ============================================================================
# back-start.sh — 后端一键启动脚本
#
# 用法：
#   scripts/back-start.sh [dev|prod] [--env-file PATH] [--log-file PATH]
#                                    [--port N] [--workers N] [--bind HOST:PORT]
#
# 示例：
#   # 本地 dev（默认 dev profile）
#   scripts/back-start.sh
#
#   # 指定 dev / prod
#   scripts/back-start.sh dev
#   scripts/back-start.sh prod
#
#   # 指定自定义 env 文件（覆盖默认的 .env.dev / .env.prod）
#   scripts/back-start.sh prod --env-file /etc/back/back.env
#
#   # 指定日志文件位置（默认 back/logs/back-<profile>.log）
#   scripts/back-start.sh prod --log-file /var/log/back/back.log
#
#   # 指定端口（dev 用 --port，prod 用 --bind）
#   scripts/back-start.sh dev --port 8090
#   scripts/back-start.sh prod --bind 0.0.0.0:9000 --workers 8
# ============================================================================

set -euo pipefail

# ---- 定位项目根 & 后端目录 ----
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BACK_DIR="$REPO_ROOT/back"

# ---- 默认值 ----
PROFILE="dev"
ENV_FILE=""
LOG_FILE=""
PORT=""
BIND=""
WORKERS=""

# ---- 参数解析 ----
while [[ $# -gt 0 ]]; do
  case "$1" in
    dev|prod|development|production|test|testing)
      PROFILE="$1"; shift ;;
    --env-file)
      ENV_FILE="$2"; shift 2 ;;
    --env-file=*)
      ENV_FILE="${1#--env-file=}"; shift ;;
    --log-file)
      LOG_FILE="$2"; shift 2 ;;
    --log-file=*)
      LOG_FILE="${1#--log-file=}"; shift ;;
    --port)
      PORT="$2"; shift 2 ;;
    --port=*)
      PORT="${1#--port=}"; shift ;;
    --bind)
      BIND="$2"; shift 2 ;;
    --bind=*)
      BIND="${1#--bind=}"; shift ;;
    --workers)
      WORKERS="$2"; shift 2 ;;
    --workers=*)
      WORKERS="${1#--workers=}"; shift ;;
    -h|--help)
      sed -n '2,25p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *)
      echo "❌ 未知参数: $1" >&2
      echo "运行 '$0 --help' 查看用法" >&2
      exit 2 ;;
  esac
done

# ---- profile 规范化 ----
case "$PROFILE" in
  dev|development) PROFILE_SHORT="dev" ;;
  prod|production) PROFILE_SHORT="prod" ;;
  test|testing)    PROFILE_SHORT="test" ;;
  *) echo "❌ 非法 profile: $PROFILE" >&2; exit 2 ;;
esac

# ---- 默认 env 文件：back/.env.<short> ----
if [[ -z "$ENV_FILE" ]]; then
  ENV_FILE="$BACK_DIR/.env.$PROFILE_SHORT"
fi
if [[ ! -f "$ENV_FILE" ]]; then
  echo "❌ env 文件不存在: $ENV_FILE" >&2
  exit 2
fi

# ---- 默认日志文件：back/logs/back-<profile>.log ----
if [[ -z "$LOG_FILE" ]]; then
  LOG_FILE="$BACK_DIR/logs/back-$PROFILE_SHORT.log"
fi
mkdir -p "$(dirname "$LOG_FILE")"

# ---- 导出 FLASK_ENV + ENV_FILE（让 config.bootstrap_env 读我们指定的文件） ----
export FLASK_ENV="$PROFILE_SHORT"
export ENV_FILE                       # config.py:_resolve_env_file 会优先使用这个
export LOG_FILE                       # observability._resolve_log_file 会优先使用这个
export LOG_FILE_ENABLED="${LOG_FILE_ENABLED:-true}"
export LOG_CONSOLE="${LOG_CONSOLE:-true}"

# ---- 激活 venv（可选） ----
if [[ -f "$BACK_DIR/.venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "$BACK_DIR/.venv/bin/activate"
fi

# ---- 启动 banner ----
cat <<EOF
────────────────────────────────────────────────
 Scaffold Python Back — 启动中
   profile   : $PROFILE_SHORT
   env_file  : $ENV_FILE
   log_file  : $LOG_FILE
   python    : $(python --version 2>&1)
   cwd       : $BACK_DIR
────────────────────────────────────────────────
EOF

cd "$BACK_DIR"

# ---- 启动命令（dev = flask dev server，prod = gunicorn）----
if [[ "$PROFILE_SHORT" == "prod" ]]; then
  # gunicorn.conf.py 的默认值会被下面的 env 覆盖
  [[ -n "$BIND" ]]    && export GUNICORN_BIND="$BIND"
  [[ -n "$WORKERS" ]] && export GUNICORN_WORKERS="$WORKERS"
  # 让 gunicorn 自己的 access/error log 也落到同一个 LOG_FILE，
  # 这样 "Starting gunicorn..." / "Listening at..." / 访问日志都在一个文件里。
  # 用户显式设过就不覆盖。
  export GUNICORN_ACCESS_LOG="${GUNICORN_ACCESS_LOG:-$LOG_FILE}"
  export GUNICORN_ERROR_LOG="${GUNICORN_ERROR_LOG:-$LOG_FILE}"
  exec gunicorn -c gunicorn.conf.py wsgi:app
else
  CMD=(python manage.py run "$PROFILE_SHORT")
  [[ -n "$PORT" ]] && CMD+=(--port "$PORT")
  exec "${CMD[@]}"
fi
