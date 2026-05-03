# 账号后台运维命令

以下命令都在项目根目录执行：

```powershell
cd D:\桌面\强国有我大思政课案例库1
```

账号只能由管理员在后台统一创建、导入、修改或重置。系统不开放个人注册接口。密码使用 bcrypt 哈希保存，无法反查明文密码。

## 初始化默认账号

仅当 `users` collection 为空时才会创建默认账号：

```powershell
python backend\init_users.py
```

默认账号：

```csv
username,password,role,nickname,must_change_password,status
10000001,default123456,normal,小杨,true,active
10000002,default123456,admin,小李,true,active
10000003,default123456,admin,小赵,true,no_active
```

## 列出所有账号

不会输出密码哈希，也不会输出明文密码：

```powershell
python backend\account_admin.py list
```

## 单个创建账号

```powershell
python backend\account_admin.py create --username 10000004 --password default123456 --role normal --nickname 小王 --must-change-password true --status active
```

角色只允许：

```text
normal
admin
```

状态只允许：

```text
active
no_active
```

## 批量导入账号

CSV 必须包含以下列：

```csv
username,password,role,nickname,must_change_password,status
10000001,default123456,normal,小杨,true,active
10000002,default123456,admin,小李,true,active
10000003,default123456,admin,小赵,true,no_active
```

执行导入：

```powershell
python backend\account_admin.py import-csv --file .\accounts.csv
```

如果 CSV 是 GBK 编码：

```powershell
python backend\account_admin.py import-csv --file .\accounts.csv --encoding gbk
```

已存在的 `username` 会跳过，不会覆盖。

## 重置指定账号密码

忘记密码时不能查看原密码，只能重置为指定临时密码。重置后会自动标记 `must_change_password=true`。

```powershell
python backend\account_admin.py reset-password --username 10000001 --password Temp@123456
```

## 修改账号信息

修改角色：

```powershell
python backend\account_admin.py update --username 10000001 --role admin
```

修改昵称：

```powershell
python backend\account_admin.py update --username 10000001 --nickname 小杨老师
```

修改状态：

```powershell
python backend\account_admin.py update --username 10000003 --status active
```

也可以一次修改多个字段：

```powershell
python backend\account_admin.py update --username 10000001 --role normal --nickname 小杨 --status active
```

## 修改 username

```powershell
python backend\account_admin.py rename --old-username 10000001 --new-username 10001001
```

如果新 username 已存在，命令会失败，不会覆盖已有账号。

## 删除单个账号

```powershell
python backend\account_admin.py delete --username 10000001
```

## 清空所有账号

这是高风险操作，必须显式添加 `--yes`。

```powershell
python backend\account_admin.py clear --yes
```

清空账号不会删除案例、审核记录、版本记录，也不会删除 MongoDB 数据库。

## 登录与改密

登录接口仍为：

```text
POST /api/auth/login
```

登录成功后会返回：

```json
{
  "id": 1,
  "username": "10000001",
  "role": "normal",
  "nickname": "小杨",
  "must_change_password": true,
  "status": "active",
  "token": "10000001_..."
}
```

当 `must_change_password=true` 时，前端应提示用户修改密码。

改密接口：

```text
POST /api/auth/change-password
```

表单字段：

```text
username
old_password
new_password
```
