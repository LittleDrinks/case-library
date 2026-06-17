# 用户导入操作手册

学校统一身份认证接入前，系统不开放自助注册。新增教师、管理员账号时，使用后台脚本
导入 CSV/XLSX。下面命令都可以在系统运行中执行，不需要停掉服务。

## 准备用户表

推荐把导入文件临时放在仓库内已忽略的位置：

```text
backend/accounts.csv
```

`.gitignore` 已忽略 `backend/accounts.csv` 和 `accounts.csv`，不要提交真实用户表。

CSV 示例：

```csv
school_id,nickname,role,password,must_change_password,status
20240001,张三,normal,TempPass123!,true,active
20240002,李老师,admin,TempPass123!,true,active
```

也可以使用 `username` 代替 `school_id`：

```csv
username,nickname,role,password,must_change_password,status
teacher001,张三,normal,TempPass123!,true,active
admin001,李老师,admin,TempPass123!,true,active
```

支持 `.csv` 和 `.xlsx`，第一行必须是表头。

## 字段说明

必填字段：

- `username` 或 `school_id`：二选一。`school_id` 会作为临时登录用户名。
- `nickname`、`display_name` 或 `name`：三选一，作为系统展示名。
- `role`：账号角色，允许 `normal`、`admin`。`user` 会自动归一为 `normal`。

可选字段：

- `password`：初始密码。长度至少 8 位。
- `must_change_password`：是否首次登录强制改密，默认 `true`。
- `status`：账号状态，默认 `active`。允许 `active`、`no_active`。
- `department`、`class`、`organization`：可放在表中用于人工核对；当前不会写入用户表。

不支持的表头会导致导入失败。正式导入前先 dry-run。

## Dry-run 校验

系统启动后执行：

```bash
docker compose run --rm app python backend/scripts/account_admin.py import-users \
  --file /app/backend/accounts.csv \
  --dry-run
```

dry-run 会检查：

- 表头是否正确。
- 必填字段是否缺失。
- 角色和状态是否合法。
- 文件内是否有重复用户名。
- 数据库中是否已有同名账号。

dry-run 不会写入数据库。确认没有错误后再正式导入。

## 正式导入

```bash
docker compose run --rm app python backend/scripts/account_admin.py import-users \
  --file /app/backend/accounts.csv
```

导入后可以列出账号确认：

```bash
docker compose run --rm app python backend/scripts/account_admin.py list
```

## 不在表里写密码

如果用户表不放 `password`，默认会生成临时密码，但脚本不会打印密码。运营侧通常不建议使用
这种方式发放账号，因为后续还需要逐个重置密码。

更可控的方式是用环境变量提供统一临时密码：

```bash
export IMPORT_DEFAULT_PASSWORD='TempPass123!'
docker compose run --rm -e IMPORT_DEFAULT_PASSWORD app \
  python backend/scripts/account_admin.py import-users \
  --file /app/backend/accounts.csv \
  --default-password-env IMPORT_DEFAULT_PASSWORD
unset IMPORT_DEFAULT_PASSWORD
```

如果要求表里必须有密码，缺失时报错：

```bash
docker compose run --rm app python backend/scripts/account_admin.py import-users \
  --file /app/backend/accounts.csv \
  --missing-password error
```

## 单个账号维护

创建一个账号：

```bash
docker compose run --rm app python backend/scripts/account_admin.py create \
  --username teacher001 \
  --password TempPass123! \
  --role normal \
  --nickname 张三 \
  --must-change-password true \
  --status active
```

重置密码：

```bash
docker compose run --rm app python backend/scripts/account_admin.py reset-password \
  --username teacher001 \
  --password NewTempPass123!
```

重置后该账号会被设置为 `must_change_password=true`。

调整角色、展示名或状态：

```bash
docker compose run --rm app python backend/scripts/account_admin.py update \
  --username teacher001 \
  --role admin
```

删除账号：

```bash
docker compose run --rm app python backend/scripts/account_admin.py delete \
  --username teacher001
```

## 注意事项

- 不要把真实用户表、真实学工号、默认密码或导入结果提交到 git。
- 不要在群聊、issue、PR 或日志里粘贴真实密码。
- 建议导入账号都设置 `must_change_password=true`。
- 管理员账号的 `role` 必须是 `admin`；普通用户使用 `normal`。
- `status=no_active` 的账号不能登录。
