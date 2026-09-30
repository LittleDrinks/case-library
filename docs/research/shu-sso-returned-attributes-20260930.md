# 上海大学 SSO 可返回哪些用户信息

查阅日期：2026-09-30。目的：为 Case Library 当前用户准入、校内素材申请和必填资料讨论核对事实；不实现接入，也不裁定完整协议票。

## 核心结论

**本次没有找到上海大学公开的第三方 SSO 属性释放合同或正式返回字段表。** 因此，无法确认 Case Library 获批接入后一定能自动取得姓名、学／工号、稳定人员标识、教师／学生身份、单位／学院或邮箱。这是公开证据不足，不代表学校不支持这些信息。[学校系统统一身份认证申请说明](https://its.shu.edu.cn/sytplb/bmfw/xttysfrzsq.htm)

官方材料能证明学校使用学／工号认证，并在账号激活／找回中持有姓名等资料；公共客户端源码还能证明某个已登录业务应用消费 `userCode`。这两类证据都不能升级为“学校对本项目保证释放同样字段”。[学校邮件公告](https://its.shu.edu.cn/info/1095/2354.htm)；[录播应用客户端代码](https://github.com/hidacow/SHU-CourseDownload/blob/02ba50c9fdad9547384c923b591eab4320f1df54/CourseDownload.py#L192-L194)

“姓名＋学工号必填、其他选填”是本项目要求用户提供哪些资料的规则；“这些资料是否能由学校接口自动填入并证明真实”是另一个尚待接口合同确认的问题。SSO 认证成功本身不证明用户自行填写的姓名、学工号、教师身份或所属单位已被学校核实。

## 逐项证据矩阵

| 资料 | 校方明确的公开事实 | 特定应用源码观察 | 能否确认 Case Library 的 SSO 返回 |
| --- | --- | --- | --- |
| 姓名 | 邮件账号激活及密码重置说明要求姓名；说明学校认证流程涉及该资料。[邮件公告](https://its.shu.edu.cn/info/1095/2354.htm)、[多因子通知](https://newits.shu.edu.cn/info/1095/6182.htm) | 本次核查的两个候选中未取得学校 SSO 姓名属性字段 | 未确认字段名、释放许可、是否必有值 |
| 学／工号 | 邮箱通过对应统一认证学／工号登录；不是第三方返回字段说明。[邮件公告](https://its.shu.edu.cn/info/1095/2354.htm) | 录播客户端读取业务用户信息的 `userCode`，但该代码未证明其字段定义就是学／工号。[代码:192–194](https://github.com/hidacow/SHU-CourseDownload/blob/02ba50c9fdad9547384c923b591eab4320f1df54/CourseDownload.py#L192-L194) | 未确认是否直接返回、字段名及准确语义 |
| 稳定用户标识 | 未找到跨升学、离校再入职／入学的不可变人员标识合同 | `userCode` 只是特定业务字段；另一前端使用自己数据库的 userInfo 主键 | 未确认 issuer／subject 或等价标识、唯一性及不重分配保证 |
| 教师／学生／在职在籍状态 | 官方多因子说明列出企业微信覆盖全日制学生、在编／聘用教职工及离退休教师；未说向第三方释放分类。[多因子通知](https://newits.shu.edu.cn/info/1095/6182.htm) | 未取得相应认证返回字段 | 未确认；不能把“有统一认证账号”等同于“当前教师”或“当前在籍学生” |
| 单位／学院 | 本次未找到 SSO 属性释放说明 | 未取得相应认证返回字段 | 未确认；业务系统已有组织数据不证明来源是 SSO |
| 邮箱 | 官方说明部分账号需另行开通学校邮箱；并非所有认证账号天然拥有同样邮箱域。[邮件公告](https://its.shu.edu.cn/info/1095/2354.htm) | 未取得相应认证返回字段 | 未确认是否返回、是否已验证、空值和多邮箱语义 |

## 第一类：校方明确说了什么

1. 信息办[系统统一身份认证申请页面](https://its.shu.edu.cn/sytplb/bmfw/xttysfrzsq.htm)说明认证系统为全校师生提供统一身份认证，并通过授权访问机制为其他应用提供数据接口。页面没有属性名称、JSON／XML 响应、scope 与字段对应关系、第三方应用默认权限或样例。
2. 2026-03-10 的[学校邮件系统公告](https://its.shu.edu.cn/info/1095/2354.htm)说明用户输入对应邮箱的统一认证学／工号，经二次验证进入邮箱。激活流程涉及学／工号、姓名、证件号码；这是学校自身识别和账户开通所需资料，**不是应用拿到的登录响应**。公告还提示没有开通过邮箱的账号需申请，不能预设所有账号都能返回学校邮箱。
3. 2026-03-02 的[多因子通知](https://newits.shu.edu.cn/info/1095/6182.htm)说明学工号与企业微信／短信验证方式；密码重置使用姓名等信息。其用户群体包含学生、教职工、退休教师，但没有定义供第三方使用的身份类别字段、枚举值或撤销规则。
4. [2025 新生企业微信说明](https://yingxin.shu.edu.cn/info/1008/2205.htm)提到之前已在上海大学就读的学生可以激活新学号。**有限推论**：不应未经保证就把学工号视为一个人终身不变的主键；这不证明学校另行提供的稳定 subject 一定变化，也不证明 Case Library 已能取得该 subject。

## 第二类：公开应用代码实际消费了什么

这些是相应客户端作者发布的源代码，可用于确认该实现如何处理用户信息；它们不是校方正式文档。本次没有运行代码、登录系统或取得任何真实用户响应。

### 录播应用的 `userCode`

仓库 `hidacow/SHU-CourseDownload`，固定提交 `02ba50c9fdad9547384c923b591eab4320f1df54`：

- [CourseDownload.py:14–17](https://github.com/hidacow/SHU-CourseDownload/blob/02ba50c9fdad9547384c923b591eab4320f1df54/CourseDownload.py#L14-L17)声明 base 为 `https://vod.cc.shu.edu.cn/`，用户信息路径为 `app/user/getUserInfo`。
- [CourseDownload.py:68–74](https://github.com/hidacow/SHU-CourseDownload/blob/02ba50c9fdad9547384c923b591eab4320f1df54/CourseDownload.py#L68-L74)在已登录 session 中 POST 该路径、解析 JSON 并返回。
- [CourseDownload.py:192–194](https://github.com/hidacow/SHU-CourseDownload/blob/02ba50c9fdad9547384c923b591eab4320f1df54/CourseDownload.py#L192-L194)消费字段：`username = userinfo['userCode']`。

可确认：作者的客户端期望录播应用返回 `userCode`。不能确认：学校 SSO 本身释放 `userCode`、其必然是学工号、其不可变、姓名是否同行返回、另一新注册应用能否获得该字段。该代码还出现课程数据的 `userName`，但它属于课程列表，不能当作登录者姓名或 SSO claim。

### 自有用户数据库的 userInfo 主键

仓库 `csycsx/vue-admin-template`，固定提交 `27fa85cce1bfa1842013e5b95acf182d630be007`：

- [src/views/login/index.vue:71–78](https://github.com/csycsx/vue-admin-template/blob/27fa85cce1bfa1842013e5b95acf182d630be007/src/views/login/index.vue#L71-L78)注释说明暂时通过 userInfo 主键取数据库用户信息，再初始化应用状态。
- [src/api/user.js:37–42](https://github.com/csycsx/vue-admin-template/blob/27fa85cce1bfa1842013e5b95acf182d630be007/src/api/user.js#L37-L42)的 `getUserInfoById` 调用该应用的 `/user/login`；[同文件:12–18](https://github.com/csycsx/vue-admin-template/blob/27fa85cce1bfa1842013e5b95acf182d630be007/src/api/user.js#L12-L18)另有 `/user/loginOauth`。

这些代码能说明应用自身的用户处理，不能提供校方的返回字段合同；`getInfo`、`userinfo` 等命名不能证明实现了 OIDC UserInfo。

## 第三类：协议规范支持什么，但上海大学尚未证实

以 [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html) 为例，而不是认定上海大学采用 OIDC：

- [§5.1 Standard Claims](https://openid.net/specs/openid-connect-core-1_0.html#StandardClaims)定义 `name`、`email`、`email_verified`、`preferred_username` 等通用字段。
- [§5.1.2 Additional Claims](https://openid.net/specs/openid-connect-core-1_0.html#AdditionalClaims)允许额外 claim；学工号、教师／学生、学院等需相应约定，没有自动通用字段合同。
- [§5.4 与 §5.5](https://openid.net/specs/openid-connect-core-1_0.html#ScopeClaims)说明申请范围与 claim 请求；提出请求不保证平台掌握或获准释放全部字段。
- [§5.7](https://openid.net/specs/openid-connect-core-1_0.html#ClaimStability)规定 OIDC 中 `iss` 与 `sub` 的组合才具有对应的稳定标识保证；`preferred_username`、姓名、邮箱不等价于该组合。此保证只适用于满足该规范的接入，不能直接附加在 SHU 的学工号上。
- 同规范[§1 Introduction](https://openid.net/specs/openid-connect-core-1_0.html#Introduction)区分 OAuth 资源授权与 OIDC 身份层。因此，`/oauth/authorize`、`response_type=code` 或名为 getUserInfo 的业务 API 都不能单独证明学校有 OIDC 及其字段。

## 尚需校方确认的最小事实

对于当前资料收集讨论，只需向正式接入方核实：授权给 Case Library 的认证后响应是否提供姓名和学／工号；它们的准确字段名、空值及真实性语义；是否存在比学工号更稳定的唯一人员标识。教师／学生和院系可以随后核实，不将这些字段预设为可自动取得。

如果只有学工号或稳定外部标识，没有姓名，用户补填姓名依然可以满足应用的必填要求，但其来源和验证状态应与校方直接返回的属性区分。这里只描述证据边界，不决定注册、资料申请或全站资料表单最终在哪一步必填。

## 查找范围和限制

- 阅读用户既有 `docs/research/shu-identity-integration.md`，重新打开学校的统一认证申请、邮件接入、多因子通知和新生账号说明；查找 `newits.shu.edu.cn`、`its.shu.edu.cn` 等官方域名中“统一身份认证＋接口／返回／姓名／属性”、`newsso`、`userinfo`、`access_token` 等组合。
- GitHub code search 查询 `newsso.shu.edu.cn` 和 `userinfo` 的交集，核查以上两份确有用户信息处理的客户端；其余主要是登录／健康填报脚本、PoC 或侦察资料，未把它们当作学校合同。
- 未使用其他大学、上海教育认证中心或厂商的字段表替代 SHU 契约；登录页面输入字段、各业务系统已有姓名院系、教务／人事数据同步都未被当作 SSO 属性释放证据。
- `newits.shu.edu.cn/info/1095/6192.htm` 本次直接打开超时，使用旧官网同名正式公告 `its.shu.edu.cn/info/1095/2354.htm` 核对。
- 未请求学校非公开接入材料、未使用账号或凭据、未访问用户数据、未调用认证后的业务接口、未运行公开脚本或测试绕过。公开材料可能不完整；应从“尚未确认”继续推进，而不能写成“学校不能返回”。
