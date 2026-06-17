# 用户导入

系统不开放注册。新增用户时，在服务器仓库目录放一个 CSV，然后用后台脚本导入。

## 1. 准备 CSV

在宿主机仓库目录创建：

```bash
cd /path/to/case-library
nano backend/accounts.csv
```

CSV 内容示例：

```csv
school_id,nickname,role,must_change_password,status
20240001,张三,normal,true,active
20240002,李老师,admin,true,active
```

说明：

- `school_id`：登录账号。也可以改用 `username`。
- `nickname`：显示名。
- `role`：`normal` 普通用户，`admin` 管理员。
- `must_change_password`：建议固定 `true`。
- `status`：正常账号写 `active`。

`backend/accounts.csv` 已被 `.gitignore` 忽略，不要提交真实用户表。

## 2. 校验

`app` 是 Compose service 名，不是 `docker ps` 里的 `case-library-app-1` 容器名。

```bash
export IMPORT_DEFAULT_PASSWORD='TempPass123!'
docker compose run --rm -e IMPORT_DEFAULT_PASSWORD app \
  python backend/scripts/account_admin.py import-users \
  --file /app/backend/accounts.csv \
  --default-password-env IMPORT_DEFAULT_PASSWORD \
  --dry-run
```

看到没有 `Import error` 后再正式导入。

## 3. 正式导入

```bash
docker compose run --rm -e IMPORT_DEFAULT_PASSWORD app \
  python backend/scripts/account_admin.py import-users \
  --file /app/backend/accounts.csv \
  --default-password-env IMPORT_DEFAULT_PASSWORD
unset IMPORT_DEFAULT_PASSWORD
```

导入后，用户用 `school_id` 和统一临时密码登录，首次登录会要求改密。

## 4. 确认账号

```bash
docker compose run --rm app python backend/scripts/account_admin.py list
```

## 单个账号维护

创建单个账号：

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

改成管理员：

```bash
docker compose run --rm app python backend/scripts/account_admin.py update \
  --username teacher001 \
  --role admin
```
