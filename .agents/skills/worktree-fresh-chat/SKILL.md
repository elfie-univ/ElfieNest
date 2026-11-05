---
name: worktree-fresh-chat
description: 在指定的现有 Git Worktree 上干净重开 Codex 对话，复用目录和分支，不复制旧对话或图片。用于用户明确要求换新对话、清空历史后继续同一 Worktree；不用于 fork、压缩历史或创建另一份 Worktree。
---

# Worktree 干净重开

这是 ElfieNest 项目级技能。使用当前 checkout 的 `.agents/skills/worktree-fresh-chat/` 内脚本，不依赖用户级技能副本或固定电脑路径。

目标：**新对话 + 原 Worktree 绝对路径 + 原 Git 状态 + 空消息历史**。
“扔掉历史”指不继承旧对话内容，不指删除原对话或文件。仓库规则、系统指令和应用自动注入的记忆仍可能存在；不得声称整个模型上下文完全为空，也不承诺必然加速。

## 确定目标

- 用户可提供 Worktree 路径、分支名或旧对话。明确说“当前 Worktree”时使用当前执行目录。仅要求制作/解释本技能时，不创建对话。
- 用原生 `list_threads` / `read_thread` 定位旧对话时，只获取确定 cwd 所需的最少元数据，不抓取整段历史、工具输出或图片。
- 用 `git worktree list --porcelain` 将分支定位到已有目录；再在该目录只读核对 `git rev-parse --show-toplevel`、`git symbolic-ref --quiet --short HEAD`、`git rev-parse HEAD` 和 `git status --short`。detached HEAD 是有效状态，记录 SHA 即可。
- 名称或路径有多个候选且上下文无法确定时，只问一个目标选择问题。路径不存在时停止，不自行重建。
- 保留所有已提交、未提交、未跟踪和忽略文件；不切分支、不 reset、不 stash、不 commit、不 fetch、不新建 Worktree。

## 创建与绑定

先发现并读取当前版本的原生对话工具参数，不猜测参数或调用未公开接口。

1. 若有支持指定现有 cwd、且不继承历史的新建对话接口，使用核实的绝对路径创建一次。
2. 当前 `create_thread` 若仅支持 project target：先 `list_projects`，只有当项目主目录与目标 Worktree 的真实路径完全相同时，才以该 projectId 和 `environment: {type: "local"}` 创建。仅父仓库相同、分支名相同或项目名称相同都不够。
3. 若原生工具没有 cwd 参数且项目目录不匹配，使用官方 Codex App Server 的 `thread/start`，它支持直接指定现有 cwd，无需新增项目。先核对 `codex app-server --help` 及下方官方文档；运行本技能的 [scripts/create_fresh_chat.mjs](scripts/create_fresh_chat.mjs)：

   ```sh
   node /绝对技能目录/scripts/create_fresh_chat.mjs /目标Worktree绝对路径 '新对话标题'
   ```

   脚本通过官方 CLI 的 stdio JSON-RPC 创建持久空白对话，设置标题，不复制历史、不启动模型推理、不改变全局配置。使用当前用户默认模型；启动沙箱为只读，后续需要写入时按用户的新任务与正常应用权限处理。脚本返回 threadId 后，通过桌面 `send_message_to_thread` 向**这个新 ID**发送下方最小启动语，再用 `wait_threads` / `read_thread` 核对。这比通过独立 CLI 启动推理更能沿用桌面的模型运行环境。不要因启动轮失败而重复创建另一个对话。
4. 若 CLI 不可用或实际调用失败，报告具体失败步骤和已返回的 threadId，保留已创建对话。只有这条路径也无法使用时，才提供“把目标目录添加为本地项目”的手动替代步骤。不能仅凭 `create_thread` 缺少 cwd 参数就判定无法绑定。

官方协议：[App Server — Threads](https://learn.chatgpt.com/docs/app-server#threads)、[stdio 初始化](https://learn.chatgpt.com/docs/app-server#getting-started)。不直接修改 SQLite、rollout 或项目配置；官方 API 的持久化不属于直接改数据库。

关键区别：`environment: {type: "worktree"}` 会创建另一份 checkout，不能满足复用原目录；`fork_thread` 继承历史，不能满足空历史。`attach_worktree` 的所有权约束必须遵守，不能把其他对话拥有的目录强行附到新对话。将路径写进 prompt 也不等于应用已绑定该路径。

默认不设置 model 或 thinking，沿用用户配置；只有用户明确指定时才覆盖。

## 最小启动语

只带目录、分支或 detached SHA，以及用户这次明确给出的下一步目标。默认**不总结、不搬运**旧对话。若用户额外要求保留某些决定，只加入这些决定的短文本；资产只给路径，不读取/附加图片。不得向新对话发送 transcript、历史工具输出、旧摘要或旧消息附件。

可按实际值使用：

> 这是一个全新的对话。工作目录是〔绝对路径〕，当前分支/提交是〔核实值〕。请先只读核对实际 cwd、HEAD 和工作区状态，确认后简短告知就绪，等待我给新任务。不要读取旧对话、rollout 或历史图片，也不要为了恢复历史搜索记忆；遵守自动加载的当前仓库规则。〔仅在用户给出时追加本次目标。〕

创建动作不转移旧任务的 push、PR、merge 或其他外部写操作授权。默认也不在新对话自动继续修改文件。

## 验证与交付

- 创建异步返回时，用原生 `wait_threads` 等待一次简短就绪结果；不要用 clientThreadId 冒充 threadId。
- 成功条件：新 threadId 不同于旧对话，持久化的 cwd 与目标真实路径一致，首次只读核对的 HEAD/分支和工作区状态与预期一致，新历史只包含本次启动和核对，没有旧消息或图片。若目录不符，停止后续工作并报告，不能称为已绑定。这里的绑定指持久化执行 cwd；不声称已转移原托管 Worktree 的所有权或清理保护。
- 给出新对话入口，并按应用要求输出 `::created-thread{threadId="实际ID"}`。只在实际成功创建后输出；若仍在异步设置中，按工具要求使用 clientThreadId 并如实标明待验证。
- 保留旧对话。不要自动归档、删除或中断它：归档旧的托管 Worktree 对话可能触发目录清理。若旧对话仍在执行写操作，提示用户先停止该轮，再在同一目录开始新的写操作。
- 若接口阻塞，交付准确路径、启动语和唯一必要的手动步骤，明确区分“技能已安装”与“新对话已创建”。
