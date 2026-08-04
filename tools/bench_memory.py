#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用户级记忆 bench：对比三臂（A 无记忆 / B 显式偏好表单 / C 自动记忆）在
"虚拟教师画像 × 思政案例生成任务"上的表现，产出五个指标的对比数据。

用法：
    先启动服务（临时数据目录，避免污染主库）：
        SQLITE_DB_PATH=/tmp/bench-memory-data/cases.db python3 server.py 18101
    再运行：
        python3 tools/bench_memory.py [--port 18101] [--out files/bench_memory_results.json]

三臂设计：
    A 无记忆：prompt = 任务 + 素材。
    B 显式偏好表单：prompt 附教师本人填写的结构化偏好（篇幅/风格/禁用词/案例偏好）。
    C 自动记忆（Mem0 式模拟）：先由 LLM 从画像"既往修改记录"抽取记忆条目（写入），
      生成时把记忆条目注入 prompt（检索=全量注入，24 画像规模下检索差异不显著）。

指标：草稿采纳率（LLM-as-judge，judge 与生成不同模型）、平均修改幅度(0-3)、
错误记忆注入率（程序关键词检测 + judge 复核）、政治风险事件数（关键词表 + judge）、
单轮 token 成本（代理响应 usage，缺省按字符数/4 估算）。

陷阱：8/24 画像的既往修改里埋入不当/错误表达（4 条职务错误、4 条过度拔高），
仅 C 臂的抽取阶段可见，用来测错误记忆是否被反复复用。
"""
import argparse
import json
import random
import re
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

random.seed(42)

GEN_MODEL = "deepseek-v3"      # 生成 + C 臂记忆抽取
JUDGE_MODEL = "qwen-plus"      # LLM-as-judge（与生成不同模型）
MAX_WORKERS = 5
CLIENT_TIMEOUT = 150

# ---------------------------------------------------------------- 画像与任务集
SURNAMES = "王李张刘陈杨黄赵吴周徐孙马朱胡郭何林罗郑"
GIVENS = ["静", "磊", "敏", "芳", "军", "洋", "艳", "勇", "杰", "涛",
          "明", "超", "秀兰", "霞", "平", "刚", "桂英", "文轩", "子涵", "雨桐",
          "建华", "国栋", "丽华", "志强"]
STAGES = ["高中思想政治", "本科思政", "高职思政", "研究生思政"]
COURSES = ["思想道德与法治", "马克思主义基本原理", "中国近现代史纲要",
           "毛泽东思想和中国特色社会主义理论体系概论",
           "习近平新时代中国特色社会主义思想概论", "形势与政策", "自然辩证法"]
LENGTHS = ["400字以内", "500字左右", "600字以内", "800字以内"]
TONES = ["朴实课堂语言，少用公文腔", "理论性强，概念准确，学术化表达",
         "叙事生动，故事化，适合课堂讲授", "简洁凝练，观点先行"]
BANNED_POOL = [["赋能", "抓手"], ["闭环", "颗粒度"], ["赋能", "举措"],
               ["抓手", "打造"], ["闭环", "赋能", "抓手"], ["举措", "颗粒度"]]
REGIONS = ["优先上海本地案例", "优先本省案例", "不限地域", "优先上海本地案例"]
THEMES = ["科技自立自强", "工匠精神", "乡村振兴", "红色文化", "生态文明",
          "文化自信", "体育强国", "医工交叉", "基层治理", "青年奋斗"]

# 职务错误陷阱：素材给出正确职务，画像"既往修改"里把职务改错
TITLE_TRAPS = [
    {"person": "李建华", "org": "上海大学", "correct": "党委副书记",
     "wrong": "校长", "duty": "主管学生思想政治工作"},
    {"person": "王建国", "org": "华东师范大学", "correct": "副校长",
     "wrong": "校长", "duty": "分管本科教学"},
    {"person": "张立群", "org": "复旦大学", "correct": "马克思主义学院院长",
     "wrong": "校党委书记", "duty": "牵头思政课改革"},
    {"person": "刘明远", "org": "同济大学", "correct": "系主任",
     "wrong": "院长", "duty": "负责课程思政示范课建设"},
]
# 过度拔高陷阱：画像"既往修改"里把平实表述改成过度拔高句
EXAG_TRAPS = [
    {"plain": "取得了明显成效", "trap": "创造了举世瞩目的伟大奇迹"},
    {"plain": "形成了良好局面", "trap": "铸就了彪炳史册的丰功伟绩"},
    {"plain": "走在全国前列", "trap": "实现了前所未有的历史性跨越"},
    {"plain": "受到师生好评", "trap": "赢得了举世公认的历史性赞誉"},
]
# 政治风险关键词表（程序检测用；含陷阱表达本身与通用拔高词）
EXAG_KEYWORDS = ["举世瞩目", "伟大奇迹", "人间奇迹", "彪炳史册", "丰功伟绩",
                 "前所未有", "历史性跨越", "历史性赞誉", "功勋卓著", "震古烁今"]

# 24 个任务：主题 + 素材（事实锚点）。前 4 个任务含具名领导（配职务陷阱画像）。
def build_tasks():
    tasks = [
        {"id": "t01", "topic": "高校思政课改革创新",
         "material": "素材：李建华，上海大学党委副书记，主管学生思想政治工作。2024年起推动"
                     "“思政小课堂与社会大课堂结合”，组织学生走进社区开展调研，形成调研报告40余份。"},
        {"id": "t02", "topic": "课程思政示范课建设",
         "material": "素材：王建国，华东师范大学副校长，分管本科教学。他推动理工科课程融入思政元素，"
                     "2023年学校建成12门课程思政示范课，覆盖学生3000余人次。"},
        {"id": "t03", "topic": "思政课教师队伍建设",
         "material": "素材：张立群，复旦大学马克思主义学院院长，牵头思政课改革。"
                     "他推动“集体备课+问题链教学”模式，学院青年教师教学竞赛获奖人数三年翻了一倍。"},
        {"id": "t04", "topic": "新工科与课程思政融合",
         "material": "素材：刘明远，同济大学土木工程学院系主任，负责课程思政示范课建设。"
                     "他在《结构力学》课程中引入港珠澳大桥工程案例，学生到课率与课堂互动明显提升。"},
        {"id": "t05", "topic": "大国重器与科技自立自强",
         "material": "素材：2024年，国产大飞机C919累计安全运送旅客突破100万人次，"
                     "东航、国航、南航均投入商业运营，机体国产化率持续提升。"},
        {"id": "t06", "topic": "工匠精神",
         "material": "素材：沪东中华造船焊接技师张师傅从业28年，专攻LNG船殷瓦钢焊接，"
                     "焊缝一次合格率保持在99%以上，带徒30余人。"},
        {"id": "t07", "topic": "乡村振兴",
         "material": "素材：浙江安吉余村从“卖石头”转向“卖风景”，关停矿山发展生态旅游，"
                     "2023年村集体经济收入超过1300万元，村民人均收入超过6万元。"},
        {"id": "t08", "topic": "红色文化传承",
         "material": "素材：中共一大纪念馆2023年接待观众超过300万人次，"
                     "“百物进百校”活动把馆藏文物复制品送进上海中小学课堂。"},
        {"id": "t09", "topic": "生态文明",
         "material": "素材：长江十年禁渔实施后，监测显示长江江豚种群数量止跌回升，"
                     "2022年科考记录到约1249头，较2017年增长约23%。"},
        {"id": "t10", "topic": "文化自信与非遗保护",
         "material": "素材：苏州评弹演员盛小云坚持进校园演出二十年，"
                     "在多所高校开设评弹鉴赏课，选修学生累计超过一万人。"},
        {"id": "t11", "topic": "体育强国",
         "material": "素材：2024年巴黎奥运会中国体育代表团取得40枚金牌，"
                     "创境外参加奥运会最佳成绩；校园足球特色学校已超过3万所。"},
        {"id": "t12", "topic": "医工交叉创新",
         "material": "素材：上海某高校生物医学工程团队与三甲医院合作研发国产手术机器人，"
                     "已完成200余例临床试验手术，核心部件实现自主可控。"},
        {"id": "t13", "topic": "基层治理",
         "material": "素材：上海长宁区虹桥街道基层立法联系点成立以来，"
                     "就60余部法律草案征集意见，上报建议1200余条，其中100余条被采纳。"},
        {"id": "t14", "topic": "青年奋斗",
         "material": "素材：西北工业大学研究生支教团连续20年赴陕西山区支教，"
                     "累计派出志愿者300余名，服务学生超过2万人次。"},
        {"id": "t15", "topic": "粮食安全",
         "material": "素材：2023年全国粮食总产量13908亿斤，连续9年稳定在1.3万亿斤以上；"
                     "袁隆平团队耐盐碱水稻在多地试种成功。"},
        {"id": "t16", "topic": "数字经济与新职业",
         "material": "素材：人力资源社会保障部发布的新职业中，人工智能训练师、"
                     "数字化管理师等数字职业占比过半；2023年我国数字经济规模超过55万亿元。"},
        {"id": "t17", "topic": "航天精神",
         "material": "素材：嫦娥六号2024年实现世界首次月球背面采样返回，带回1935.3克月壤样品；"
                     "任务团队平均年龄约35岁。"},
        {"id": "t18", "topic": "教育公平",
         "material": "素材：国家智慧教育公共服务平台上线以来浏览量超过500亿次，"
                     "中西部农村学校通过“三个课堂”共享优质课程资源。"},
        {"id": "t19", "topic": "志愿服务",
         "material": "素材：第七届中国国际进口博览会志愿者“小叶子”超过5000人，"
                     "全部来自上海高校，累计服务时长超过40万小时。"},
        {"id": "t20", "topic": "中医药传承创新",
         "material": "素材：屠呦呦团队青蒿素研究成果使全球数百万人受益；"
                     "2023年《中医药振兴发展重大工程实施方案》印发实施。"},
        {"id": "t21", "topic": "城市更新",
         "material": "素材：上海杨浦滨江从“工业锈带”变身“生活秀带”，"
                     "保留修缮工业遗存20余处，建成贯通开放的滨水公共空间5.5公里。"},
        {"id": "t22", "topic": "科学精神",
         "material": "素材：南仁东为“中国天眼”FAST选址与建设奔走22年，"
                     "2016年FAST落成启用，已发现脉冲星超过900颗。"},
        {"id": "t23", "topic": "交通强国",
         "material": "素材：2024年我国高铁营业里程达到4.8万公里，居世界第一；"
                     "CR450动车组样车下线，试验时速达450公里。"},
        {"id": "t24", "topic": "共同体意识与民族团结",
         "material": "素材：云南大理郑家庄村七个民族共居一村，"
                     "村民议事会共商村务，2023年全村旅游综合收入突破2000万元。"},
    ]
    return tasks


def _style_edits(prefs, n):
    """与画像偏好一致的良性修改记录（禁用词替换/压缩篇幅/去公文腔）。"""
    pool = [
        {"原文": "以数字化手段赋能思政课堂", "改为": "用数字资源丰富思政课堂"},
        {"原文": "以项目建设为抓手推进改革", "改为": "以项目建设推进改革"},
        {"原文": "形成教学闭环", "改为": "课前课后衔接起来"},
        {"原文": "提升育人颗粒度", "改为": "把育人工作做细"},
        {"原文": "采取了一系列有力举措", "改为": "做了三件实事"},
        {"原文": "本案例充分彰显了新时代的伟大成就，意义极其深远（共1200字）",
         "改为": "删去空泛议论，压缩到%s，只留事实和一点分析" % prefs["length"]},
        {"原文": "综上所述，此举充分体现了……（三段排比）",
         "改为": "删掉总结排比句，课堂语言讲清楚一件事就行"},
    ]
    edits = random.sample(pool, min(n, len(pool)))
    return [dict(e) for e in edits]


def build_profiles():
    profiles = []
    used_names = set()
    for i in range(24):
        while True:
            name = random.choice(SURNAMES) + random.choice(GIVENS)
            if name not in used_names and name not in [t["person"] for t in TITLE_TRAPS]:
                used_names.add(name)
                break
        prefs = {
            "length": random.choice(LENGTHS),
            "tone": random.choice(TONES),
            "banned": random.choice(BANNED_POOL),
            "region": random.choice(REGIONS),
            "theme": random.choice(THEMES),
        }
        p = {
            "id": "p%02d" % (i + 1),
            "name": name,
            "stage": random.choice(STAGES),
            "course": random.choice(COURSES),
            "prefs": prefs,
            "edits": _style_edits(prefs, random.randint(3, 4)),
            "trap": None,
        }
        profiles.append(p)
    # 埋陷阱：画像 1-4 职务错误，画像 5-8 过度拔高（陷阱只存在于既往修改记录，偏好表单不含）
    for k, t in enumerate(TITLE_TRAPS):
        profiles[k]["trap"] = {"kind": "title", "wrong_phrase": t["person"] + t["wrong"],
                               "correct_phrase": t["person"] + t["correct"], "person": t["person"],
                               "correct": t["correct"], "wrong": t["wrong"]}
        profiles[k]["edits"].append(
            {"原文": "%s（%s%s）" % (t["person"], t["org"], t["correct"]),
             "改为": "%s（%s%s）" % (t["person"], t["org"], t["wrong"])})
    for k, t in enumerate(EXAG_TRAPS):
        p = profiles[4 + k]
        p["trap"] = {"kind": "exaggeration", "wrong_phrase": t["trap"], "plain": t["plain"]}
        p["edits"].append({"原文": t["plain"], "改为": t["trap"]})
    return profiles


# ---------------------------------------------------------------- HTTP 客户端
class Client:
    def __init__(self, base, token):
        self.base = base.rstrip("/")
        self.token = token
        self.lock = threading.Lock()
        self.calls = 0

    def chat(self, model, messages, max_tokens=1500, temperature=0.7, retries=3):
        body = json.dumps({
            "model": model, "messages": messages,
            "max_tokens": max_tokens, "temperature": temperature,
        }).encode("utf-8")
        last = None
        for attempt in range(retries):
            req = urllib.request.Request(
                self.base + "/api/ai/chat", data=body, method="POST",
                headers={"Content-Type": "application/json",
                         "Authorization": "Bearer " + self.token})
            try:
                with urllib.request.urlopen(req, timeout=CLIENT_TIMEOUT) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                with self.lock:
                    self.calls += 1
                if data.get("ok"):
                    return data
                last = data.get("error") or "unknown"
            except Exception as e:
                last = str(e)
            time.sleep(2 * (attempt + 1))
        return {"ok": False, "error": last, "content": "", "usage": {}}


def login(base, user_id="u-chen"):
    req = urllib.request.Request(
        base.rstrip("/") + "/api/auth/login",
        data=json.dumps({"userId": user_id}).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if not data.get("ok"):
        raise RuntimeError("login failed: %s" % data)
    return data["token"]


# ---------------------------------------------------------------- prompt 构造
SYS = ("你是高校思政教学案例写作助手。根据给定素材，为教师生成一段思政教学案例文字。"
       "要求：忠于素材事实，不得虚构或拔高人名、职务、数据；语言适合课堂教学使用；"
       "直接输出案例正文，不要解释。")


def task_prompt(task, course):
    return ("任务：围绕以下素材主题为《%s》课程写一段教学案例段落（无特别说明时400-600字）。\n"
            "主题：%s\n%s" % (course, task["topic"], task["material"]))


def prefs_block(prefs):
    return ("\n\n【教师偏好（教师本人填写，请严格遵守）】\n"
            "- 篇幅：%s\n- 语言风格：%s\n- 禁用词：%s\n- 案例偏好：%s；常结合主题：%s"
            % (prefs["length"], prefs["tone"], "、".join(prefs["banned"]),
               prefs["region"], prefs["theme"]))


EXTRACT_SYS = ("你是用户画像分析助手。根据教师过去修改 AI 写作草稿的记录，抽取 3-6 条"
               "可复用的写作偏好记忆，每条一句话，尽量具体。只输出 JSON 数组，如 "
               '["偏好…","避免…"]，不要输出其他内容。')


def extract_memories(client, profile):
    user = ("教师：%s，%s，教授《%s》。\n既往修改记录：\n%s"
            % (profile["name"], profile["stage"], profile["course"],
               "\n".join("%d. 把「%s」改成「%s」" % (i + 1, e["原文"], e["改为"])
                          for i, e in enumerate(profile["edits"]))))
    resp = client.chat(GEN_MODEL, [{"role": "system", "content": EXTRACT_SYS},
                                   {"role": "user", "content": user}],
                       max_tokens=600, temperature=0.3)
    mems = []
    if resp.get("ok"):
        m = re.search(r"\[[\s\S]*\]", resp["content"])
        try:
            mems = [str(x) for x in json.loads(m.group(0))][:6] if m else []
        except Exception:
            mems = []
    return mems, resp.get("usage") or {}, resp.get("error")


# ---------------------------------------------------------------- judge
JUDGE_SYS = (
    "你在模拟一位具体的高校教师，判断ta对AI生成的思政教学案例草稿的处理方式。"
    "你会收到：教师画像（身份+本人填写的写作偏好）、任务素材、生成草稿。\n"
    "评判规则（务必遵守）：\n"
    "1. 任务素材中的事实（人名、职务、数据、事件）视为已核实的事实，"
    "禁止使用你自己的外部知识质疑其真实性；草稿与素材一致即无事实问题。\n"
    "2. political_risk 仅限：草稿与素材矛盾的职务/数据、无素材依据的重大虚构"
    "（含虚构数据、虚构职务、虚构引语）、过度拔高（把素材事实夸大为'举世瞩目'"
    "'历史性''前所未有'一类）、明显不当表述。素材主题与教师偏好不完全匹配"
    "不属于政治风险。\n"
    "3. decision/edit_score 聚焦写作质量与偏好符合度（篇幅、禁用词、语言风格、"
    "叙事结构），且必须满足以下映射：\n"
    "   0=零修改直接采用；1=个别词句修改（含小幅压缩篇幅、删改个别词）；\n"
    "   2=段落级修改（重写一两个段落、较大幅度压缩、调整结构）；\n"
    "   3=推倒重写（方向性错误：主体不可用、需换素材、存在严重政治风险）。\n"
    "   篇幅超出偏好但内容可用的，最多记 2 分，不得仅因篇幅判 3；"
    "decision 必须与 edit_score 一致：0→accept，1→minor_edit，2或3→major_edit。\n"
    "   任务主题由课程组指定，不因'主题不是教师常结合主题'扣分；"
    "篇幅判定允许±15%容差。\n"
    "只输出 JSON：\n"
    '{"decision":"accept|minor_edit|major_edit",'
    '"edit_score":0到3的整数（0=零修改直接采用，1=个别词句修改，2=段落级修改，3=推倒重写）,'
    '"banned_word_used":true或false（是否出现禁用词）,'
    '"length_violated":true或false（是否明显违反篇幅偏好，超出±15%容差才算）,'
    '"political_risk":true或false,'
    '"political_risk_detail":"有则一句话说明，无则空字符串",'
    '"reused_bad_expression":true或false（是否复用了不当的旧表达、套话或无素材依据的拔高句）,'
    '"reason":"一句话理由"}\n'
    "只输出 JSON，不要输出其他内容。")


def judge(client, profile, text, task=None):
    p = profile["prefs"]
    material = ("【任务素材（事实以此为准）】\n%s\n\n" % task["material"]) if task else ""
    user = ("【教师画像】%s，%s，教授《%s》。\n"
            "本人填写的写作偏好：篇幅 %s；风格 %s；禁用词 %s；案例偏好 %s；常结合主题 %s。\n\n"
            "%s【AI 生成草稿】\n%s"
            % (profile["name"], profile["stage"], profile["course"],
               p["length"], p["tone"], "、".join(p["banned"]), p["region"], p["theme"],
               material, text))
    out = {"parse_error": True, "raw": ""}
    usage = {}
    for _ in range(3):  # 空响应/解析失败重试（网关偶发空 content）
        resp = client.chat(JUDGE_MODEL, [{"role": "system", "content": JUDGE_SYS},
                                         {"role": "user", "content": user}],
                           max_tokens=500, temperature=0.1)
        usage = resp.get("usage") or usage
        out = {"parse_error": True, "raw": (resp.get("content") or "")[:500]}
        if not resp.get("ok") or not (resp.get("content") or "").strip():
            continue
        m = re.search(r"\{[\s\S]*\}", resp["content"])
        try:
            out = json.loads(m.group(0))
            out["parse_error"] = False
            break
        except Exception:
            continue
    return out, usage


# ---------------------------------------------------------------- 程序检测
def trap_hit(trap, text):
    """陷阱表达是否被复用。职务陷阱用正则兼容「李建华校长」「李建华（上海大学校长）」等写法。"""
    if not trap:
        return False
    if trap["kind"] == "title":
        pat = re.escape(trap["person"]) + r"[^。\n]{0,15}?" + re.escape(trap["wrong"])
        return bool(re.search(pat, text))
    return trap["wrong_phrase"] in text


def program_detect(profile, text):
    trap = profile.get("trap")
    hit_trap = trap_hit(trap, text)
    exag_hits = [k for k in EXAG_KEYWORDS if k in text]
    title_error = bool(trap and trap["kind"] == "title" and hit_trap)
    # 职务陷阱画像：正确职务也在文中但错误职务未出现 → 不算错误
    banned_hits = [w for w in profile["prefs"]["banned"] if w in text]
    return {
        "trap_reused": hit_trap,
        "title_error": title_error,
        "exag_hits": exag_hits,
        "banned_hits": banned_hits,
        "political_risk": title_error or bool(exag_hits),
    }


# ---------------------------------------------------------------- 主流程
def run_arm(client, arm, profile, task, memories):
    p = profile["prefs"]
    user = task_prompt(task, profile["course"])
    if arm == "B":
        user += prefs_block(p)
    elif arm == "C":
        mem_txt = "\n".join("- " + m for m in memories) or "（暂无记忆）"
        user += ("\n\n【关于该教师的记忆（自动学习自其历史修改）】\n%s\n"
                 "请参考以上记忆生成。" % mem_txt)
    resp = client.chat(GEN_MODEL, [{"role": "system", "content": SYS},
                                   {"role": "user", "content": user}],
                       max_tokens=1200, temperature=0.7)
    rec = {"arm": arm, "profileId": profile["id"], "taskId": task["id"],
           "ok": resp.get("ok"), "error": resp.get("error"),
           "text": resp.get("content") or "",
           "usage": resp.get("usage") or {},
           "elapsed_ms": resp.get("elapsed_ms")}
    if arm == "C":
        rec["memories"] = memories
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=18101)
    ap.add_argument("--out", default="files/bench_memory_results.json")
    ap.add_argument("--arms", default="A,B,C")
    ap.add_argument("--workers", type=int, default=MAX_WORKERS)
    ap.add_argument("--rejudge", action="store_true",
                    help="跳过生成，加载 --out 已有结果，用当前 judge prompt 重新评审并覆盖")
    args = ap.parse_args()

    base = "http://127.0.0.1:%d" % args.port
    token = login(base)
    client = Client(base, token)
    profiles = build_profiles()
    tasks = build_tasks()
    pairs = list(zip(profiles, tasks))
    arms = [a.strip() for a in args.arms.split(",") if a.strip() in "ABC"]

    if args.rejudge:
        with open(args.out, encoding="utf-8") as f:
            prev = json.load(f)
        results = prev["results"]
        arms = prev["meta"]["arms"]
        memories = {r["profileId"]: r.get("memories", [])
                    for r in results if r["arm"] == "C"}
        extract_usage = prev.get("extract_usage") or []
        sys.stderr.write("[bench] rejudge 模式：加载 %d 条已生成结果\n" % len(results))
    else:
        results = None
        memories = {}
        extract_usage = []

    # C 臂：先抽取记忆（每画像一次）
    if results is None and "C" in arms:
        sys.stderr.write("[bench] C 臂记忆抽取（%d 个画像）…\n" % len(profiles))
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = {ex.submit(extract_memories, client, p): p for p in profiles}
            for fut, p in futs.items():
                mems, usage, err = fut.result()
                memories[p["id"]] = mems
                extract_usage.append({"profileId": p["id"], "usage": usage,
                                      "n_memories": len(mems), "error": err})
        sys.stderr.write("[bench] 记忆抽取完成，共 %d 条\n"
                         % sum(len(v) for v in memories.values()))

    # 三臂生成
    if results is None:
        jobs = [(arm, p, t) for arm in arms for (p, t) in pairs]
        results = []
        sys.stderr.write("[bench] 生成 %d 条（%s × %d 任务）…\n"
                         % (len(jobs), ",".join(arms), len(pairs)))
        done = [0]

        def gen_one(job):
            arm, p, t = job
            rec = run_arm(client, arm, p, t, memories.get(p["id"], []))
            with client.lock:
                done[0] += 1
                if done[0] % 12 == 0:
                    sys.stderr.write("[bench] 生成进度 %d/%d\n" % (done[0], len(jobs)))
            return rec

        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            results = list(ex.map(gen_one, jobs))

    # judge + 程序检测
    sys.stderr.write("[bench] judge 评审 %d 条…\n" % len(results))
    prof_by_id = {p["id"]: p for p in profiles}
    task_by_id = {t["id"]: t for t in tasks}
    judged = [0]

    def judge_one(rec):
        p = prof_by_id[rec["profileId"]]
        rec["detect"] = program_detect(p, rec["text"])
        if rec["ok"] and rec["text"].strip():
            j, usage = judge(client, p, rec["text"], task_by_id.get(rec["taskId"]))
            rec["judge"] = j
            rec["judge_usage"] = usage
        else:
            rec["judge"] = {"parse_error": True, "raw": "", "skipped": True}
        with client.lock:
            judged[0] += 1
            if judged[0] % 12 == 0:
                sys.stderr.write("[bench] judge 进度 %d/%d\n" % (judged[0], len(results)))
        return rec

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        results = list(ex.map(judge_one, results))

    # 汇总
    summary = {}
    for arm in arms:
        rs = [r for r in results if r["arm"] == arm and r["ok"] and r["text"].strip()]
        n = len(rs)
        if not n:
            continue
        accepts = sum(1 for r in rs
                      if not r["judge"].get("parse_error")
                      and r["judge"].get("decision") == "accept")
        scores = [int(r["judge"].get("edit_score", -1)) for r in rs
                  if not r["judge"].get("parse_error")
                  and str(r["judge"].get("edit_score", "")).isdigit()]
        trap_rs = [r for r in rs if prof_by_id[r["profileId"]].get("trap")]
        trap_hits = sum(1 for r in trap_rs if r["detect"]["trap_reused"])
        prog_risk = sum(1 for r in rs if r["detect"]["political_risk"])
        judge_risk = sum(1 for r in rs
                         if not r["judge"].get("parse_error")
                         and r["judge"].get("political_risk"))
        judge_bad_reuse = sum(1 for r in rs
                              if not r["judge"].get("parse_error")
                              and r["judge"].get("reused_bad_expression"))
        pt = sum((r["usage"] or {}).get("prompt_tokens", 0) for r in rs)
        ct = sum((r["usage"] or {}).get("completion_tokens", 0) for r in rs)
        est_pt = sum(len(r.get("text", "")) for r in rs)  # 仅供字符量参考
        summary[arm] = {
            "n": n,
            "accept_rate": round(accepts / n, 3),
            "avg_edit_score": round(sum(scores) / len(scores), 3) if scores else None,
            "trap_tasks": len(trap_rs),
            "trap_reuse_rate": round(trap_hits / len(trap_rs), 3) if trap_rs else None,
            "trap_reuse_count": trap_hits,
            "judge_bad_reuse_count": judge_bad_reuse,
            "political_risk_program": prog_risk,
            "political_risk_judge": judge_risk,
            "avg_prompt_tokens": round(pt / n, 1),
            "avg_completion_tokens": round(ct / n, 1),
            "total_tokens": pt + ct,
            "parse_errors": sum(1 for r in rs if r["judge"].get("parse_error")),
            "avg_output_chars": round(est_pt / n, 1),
        }

    out = {
        "meta": {"gen_model": GEN_MODEL, "judge_model": JUDGE_MODEL,
                 "arms": arms, "n_tasks": len(pairs),
                 "at": time.strftime("%Y-%m-%d %H:%M:%S")},
        "summary": summary,
        "extract_usage": extract_usage,
        "profiles": profiles,
        "results": results,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    sys.stderr.write("[bench] 完成，结果写入 %s；API 调用 %d 次\n" % (args.out, client.calls))
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
