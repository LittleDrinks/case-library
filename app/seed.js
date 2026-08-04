// 平台基础数据：账号、案例类型与模板、素材注册表、知识来源、演示工作稿
window.SEED = {

  // ---------------------------------------------------------- 账号
  // level: 0 公开 / 1 校内 / 2 受限
  users: [
    {
      id: "u-chen", name: "陈静", role: "硕博公共思政教师", audience: "grad",
      courses: ["自然辩证法概论", "习近平新时代中国特色社会主义思想概论"],
      maxLevel: 2, org: "马克思主义学院",
      prefs: { authorityFirst: true, style: "简练", classForm: "小班研讨", defaultStage: "grad" },
    },
    {
      id: "u-wang", name: "王磊", role: "本科思政教师", audience: "ug",
      courses: ["思想道德与法治", "中国近现代史纲要"],
      maxLevel: 1, org: "马克思主义学院",
      prefs: { authorityFirst: true, style: "通俗", classForm: "大班讲授", defaultStage: "ug" },
    },
    {
      id: "u-zhao", name: "赵敏", role: "专业课程思政教师", audience: "embed",
      courses: ["计算机科学与技术"],
      maxLevel: 0, org: "计算机工程与科学学院",
      prefs: { authorityFirst: false, style: "简练", classForm: "课堂嵌入", defaultStage: "embed" },
    },
    {
      id: "u-admin", name: "周正", role: "案例管理员", audience: "grad",
      courses: [], maxLevel: 2, admin: true, org: "教务部",
      prefs: { authorityFirst: true, style: "规范", classForm: "", defaultStage: "grad" },
    },
  ],

  audienceNames: { grad: "硕博公共思政", ug: "本科思政", embed: "专业课程思政" },
  levelNames: ["公开", "校内", "受限"],
  credNames: { high: "权威来源", normal: "一般来源", low: "待核实" },

  // ---------------------------------------------------------- 案例类型与模板
  // 模板即用途：每个模板声明适用学段与用途，创建案例时不再单独选择用途
  caseTypes: [
    {
      id: "ct-policy", name: "政策落实类",
      templates: [
        { id: "tp-policy-std", name: "课堂讲授模板", stages: ["ug", "grad"], purpose: "日常授课",
          sections: ["政策背景与要求", "落实过程与举措", "成效与反响", "经验与启示"] },
        { id: "tp-policy-deep", name: "集体备课模板", stages: ["grad"], purpose: "集体备课",
          sections: ["政策演进与理论溯源", "落实中的关键矛盾", "落实过程与举措", "成效评估", "理论启示与研讨问题"] },
        { id: "tp-policy-embed", name: "课堂嵌入模板", stages: ["embed"], purpose: "日常授课",
          sections: ["政策要点", "专业结合点", "课堂讨论片段"] },
      ],
    },
    {
      id: "ct-figure", name: "人物传记类",
      templates: [
        { id: "tp-figure-std", name: "课堂讲授模板", stages: ["ug", "grad"], purpose: "日常授课",
          sections: ["人物经历", "关键选择", "精神品格", "价值引领与讨论"] },
        { id: "tp-figure-deep", name: "理论研讨模板", stages: ["grad"], purpose: "集体备课",
          sections: ["人物经历与时代背景", "关键选择与价值冲突", "精神品格的理论解读", "研讨问题与延伸阅读"] },
        { id: "tp-figure-decl", name: "申报模板", stages: ["ug", "grad"], purpose: "案例申报",
          sections: ["人物事迹概述", "精神品格与时代价值", "教学应用设计", "推广价值", "申报说明"] },
        { id: "tp-figure-embed", name: "课堂嵌入模板", stages: ["embed"], purpose: "日常授课",
          sections: ["人物片段", "精神要点", "课堂提问"] },
      ],
    },
    {
      id: "ct-thought", name: "思想实验类",
      templates: [
        { id: "tp-thought-std", name: "课堂讲授模板", stages: ["ug", "grad"], purpose: "日常授课",
          sections: ["情境设定", "矛盾冲突", "讨论路径", "理论回应"] },
        { id: "tp-thought-deep", name: "研讨课模板", stages: ["grad"], purpose: "集体备课",
          sections: ["情境设定与前提假设", "矛盾冲突的多方立场", "讨论路径与引导设计", "理论回应与方法论提升"] },
      ],
    },
    {
      id: "ct-school", name: "校本实践类",
      templates: [
        { id: "tp-school-std", name: "课堂讲授模板", stages: ["ug", "grad"], purpose: "日常授课",
          sections: ["实践背景", "做法与过程", "成效与影响", "总结与启示"] },
        { id: "tp-school-decl", name: "申报模板", stages: ["ug", "grad"], purpose: "案例申报",
          sections: ["实践背景与问题提出", "做法与创新点", "成效与证据", "推广价值", "申报说明"] },
        { id: "tp-school-embed", name: "课堂嵌入模板", stages: ["embed"], purpose: "日常授课",
          sections: ["校本片段", "结合点", "课堂活动"] },
      ],
    },
    {
      id: "ct-tech", name: "科技创新与科技报国类",
      templates: [
        { id: "tp-tech-std", name: "课堂讲授模板", stages: ["ug", "grad"], purpose: "日常授课",
          sections: ["创新背景与需求", "攻关历程", "成果与价值", "精神内涵与讨论"] },
        { id: "tp-tech-deep", name: "理论研讨模板", stages: ["grad"], purpose: "集体备课",
          sections: ["创新背景与国家战略需求", "攻关历程与方法论", "成果的科学技术论分析", "精神内涵与研讨问题"] },
        { id: "tp-tech-decl", name: "申报模板", stages: ["ug", "grad"], purpose: "案例申报",
          sections: ["创新背景与需求", "攻关历程与突破", "成果与证明材料", "精神内涵", "推广价值与申报说明"] },
        { id: "tp-tech-embed", name: "课堂嵌入模板", stages: ["embed"], purpose: "日常授课",
          sections: ["创新片段", "方法论要点", "课堂讨论"] },
      ],
    },
    {
      id: "ct-society", name: "社会热点与治理类",
      templates: [
        { id: "tp-society-std", name: "课堂讲授模板", stages: ["ug", "grad"], purpose: "日常授课",
          sections: ["热点缘起", "各方关切", "治理实践", "分析与讨论"] },
        { id: "tp-society-deep", name: "研讨课模板", stages: ["grad"], purpose: "集体备课",
          sections: ["热点缘起与传播过程", "利益相关方与价值冲突", "治理实践与制度分析", "理论回应与研讨问题"] },
      ],
    },
    {
      id: "ct-general", name: "通用案例",
      templates: [
        { id: "tp-general-std", name: "标准叙事模板", stages: ["ug", "grad", "embed"], purpose: "日常授课",
          sections: ["案例背景", "案例正文", "分析讨论", "总结启示"] },
        { id: "tp-general-pev", name: "现象-本质-价值模板", stages: ["ug", "grad"], purpose: "日常授课",
          sections: ["现象呈现", "本质分析", "价值阐释", "讨论与延伸"] },
        { id: "tp-general-cmp", name: "比较分析模板", stages: ["ug", "grad"], purpose: "集体备课",
          sections: ["比较对象与背景", "相同点与共性", "差异与成因", "规律与启示", "研讨问题"] },
        { id: "tp-general-ref", name: "问题反思模板", stages: ["grad"], purpose: "集体备课",
          sections: ["问题情境", "成因分析", "反思与批判", "改进路径", "理论回应"] },
        { id: "tp-general-decl", name: "申报模板", stages: ["ug", "grad"], purpose: "案例申报",
          sections: ["案例背景与问题", "案例正文", "创新点与成效", "推广价值", "申报说明"] },
      ],
    },
  ],

  purposes: ["日常授课", "集体备课", "案例申报", "其他"],

  // ---------------------------------------------------------- 知识来源登记
  knowledgeSources: [
    { id: "ks-mks", name: "马克思主义基本原理", version: "2023版", updatedAt: "2023-03-01", entries: 0, status: "已登记" },
    { id: "ks-sx", name: "思想道德与法治", version: "2023版", updatedAt: "2023-03-01", entries: 0, status: "已登记" },
    { id: "ks-jx", name: "中国近现代史纲要", version: "2023版", updatedAt: "2023-04-10", entries: 0, status: "已登记" },
    { id: "ks-mg", name: "毛泽东思想和中国特色社会主义理论体系概论", version: "2023版", updatedAt: "2023-04-10", entries: 0, status: "已登记" },
    { id: "ks-xg", name: "习近平新时代中国特色社会主义思想概论", version: "2023版", updatedAt: "2023-08-01", entries: 0, status: "已登记" },
    { id: "ks-zr", name: "自然辩证法概论", version: "2025版", updatedAt: "2026-07-01", entries: 52, status: "已导入" },
    { id: "ks-jh", name: "习近平总书记重要讲话、重要文章和权威论述", version: "持续更新", updatedAt: "2026-07-10", entries: 0, status: "已登记" },
    { id: "ks-xb", name: "学校课程标准及校本理论内容", version: "2026春季", updatedAt: "2026-03-01", entries: 0, status: "已登记" },
  ],

  // ---------------------------------------------------------- 素材（学习资料之外）
  extraMaterials: [
    {
      id: "m-kcsz", tags: ["政策文件", "课程思政"], title: "高等学校课程思政建设指导纲要（教高〔2020〕3号）", kind: "文档",
      source: "教育部官网", sourceUrl: "http://www.moe.gov.cn/srcsite/A08/s7056/202006/t20200603_462437.html",
      publishedAt: "2020-06-01", collectedAt: "2026-05-12", level: 0, credibility: "high",
      scope: "全体教师", status: "正常",
      summary: "教育部关于课程思政建设的纲领性文件，明确各类课程承担育人责任的要求。",
      excerpt: "落实立德树人根本任务，必须将价值塑造、知识传授和能力培养三者融为一体、不可割裂。全面推进课程思政建设，就是要寓价值观引导于知识传授和能力培养之中，帮助学生塑造正确的世界观、人生观、价值观。让所有高校、所有学科、所有课程都承担好育人责任，守好一段渠、种好责任田。",
    },
    {
      id: "m-kxjsh", tags: ["政策文件", "科学家精神"], title: "关于进一步弘扬科学家精神加强作风和学风建设的意见", kind: "文档",
      source: "中国政府网", sourceUrl: "https://www.gov.cn/zhengce/2022-09/07/content_5708685.htm",
      publishedAt: "2022-09-07", collectedAt: "2026-05-12", level: 0, credibility: "high",
      scope: "全体教师", status: "正常",
      summary: "中办、国办印发，将科学家精神纳入新时代精神文明建设体系。",
      excerpt: "科学家精神是科技工作者在长期科学实践中积累的宝贵精神财富。大力弘扬胸怀祖国、服务人民的爱国精神，勇攀高峰、敢为人先的创新精神，追求真理、严谨治学的求实精神，淡泊名利、潜心研究的奉献精神，集智攻关、团结协作的协同精神，甘为人梯、奖掖后学的育人精神。",
    },
    {
      id: "m-ershida", tags: ["政策文件", "交叉创新"], title: "党的二十大报告（教育、科技、人才部分节选）", kind: "文档",
      source: "新华网", sourceUrl: "https://www.news.cn/politics/cpc20/2022-10/25/c_1129079429.htm",
      publishedAt: "2022-10-25", collectedAt: "2026-05-12", level: 0, credibility: "high",
      scope: "全体教师", status: "正常",
      summary: "二十大报告关于教育、科技、人才三位一体部署与交叉学科建设的论述。",
      excerpt: "教育、科技、人才是全面建设社会主义现代化国家的基础性、战略性支撑。必须坚持科技是第一生产力、人才是第一资源、创新是第一动力。加强基础学科、新兴学科、交叉学科建设，加快建设中国特色、世界一流的大学和优势学科。",
    },
    {
      id: "m-qwllib", tags: ["科学家精神", "校本实践", "大思政课"], title: "钱伟长图书馆入选上海市“大思政课”实践教学基地", kind: "链接",
      source: "上海大学新闻网", sourceUrl: "https://www.shu.edu.cn/",
      publishedAt: "2024-12-18", collectedAt: "2026-05-20", level: 0, credibility: "high",
      scope: "全体教师", status: "正常",
      summary: "钱伟长图书馆入选上海市第二批“大思政课”实践教学基地的校方报道。",
      excerpt: "2024年12月，上海大学钱伟长图书馆入选上海市第二批“大思政课”实践教学基地。该馆自2019年5月建成开放以来，先后获评全国首批科学家精神教育基地、上海市爱国主义教育基地、民盟中央传统教育基地，开设《走进科学家书房》等特色课程，通过主题展览、主题图书出版构建多维育人矩阵。",
    },
    {
      id: "m-kc4", tags: ["校本科创", "案例文本"], title: "上海大学“强国有我”思政案例库课题组案例文本（4篇）", kind: "资料包",
      source: "上海大学马克思主义学院", sourceUrl: "",
      publishedAt: "2026-05-01", collectedAt: "2026-05-01", level: 2, credibility: "high",
      scope: "经授权的硕博公共思政教师、案例管理员", status: "正常",
      summary: "课题组编写的四篇校本案例全文：钱伟长图书馆、《智能控制》课程、中瑞先进技术研究院、任新振医工交叉。",
      excerpt: "含《钱伟长图书馆——科学家精神的大思政课堂》《〈智能控制〉：高挑战项目牵引新工科育人》《微电子赋能生物医药——中瑞先进技术研究院的科教融合实践》《工学+医学=？——任新振的“医工交叉”科技报国路》四篇案例文本（Word），供深度教学与申报参考。",
    },
    {
      id: "m-zrjs", tags: ["校本科创", "交叉创新"], title: "中瑞先进技术研究院建设纪实（校内科创纪实）", kind: "文档",
      source: "上海大学科研管理部", sourceUrl: "",
      publishedAt: "2025-11-20", collectedAt: "2026-04-15", level: 1, credibility: "high",
      scope: "校内教师", status: "正常",
      summary: "研究院在微电子赋能生物医药方向的交叉学科建设、国际合作机制与育人体系纪实。",
      excerpt: "研究院以“微电子赋能生物医药”为核心理念，构建“科研—教学—实践”三位一体培养体系，建立中瑞两国在微电子与生物医药领域的长效合作机制，在医疗影像、生物传感等方向形成系列交叉创新成果。",
    },
    {
      id: "m-rxzjz", tags: ["校本科创", "医工交叉"], title: "任新振团队医工交叉研究简报", kind: "文档",
      source: "上海大学科研管理部", sourceUrl: "",
      publishedAt: "2026-02-10", collectedAt: "2026-04-15", level: 1, credibility: "high",
      scope: "校内教师", status: "正常",
      summary: "任新振团队在医工交叉方向的研究进展、研究生培养经验与成果转化情况简报。",
      excerpt: "团队在工学与医学的交叉地带形成独特研究方向，为医疗技术的精准化、智能化提供工程学支撑，并为医工交叉方向研究生培养提供可借鉴的指导经验。",
    },
    {
      id: "m-zmt", tags: ["社会热点", "待甄别"], title: "“一堂课刷屏”背后的思政课流量逻辑", kind: "链接",
      source: "某教育类自媒体公众号", sourceUrl: "https://mp.weixin.qq.com/",
      publishedAt: "2026-03-02", collectedAt: "2026-03-05", level: 0, credibility: "low",
      scope: "全体教师（非权威来源，引用前需核验）", status: "来源失效",
      summary: "自媒体对思政课“出圈”现象的观察文章，原链接已失效，仅保留采集时副本供甄别。",
      excerpt: "文章以多篇网络热帖为例，讨论思政类内容在社交媒体传播中的标题化、情绪化倾向，部分数据未标明出处，观点仅供参考。原页面已删除，无法回溯核实。",
    },
  ],

  // 权威来源白名单（域名）
  whitelist: ["gov.cn", "moe.gov.cn", "people.com.cn", "xinhuanet.com", "news.cn", "qstheory.cn", "shu.edu.cn"],

  // ---------------------------------------------------------- 演示工作稿
  draftCases: [
    {
      id: "c-draft-1",
      title: "供应链中断情境下的抉择：科技自立自强思想实验",
      typeId: "ct-thought", audience: "grad", course: "自然辩证法概论",
      purpose: "日常授课", ownerId: "u-chen", status: "draft",
      summary: "以关键技术供应链中断为思想实验情境，组织研究生研讨科技自立自强的方法论内涵。",
      theoryPoints: ["科技自立自强", "科学技术创新观", "风险评价与决策"],
      blocks: [
        { kind: "h2", text: "情境设定与前提假设" },
        { kind: "p", text: "某高端制造团队长期依赖进口精密传感部件。假设国际贸易环境突变，关键部件供应中断，且短期内无法通过第三渠道获得。团队手头有一批处于不同研发阶段的国产替代方案，成熟度参差不齐。" },
        { kind: "p", text: "情境设定三条前提：一是供应中断周期不明；二是团队承担的在研项目有明确交付节点；三是国产替代方案的性能指标与进口件存在可量化差距。" },
        { kind: "h2", text: "矛盾冲突的多方立场" },
        { kind: "p", text: "项目方主张“先用再说”，接受性能折损以保交付；质量方坚持标准不妥协，宁可延期；团队内部青年成员提出借机制定国产件迭代路线，但面临当期考核压力。" },
        { kind: "p", text: "三类立场背后是短期交付、质量标准与长期能力安全之间的价值排序问题。" },
        { kind: "h2", text: "讨论路径与引导设计" },
        { kind: "h2", text: "理论回应与方法论提升" },
        { kind: "p", text: "科学技术的发展动力既来自体系内部的逻辑展开，也来自社会需求的外部牵引。供应链中断情境把“需求牵引”推向极端，迫使讨论者区分“被迫替代”与“主动布局”两种创新路径。" },
      ],
      citations: [
        { target: "kn-06-01", note: "科学技术创新观——创新路径与动力分析" },
        { target: "kn-05-04", note: "科学技术的风险评价与决策——供应中断的风险评估框架" },
      ],
      kit: { design: "", discussion: ["如果你来拍板，当期交付与国产替代如何排序？给出你的决策依据。", "“被迫替代”与“主动布局”在资源配置上有何本质差异？"], ppt: [], reflist: [] },
      annotations: [
        { id: "an-1", kind: "ai", status: "pending", section: 4,
          quote: "项目方主张“先用再说”",
          text: "建议在“矛盾冲突”一节补充短期损失与长期安全的量化讨论支架（如交付违约金、迭代周期估算），便于研讨课分组辩论。", author: "Copilot", lowRisk: false, createdAt: "2026-07-15 10:22" },
        { id: "an-2", kind: "risk", status: "pending", section: 1,
          quote: "国际贸易环境突变",
          text: "情境表述建议去具体化：避免影射特定国家与企业，改为“假设供应环境发生不利变化”一类中性表述。", author: "风险检查", lowRisk: false, createdAt: "2026-07-15 10:23" },
        { id: "an-3", kind: "admin", status: "resolved", section: 8,
          quote: "科学技术的发展动力",
          text: "理论回应部分应引用教材原文并标注章节出处，退回后已补充。", author: "周正", lowRisk: false, createdAt: "2026-07-12 16:40" },
        { id: "an-4", kind: "ai", status: "outdated", section: 1,
          quote: "某高端制造团队长期依赖进口精密传感部件",
          text: "原批注针对旧版情境表述，正文改写后锚点失效。", author: "Copilot", lowRisk: false, createdAt: "2026-07-11 09:05" },
        { id: "an-5", kind: "ai", status: "pending", section: 2,
          quote: "三是国产替代方案的性能指标与进口件存在可量化差距",
          text: "标点与格式：建议统一“一是/二是/三是”后的停顿符号；另“可量化差距”建议给出示例量级。", author: "Copilot", lowRisk: true, createdAt: "2026-07-15 10:24" },
      ],
      versions: [
        { id: "v-1", label: "工作稿 v1", at: "2026-07-10 14:00", note: "初稿完成" },
        { id: "v-2", label: "提交版 v2", at: "2026-07-12 15:30", note: "提交审核，因理论引用未标注出处被退回" },
        { id: "v-3", label: "工作稿 v3（当前）", at: "2026-07-15 10:30", note: "按退回意见修订中" },
      ],
      createdAt: "2026-07-08 09:00", updatedAt: "2026-07-15 10:30",
    },
    {
      id: "c-pending-1",
      title: "生成式人工智能进课堂：使用边界与课堂治理研讨",
      typeId: "ct-society", audience: "grad", course: "自然辩证法概论",
      purpose: "集体备课", ownerId: "u-chen", status: "pending",
      summary: "围绕学生使用生成式人工智能完成作业的现象，研讨技术使用边界与课堂治理方案。",
      theoryPoints: ["科学技术的异化及其反思", "科学技术与社会变迁", "学术规范"],
      blocks: [
        { kind: "h2", text: "热点缘起与传播过程" },
        { kind: "p", text: "本学期多门课程发现学生作业中存在生成式人工智能代写痕迹，相关讨论在教师群内持续发酵。部分教师主张全面禁止，部分教师主张引导使用。" },
        { kind: "p", text: "同类讨论在多所高校出现，教育主管部门尚未出台统一细则，各校处于各自探索阶段。" },
        { kind: "h2", text: "利益相关方与价值冲突" },
        { kind: "p", text: "学生关注学习效率与评价公平；教师关注能力培养的真实性与学术诚信；教学管理部门关注规范的可执行性与舆情风险。" },
        { kind: "h2", text: "治理实践与制度分析" },
        { kind: "h2", text: "理论回应与研讨问题" },
        { kind: "p", text: "技术应用的价值负荷问题提示我们：工具本身并非中立，使用边界的划定本质上是教育目标的再确认。" },
      ],
      citations: [
        { target: "kn-05-04", note: "科学技术的异化及其反思" },
        { target: "kn-05-02", note: "科学技术与社会变迁" },
        { target: "m-zmt", note: "舆情现象参考（待核实来源，仅作现象佐证）" },
      ],
      kit: { design: "", discussion: [], ppt: [], reflist: [] },
      annotations: [],
      versions: [
        { id: "v-1", label: "工作稿 v1", at: "2026-07-14 11:00", note: "初稿" },
        { id: "v-2", label: "提交版（待审）", at: "2026-07-16 09:20", note: "提交审核" },
      ],
      createdAt: "2026-07-13 15:00", updatedAt: "2026-07-16 09:20",
      submittedAt: "2026-07-16 09:20",
    },
  ],

  // ---------------------------------------------------------- 已发布案例的类型与引用映射
  // key 为 examples 文件名前缀
  publishedMeta: {
    "02_": { typeId: "ct-school", audience: "ug", course: "习近平新时代中国特色社会主义思想概论",
      citations: [{ target: "kn-06-02", note: "科学技术人才观" }, { target: "kn-05-02", note: "科学技术与社会变迁" },
                  { target: "m-qwllib", note: "场馆入选与育人矩阵的事实来源" }, { target: "m-kxjsh", note: "科学家精神的政策依据" }],
      likes: 46, publishedAt: "2026-06-02" },
    "05_": { typeId: "ct-tech", audience: "embed", course: "智能控制",
      citations: [{ target: "kn-04-01", note: "问题意识与问题导向" }, { target: "kn-06-01", note: "科学技术创新观" },
                  { target: "m-kcsz", note: "课程思政建设的政策依据" }],
      likes: 38, publishedAt: "2026-06-02" },
    "08_": { typeId: "ct-tech", audience: "grad", course: "微电子科学与工程导论",
      citations: [{ target: "kn-04-10", note: "移植、交叉与跨学科研究方法" }, { target: "kn-05-01", note: "科学技术与经济转型" },
                  { target: "m-ershida", note: "交叉学科建设的战略要求" }, { target: "m-zrjs", note: "研究院建设纪实（校内）" }],
      likes: 31, publishedAt: "2026-06-02" },
    "11_": { typeId: "ct-figure", audience: "ug", course: "习近平新时代中国特色社会主义思想概论",
      citations: [{ target: "kn-04-10", note: "移植、交叉与跨学科研究方法" }, { target: "kn-06-01", note: "科学技术创新观" },
                  { target: "m-ershida", note: "健康中国与交叉学科战略" }, { target: "m-rxzjz", note: "团队研究简报（校内）" }],
      likes: 52, publishedAt: "2026-06-02" },
  },
};
