#!/usr/bin/env bash
# ============================================================================
# rename-project.sh — Fork 一份脚手架后用来做一次性项目改名。
#
# 本仓 ( scaffolding-all/ ) 里所有"项目名占位"统一用 literal 字符串：
#   scaffold   -> kebab / lower-case 形式 (URL base、artifactId、docker、env 等)
#   Scaffold   -> TitleCase 形式 (页面标题、OpenAPI title、README 标题等)
#
# 注意：仓库名 scaffolding-java / scaffolding-python / scaffolding-middleware /
#       scaffolding-all 里的 "scaffolding" 不是项目名占位，只是本仓自己的目录名，
#       不参与替换。脚本只用 word-boundary 匹配 \bscaffold\b / \bScaffold\b，
#       所以 "scaffolding-java" 不会被改成 "my-awesome-apping-java"。
#
# 使用：
#   ./rename-project.sh <new-name>                   # 默认 dry-run，只打印 diff
#   ./rename-project.sh <new-name> --apply           # 实际写入
#   ./rename-project.sh <new-name> --apply --backup  # 实际写入并保留 .bak 备份
#   ./rename-project.sh <new-name> --apply --pom     # 自动探测 back/pom.xml 并改 artifactId/name
#
# 项目类型自动探测：
#   1) 若存在 ./back/pom.xml 或 ./scaffolding-java/back/pom.xml      → java
#   2) 若存在 ./back/pyproject.toml / requirements.txt 或 scaffolding-python/back/* → python
#   3) 否则 unknown
# --pom 仅在 java 项目下生效；其他类型会自动跳过 pom 改写并提示。
#
# 前端 package.json 自动改名（默认行为，无需 flag）：
#   会扫描 ./front/package.json、./scaffolding-java/front/package.json、
#   ./scaffolding-python/front/package.json 三处候选；找到的每一份都会把顶层
#   "name": "..." 改成 "<new-name>-front"（加后缀避免和后端工程名冲突）。
#
# 例：
#   ./rename-project.sh my-awesome-app --apply --pom
#     scaffold -> my-awesome-app
#     Scaffold -> MyAwesomeApp          (自动根据 new-name 推导 TitleCase)
#     pom.xml: <artifactId>quick</artifactId> -> <artifactId>my-awesome-app</artifactId>
#              <name>quick</name>             -> <name>my-awesome-app</name>
#     （只改顶层工程坐标；quick-starter-* 依赖和 scaffolding-middleware 都不动。）
#
# 可选：想改域名/Java 包名/Maven 坐标，自己在替换完成后另起 PR 处理，
#       本脚本只负责"项目名"这一类占位，避免误伤。
# ============================================================================

set -euo pipefail

# --- args --------------------------------------------------------------------
if [[ $# -lt 1 ]]; then
  echo "usage: $0 <new-name> [--apply] [--backup] [--pom] [--title <TitleCase>]"
  echo "  <new-name>       new project name in kebab/lower form (e.g. my-awesome-app)"
  echo "  --apply          actually write changes (default: dry-run)"
  echo "  --backup         keep .bak files when writing"
  echo "  --pom            auto-detect back/pom.xml and rewrite <artifactId>/<name> (java only)"
  echo "  --title <s>      override TitleCase form (default: auto from <new-name>)"
  exit 64
fi

NEW_NAME="$1"
shift

APPLY=0
BACKUP=0
DO_POM=0
TITLE_OVERRIDE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply)   APPLY=1; shift;;
    --backup)  BACKUP=1; shift;;
    --pom)     DO_POM=1; shift;;
    --title)   TITLE_OVERRIDE="${2:-}"; shift 2;;
    *) echo "unknown arg: $1" >&2; exit 64;;
  esac
done

# --- validate new name -------------------------------------------------------
if ! [[ "$NEW_NAME" =~ ^[a-z][a-z0-9-]*$ ]]; then
  echo "error: <new-name> must be kebab/lower (start with a-z, chars in [a-z0-9-])" >&2
  echo "       got: $NEW_NAME" >&2
  exit 65
fi

if [[ "$NEW_NAME" == "scaffold" ]]; then
  echo "error: new-name is still 'scaffold'; pick a different name." >&2
  exit 66
fi

# --- derive TitleCase --------------------------------------------------------
# my-awesome-app -> MyAwesomeApp
derive_title() {
  local s="$1" out="" token
  IFS='-' read -r -a tokens <<< "$s"
  for token in "${tokens[@]}"; do
    [[ -z "$token" ]] && continue
    out+="$(tr '[:lower:]' '[:upper:]' <<< "${token:0:1}")${token:1}"
  done
  printf '%s' "$out"
}

if [[ -n "$TITLE_OVERRIDE" ]]; then
  NEW_TITLE="$TITLE_OVERRIDE"
else
  NEW_TITLE="$(derive_title "$NEW_NAME")"
fi

# --- locate repo root --------------------------------------------------------
REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_ROOT"

# --- detect project type & locate pom ---------------------------------------
# 自动探测：在以下候选路径里找 back/pom.xml 或 back/pyproject.toml / requirements.txt。
# 兼容两种布局：
#   1. 单项目布局:           ./back/pom.xml          或 ./back/pyproject.toml
#   2. monorepo 布局:        ./scaffolding-java/back/pom.xml
#                            ./scaffolding-python/back/pyproject.toml
#
# 找到的第一个 pom 路径写入 DETECTED_POM；探测出的项目类型写入 PROJECT_TYPE
# (java | python | unknown)。--pom 在 unknown / python 项目上会自动跳过。
#
# 同时探测所有 front/package.json，写入 DETECTED_FRONT_PKGS 数组（可能 0 个、
# 1 个或 2 个，monorepo 下可能两边都有）。它们的 "name" 字段会被改成
# "<new-name>-front"，避免和后端工程名冲突。
DETECTED_POM=""
PROJECT_TYPE="unknown"
DETECTED_FRONT_PKGS=()

POM_CANDIDATES=(
  "back/pom.xml"
  "scaffolding-java/back/pom.xml"
)
PY_CANDIDATES=(
  "back/pyproject.toml"
  "back/requirements.txt"
  "scaffolding-python/back/pyproject.toml"
  "scaffolding-python/back/requirements.txt"
)
FRONT_PKG_CANDIDATES=(
  "front/package.json"
  "scaffolding-java/front/package.json"
  "scaffolding-python/front/package.json"
)

for cand in "${POM_CANDIDATES[@]}"; do
  if [[ -f "$cand" ]]; then
    DETECTED_POM="$cand"
    PROJECT_TYPE="java"
    break
  fi
done

if [[ -z "$DETECTED_POM" ]]; then
  for cand in "${PY_CANDIDATES[@]}"; do
    if [[ -f "$cand" ]]; then
      PROJECT_TYPE="python"
      break
    fi
  done
fi

for cand in "${FRONT_PKG_CANDIDATES[@]}"; do
  [[ -f "$cand" ]] && DETECTED_FRONT_PKGS+=("$cand")
done

# 如果用户加了 --pom 但探测出来不是 Java，给个明确提示，并把 DO_POM 强行关掉，
# 避免后面的 apply 段报 warning。
if [[ $DO_POM -eq 1 && "$PROJECT_TYPE" != "java" ]]; then
  echo "note: --pom requested but project type is '$PROJECT_TYPE' (no back/pom.xml found)." >&2
  echo "      pom rewrite will be skipped." >&2
  DO_POM=0
fi

echo "========================================================================"
echo " scaffold  -> $NEW_NAME"
echo " Scaffold  -> $NEW_TITLE"
echo " root:       $REPO_ROOT"
echo " project:    $PROJECT_TYPE${DETECTED_POM:+ (pom: $DETECTED_POM)}"
if [[ ${#DETECTED_FRONT_PKGS[@]} -gt 0 ]]; then
  echo " front pkg:  ${#DETECTED_FRONT_PKGS[@]} found → ${DETECTED_FRONT_PKGS[*]}"
else
  echo " front pkg:  0 found"
fi
echo " mode:       $([[ $APPLY -eq 1 ]] && echo APPLY || echo 'DRY-RUN (no changes)')"
echo " backup:     $([[ $BACKUP -eq 1 ]] && echo yes || echo no)"
echo " pom rename: $([[ $DO_POM -eq 1 ]] && echo "yes ($DETECTED_POM artifactId+name)" || echo no)"
echo "========================================================================"
echo

# --- file discovery ----------------------------------------------------------
# 排除所有生成产物 / 三方依赖 / 版本控制 / IDE 缓存。
EXCLUDES=(
  -name node_modules -o
  -name target -o
  -name dist -o
  -name build -o
  -name .mypy_cache -o
  -name .ruff_cache -o
  -name .pytest_cache -o
  -name __pycache__ -o
  -name .git -o
  -name .idea -o
  -name .vscode -o
  -name .gradle -o
  -name .next -o
  -name .turbo -o
  -name .venv -o
  -name venv -o
  -name logs
)

# 找出包含 scaffold / Scaffold 的文本文件，且不在排除目录下。
# 脚本自己不碰自己。
SELF="$(basename "$0")"

# macOS 默认 bash 3.2 没有 mapfile/readarray，用 while read 兼容。
CANDIDATES=()
while IFS= read -r line; do
  [[ -n "$line" ]] && CANDIDATES+=("$line")
done < <(
  find . \
    \( "${EXCLUDES[@]}" \) -prune -o \
    -type f -print \
  | grep -Ev '\.(png|jpg|jpeg|gif|ico|webp|pdf|zip|tar|gz|jar|class|woff2?|ttf|eot|mp4|mov)$' \
  | while read -r f; do
      [[ "$(basename "$f")" == "$SELF" ]] && continue
      # 只保留真的命中 \bscaffold\b / \bScaffold\b 的文本文件。
      # 用 perl 做 word-boundary 匹配，避开 "scaffolding-java" 这种子串误命中。
      if perl -ne 'if (/\bscaffold\b/ || /\bScaffold\b/) { print "HIT\n"; exit 0 }' "$f" 2>/dev/null | grep -q HIT; then
        printf '%s\n' "$f"
      fi
    done \
  | sort
)

if [[ ${#CANDIDATES[@]} -eq 0 ]]; then
  echo "no files contain 'scaffold' / 'Scaffold' — nothing to do."
  exit 0
fi

echo "files to touch (${#CANDIDATES[@]}):"
printf '  %s\n' "${CANDIDATES[@]}"
echo

# --- dry-run: show the diff --------------------------------------------------
if [[ $APPLY -eq 0 ]]; then
  echo "--- dry-run diff preview (word-boundary hit count) ---"
  for f in "${CANDIDATES[@]}"; do
    # 大小写敏感 + word-boundary，避免 "scaffolding-xxx" 被误计。
    lower=$(perl -ne 'print scalar(() = /\bscaffold\b/g), "\n"' "$f" 2>/dev/null | awk '{s+=$1} END {print s+0}')
    title=$(perl -ne 'print scalar(() = /\bScaffold\b/g), "\n"' "$f" 2>/dev/null | awk '{s+=$1} END {print s+0}')
    # 只显示真正有命中的文件
    if [[ "$lower" != "0" || "$title" != "0" ]]; then
      printf '  %-70s  scaffold:%s  Scaffold:%s\n' "$f" "$lower" "$title"
    fi
  done

  # pom 预览
  if [[ $DO_POM -eq 1 ]]; then
    POM="$DETECTED_POM"
    if [[ -f "$POM" ]]; then
      echo
      echo "--- pom preview ($POM) ---"
      # <artifactId>quick</artifactId> (后面不能紧跟 '-'，否则就是 quick-starter-*)
      perl -ne 'print "  L$.: $_" if m{<artifactId>quick</artifactId>} || m{<name>quick</name>}' "$POM"
    else
      echo
      echo "  warning: --pom requested but no back/pom.xml found, skipping pom preview."
    fi
  fi

  # front/package.json 预览（始终执行，无需 flag——这是默认行为）
  if [[ ${#DETECTED_FRONT_PKGS[@]} -gt 0 ]]; then
    for FPKG in "${DETECTED_FRONT_PKGS[@]}"; do
      echo
      echo "--- front package.json preview ($FPKG) ---"
      # 只匹配顶层 "name": "..." 那一行（package.json 第 1-3 行，必然命中）。
      perl -ne 'print "  L$.: $_" if m{^\s*"name"\s*:\s*"[^"]*",?\s*$}' "$FPKG"
      echo "  → will become: \"name\": \"${NEW_NAME}-front\""
    done
  fi

  echo
  echo "dry-run done. Re-run with --apply to write changes."
  exit 0
fi

# --- apply -------------------------------------------------------------------
# 用 perl 做 in-place 替换（跨平台比 sed -i 更稳，GNU sed / BSD sed 语法差异大）。
# 顺序：先换 Scaffold (TitleCase)，再换 scaffold (kebab)。
# 因为 "Scaffold" 完全包含 "scaffold" 的大小写变体，先 lower 替换会污染 TitleCase。

PERL_BIN="$(command -v perl || true)"
if [[ -z "$PERL_BIN" ]]; then
  echo "error: perl not found in PATH — required for in-place replacement." >&2
  exit 70
fi

perl_args=(-i)
if [[ $BACKUP -eq 1 ]]; then
  perl_args=(-i.bak)
fi

# 转义反斜杠和斜杠。项目名是 kebab，一般不会有特殊字符，这里稳妥点。
escape_for_perl() {
  printf '%s' "$1" | perl -pe 's{([\\/@\$])}{\\$1}g'
}
NEW_NAME_ESC="$(escape_for_perl "$NEW_NAME")"
NEW_TITLE_ESC="$(escape_for_perl "$NEW_TITLE")"

CHANGED=0
for f in "${CANDIDATES[@]}"; do
  # \b 是 word-boundary；Scaffold 在前，避免下游 scaffold 的替换污染 TitleCase。
  "$PERL_BIN" "${perl_args[@]}" -pe "s/\\bScaffold\\b/${NEW_TITLE_ESC}/g; s/\\bscaffold\\b/${NEW_NAME_ESC}/g;" "$f"
  CHANGED=$((CHANGED + 1))
  printf '  rewrote  %s\n' "$f"
done

# --- optional: rewrite back/pom.xml <artifactId>/<name> ---------------------
# 路径来自上面的项目类型探测：DETECTED_POM 会指向 ./back/pom.xml 或
# ./scaffolding-java/back/pom.xml；Python 项目时 DO_POM 已被强制关掉。
POM_CHANGED=0
if [[ $DO_POM -eq 1 ]]; then
  POM="$DETECTED_POM"
  if [[ -f "$POM" ]]; then
    # 只匹配完整 tag <artifactId>quick</artifactId> 和 <name>quick</name>。
    # back/pom.xml 里其他位置都是 <artifactId>quick-starter-*</artifactId>，
    # 加上闭合 tag 后 "quick</" 不会被误命中（只有顶层工程坐标才是孤立的 quick）。
    "$PERL_BIN" "${perl_args[@]}" -pe "
      s{<artifactId>quick</artifactId>}{<artifactId>${NEW_NAME_ESC}</artifactId>}g;
      s{<name>quick</name>}{<name>${NEW_NAME_ESC}</name>}g;
    " "$POM"
    printf '  rewrote  %s (pom artifactId + name)\n' "$POM"
    POM_CHANGED=1
  else
    echo "  warning: --pom requested but no back/pom.xml found, skipped."
  fi
fi

# --- always: rewrite front/package.json "name" -> "<new-name>-front" --------
# 默认行为，不需要 flag。只改顶层 "name": "front" 这一行；其他出现的 "front"
# 字符串（描述文本、scripts 里的目录名）不动。bash 数组在 set -u 下空数组直接
# 展开会触发 unbound variable，先判长度再展开。
FRONT_CHANGED=0
if [[ ${#DETECTED_FRONT_PKGS[@]} -gt 0 ]]; then
  FRONT_NEW_NAME="${NEW_NAME}-front"
  FRONT_NEW_NAME_ESC="$(escape_for_perl "$FRONT_NEW_NAME")"
  for FPKG in "${DETECTED_FRONT_PKGS[@]}"; do
    # 只匹配顶层 "name": "...", 行（行首允许任意空白，行尾允许逗号）。
    # \K 让前缀不被替换；只重写引号里的值。
    "$PERL_BIN" "${perl_args[@]}" -pe '
      s{^(\s*"name"\s*:\s*")[^"]*(",?\s*)$}{${1}'"${FRONT_NEW_NAME_ESC}"'${2}}g;
    ' "$FPKG"
    printf '  rewrote  %s (front "name" -> "%s")\n' "$FPKG" "$FRONT_NEW_NAME"
    FRONT_CHANGED=$((FRONT_CHANGED + 1))
  done
fi

echo
echo "done. $CHANGED files rewritten.$([[ $POM_CHANGED -eq 1 ]] && echo ' +pom')$([[ $FRONT_CHANGED -gt 0 ]] && echo " +${FRONT_CHANGED} front pkg")"
if [[ $BACKUP -eq 1 ]]; then
  echo "backups kept as <file>.bak"
fi
echo
echo "next steps:"
echo "  1) git diff                       # review the rewrite"
echo "  2) perl -ne 'print \"\$ARGV:\$.: \$_\" if /\\bscaffold\\b/ || /\\bScaffold\\b/' \$(git ls-files) | head"
echo "                                    # 确认没有 word-boundary 命中残留"
echo "  3) cd scaffolding-java/front && npm install && npm run build"
echo "     cd scaffolding-java/back  && mvn -DskipTests compile"
echo "     cd scaffolding-python/back && ruff check . && mypy app/ config.py"
echo "  4) 可选：再手工处理域名 (staff*.dushu365.com) / Java 包名 (com.soybean.quick) / Maven 坐标"
