# PDF 资料包、解析与多模态 RAG：一手来源研究

查阅日期：2026-10-01。范围：数字版与扫描版 PDF、CPU 本地解析、可选外部 OCR/视觉 API、管理员维护的多文件资料，以及这些内容如何进入检索和 AI 阅读。本文是方案研究，不是实现验收；没有安装依赖、运行模型、测服务器性能、读取凭据或向外部服务发送平台 PDF。

## 结论与证据边界

可以把一份资料做成一个管理员维护的条目，里面保存原 PDF、阅读用 Markdown、插图及其他附件。**资料条目是一份可被选入案例的内容，文件是它的不同组成部分或表示形式**。用户已确认采用“一条资料、多份文件”；它是本项目的产品选择，不是 RAG 规定的文件格式。已有文献管理产品也区分条目、附件和笔记：[Zotero 官方条目与附件说明](https://www.zotero.org/support/adding_items_to_zotero#standalone_attachments_and_parent_items)。

需要纠正“OpenDataLoader-PDF 只能处理数字版”的判断：它的本地快路径与混合模式不同，官方明确提供扫描件 OCR。数字版可先走本地 CPU；扫描件与复杂表格可使用 Docling 后端；视觉模型或外部 API 是进一步处理疑难内容的候选，不能承诺本服务器已跑通。[OpenDataLoader 官方 README](https://github.com/opendataloader-project/opendataloader-pdf/blob/9bae9a6aea808fe6e2e659ccd3a5c5193cedc871/README.md)

多模态 API 可以接收 PDF 页面截图；部分厂商也能直接接收 PDF。**具备这些厂商能力，不代表本项目当前配置的模型和纯文本调用路径具备同样能力**。本文只核验厂商公开契约，现有 provider 的实际接入能力需由本项目代码调查及之后的真实调用验证确定。

建议首版先完成资料包、原文件阅读、可追溯的阅读文本和管理员整理；采用 CPU 优先的异步解析；保留对疑难页调用外部 OCR/视觉 API 的接口。全库页图向量检索作为有真实查询证据之后的扩展。后两项是成本与当前产品范围的判断，不是行业统一标准。

用户补充后，本次重点是 **Xiaomi-OCR-0** 和阿里 **Logics-Parsing** 候选：小米确有官方 CPU 示例，不能未经测量判断服务器跑不动；Logics 当前 V3 官方路径为单 GPU、多页结构解析。首版允许管理员在其他机器解析并导入资料包，就能利用这些模型而无需平台服务器常驻它们。具体证据见下面“用户补充的 Xiaomi-OCR-0 与阿里候选”。

本轮已确认的产品范围：管理员可主动调用外部 OCR，也可导入其他机器解析出的正文与图片；原件先开放，正文独立显示处理状态；原文与整理／解读分开；自动解析正文经管理员确认后才供 AI 使用。具体供应商、解析器和性能目标尚未选定；本文其余工程建议不因此全部成为已批准规格。

用户随后要求扩大资料包讨论：可能保存原 PDF＋解析 PDF，也可能管理同一本书的多个版次。上述确认不要求所有资料都具有 Markdown，也不决定一个包等于一本书、一个版次还是一组独立资料。当前先澄清粒度，默认阅读与 AI 输入暂缓确定。

## 1. 已核验的解析能力

| 方案 | 官方可确认的行为 | 不能由此承诺的效果 |
| --- | --- | --- |
| OpenDataLoader-PDF 本地模式 | Java 的规则解析输出 Markdown、结构 JSON 等；JSON 保留元素页码与坐标；不要求 GPU。标准数字版是官方建议的使用场景。[固定版本 README](https://github.com/opendataloader-project/opendataloader-pdf/blob/9bae9a6aea808fe6e2e659ccd3a5c5193cedc871/README.md) | 抽出字不代表扫描件 OCR、图表含义理解或复杂表格已经解决；作者吞吐量不能作为本校服务器性能。 |
| OpenDataLoader-PDF 混合模式 | `--hybrid docling-fast` 对接 Docling；`auto` 分流简单与复杂页，`full` 全部送后端；扫描件后端可启用 `--force-ocr`，可指定 CPU 与 OCR 引擎。[官方混合模式](https://opendataloader.org/docs/hybrid-mode) | CPU 可以执行不等于中文长教材能在可接受时间内完成；需要实测模型下载、内存峰值、页耗时和失败情况。 |
| Docling | 官方支持扫描 PDF/图片 OCR、文本、表格、图片及统一结构表示；代码可本地执行。[官方仓库](https://github.com/docling-project/docling/blob/d6f03078ad364108df3e7e82e8f0dcc3fd7f39ea/README.md) | 解析器代码许可与各模型许可不同；默认参数和 OCR 引擎会随版本变化。不能只锁主包而忽略模型与 OCR 依赖。 |
| Docling CPU/OCR 配置 | CLI 文档列出 `--device cpu`、多个 OCR 引擎、语言和页范围；OCR 语言既可能是引擎自身代码，也可通过 `iso:` 前缀使用 BCP-47。[官方 CLI](https://docling-project.github.io/docling/reference/cli/) | 不同引擎的“中文”参数不能随意互换；尚未核验本项目实际装包版本的帮助输出。 |
| PaddleOCR-VL | 官方模型卡介绍 0.9B 文档视觉模型，涉及文字、表格、公式、图表；示例包含 CPU 的设备分支，但 Transformers 示例明确只做元素识别，完整页解析另用官方管线。[官方模型卡](https://huggingface.co/PaddlePaddle/PaddleOCR-VL) | 不能把一个裁剪区域的 CPU 示例当作整本教材在小服务器上的性能证明。该模型是比较候选，不能代指用户补充的小米模型。 |
| GLM-OCR | 官方介绍 0.9B 模型，提供 MaaS 与自托管路径；分离客户端可无 GPU，完整自托管示例使用 GPU 服务。[官方仓库](https://github.com/zai-org/GLM-OCR/blob/cef4d0ea120d1741f5cefe8985eee45f6c8eff1d/README.md)、[官方自托管说明](https://github.com/zai-org/GLM-OCR/blob/cef4d0ea120d1741f5cefe8985eee45f6c8eff1d/examples/self-host/README.md) | “客户端无需 GPU”不等于模型在客户端 CPU 本地运行。配置中的 layout CPU 选项也只描述版面模型的位置。[官方配置](https://github.com/zai-org/GLM-OCR/blob/cef4d0ea120d1741f5cefe8985eee45f6c8eff1d/glmocr/config.yaml) |

### 用户补充的 Xiaomi-OCR-0 与阿里候选

用户后续明确了 `xiaomi-OCR-0`，并提到“阿里也有一个 logis-parser 什么的”。可以确认前者有同名官方模型；后者找到的最接近官方项目名是 **Logics-Parsing**，但用户未指定 v1、v2、V3 或 Omni，下面以当前 **V3** 调查，不能把这个版本猜测当用户已经确认的选型。

| 具体候选 | 图像/PDF 与输出 | CPU/GPU 与托管能力边界 |
| --- | --- | --- |
| Xiaomi-OCR-0 | 作者论文称 0.8B；官方权重开源，模型卡为 Apache-2.0，提供整页图像转 Markdown、OTSL 表格、LaTeX 公式以及 KIE/VQA 示例。[原论文](https://arxiv.org/abs/2609.36136)、[固定版本官方模型卡](https://huggingface.co/SeerRay-Lab/Xiaomi-OCR-0/blob/e4d1c4a6804bd9ef342b93d705a73af003e2ef4e/README.md) | 模型卡示例明确支持 `cuda`、`mps`、`cpu`，CPU 使用 float32；因此不能断言必须 GPU。官方服务化默认示例走 GPU 的 SGLang/vLLM，尚无本服务器可接受性能的证据。 |
| Xiaomi-OCR-0 的 PDF 管线 | 官方 demo 支持 PDF 渲染后逐页处理，整页模式与 PP-DocLayoutV3 区域模式；OTSL 经后处理转换为 Markdown 中的 HTML 表格。[官方 demo 说明](https://github.com/SeerRay-Lab/Xiaomi-OCR-0/blob/6499f6c8c65081e41830cd7d5740ed82dfabf0bf/demo/README.md) | 区域模式额外需要布局运行时；不等于 Logics V3 宣称的跨页递推结构模型。安装说明明确这里是本机运行，所述工作流无托管 OCR 服务。[官方安装说明](https://github.com/SeerRay-Lab/Xiaomi-OCR-0/blob/6499f6c8c65081e41830cd7d5740ed82dfabf0bf/INSTALL.md) |
| Logics-Parsing-V3 | 官方称 0.8B；2026-09-22 发布，支持图片、PDF、多页图片目录；输出 `markdown.md`、`hierarchy.md`、`raw_output.dsl`、`result.json`，多页解析使用结构状态递推。[固定版本官方 README](https://github.com/alibaba/Logics-Parsing/blob/d75d42dbd92c518a4def19ac5895792828138d35/README.md) | 官方脚本标注单 GPU vLLM，使用 BF16 和 GPU 内存参数；文档速度测试使用 H100，不能外推 CPU 或小服务器。[固定版本推理脚本](https://github.com/alibaba/Logics-Parsing/blob/d75d42dbd92c518a4def19ac5895792828138d35/inference_v3.py) |

小米 Hugging Face 项目页的源码配置为 `sdk: static`，所以“项目页可打开”不是“有在线 OCR API”的证据。[项目页配置](https://huggingface.co/spaces/SeerRay-Lab/Xiaomi-OCR-0/blob/513f8fd5b052e65c0d6c455e76d4cee7ac1411b6/README.md)

Logics V3 官方提供下载权重的入口；其 Hugging Face 模型页本次显示没有托管 Inference Provider。已读官方仓库和模型卡未找到正式商用托管该具体模型的 API 契约；这只是调查范围内未找到，不声称所有阿里服务都没有。百炼视觉聊天 API、第三方 GGUF 包、演示网页都不能自动视为 Logics 官方托管 API。[官方权重与模型卡](https://huggingface.co/Logics-MLLM/Logics-Parsing-V3)、[仓库许可](https://github.com/alibaba/Logics-Parsing/blob/d75d42dbd92c518a4def19ac5895792828138d35/LICENSE)

Hugging Face 公共元数据实际统计小米权重约 0.873B、Logics V3 约 0.853B，页面四舍五入可能显示 0.9B，不是发现了另一版大模型。[小米模型元数据](https://huggingface.co/api/models/SeerRay-Lab/Xiaomi-OCR-0)、[Logics 模型元数据](https://huggingface.co/api/models/Logics-MLLM/Logics-Parsing-V3)。按小米示例 CPU float32 计算，单权重理论就约 3.5 GB（十进制）；这是一项计算推论，不是实测峰值，还未包含运行时、激活、PDF 渲染和布局模型。

因此资料管理首版可以支持**在管理员自己的其他机器离线解析，再导入原 PDF＋Markdown＋图片/结构结果**，平台服务器负责保存、阅读、权限和检索，无需常驻小米或 Logics 模型。要自动化时再比较本机小米 CPU、小批异步 GPU worker 或已核验的外部 OCR API。离线导入也应核对原件校验值、页码和图片链接；没有坐标时保留页级出处，不能伪造块坐标。

### 版本与参数核验

本次通过 GitHub 公共 API 核对的 main 提交为：OpenDataLoader `9bae9a6aea808fe6e2e659ccd3a5c5193cedc871`（2026-10-01），Docling `d6f03078ad364108df3e7e82e8f0dcc3fd7f39ea`（2026-09-30），GLM-OCR `cef4d0ea120d1741f5cefe8985eee45f6c8eff1d`（2026-04-21）。这是查阅锚点，不是已选择的生产依赖，也不表示已安装对应发行包。

本轮补充：小米代码提交 `6499f6c8c65081e41830cd7d5740ed82dfabf0bf`（2026-09-30），权重/model card revision `e4d1c4a6804bd9ef342b93d705a73af003e2ef4e`；Logics 代码提交 `d75d42dbd92c518a4def19ac5895792828138d35`（2026-09-21），V3 权重 revision `e6d324e30e0f64f1a0dfb652efcb83a4b244591e`。只读取公共文档/元数据，没有下载模型权重。部分新发布小米 Hugging Face 页面无法经浏览工具打开，本次以官方公开 raw 文件和公共 API 读取模型卡/项目页配置，并以可访问的官方 GitHub 仓库交叉核对。

OpenDataLoader 官网与 main README 已有不同细节，例如 RapidOCR 的语言示例、图片描述输出字段。官网示例仍写 `description`，固定提交 README 展示 `alt`、`alt_source`。因此接入必须以选定发行版的实际输出、schema 和帮助参数验证，本文不提供假定所有版本通用的复制即用命令。[官网混合模式](https://opendataloader.org/docs/hybrid-mode)、[固定版本 README](https://github.com/opendataloader-project/opendataloader-pdf/blob/9bae9a6aea808fe6e2e659ccd3a5c5193cedc871/README.md)

## 2. 图表、插图与出处不能只靠 Markdown

Markdown 不是资料必填文件。作为另一条处理路线，OCRmyPDF 能为扫描 PDF 加文字层，输出可搜索、复制的 PDF；原 PDF 与处理后的 PDF 可以同时保留。官方也说明 OCR 文字层不自动提供段落、标题等文档结构，且识别与阅读顺序可能出错，因此“能搜字”不等于“已具备准确的结构化正文”。[OCRmyPDF 官方介绍](https://ocrmypdf.readthedocs.io/en/latest/introduction.html)

OpenDataLoader 结构 schema 明确使用从 1 开始的 `page number`，bbox 为 `[left, bottom, right, top]`。它也区分表格行列、跨度、图片与文本等结构。不能只存一段 Markdown 后期待准确反查原页。[固定版本 schema](https://github.com/opendataloader-project/opendataloader-pdf/blob/9bae9a6aea808fe6e2e659ccd3a5c5193cedc871/schema.json)

DoclingDocument 保留文本、表格、图片、层级、出处以及“存在时”的布局坐标；这个“存在时”意味着不是所有后端结果都一定有坐标。官方图片导出示例显式开启 `generate_page_images`、`generate_picture_images` 并导出页图、表格或图片。[官方结构说明](https://docling-project.github.io/docling/concepts/docling_document/)、[固定版本导出示例](https://github.com/docling-project/docling/blob/d6f03078ad364108df3e7e82e8f0dcc3fd7f39ea/docs/examples/export_figures.py)

据此推荐保留四类产物：原文件、结构 JSON、阅读 Markdown、需要的页图/图片资产。JSON 服务于出处映射；Markdown 服务于阅读和文本检索；页图供核对与视觉理解。图片 Markdown 相对链接应解析到资料包内的附件，页面坐标需记录坐标原点、单位与渲染尺寸。没有坐标的结果允许只有页级出处，不捏造词级或表格单元格坐标。这些是本项目的派生设计。

对图表的自然语言描述应标“机器生成”，并保留原图。抽出了“图 3”图片不代表读懂轴标签和数值；管理员核对政策条文、日期、数字、表格标题的成本需要计入验收。OpenDataLoader 官方还说明其图片描述采用 SmolVLM-256M，中文输出及复杂图表精确数值存在适用限制，默认不宜把此描述当可信正文。[官方混合模式的图片描述说明](https://opendataloader.org/docs/hybrid-mode)

## 3. API 是否能接收 PDF 截图

| 官方 API 路线 | 已核验内容 | 本项目意义 |
| --- | --- | --- |
| 阿里百炼 Qwen-OCR | 专门的 OCR 模型接口接收图片 URL 或 Base64，提供文字识别、文档解析、表格等任务；提供 OpenAI 兼容与 DashScope 请求方式。[官方 OCR API 文档](https://help.aliyun.com/en/model-studio/qwen-vl-ocr-api-reference) | PDF 应先渲染成页图再识别。它与开源 Logics-Parsing 项目不同，不能将此接口当作托管 Logics V3 的证据。 |
| 百炼视觉模型的 OpenAI 兼容接口 | Chat Completions 中的 `content` 可含文本与 `image_url`；官方另提供 Base64 图片的 data URL 示例。[兼容接口](https://help.aliyun.com/zh/model-studio/qwen-vl-compatible-with-openai)、[视觉理解与 Base64](https://help.aliyun.com/zh/model-studio/vision) | 本地将 PDF 页渲染为受支持图片后，可以按该接口送入支持图像的具体模型。模型支持、图片大小、计费和地区配置需另核验。 |
| Claude 原生 API | 图像可使用 Base64、URL 或 Files API；PDF 输入会同时提供提取文字与逐页图像用于分析。[官方图像输入](https://platform.claude.com/docs/en/build-with-claude/vision)、[官方 PDF](https://platform.claude.com/docs/en/build-with-claude/pdf-support) | 可以直接用 PDF 或页截图，但消息契约属于原生 API；不能据此假定任意 Chat Completions 网关接受 PDF。 |
| Gemini 原生 API | 官方支持 PDF 的文字和视觉内容理解，包含图表、表格、图像；支持文件上传或直接输入。[官方文档理解](https://ai.google.dev/gemini-api/docs/document-processing) | 可做整份/分段文档理解，不等同于一个永久、可引用的检索索引。 |
| Mistral OCR API | 专用 `/v1/ocr` 接收文档或图片，结果按页返回 Markdown、图像、表格等，支持结构块 bbox；不是普通聊天端点。[OCR 使用文档](https://docs.mistral.ai/studio/document-processing/basic_ocr)、[API 契约](https://docs.mistral.ai/api/endpoint/ocr) | 可作为无需本地视觉模型的解析候选。API 参数中的页序从 0 开始，应转换成产品呈现的原 PDF 页码。 |

以上能力均来自公开文档，未调用 API。没有查询或复制本项目的 API key、网关地址、当前模型名，也未确认任一候选供应商在学校网络可达。

按需把检索命中的原页截图送给视觉模型，是可实施的组合思路。送多少页、分辨率与调用模型需要以小样本测准确性和成本；不应默认每次问答把整本教材全部截图外发。用户已确认首版管理员主动调用外部 OCR 的入口，这不等于批准聊天请求自动把所有页图交给任意供应商。本文没有实际外发文件。

## 4. 管理员维护的“资料包”应有哪些文件角色

“一条资料多份文件”已确认；下表是具体角色和出处的细化建议。**检索结果仍显示一条资料，不把 PDF、Markdown 和每张插图当作三种重复资料。** 资料类型（教材、政策、时政新闻等）与文件格式/角色分开；一条时政新闻同样可以包含来源 URL、保存的原文、阅读文本和配图。

| 文件/内容角色 | 用途 | 建议规则 |
| --- | --- | --- |
| 原始文件 | PDF 原件、保存的原始 HTML 或其他主要依据 | 一版是否含上册、下册等多个组成文档继续确认；不因解析或纠错覆盖旧字节。 |
| 处理后 PDF | 增加文字层、清理页面或重新排版的 PDF | 记录来自哪个原件及处理方法；与原件分别保留。若改变分页，不假定页码与原件一致。 |
| 自动提取正文 | PDF/OCR 生成的 Markdown 与结构 JSON | 记录来自哪一个原件及哪个处理运行；允许重试重建，不能覆盖人工整理。 |
| 管理员整理正文 | 核对后修正的 Markdown | 与原件版本绑定，注明人工整理；若删节/改写，不能显示为逐字原文。 |
| 摘要/学习提示 | 阅读入口中的简述或说明 | 单独标明，不能作为原文的唯一替代输入，也不假装覆盖整份 PDF。 |
| 插图、表格、页图 | Markdown 内资源、出处核对、视觉阅读 | 绑定文件 ID、原件版本及来源页；插图与整页截图分别识别。 |
| 补充附件 | 同期资料、数据表、解读文件等 | 用户能看见附件角色与标题，不应默认把所有附件拼成一篇正文。 |

这不要求后台真的创建一个 ZIP，也不要求每次上传预制目录。可以在条目页面逐个上传并指定角色；整理完成后统一发布这个条目版本。原件与处理后 PDF 同时存在并不要求额外上传 Markdown，提取正文可以是平台生成的读取产物；具体支持范围仍待实现验证。若以后需要完整导入/导出，可借鉴“文件清单＋校验值”的保存方法；BagIt 是一个现成文件打包规范，但它不定义本平台的正文、附件或权限角色，首版无需强制使用。[RFC 8493 BagIt](https://www.rfc-editor.org/rfc/rfc8493)

版本一致性建议：一版资料明确列出原文件、正文、附件及校验值；替换主 PDF 先创建待整理的新版本，旧版继续供已有案例核对。案例引用固定版本遵循已接受的 [统一案例资料区与固定版本引用](https://github.com/LittleDrinks/case-library/issues/158)，本轮未重新打开此决定。管理员校对 Markdown 时，正文版本和出处映射同时变化；如果新增内容缺乏页码，应展示“管理员补充说明”，不能强行映射到原页。包内共用访问范围和版本已确认，具体文件清单和校验实现属于后续设计；本文没有修改现有业务模型。

## 5. RAG 的三条路线与局限

“RAG 标准做法”并不存在一个必须使用的 PDF 模型或文件结构。下面分别列出成熟厂商模式及论文证据，并据此判断本项目的适用顺序。

| 路线 | 处理与读取 | 证据及限制 | 本项目建议 |
| --- | --- | --- | --- |
| 结构化文本检索 | PDF/OCR → 正文/表格结构 → 按标题、段落分块 → 文本检索 → 原文引用 | Azure 官方模式用版面分析后得到的 Markdown、标题、段落与表格改善分块；不等于纯文本能回答所有视觉问题。[结构分块](https://learn.microsoft.com/en-us/azure/search/search-how-to-semantic-chunking)、[Document Intelligence RAG](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/concept-retrieval-augumented-generation?view=doc-intel-4.0.0) | 首版优先。数字版文字与管理员整理正文能先覆盖多数教材、政策文字查询；不要求立即上向量库。 |
| 文本检索＋原图阅读 | 文本或图像说明定位候选页 → 按出处取得原页/图 → 视觉模型回答 | 文档解析的页码、图片出处与官方视觉 API 提供组成能力；组合效果是待验证的工程推论，没有本项目实测。 | 下一步优先。回答图表题时使用原图，图像说明只帮助查找。未找到候选页时明确无法定位，不能假装看过全书。 |
| 全页视觉检索 | PDF 每页图片 → 视觉模型产生多向量表示 → 查询匹配 → 页图交给视觉模型 | ColPali 原始论文展示页图多向量检索，评估目标是视觉文档检索，不是本校教材生成答案准确率。[原论文](https://arxiv.org/abs/2407.01449) | 作为扩展候选。需要额外模型推理、多向量存储/检索和本校样本评估，不能仅靠当前纯文本 embedding 或聊天 API 自然实现。 |

ColPali 官方仓库当前已将 `colpali-engine` 标为 deprecated，建议新项目迁移到 Sentence Transformers 的多向量支持。即使以后采用此路线，也不应从旧教程直接选取安装包。[固定版本官方仓库](https://github.com/illuin-tech/colpali/blob/97487f8871ff4d5d2284411fe61bdcd2cfe99894/README.md)

检索可用性、正文校对和阅读权限是三回事。平台建议只把当前允许 AI 使用的正文版本纳入索引；检索时按用户可读范围过滤，取原件、Markdown 或页图时再次检查读取权。查询阶段按文档权限过滤是官方企业检索已有的做法，但这里应实现本项目自己的校内资格与案例权限，不照搬 Azure 的身份系统。[Azure 文档权限概览](https://learn.microsoft.com/en-us/azure/search/search-document-level-access-overview)

## 6. CPU 优先的分阶段管线建议

### 阶段一：资料可用，管理员能够补齐

1. 上传原文件，先保存原件、资料元数据及权限；原件可阅读/下载不依赖全文解析完成。
2. 管理员可以追加 Markdown 与图片附件，也可导入在其他机器用小米/Logics 等解析的产物，并指定“提取正文 / 整理正文 / 摘要 / 补充附件”，不用等待平台服务器部署视觉模型。
3. 数字 PDF 先用 OpenDataLoader 本地路径提取；保留 JSON、Markdown 及所需插图。异常空白或缺页进入“需核对”，不标全文就绪。
4. 首版不默默把所有原文、OCR 与人工正文重复入库；原文与整理／解读分别标识。用户已确认自动正文先待核对，由管理员确认后供 AI 使用；默认检索哪些正文角色仍待回答。

### 阶段二：扫描件、表格、图文缺口

1. 提供本地 CPU 的 Docling/OCR 任务；中文引擎与参数按固定版本小样本核验后选取。初始并发建议为 1，并限制单次页面范围，这是防止小服务器任务挤占交互服务的工程方案，不是已实测容量。
2. 扫描件可按页/小批运行，保存已成功页，失败只重试未完成页；不必因一页失败丢弃整个资料条目。
3. 管理员可对缺损页主动选择外部 OCR API，或上传自己校对的 Markdown；该功能入口已经确认。供应商、调用范围、费用与失败重试参数仍需在具体接入设计和小样本验证中明确，目前未调用任何服务。
4. 图表说明与机器摘要作为带标签的辅助产物；关键数字、政策条文依然能点回原文件原页核对。

### 阶段三：验证有必要再加强视觉检索

先收集真实教师问题：它们是否确实依赖图表、图片、版面，而且文本检索不能定位候选页。如果缺口来自 OCR 错误，先修正文；如果能定位原页但模型读不懂，测视觉阅读；只有“找不到视觉证据”才优先比较页图检索。无需为了“上 RAG”同时部署所有模型。

## 7. 处理状态与故障语义建议

界面不要把一个“已上传”绿标兼作“可在线阅读”“AI 已读全文”。推荐分别显示：原件可读取、正文处理中、部分页可用/需核对、正文可供 AI 使用、处理失败可重试。扫描件失败仍可看原件，管理员整理完成也不应被机器任务失败一并撤销。

每次处理运行至少绑定：资料版本、原文件校验值、解析器/模型版本与参数、成功/失败/空白页数、耗时、输出产物、错误原因。后续重跑生成新候选产物，由明确的激活动作替换当前可用正文；已投稿/发布案例不会因为一次重跑悄悄变成另一套依据。这是保证可追溯和人工校对不丢失的实现建议，尚未实现。

## 8. 最小验证计划与待决策点

不先做全库导入。建议用 10–20 个由用户授权的代表页面，包含中文数字政策、扫描教材、双栏文字、带合并格的表格、图表、混合文字/扫描页、低质量照片。先对比本地快路径、本地 OCR 与管理员修正；如同意外部处理，再增加一条 API 候选。

报告每条路线的完整页覆盖、数字/日期/引用准确性、表格可读性、图片链接有效性、原页定位成功率、峰值内存及每页耗时。另用几条真实问题检查“找到了证据但回答错”与“根本未检索到证据”，不要仅给一个整体 OCR 分数。本文没有执行这些验证。

产品采访的已定与未定问题如下；不要求用户先选择具体模型：

- 已定：一份资料可包含 PDF、Markdown 和图片，仍是一条检索资料。
- 已定：原文与整理／解读区分，自动正文由管理员确认后启用 AI；原件照常可读、可下载、可选入案例。
- 已定：首版提供管理员主动调用外部 OCR 的入口，也允许上传外部解析结果。
- 当前优先待定：同一著作多版次是否共用入口，独立资料如何组织为合集，一个版次可否含多个组成文档。引用时需要准确定位具体来源，不能让 AI 按文件名猜版次。
- 等上述粒度确定后再问：打开资料时优先显示原件还是正文，AI 默认使用哪些正文角色。
- 待定：新版资料提醒、历史失效资料的选用方式和共享新闻维护方式。案例引用固定版本已确定，问题在展示与主动升级体验。

查阅结果已经足以支持“资料包＋CPU 优先＋可选 API”的候选方案，但不足以认定任何解析器在本服务器最优、任何扫描件都能准确解析，或者目前已具备多模态 RAG。

## 9. 当前仓库的实现边界

本节在当前 checkout `7afc5bb9e182b1c61827d6024670002a42937fc6` 重新读取指定代码核对。没有修改这些实现。以下结果也说明为什么“上一个 ZIP”与“已经支持一条多文件资料包”不能画等号。

| 当前代码证据 | 已有行为 | 资料包 / 多模态接入需要补的具体能力 |
| --- | --- | --- |
| [materials/service.py](../../backend/app/modules/materials/service.py)：44–55、271–285 | 单个候选、正式素材只有一个 `blobId` 及一组文件属性。 | 一个资料版本的多个文件清单、文件角色、主原件/正文选择、派生产物出处。 |
| [materials/archive.py](../../backend/app/modules/materials/archive.py)：55–56、216–233 | 归档条目取 basename，文件变成独立 PreparedFile；不保存原相对目录。导入候选路径见 [materials/service.py](../../backend/app/modules/materials/service.py)：73–83。 | 为资料包显式保留安全的相对路径与目录关系，关联 Markdown 图片链接；现有逐文件候选不能自动恢复这些关系。 |
| [agent/routes.py](../../backend/app/modules/agent/routes.py)：247–255、273–285 | 请求适配器关闭上传文件；规范化只持久化 data/text 部分。 | 若要在聊天消息中喂图片/PDF，需增加受控输入、读取权限、版本/文件绑定与可回放消息契约。只换模型名不足以完成。 |
| [agent/service.py](../../backend/app/modules/agent/service.py)：67–85 | 当前用户 prompt 的入口返回字符串，选区也拼成文字。 | 对视觉内容的模型输入装配应独立验证；保留当前文字历史、引用和运行行为。 |
| [ai/provider.py](../../backend/app/modules/ai/provider.py)：146–153 | 装配 OpenAIChatModel 兼容通道；这段代码没有组装图片/PDF。 | 某个兼容模型支持图像仍需上层构造对应输入；专用 OCR 原生 API 也不应假装是同一个文本聊天请求。 |
| [agent/source_reader.py](../../backend/app/modules/agent/source_reader.py)：16、48–54 | 单次来源读取最多返回 6000 字符，超出标 `truncated`。 | 阅读整本教材需分段/分页访问或检索，不能把首段读取宣称为读了全书。 |
| [attachments/text.py](../../backend/app/modules/attachments/text.py)：70–78 | 只提取 text/* 与 DOCX；PDF/图片返回空文字。 | PDF/OCR 解析、处理状态与供 AI 阅读正文的选择都尚需新增。 |
| [backup-bundle-tool.sh](../../scripts/backup-bundle-tool.sh)：45–49、184–188 | 备份与恢复校验枚举 attachments、版本/快照附件、素材候选中的单 `blobId`。 | 新资料包文件和派生产物引用必须一起纳入枚举与恢复校验，否则数据库里有条目但原件/Markdown/图片可能未完整备份。 |

本节的需求补充是基于代码的推论；具体 schema、处理任务和 provider 实现仍待产品问题收敛，未实施。当前已经确认的统一检索保留案例/共享归属、勾选跨搜索筛选翻页保留、部分失败留页，与上述解析路线相容，不应因为新增文件格式重新翻掉这些选择。
