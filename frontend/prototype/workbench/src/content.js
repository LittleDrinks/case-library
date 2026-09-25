// 初始文档内容（ProseMirror JSON）。中文真实教学内容：钱伟长课程思政案例。
// 修订预览全部由 decoration 层渲染，不写入正文结构。
export const initialDoc = {
  type: "doc",
  content: [
    { type: "paragraph", content: [{ type: "text", text: "1931 年，十九岁的钱伟长以中文、历史双百的成绩考入清华大学历史系。入学三天后，“九一八”事变爆发，他做出了改变一生的决定：" },
      { type: "text", text: "我不知道什么专业是热门的，我只知道国家需要什么，我就做什么" },
      { type: "text", text: "。此后他毅然弃文从理，转入物理系，尽管入学时物理仅考了个位数分数。" }] },
    { type: "heading", attrs: { level: 2 }, content: [{ type: "text", text: "一、国家的需要就是我的专业" }] },
    { type: "paragraph", content: [{ type: "text", text: "在上海大学执教期间，钱伟长反复向学生强调，" },
      { type: "text", text: "科学家最重要的品质是爱国" },
      { type: "text", text: "。他认为，个人的学术选择只有嵌入国家发展的坐标系，才能获得持久的意义。这一判断在他身上体现得尤为彻底：从物理学到力学，从弹性力学到中文信息处理，他数度转向，每一次都追随国家急需。" }] },
    { type: "paragraph", content: [{ type: "text", text: "本案例选取钱伟长 1931 年的转系决定与晚年办学实践为两条主线，引导学生在具体历史情境中理解“强国何以有我”这一命题。教学中可结合校史馆讲解词与《教育和教学问题的思考》节选，组织学生对比个人志趣与国家需要在不同时代的表现形式。" }] },
    { type: "heading", attrs: { level: 2 }, content: [{ type: "text", text: "二、既做科学家，又做教育家" }] },
    { type: "paragraph", content: [{ type: "text", text: "1983 年，钱伟长出任上海工业大学校长，提出拆除“四堵墙”——学校与社会之墙、教学与科研之墙、各学院各专业之墙、教与学之墙。他晚年" },
      { type: "text", text: "既做科学家，又做教育家" },
      { type: "text", text: "，把“自强不息、先天下之忧而忧”的校训精神落实到培养方案、课程体系与学生评价的每一个环节。" }] },
    { type: "heading", attrs: { level: 2 }, content: [{ type: "text", text: "三、课堂讨论设计" }] },
    { type: "bulletList", content: [
      { type: "listItem", content: [{ type: "paragraph", content: [{ type: "text", text: "讨论一：如果钱伟长生活在今天，他会选择哪些“国家需要”的专业方向？" }] }] },
      { type: "listItem", content: [{ type: "paragraph", content: [{ type: "text", text: "讨论二：“国家的需要就是我的专业”与个人自由发展是否矛盾？请结合案例材料论证。" }] }] },
      { type: "listItem", content: [{ type: "paragraph", content: [{ type: "text", text: "讨论三：上海大学校训中“先天下之忧而忧”如何体现在具体办学制度中？" }] }] },
    ] },
    { type: "paragraph", content: [{ type: "text", text: "课后作业要求学生访谈一位本校教师，记录其研究方向与国家需求的关联，形成八百字短文，下节课交流。" }] },
  ],
};
