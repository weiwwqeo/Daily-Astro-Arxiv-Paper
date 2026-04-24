import os
import smtplib
import logging
import json
import random
import time
import re
import arxiv
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from html import escape
from openai import OpenAI

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

### use Arxiv api instead of Benty-Fields
class DailyPaperBot:
    def __init__(self, config):
        self.config = config
        # self.session = HTMLSession()
        # self.client = OpenAI(api_key=config['api_key'], base_url=config['api_base'])
        self.target_date1 = self.config.get('target_date1', (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d'))
        self.target_date2 = self.config.get('target_date2', (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d'))
        self.papers = []


    def _retry_wait_seconds(self, attempt_index):
        base = float(self.config.get('arxiv_backoff_seconds', 8))
        jitter = random.uniform(0, 1.5)
        # 指数退避：base * 2^n + jitter
        return base * (2 ** attempt_index) + jitter

    def _is_retryable_arxiv_error(self, err):
        if isinstance(err, arxiv.HTTPError):
            # 5xx与429通常是暂时性问题
            return err.status in (429, 500, 502, 503, 504)
        if isinstance(err, (arxiv.UnexpectedEmptyPageError, arxiv.ArxivError)):
            return True
        return False

    def get_arxiv_papers(self, category='astro-ph.GA'):
        """使用arXiv API获取指定日期的astro-ph.GA论文"""    
        query = f"cat:{category} AND submittedDate:[{self.target_date1} TO {self.target_date2}]"
        fetch_attempts = int(self.config.get('arxiv_fetch_attempts', 4))
        delay_seconds = float(self.config.get('arxiv_delay_seconds', 3))
        num_retries = int(self.config.get('arxiv_num_retries', 3))

        for attempt in range(fetch_attempts):
            try:
                search = arxiv.Search(
                    query=query,
                    max_results=1000,  # 设置足够大的数量以获取全部结果
                    sort_by=arxiv.SortCriterion.SubmittedDate,  # 按提交日期排序
                    sort_order=arxiv.SortOrder.Ascending  # 升序排列
                )
                client = arxiv.Client(
                    delay_seconds=delay_seconds,
                    num_retries=num_retries
                )
                results = client.results(search)

                paper_list = []
                for paper in results:
                    paper_list.append({
                        "title": paper.title,
                        "authors": [author.name for author in paper.authors],
                        "published": paper.published,  # 发布时间
                        "summary": paper.summary,
                        "pdf_url": paper.pdf_url  # 下载链接
                    })
                    # 你可以在此处直接下载PDF：paper.download_pdf(dirpath="./papers/")
                print(f"在 {self.target_date1} 到 {self.target_date2} 找到了 {len(paper_list)} 篇 {category} 论文。")
                return paper_list
            except Exception as e:
                is_retryable = self._is_retryable_arxiv_error(e)
                is_last_attempt = (attempt == fetch_attempts - 1)
                logger.warning(
                    "抓取 %s 失败（attempt %s/%s）: %s",
                    category,
                    attempt + 1,
                    fetch_attempts,
                    e
                )
                if (not is_retryable) or is_last_attempt:
                    raise
                wait_s = self._retry_wait_seconds(attempt)
                logger.info("等待 %.1f 秒后重试分类 %s ...", wait_s, category)
                time.sleep(wait_s)

        # 理论上不会到这里
        raise RuntimeError(f"抓取 {category} 失败")
    def save_papers_to_json(self,papers, filename='parsed_papers.json'):
        """将解析后的论文保存为JSON文件"""
        # with open(filename, 'w', encoding='utf-8') as f:
            # json.dump(papers, f, ensure_ascii=False, indent=2)
        with open(filename, 'w', encoding='utf-8') as f:
            # 使用自定义序列化函数，并设置缩进使文件易读
            json.dump(papers, f, default=self.json_serializer, ensure_ascii=False, indent=2)
            print(f"已保存 {len(papers)} 篇论文到 {filename}")
    def json_serializer(self, obj):
        """处理JSON无法直接序列化的对象，如datetime"""
        if isinstance(obj, datetime):
            # 转换为ISO 8601格式字符串，通用且标准
            return obj.isoformat()
        # 可以在此添加对其他类型的处理，如date, time等
        raise TypeError(f"Type {type(obj)} not serializable")

    def print_papers_summary(self,papers, max_display=5):
        """打印论文摘要信息"""
        print(f"共解析到 {len(papers)} 篇论文\n")
        print("=" * 80)
        
        for i, paper in enumerate(papers[:max_display]):
            print(f"Paper {i+1}:")
            print(f"Published Date: {paper['published']}")
            print(f"Title: {paper['title'][:80]}..." if len(paper['title']) > 80 else f"Title: {paper['title']}")
            print(f"Authors: {paper['authors'][:60]}..." if len(paper['authors']) > 60 else f"Authors: {paper['authors']}")
            print(f"Abstract (first 100 chars): {paper['summary'][:100]}...")
            print(f"Link: {paper['pdf_url']}")
            print("-" * 80)
        return len(papers)

    def _get_deepseek_client(self):
        api_key = self.config.get('deepseek_api_key', '').strip()
        if not api_key:
            raise RuntimeError("DEEPSEEK_API_KEY 未配置")
        return OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

    def _get_deepseek_model_name(self):
        model_name = self.config.get('deepseek_model', '')
        if not model_name:
            model_name = "deepseek-chat"
        if model_name == "deepseek-chat" and self.config.get('thinking', True):
            model_name = "deepseek-reasoner"
        return model_name

    def _deepseek_retry_wait_seconds(self, attempt_index):
        base = float(self.config.get('deepseek_backoff_seconds', 4.0))
        jitter = random.uniform(0, 1.2)
        return base * (2 ** attempt_index) + jitter

    def _extract_json_object(self, text):
        if not text:
            raise RuntimeError("DeepSeek返回为空")
        text = text.strip()
        fenced_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, flags=re.S)
        if fenced_match:
            return json.loads(fenced_match.group(1))
        first = text.find("{")
        last = text.rfind("}")
        if first == -1 or last == -1 or first >= last:
            raise RuntimeError("DeepSeek返回中未找到JSON对象")
        return json.loads(text[first:last + 1])

    def _call_deepseek_json(self, system_prompt, user_prompt, max_tokens):
        retry_attempts = int(self.config.get('deepseek_retry_attempts', 3))
        model_name = self._get_deepseek_model_name()
        last_error = None

        for attempt in range(retry_attempts):
            try:
                client = self._get_deepseek_client()
                response = client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=self.config.get('temperature', 0.3),
                    max_tokens=max_tokens,
                    stream=False
                )
                content = response.choices[0].message.content
                return self._extract_json_object(content)
            except Exception as e:
                last_error = e
                if "DEEPSEEK_API_KEY 未配置" in str(e):
                    raise RuntimeError("AI分析失败: DEEPSEEK_API_KEY 未配置") from e
                is_last_attempt = (attempt == retry_attempts - 1)
                logger.warning(
                    "DeepSeek调用失败（attempt %s/%s）: %s",
                    attempt + 1,
                    retry_attempts,
                    e
                )
                if is_last_attempt:
                    break
                wait_s = self._deepseek_retry_wait_seconds(attempt)
                logger.info("等待 %.1f 秒后重试DeepSeek ...", wait_s)
                time.sleep(wait_s)

        # 兜底：非JSON返回或服务短暂不可用时，再强制重试1次
        logger.warning("DeepSeek常规重试已耗尽，执行额外兜底重试1次。最后错误: %s", last_error)
        try:
            client = self._get_deepseek_client()
            strict_system_prompt = system_prompt + " 你必须只输出单个合法JSON对象，禁止输出解释或Markdown代码块。"
            strict_user_prompt = user_prompt + "\n\n提醒：上一次输出不符合JSON要求。请仅返回合法JSON对象。"
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": strict_system_prompt},
                    {"role": "user", "content": strict_user_prompt}
                ],
                temperature=self.config.get('temperature', 0.3),
                max_tokens=max_tokens,
                stream=False
            )
            content = response.choices[0].message.content
            return self._extract_json_object(content)
        except Exception as e:
            raise RuntimeError(f"AI分析失败: {e}") from e

    def _build_chunk_prompt(self, chunk_papers):
        return f"""你是专业天文学助手。请基于以下论文列表筛选“高红移星系及宇宙早期相关研究”。

筛选范围（包括但不限于）：
1) 直接高红移/早期宇宙目标
- high-redshift galaxies, cosmic dawn, first light, early universe, reionization/EoR
- z>=1 星系、Lyman-break galaxies (LBG), dropout, Lyman-alpha emitters (LAE)
- Pop III / very massive stars, primordial galaxies, UV luminosity function, stellar mass function at high-z
- 高红移AGN/quasar及其宿主星系、SMBH早期增长
- 与高红移观测相关的宇宙学开放问题：Hubble tension、暗物质本质、暗能量本质

2) 与高红移星系物理紧密相关
- galaxy formation/evolution, star formation history, metal enrichment
- ISM/CGM/IGM, neutral fraction, ionizing photon budget, escape fraction
- nebular emission lines (如 [OIII], Hβ, Hα 等), photoionization diagnostics
- dust-obscured high-z galaxies, submm/mm studies, [CII]/CO lines
- 高红移环境与大尺度结构：overdensity, cluster, proto-cluster, galaxy group

3) 关键观测与方法（只要与高红移目标有明确联系）
- JWST (NIRCam/NIRSpec/MIRI), ALMA, VLA, HST, Roman, Euclid, DESI, LSST 等
- gravitational lensing (strong/weak/cluster lensing), magnification
- photometric/spectroscopic redshift methods, SED fitting for high-z constraints

筛选规则：
- 保留与“高红移星系/早期宇宙”有明确实质关联的论文。
- 若仅为方法论文，需能明确服务于高红移科学目标，否则不选。
- 严格使用输入中的 paper_id，不可编造。

只输出 JSON 对象，不要输出任何额外文本。格式必须是：
{{
  "selected_papers": [
    {{
      "paper_id": "P001",
      "title_zh": "中文标题",
      "abstract_zh": "中文摘要翻译（建议 150~320 字，可按内容复杂度浮动）",
      "relevance_reason_zh": "为何相关（建议 60~140 字，需点明与高红移科学的连接）",
      "relevance_tags": ["high-z", "reionization", "lensing"]
    }}
  ],
  "chunk_summary_zh": "该批次研究方向总结（建议 100~220 字）"
}}

论文数据:
{json.dumps(chunk_papers, ensure_ascii=False, default=self.json_serializer)}
"""

    def _analyze_chunk(self, chunk_index, chunk_papers):
        system_prompt = "你是严谨的天文学文献筛选与翻译助手。必须返回合法JSON。"
        user_prompt = self._build_chunk_prompt(chunk_papers)
        chunk_result = self._call_deepseek_json(system_prompt, user_prompt, max_tokens=3200)
        selected = chunk_result.get("selected_papers", [])
        if not isinstance(selected, list):
            selected = []
        summary = chunk_result.get("chunk_summary_zh", "")
        if not isinstance(summary, str):
            summary = ""
        return chunk_index, selected, summary

    def _build_final_summary(self, selected_papers, chunk_summaries):
        if not selected_papers:
            return "当日未筛选出与高红移星系高度相关的论文。建议关注后续发布批次。"

        # 严格覆盖全部入选论文：先分批摘要，再汇总为最终总结
        selected_brief = []
        for p in selected_papers:
            selected_brief.append({
                "title": p.get("title", ""),
                "title_zh": p.get("title_zh", ""),
                "reason": p.get("relevance_reason_zh", ""),
            })

        batch_size = 20
        batch_summaries = []
        for i in range(0, len(selected_brief), batch_size):
            batch = selected_brief[i:i + batch_size]
            batch_prompt = f"""你将看到一批入选论文要点。请写一段中文批次总结（90~160字），提炼该批次主要方向。
只输出JSON对象:
{{
  "batch_summary_zh": "..."
}}

批次索引: {i // batch_size + 1}
批次论文要点:
{json.dumps(batch, ensure_ascii=False)}
"""
            batch_result = self._call_deepseek_json(
                "你是天文学综述助手。必须返回合法JSON。",
                batch_prompt,
                max_tokens=500
            )
            batch_summary = batch_result.get("batch_summary_zh", "")
            if isinstance(batch_summary, str) and batch_summary.strip():
                batch_summaries.append(batch_summary.strip())

        final_prompt = f"""请根据以下信息写一段中文总结（约180~280字），面向天文专业研究者，突出当日趋势和重点方向。
注意：批次总结已覆盖全部入选论文，请综合后给出总览。
只输出JSON对象:
{{
  "daily_summary_zh": "..."
}}

分块总结:
{json.dumps(chunk_summaries, ensure_ascii=False)}

批次总结:
{json.dumps(batch_summaries, ensure_ascii=False)}
"""
        result = self._call_deepseek_json(
            "你是天文学综述助手。必须返回合法JSON。",
            final_prompt,
            max_tokens=700
        )
        summary = result.get("daily_summary_zh", "")
        if not isinstance(summary, str) or not summary.strip():
            return "当日相关研究主要围绕高红移星系形成与演化、星系环境气体过程及关键观测数据分析展开。"
        return summary.strip()

    def render_html_email(self, selected_papers, daily_summary_zh, total_papers):
        date_text = f"{self.target_date1} to {self.target_date2}"
        paper_items_html = []
        for p in selected_papers:
            title = escape(p.get("title", ""))
            title_zh = escape(p.get("title_zh", ""))
            published = escape(str(p.get("published", "")))
            authors_list = p.get("authors", [])
            shown_authors = authors_list[:10]
            authors_text = ", ".join(shown_authors)
            if len(authors_list) > 10:
                authors_text += f" 等{len(authors_list)}位作者"
            authors = escape(authors_text)
            abstract = escape(p.get("summary", ""))
            if len(abstract) > 420:
                abstract = abstract[:210] + " ... " + abstract[-140:]
            abstract_zh = escape(p.get("abstract_zh", ""))
            reason_zh = escape(p.get("relevance_reason_zh", ""))
            url = escape(p.get("pdf_url", ""))
            item = f"""
            <div class="paper">
                <div class="paper-title">论文名: {title}</div>
                <div class="paper-title-translation">论文名翻译: {title_zh}</div>
                <div class="paper-meta">发表时间: {published}</div>
                <div class="paper-meta">作者: {authors}</div>
                <div class="paper-abstract">摘要: {abstract}</div>
                <div class="paper-abstract-translation">摘要翻译: {abstract_zh}</div>
                <div class="paper-meta">相关性说明: {reason_zh}</div>
                <a class="paper-link" href="{url}" target="_blank">查看论文</a>
            </div>
            """
            paper_items_html.append(item)
        if not paper_items_html:
            paper_items_html.append(
                "<div class=\"paper\"><div class=\"paper-title\">今日未筛选出高相关论文。</div></div>"
            )

        return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <style>
    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 900px; margin: 0 auto; padding: 20px; }}
    .header {{ background: #2c3e50; color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}
    .section {{ background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; border-left: 4px solid #4a6491; }}
    .section-title {{ color: #2c3e50; font-size: 18px; font-weight: 600; margin-bottom: 15px; }}
    .paper {{ margin-bottom: 24px; padding-bottom: 20px; border-bottom: 1px dashed #eee; }}
    .paper-title {{ font-size: 16px; font-weight: 600; color: #2c3e50; margin-bottom: 5px; }}
    .paper-title-translation {{ font-size: 14px; color: #555; font-style: italic; margin-bottom: 8px; }}
    .paper-meta {{ font-size: 13px; color: #666; background-color: #f5f5f5; padding: 8px 12px; border-radius: 4px; margin: 8px 0; }}
    .paper-abstract {{ font-size: 14px; line-height: 1.7; margin: 10px 0; padding: 12px; background-color: #f8f9fa; border-radius: 4px; }}
    .paper-abstract-translation {{ font-size: 14px; line-height: 1.7; margin: 10px 0; padding: 12px; background-color: #f1f7ff; border-radius: 4px; }}
    .paper-link {{ display: inline-block; background-color: #4a6491; color: white; padding: 6px 12px; text-decoration: none; border-radius: 4px; font-size: 13px; margin-top: 8px; }}
    .summary {{ background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 25px 0; }}
    .footer {{ text-align: center; font-size: 12px; color: #666; margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee; }}
  </style>
</head>
<body>
  <div class="header">
    <h1>arXiv天文论文每日摘要</h1>
    <div>发布日期: {escape(date_text)}</div>
  </div>
  <div class="section">
    <div class="section-title">📚 筛选与整理结果</div>
    {"".join(paper_items_html)}
  </div>
  <div class="summary">
    <div class="section-title">📊 当日研究总结</div>
    <p>{escape(daily_summary_zh)}</p>
  </div>
  <div class="footer">
    <p>此邮件由DeepSeek分块分析 + Python模板渲染生成 | 共抓取 {total_papers} 篇，入选 {len(selected_papers)} 篇</p>
    <p>weiwwqeo只是用ai写了个ai bot</p>
  </div>
</body>
</html>"""

    def analyze_papers_with_deepseek(self, papers):
        """分块并发调用DeepSeek，返回结构化筛选结果"""
        if not papers:
            return {"selected_papers": [], "chunk_summaries": []}

        # 为每篇论文分配稳定ID，方便分块返回后精确关联
        paper_index = {}
        paper_rows = []
        for i, paper in enumerate(papers):
            paper_id = f"P{i:04d}"
            paper_index[paper_id] = paper
            paper_rows.append({
                "paper_id": paper_id,
                "title": paper.get("title", "")[:220],
                "authors": ", ".join(paper.get("authors", []))[:240],
                "published": str(paper.get("published", "")),
                "abstract": paper.get("summary", "")[:1800],
                "url": paper.get("pdf_url", "")
            })

        chunk_size = int(self.config.get('deepseek_chunk_size', 10))
        workers = int(self.config.get('deepseek_parallel_workers', 4))
        chunks = [paper_rows[i:i + chunk_size] for i in range(0, len(paper_rows), chunk_size)]
        logger.info("DeepSeek分块分析: %s 篇论文, %s 个分块, %s 并发", len(paper_rows), len(chunks), workers)

        selected_merged = []
        chunk_summaries = []
        futures = []
        paper_order = {row["paper_id"]: idx for idx, row in enumerate(paper_rows)}
        with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
            for idx, chunk in enumerate(chunks):
                futures.append(executor.submit(self._analyze_chunk, idx, chunk))

            for fut in as_completed(futures):
                try:
                    chunk_index, selected_rows, chunk_summary = fut.result()
                except Exception as e:
                    logger.error("DeepSeek分块任务失败: %s", e)
                    continue
                logger.info("DeepSeek分块 %s 完成, 入选 %s 篇", chunk_index + 1, len(selected_rows))
                chunk_summaries.append((chunk_index, chunk_summary))
                for row in selected_rows:
                    paper_id = row.get("paper_id", "")
                    if paper_id not in paper_index:
                        continue
                    original = paper_index[paper_id]
                    selected_merged.append({
                        "paper_id": paper_id,
                        "title": original.get("title", ""),
                        "authors": original.get("authors", []),
                        "published": original.get("published", ""),
                        "summary": original.get("summary", ""),
                        "pdf_url": original.get("pdf_url", ""),
                        "title_zh": str(row.get("title_zh", "")).strip(),
                        "abstract_zh": str(row.get("abstract_zh", "")).strip(),
                        "relevance_reason_zh": str(row.get("relevance_reason_zh", "")).strip(),
                        "relevance_tags": row.get("relevance_tags", []),
                    })

        # 去重：按paper_id保留第一条，并恢复原始抓取顺序
        best_by_id = {}
        for p in selected_merged:
            pid = p["paper_id"]
            if pid not in best_by_id:
                best_by_id[pid] = p
        deduped = list(best_by_id.values())
        if not deduped and not chunk_summaries:
            raise RuntimeError("DeepSeek分块分析全部失败")
        deduped.sort(key=lambda x: paper_order.get(x["paper_id"], 10**9))
        chunk_summaries_sorted = [s for _, s in sorted(chunk_summaries, key=lambda x: x[0]) if s]

        return {
            "selected_papers": deduped,
            "chunk_summaries": chunk_summaries_sorted
        }
        
    
    
    def send_html_email(self,html_content, email_config, subject=None):
        """
        发送HTML格式邮件（不再需要复杂的格式化）
        """
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        receivers_list = email_config.get('email_receiver', [])
        sender = email_config.get('email_sender', '').strip()
        password = email_config.get('email_password', '').strip()
        smtp_server = email_config.get('smtp_server', 'smtp.qq.com')
        smtp_port = int(email_config.get('smtp_port', 587))

        if not sender:
            print("❌ EMAIL_SENDER 未配置")
            return False
        if not password:
            print("❌ EMAIL_PASSWORD 未配置")
            return False
        if not receivers_list:
            print("❌ EMAIL_RECEIVER 未配置或为空")
            return False

        print(f"发送邮件给：{len(receivers_list)} 个收件人")
        receivers = ','.join(receivers_list)

        try:
            # 如果没有提供主题，从HTML中提取或使用默认
            if not subject:
                # # 尝试从HTML中提取标题
                # import re
                # title_match = re.search(r'<h1[^>]*>(.*?)</h1>', html_content, re.IGNORECASE)
                # if title_match:
                #     subject = title_match.group(1).strip()
                # else:
                subject = f"每日食一啲Astro-Paper🐧 (arXiv)// {self.target_date1} to {self.target_date2}"
            
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = sender
            msg['To'] = receivers
            
            # 直接附加HTML内容
            msg.attach(MIMEText(html_content, 'html', 'utf-8'))
            
            # 发送邮件（使用SSL连接，更稳定）
            with smtplib.SMTP_SSL(smtp_server, 465, timeout=10) as server:
                server.login(sender, password)
                server.send_message(msg)
            
            print(f"✅ HTML邮件发送成功！")
            return True
        
        except smtplib.SMTPAuthenticationError as e:
            print(f"❌ 认证失败，请检查邮箱密码是否正确")
            print(f"Gmail需要使用16位应用专用密码")
            return False
        except Exception as e:
            print(f"❌ 邮件发送失败: {type(e).__name__}: {e}")
            
            # 尝试使用TLS连接作为备选
            try:
                print("尝试使用TLS连接...")
                with smtplib.SMTP(smtp_server, smtp_port, timeout=10) as server:
                    server.starttls()
                    server.login(sender, password)
                    server.send_message(msg)
                print("✅ 使用TLS连接发送成功！")
                return True
            except Exception as e2:
                print(f"❌ TLS连接也失败: {e2}")
                return False

    def test_email_sending(self, html_content, email_config):

        
        # 使用你提供的AI输出作为测试内容
        test_ai_content = html_content
        
        # 测试发送
        print("Sending Email...")
        success = self.send_html_email(test_ai_content, email_config, )
        
        if success:
            print("邮件已发送。")
        else:
            print("发送失败，请检查配置。")
        return success

    def run(self):
        print(f"📅 Target Date: {self.target_date1} to {self.target_date2}")

        print('fetching papers ...')
        papers = []
        failed_categories = []
        for category in ('astro-ph.GA', 'astro-ph.CO'):
            try:
                papers.extend(self.get_arxiv_papers(category))
            except Exception as e:
                failed_categories.append(category)
                logger.error("分类 %s 抓取失败: %s", category, e)

        if failed_categories:
            logger.warning("以下分类抓取失败: %s", ", ".join(failed_categories))
        if not papers:
            raise RuntimeError("arXiv抓取失败：所有分类都未成功返回数据")

        print('parsing papers ...')

        n_papers = self.print_papers_summary(papers)
        if n_papers == 0:
            print("今日未抓取到相关论文，终止运行。")
            return
        print('analyzing papers with DeepSeek ...')
        analysis_result = self.analyze_papers_with_deepseek(papers)
        selected_papers = analysis_result.get("selected_papers", [])
        chunk_summaries = analysis_result.get("chunk_summaries", [])
        daily_summary_zh = self._build_final_summary(selected_papers, chunk_summaries)
        html_output = self.render_html_email(selected_papers, daily_summary_zh, total_papers=n_papers)
        print('sending email ...')
        email_sent = self.test_email_sending(html_output, email_config=self.config)
        if not email_sent:
            raise RuntimeError("邮件发送失败")

if __name__ == '__main__':
    # 判断是否在 GitHub Actions 环境中
    print(os.environ.get('GITHUB_ACTIONS'))
    if os.environ.get('GITHUB_ACTIONS') == 'true':
        # 使用 GitHub 环境变量配置
        from github_config import get_github_config
        config_my = get_github_config()

        bot = DailyPaperBot(config_my)
        bot.run()
    else:
      print('github action error!')

    
