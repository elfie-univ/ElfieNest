# ElfieNest 生产数据与旧入口迁移矩阵

本文是生产升级前的人工迁移清单。它描述当前仓库已经实现的迁移边界，**不把
兼容读取或迁移函数的存在当成某一台机器已经迁移成功**。所有命令都应在停止
ElfieNest 服务、完成备份并确认目标目录后执行；示例使用 `ELFIE_HOME` 覆盖目标
目录，未设置时目标是 `~/.elfienest/`（见
[`runtime/storage/data_home.py:14-22`](../../runtime/storage/data_home.py)）。

## 执行前检查

```bash
git status --short --branch
test -d "$HOME/.elfienest" && find "$HOME/.elfienest" -maxdepth 2 -type f -print
test -d data && find data -maxdepth 2 -type f -print
```

若工作区不是干净状态，先记录并暂停迁移；迁移命令不应修改 git 跟踪文件。对
目标目录已有内容的情况，先执行一次完整备份：

```bash
set -eu
home="${ELFIE_HOME:-$HOME/.elfienest}"
backup="${home}.backup.$(date +%Y%m%d%H%M%S)"
if [ -e "$home" ]; then cp -a "$home" "$backup"; fi
printf '备份目录: %s\n' "$backup"
```

## 迁移矩阵

| 项目 | 目标与当前状态 | 来源（仓库证据） | 显式迁移命令 | 备份与回滚 | 删除条件 |
| --- | --- | --- | --- | --- | --- |
| `~/.elfienest/config.yaml` | 生产主配置，版本化到 `config_version=2`；目标已存在时不得盲目覆盖。 | `get_config_path()` 返回 `$ELFIE_HOME/config.yaml`（[`runtime/storage/data_home.py:25-28`](../../runtime/storage/data_home.py)）；迁移器在目标已有内容时直接跳过（[`runtime/storage/migration.py:111-114`](../../runtime/storage/migration.py)）。 | `home="${ELFIE_HOME:-$HOME/.elfienest}"; ELFIE_HOME="$home" .venv/bin/python -c 'from runtime.storage.migration import migrate_config; migrate_config()'; grep -n '^config_version:' "$home/config.yaml"`。 | 迁移前复制整个 `ELFIE_HOME`；回滚时停止服务并将备份目录原子改名恢复。`migrate_config()` 写回 YAML（[`runtime/storage/migration.py:237-294`](../../runtime/storage/migration.py)）。 | 只有目标 `config.yaml` 已验证、备份可读且连续两次启动/配置读取通过后，才可删除旧配置副本；保留最近一个版本备份。 |
| `~/.elfienest/.env` | 仅保存 Provider/工具密钥，权限 0600；`config.yaml` 不应再含 `api_key` 明文。 | 路径与用途见 [`runtime/storage/data_home.py:30-33`](../../runtime/storage/data_home.py)；密钥写入采用临时文件替换并设 0600（[`runtime/storage/secrets.py:57-77`](../../runtime/storage/secrets.py)）。 | `home="${ELFIE_HOME:-$HOME/.elfienest}"; ELFIE_HOME="$home" .venv/bin/python -c 'from runtime.storage.migration import migrate_config; migrate_config()'; stat -f '%Lp' "$home/.env" 2>/dev/null || stat -c '%a' "$home/.env"`。 | 备份 `.env` 时仅允许当前用户可读；回滚恢复备份文件并再次检查 0600。迁移器会把旧 `api_key` 转为环境变量名（[`runtime/storage/migration.py:328-343`](../../runtime/storage/migration.py)）。 | 确认所有 Provider 连通性检查只读取新 `.env` 且备份可恢复后，才删除旧主目录或旧 JSON 中的密钥副本；任何密钥泄露迹象都禁止删除。 |
| `nest.db` | 系统 SQLite（Owner、精灵注册、会话）迁移到 `$ELFIE_HOME/nest.db`；当前仓库仍有旧 `data/nest.db` 样本。 | 默认数据库路径见 [`runtime/storage/data_home.py:60-63`](../../runtime/storage/data_home.py)；旧目录复制映射见 [`runtime/storage/migration.py:162-177`](../../runtime/storage/migration.py)。 | `home="${ELFIE_HOME:-$HOME/.elfienest}"; ELFIE_HOME="$home" .venv/bin/python -c 'from runtime.storage.migration import migrate_data_home; migrate_data_home()'; sqlite3 "$home/nest.db" 'PRAGMA integrity_check;'`，应返回 `ok`。 | 迁移前 `cp -p data/nest.db "$backup/nest.db"`；回滚时停止服务、替换目标数据库，并重新运行完整性检查。不要在服务运行时复制 SQLite。 | 只有完整性检查、Owner 登录、精灵列表和会话读取均通过，且至少保留一个离线备份后，才可删除 `data/nest.db`。 |
| `foods.yaml` | 当前生效的粮食目录，目标为 `$ELFIE_HOME/foods.yaml`；**不由旧数据迁移器自动复制**。若目标缺失，Runtime 可能仅使用旧模型字段生成临时兼容目录。 | 目标路径见 [`runtime/storage/data_home.py:35-38`](../../runtime/storage/data_home.py)；兼容目录明确标记为 `legacy_compatibility`（[`runtime/food/bootstrap.py:1-5`](../../runtime/food/bootstrap.py)、[`runtime/food/bootstrap.py:41-45`](../../runtime/food/bootstrap.py)）。 | 仅在来源存在且目标不存在时执行：`home="${ELFIE_HOME:-$HOME/.elfienest}"; test -e "$home/foods.yaml" && { echo '目标已存在，拒绝覆盖'; exit 2; }; test -f data/foods.yaml || { echo '未找到旧 foods.yaml，需先生成正式目录'; exit 3; }; install -m 600 data/foods.yaml "$home/foods.yaml"`；然后用 `ELFIE_HOME="$home" .venv/bin/python -c 'from runtime.food.store import FoodCatalogStore; print(len(FoodCatalogStore().load().recipes))'` 验证可读。 | `FoodCatalogStore.save()` 会在覆盖前写入 `food_history/` 快照（[`runtime/food/store.py:65-74`](../../runtime/food/store.py)）；手工复制前仍应备份整个目录。回滚优先 `foods` 历史版本，失败时恢复备份。 | 正式目录可读、验证状态不是兼容来源且连续运行通过后，才可删除旧 `data/foods.yaml` 或清理临时兼容配置；当前仓库未发现 `data/foods.yaml`，因此不能声称已迁移。 |
| `elfies/` | 精灵配置和身份目录迁移到 `$ELFIE_HOME/elfies/`；每个精灵的 `config_dir` 必须与 `nest.db` 中注册值一致。 | 旧目录复制规则见 [`runtime/storage/migration.py:162-186`](../../runtime/storage/migration.py)；默认精灵配置目录见 [`runtime/storage/data_home.py:65-68`](../../runtime/storage/data_home.py)。仓库当前 `data/elfies/` 含多个精灵目录。 | `home="${ELFIE_HOME:-$HOME/.elfienest}"; ELFIE_HOME="$home" .venv/bin/python -c 'from runtime.storage.migration import migrate_data_home; migrate_data_home()'; find data/elfies -mindepth 1 -maxdepth 1 -type d | wc -l; find "$home/elfies" -mindepth 1 -maxdepth 1 -type d | wc -l`，再检查每个目录的 YAML 可解析。 | 迁移器复制前若目标 `elfies/` 已存在会先删除目标子目录（[`runtime/storage/migration.py:179-185`](../../runtime/storage/migration.py)），所以必须先做整目录备份。回滚时停止服务并恢复备份目录。 | 只有数据库注册、精灵配置 YAML、单精灵会话均核对一致且备份可恢复，才可删除 `data/elfies/`；不要按文件时间戳推断迁移完成。 |
| 旧 `runtime/runtime_config.json` | 迁移为 `$ELFIE_HOME/config.yaml`，旧 JSON 仍被 `runtime/config.py` 兼容读取；该兼容读取不是完成标志。 | JSON 转换逻辑及“目标 config 已存在则跳过”见 [`runtime/storage/migration.py:201-229`](../../runtime/storage/migration.py)；兼容读取见 [`runtime/config.py:229-241`](../../runtime/config.py)。仓库中的文件由 `.gitignore` 忽略。 | 先复制 `runtime/runtime_config.json` 到离线备份，再执行 `ELFIE_HOME="$HOME/.elfienest" .venv/bin/python -c 'from runtime.storage.migration import migrate_data_home; migrate_data_home()'`；检查新 YAML 与 `.env`，确认 JSON 不再是唯一配置来源。 | 原 JSON 只读备份；回滚时删除（或移走）新 YAML 后恢复旧 JSON，并重新验证 Provider。 | 目标 YAML 已生成且 `config_version` 达到当前版本、密钥已转移、两次冷启动均不读取 JSON 后，才可删除 `runtime/runtime_config.json` 及 `.bak`；在此之前只能标记“已迁移待清理”。 |
| 旧项目 `data/` | 仅作为迁移输入；迁移器复制 `nest.db`、`elfies/`、`.elfie_memories.json`、`graph_memory.db`，不会删除旧文件；进入复制路径时写 `.migrated` 标记，目标已有内容则会提前返回（[`runtime/storage/migration.py:111-159`](../../runtime/storage/migration.py)）。 | 迁移器说明与实现见 [`runtime/storage/migration.py:1-8`](../../runtime/storage/migration.py)、[`runtime/storage/migration.py:162-199`](../../runtime/storage/migration.py)；当前 `data/` 被 `.gitignore` 忽略。 | `ELFIE_HOME="$HOME/.elfienest" .venv/bin/python -c 'from runtime.storage.migration import migrate_data_home; migrate_data_home()'`；检查 `test -f data/.migrated` 并逐项核对目标。 | 迁移前将整个 `data/` 打包为只读归档；回滚使用归档恢复，禁止用目标目录反向覆盖未知旧数据。 | 目标数据经过人工抽样、SQLite 完整性检查、精灵和记忆读取验证，且归档可恢复后，才可删除 `data/`；`.migrated` 标记本身不代表可删除。 |
| `model_route.yaml` / `scene_routes` | 旧的每精灵模型路由配置（`idle/deep/vision/tool_use/sleep`）不再作为生产模型选择入口；当前 Runtime 以粮食策略为边界。 | 旧文件路径与场景槽定义见 [`runtime/policy/model_route.py:1-9`](../../runtime/policy/model_route.py)、[`runtime/policy/model_route.py:31-45`](../../runtime/policy/model_route.py)；`scene_routes` 字段序列化见 [`runtime/policy/model_route.py:59-89`](../../runtime/policy/model_route.py)。 | 不执行自动改写。逐个精灵先导出旧 YAML 备份，再按产品确认把主/降级模型映射为 `food_policy.yaml` 的 `default_food`、`allowed_foods`、`fallback_food`；新接口写入示例：`curl -X PUT "$BASE/api/user/elfies/$ID/food-policy" -H 'Content-Type: application/json' --data @food-policy.json`。 | 保留原 `model_route.yaml` 只读副本；回滚删除新 `food_policy.yaml` 并恢复旧文件。无法一一映射的场景必须人工决策，不能猜测。 | 新粮食策略已验证且所有调用方不再读取 `model_route.yaml` 后，才可删除该文件；仅看到 410 或默认配置不等于迁移完成。 |
| 旧 `/api/user/elfies/{elfie_id}/route` API | 兼容入口仍保留，但只读写粮食权限并返回 `deprecated=true`；提交 `scene_routes` 明确返回 410。生产客户端应切换到 `/food-policy`。 | 路由前缀、弃用标记和替代地址见 [`elfienest/api/route_routes.py:24-25`](../../elfienest/api/route_routes.py)、[`elfienest/api/route_routes.py:58-77`](../../elfienest/api/route_routes.py)；拒绝旧模型结构见 [`elfienest/api/route_routes.py:85-114`](../../elfienest/api/route_routes.py)。新 API 定义见 [`elfienest/api/food_policy_routes.py:19-22`](../../elfienest/api/food_policy_routes.py)。 | 先在客户端配置中把 GET/PUT 改为 `/api/user/elfies/{id}/food-policy`，用测试数据验证 200；对旧入口发送 `scene_routes` 应得到 410，不能把 410 记录为成功迁移。 | API 切换前保留客户端版本和旧配置；回滚只需恢复客户端路由，不改数据库。 | 生产客户端 telemetry 连续一个发布周期无旧 `/route` 请求、旧配置已迁移且有回滚版本后，才可删除兼容路由（需单独代码变更和评审；本文不执行）。 |
| 旧 `elfie` 安装入口 | 新入口是用户级 `elfienest` 包装器；旧 `$HOME/bin/elfie` 或 `$HOME/.local/bin/elfie` 仅在包装器内容精确匹配本项目时自动清理，`/usr/local/bin/elfie` 只警告。根目录 `elfie.sh` 在当前仓库文件清单中不存在，状态为“已删除”；旧包装器识别代码仍保留用于安全清理。 | 安装脚本写入新入口并调用清理（[`install.sh:159-213`](../../install.sh)）；旧包装器匹配与清理规则见 [`scripts/elfienest_install_helpers.sh:241-299`](../../scripts/elfienest_install_helpers.sh)，系统级入口警告见 [`scripts/elfienest_install_helpers.sh:327-364`](../../scripts/elfienest_install_helpers.sh)。 | 先运行 `./install.sh --env-only` 验证环境，再由用户确认后运行 `./install.sh`；安装后执行 `command -v elfienest`、`elfienest version`。系统入口需人工执行脚本打印的 `sudo rm -f` 命令，禁止自动删除未知文件。 | 安装前复制旧包装器文本；新入口失败时恢复旧包装器。安装器遇到非本项目同名命令会拒绝覆盖。 | 只有新 `elfienest` 可用、旧入口确认属于本项目且无其他脚本依赖时，才可删除旧入口；第三方或内容不匹配入口必须保留并人工处理。 |

## 异常与中断处理

- **格式异常**：旧 JSON 解析失败时迁移器只记录 warning 并返回；坏 YAML 或顶层非对象同样不能视为成功（[`runtime/storage/migration.py:211-216`](../../runtime/storage/migration.py)、[`runtime/storage/config_store.py:20-30`](../../runtime/storage/config_store.py)）。保留原文件，人工修复或从备份恢复后重试。
- **目标陈旧状态**：`~/.elfienest` 只要已有任意内容，`migrate_data_home()` 就跳过整体迁移；`config.yaml` 已存在时 JSON 转换也跳过。先备份并将目标移到隔离目录，再决定合并，禁止用“命令返回 True”证明数据已更新。
- **脏工作区**：本矩阵只允许修改本文件和 `.omo/evidence/task-1-config-boundary.md`；发现其他 git 改动应暂停，不执行删除或自动修复。
- **重复中断**：迁移可重复运行，但每次都要重新检查备份、目标文件计数、`config_version` 和 SQLite 完整性；不要删除 `.migrated` 或旧输入来“清除”失败痕迹。

## 完成判据

逐项完成“目标可读、来源已核对、备份可恢复、回滚演练记录、旧入口使用量为零”后，
由发布负责人逐项批准删除。未满足任一项时状态只能写为“待迁移”或“已迁移待清理”，
不得在发布说明中写成“自动迁移完成”。
