# 教育学博士｜Codex 文献检索与免费 PDF 下载工作包 v2.0

## 0. 本次严格规则（最重要）

> **最终清单里的每一篇论文，必须有一个已经实际核查过的匿名、HTTPS、免费 PDF 直链。**

仅有 DOI、摘要、期刊主页、数据库收录记录、Open Access 标签、`Full text` 按钮、网页登录页，**均不达标**。程序会发送不带学校账号、不带浏览器 Cookie 的 HTTP Range GET 请求，核查服务器是否实际响应 `%PDF-` 文件头；若失败则继续尝试其他开放位置。如果服务器返回付费墙、403、404、网页、必须登录等页面，该链接不能进入正式清单。验证结果仅代表**核查时**该链接响应了 PDF 文件头，并不保证今后永不失效或 PDF 内容完整。

**注意区别**：免费在线浏览、链接免费提供，以及完整 PDF 已经下载到本机，是三种不同状态。默认只将“直接链接经过 PDF 文件头核查”的论文列入正式清单；最多另外保存 40 个完整 PDF 文件（可配置）。

## 1. 检索的数据库与下载来源

| 渠道 | 工作包实际支持方式 | 能否当成免费的 PDF？ |
|---|---|---|
| **OpenAlex** | 自动按期刊/关键词检索 DOI、题目、期刊等；逐一检查 `best_oa_location`、`locations` 中的出版社、大学知识库及主题仓库的所有 OA PDF 地址 | **须逐条验证**，不能直接根据 OA 标记确定 |
| **高校机构知识库** | 通过 OpenAlex 收录的各大学公开储存库位置寻找 accepted manuscript / published PDF | **须逐条验证**；版本可能不是出版社最终版 |
| **Unpaywall** | **可选**的 DOI 补充查询：如果设置 `SCHOLAR_EMAIL` 环境变量，且 OpenAlex 所有 PDF 候选均失败，再查询 Unpaywall OA 位置 | **须逐条验证**；Unpaywall 已停用标题搜索，仍支持 DOI 查询 |
| **Crossref** | 自动补齐或核对 DOI/文献信息 | 仅元数据，**不是 PDF 来源** |
| **Web of Science** | 使用用户从 WoS 合法导出的 `.csv` / `.tsv` / `.ris` 中的 DOI 导入，自动去寻找公开 PDF | WoS **不是该程序直接 API 检索的站点**；收录不等于免费全文 |
| **Scopus** | 使用用户从 Scopus 合法导出的 `.csv` / `.tsv` / `.ris` 中的 DOI 导入，自动去寻找公开 PDF | Scopus **不是该程序直接 API 检索的站点**；馆藏权限不等于公众免费下载 |
| **ERIC**（教育学专项） | 用户/ Codex 可在 https://eric.ed.gov 上补充检索 “Full text available on ERIC” ，核验后单独查看，程序**暂未内置 ERIC API** | 仅明确提供公开可下载 PDF 的文献可手动补充 |

有些付费期刊论文在出版社网站不能下载，但作者已把合法可共享的接受稿（Accepted Manuscript）上传高校机构知识库。程序会检查这些版本，而不是只看出版社第一页的链接。

**不包含**：破解付费墙、学校账号代登录、Cookie 提取、绕过验证码、爬取需登录的 WoS/Scopus 或 Sci-Hub 等非授权镜像。订阅获取全文不代表该链接是公众可免费使用的链接。

## 2. 首次使用：先改两个文件

**`config/settings.json`** 修改研究关键词（英文）、年份、数量。默认关键词是演示样例，**不是你自己的教育学博士课题**。

关键配置：

```json
{
  "require_verified_free_pdf": true,
  "use_unpaywall_fallback": true,
  "max_pdf_candidates_per_record": 15,
  "download_open_access_pdfs": true,
  "max_pdf_downloads": 40
}
```

`require_verified_free_pdf=true` 是强制设置，改为 `false` 会在配置检查时报错，防止正式清单混入未核查候选。`max_pdf_downloads` 是保存 PDF 文件的数量上限，**不是验证免费下载链接的数量上限**。

**`config/journals.csv`** 内有 15 种教育学相关候选期刊。按 `journal,field,include` 管理，想忽略某本，将 `include` 改为 `no`。这些刊名不是经过实时 JCR 核实的“2026 顶级期刊名单”，请自行按子领域调整。

## 3. 网页版 Codex 使用（推荐先上传 GitHub）

1. 下载并解压 ZIP，将解压目录中的文件全部放入 GitHub **Private** 仓库（可使用 GitHub Desktop，仓库例如 `education-literature-codex`）。别把你学术邮箱密码或 API key 提交到仓库。
2. 在 https://chatgpt.com/codex 中选择这个仓库的环境，设置 Internet access。允许 `api.openalex.org`、`api.crossref.org`；可选允许 `api.unpaywall.org`；实际 PDF 的出版社和高校知识库域名需按需求允许。Cloud 环境里若不允许外部 PDF 地址，验证会失败，不能假称论文可下载。
3. 按需要在环境秘密变量中设置 `OPENALEX_API_KEY`（可选）和 `SCHOLAR_EMAIL`（有效的学术联系邮箱；供 Unpaywall 用，不是账号密码）。
4. 修改 `config/settings.json` 和 `config/journals.csv`。打开 `CODEX_PROMPT_复制到Codex.txt`，将完整文字粘贴到 Codex 任务框。
5. Codex 按照 `AGENTS.md` 运行测试、检索、验证 PDF 直链，输出 `output/verified_free_pdf_results.csv` 等报告。获取结果表可审阅 Codex 工作区或通过 GitHub 分支/PR 带回。**pdf/ 已在 .gitignore**，大量 PDF 建议使用下节 Windows 本地运行，避免云端下载文件难以同步。
6. 如 `output/verified_free_pdf_results.csv` 为空，表示**本轮没有通过链接验证的文献**，不是“没找到论文”。应查看 `search_candidates.csv`、`needs_manual_access.csv`、网络白名单及期刊匹配日志。

## 4. Windows 本地运行（推荐真正批量保存 PDF）

需要 Python 3.10+。在 Windows 安装 Python 时勾选 Add Python to PATH。用 VS Code / 记事本配置关键词。

打开项目目录的命令提示符 `cmd`：

```bat
py -3 run.py --check
py -3 -m unittest discover -s tests -v
py -3 run.py --mode search
```

也可以直接双击 `run_windows.bat`。

**只验证免费下载链接、不实际保存 PDF 文件**：

```bat
py -3 run.py --mode search --no-pdf
```

`--no-pdf` 不代表不检查链接，仍发起少量 HTTP 读取以确认服务器返回 PDF 文件头；它只是跳过整个 PDF 保存操作。某些网站禁止自动化请求，程序不会尝试绕过。

**增加公开资源覆盖率（可选）**：Windows PowerShell 里先设置环境变量：

```powershell
$env:SCHOLAR_EMAIL="your-research-email@example.edu"
$env:OPENALEX_API_KEY="your-key-if-you-have-one"
python run.py --mode search
```

Unpaywall DOI 端点要求有效邮箱，提供此变量才能开启 Unpaywall 补充检索。这里的 `example.edu` 只是格式范例，**必须更换成自己的真实邮箱**。

## 5. WoS / Scopus 批量导入 DOI 的实际步骤

1. 在有权限使用的 WoS、Scopus 官网检索你的教育学主题，导出论文记录，尽量勾选 **DOI** 字段。
2. 选择保存为 **CSV、TSV 或 RIS**；工作包可直接识别这些文件的 `DOI`、`DI`、`Digital Object Identifier` 等列，**不要求你逐行复制 DOI**。也支持只有 DOI、每行一个的 `.txt`。
3. 把导出的文件放到工作包 `input/` 文件夹，例如 `input/scopus_export.csv`。
4. 在命令行执行（选择对应文件即可）：

```bat
py -3 run.py --mode doi --input input/scopus_export.csv
py -3 run.py --mode doi --input input/wos_export.ris
```

**重要**：每次运行会覆盖上一次 `output/` 中的同名报表。需要多库合并时，建议先在 Excel 中把 DOI 合并去重、导出统一 CSV，再做一次导入；或每跑一库就把结果复制到独立目录保存。**工作包不会未经说明就宣称直接查询过 WoS/Scopus 的订阅数据库**。

## 6. 输出文件（强制免费链接筛选）

| 输出 | 确切含义 |
|---|---|
| `output/verified_free_pdf_results.csv` | **正式清单**：每篇都有核验成功的 `verified_pdf_url`（HTTPS，实际 PDF 响应） |
| `output/all_results.csv` | 默认与正式清单相同，**不包括无免费下载链接的论文** |
| `output/open_access_results.csv` | 与正式清单相同（兼容旧文件名）；不能误读为所有 OA 标记的候选 |
| `output/search_candidates.csv` | **审计表**：所有元数据检索候选，包括不满足免费 PDF 要求的论文 |
| `output/needs_manual_access.csv` | 失败或仅有落地页的论文；不进入正式清单，仅供手动继续找公开版本 |
| `output/references.ris`、`references.bib` | **只包含正式清单**；可导入 Zotero / EndNote |
| `output/search_log.csv` | 期刊识别失败、检索式及数量、API 错误 |
| `output/run_summary.json` | 候选数、符合免费 PDF 条件数、实际下载数量与局限 |
| `pdf/` | 依配置成功下载的完整 PDF 文件（可少于验证的链接数） |

正式表中最重要的列：

- `verified_pdf_url`：**已核验的免费 PDF 下载地址**；是必须非空的列。
- `pdf_link_status`：`verified_pdf_header` 或 `downloaded_pdf_verified`。
- `pdf_source`、`pdf_source_type`：从哪个出版社/高校知识库获得。
- `pdf_version`：出版版、接受稿或预印本版本（如原始来源有提供）。
- `pdf_repository_landing_url`：机构知识库的可追溯记录页。
- `pdf_link_checked_at_utc`：核查日期和时间；链接可能日后失效。
- `pdf_status`、`pdf_file`：该 PDF 是否真正保存到电脑，不要与“已核验链接”混为一谈。

Zotero：**文件 → 导入 → 选择 `output/references.ris`**。RIS 导入书目信息；PDF 文件需要另行关联，工作包不会直接附加到 Zotero 条目。

## 7. 严谨性、局限与补充核验

- **只有期刊论文，不必然是高质量或满足博士研究主题**：正式表的免费 PDF 条件不替代文献主题筛选、全文学术评估、同行评议核查。
- **非穷尽式检索**：默认每期刊×关键词只检索一页最相关记录，且有全局数量限制；不能据此宣称 PRISMA 系统综述完整检索。
- **OA 数据源不覆盖全部高校公开库**：若 OpenAlex/Unpaywall 没收录某大学的公开稿件，程序可能漏掉。可在学校知识库、ERIC、Google Scholar 所指向的公开主页、DOAJ 或出版社官网继续找，最终仍要验证免费 PDF 直链。
- **免费并不代表可任意转载**：程序只用于个人合法研究访问；下载/传播仍遵守原站许可与条款。
- **HTTP 访问核验是当时抽样读取 PDF 文件头**，不保证全文内容匹配题目或完整性；下载的文件只检查了 PDF 魔数，不等于完成了文件内容校验。严谨研究需人工核对标题页、作者、年份、方法和 PDF 版本。
- **仅在有合法许可且可匿名访问时下载**。不要通过机器程序绕过图书馆登录和网站的 robots/访问限制。
- **接口额度、超时、被屏蔽的站点**都可能使明明公开的文献暂时失败；这属于无法核验，不应标成已成功。

## 8. 故障处理

- `CONFIG OK`：本地配置有效，不代表已经联网下载。
- `source_not_exactly_matched`：修正期刊名称；不会猜测最像的期刊。
- `response_not_pdf`、`returned_html_or_non_pdf`：原链接实际不是 PDF，或要求进一步打开页面；自动剔除。
- `http_403` / `http_404`：无法公开下载，自动剔除；不要绕过访问限制。
- `probe_error`：网络中断、PDF 域名未允许、证书或连接故障，自动剔除。
- 已验证但 `download_failed`：PDF 链接在核验时是公开的，但完整下载没有成功；`verified_pdf_url` 仍可供人工重试。

**权威参考**：
- OpenAlex API：https://help.openalex.org/api/
- OpenAlex Locations（多个开放来源、大学知识库、PDF URL）：https://help.openalex.org/data/locations/
- Unpaywall API（DOI 端点与邮箱要求）：https://data.unpaywall.org/products/api
- 教育资源 ERIC：https://eric.ed.gov/
- Crossref：https://www.crossref.org/documentation/retrieve-metadata/rest-api/
