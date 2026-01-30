import os
import smtplib
import logging
import json
import arxiv
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
# from requests_html import HTMLSession
import traceback
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


    def get_arxiv_papers(self, category='astro-ph.GA'):
        """使用arXiv API获取指定日期的astro-ph.GA论文"""    
        query = f"cat:{category} AND submittedDate:[{self.target_date1} TO {self.target_date2}]"

        search = arxiv.Search(
            query=query,
            max_results=1000,  # 设置足够大的数量以获取全部结果
            sort_by=arxiv.SortCriterion.SubmittedDate,  # 按提交日期排序
            sort_order=arxiv.SortOrder.Ascending  # 升序排列
        )
        client = arxiv.Client()
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
        print(f"在 {self.target_date1} 到 {self.target_date2} 找到了 {len(paper_list)} 篇 astro-ph.GA 论文。")
        return paper_list
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

    def get_analysis_prompt(self, papers_data,):
        """
        生成让AI直接输出HTML格式邮件的Prompt
        """
        
        return f"""你是一个天文学文献分析助手。我将提供一份JSON格式的论文数据，这些论文来自arXiv，涉及天文学、天体物理等领域。
        你的任务是：1) 筛选出与“高红移星系”高度相关的论文：请首先根据title和abstract，筛选出与 “高红移星系” 研究高度相关的论文。相关性判断应基于以下关键词或主题（包括但不限于）：high-redshift galaxies, AGN, galaxy evolution, early universe, galaxy formation, ISM, CGM, IGM, deionization, JWST, ALMA, VLA ...。
        2) 对筛选出的每篇论文进行格式化整理与翻译；3) 对当日所有论文（或筛选出的子集）撰写简短总结；4) 生成一封准备发送的摘要邮件,生成完整的HTML邮件内容。

    【论文数据】：
    {json.dumps(papers_data, ensure_ascii=False, default=self.json_serializer, indent=2)}

    【输出要求】：
    1. 直接输出完整的HTML邮件内容，无需额外说明
    2. 使用以下HTML结构（包含样式和内容）：
    ```html
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 800px; margin: 0 auto; padding: 20px; }}
            .header {{ background: #2c3e50; color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}
            .section {{ background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; border-left: 4px solid #4a6491; }}
            .section-title {{ color: #2c3e50; font-size: 18px; font-weight: 600; margin-bottom: 15px; }}
            .paper {{ margin-bottom: 25px; padding-bottom: 20px; border-bottom: 1px dashed #eee; }}
            .paper-title {{ font-size: 16px; font-weight: 600; color: #2c3e50; margin-bottom: 5px; }}
            .paper-title-translation {{ font-size: 14px; color: #555; font-style: italic; margin-bottom: 8px; }}
            .paper-meta {{ font-size: 13px; color: #666; background-color: #f5f5f5; padding: 8px 12px; border-radius: 4px; margin: 8px 0; }}
            .paper-abstract {{ font-size: 14px; line-height: 1.7; margin: 10px 0; padding: 12px; background-color: #f8f9fa; border-radius: 4px; }}
            .paper-link {{ display: inline-block; background-color: #4a6491; color: white; padding: 6px 12px; text-decoration: none; border-radius: 4px; font-size: 13px; margin-top: 8px; }}
            .summary {{ background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 25px 0; }}
            .footer {{ text-align: center; font-size: 12px; color: #666; margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>arXiv天文论文每日摘要</h1>
            <div>发布日期: {self.target_date1} to {self.target_date2}</div>
        </div>
        
        <div class="section">
            <div class="section-title">📚 筛选与整理结果</div>
            
            <!-- 对每篇筛选出的论文，重复以下结构 -->
            <div class="paper">
                <div class="paper-title">论文名: [原文标题]</div>
                <div class="paper-title-translation">论文名翻译: [中文翻译标题]</div>
                <div class="paper-meta">发表时间: [发表时间]</div>
                <div class="paper-meta">作者: [作者列表]</div>
                <div class="paper-abstract">摘要: [原文摘要文本，仅保留开头和结尾100字符]</div>
                <div class="paper-abstract-translation">摘要翻译: [中文摘要翻译,要求专业、流畅]</div>
                <a class="paper-link" href="https://arxiv.org/abs/[arXiv ID]" target="_blank">查看论文</a>
            </div>
            <!-- 结束论文条目 -->
            
        </div>
        
        <div class="summary">
            <div class="section-title">📊 当日研究总结</div>
            <p>[基于所有筛选出的论文，写一段200字左右的当日总结，面向专业研究者，突出重要发现与趋势]</p>
        </div>
        
        <div class="footer">
            <p>此邮件由DeepSeek V3.2（思考模型）生成 | 共处理 [论文数量] 篇论文</p>
            <p>weiwwqeo只是用ai写了个ai bot🫡 </p>
        </div>
    </body>
    </html>
    """

    def analyze_papers_with_deepseek(self, papers,): #temperature=0.3,max_tokens=8192,thinking = False
        """使用DeepSeek API分析论文并生成摘要邮件"""
        if not papers:
            return "今日未抓取到相关论文。"
        
        # 1. 准备精简的论文数据（节省token）
        minimal_papers = []
        for paper in papers:
            minimal_papers.append({
                "title": paper.get("title", "")[:150],  # 限制标题长度
                "authors": paper.get("authors", "")[:30],  # 限制作者列表长度
                "abstract": paper.get("summary", "")[:1000],  # 限制摘要长度
                "date": paper.get("published", ""),
                "url": paper.get("pdf_url", "")
            })
        
        # 2. 构建Prompt
        system_prompt = """你是一个专业的天文学文献分析助手，精通中英双语。请严格按照要求处理论文数据。"""
        
        user_prompt = self.get_analysis_prompt(minimal_papers,)
        
        try:
            deepseek_client = OpenAI(
            api_key=self.config['deepseek_api_key'],
            base_url="https://api.deepseek.com")
            model_name = "deepseek-chat"
            if self.config.get('thinking', True):
                model_name = "deepseek-reasoner"
            # 3. 调用DeepSeek API（使用OpenAI SDK格式）
            response = deepseek_client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=self.config.get('temperature', 0.3),
                max_tokens=self.config.get('max_tokens', 8192),
                stream=False
            )
            
            ai_output = response.choices[0].message.content
            logger.info("DeepSeek分析完成")
            
            return ai_output
            
        except Exception as e:
            logger.error(f"DeepSeek API调用失败: {e}")
            return f"AI分析失败: {str(e)}"
        
    
    
    def send_html_email(self,html_content, email_config, subject=None):
        """
        发送HTML格式邮件（不再需要复杂的格式化）
        """
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        print(f"发送邮件给：{len(email_config['email_receiver'])} 个收件人")
        receivers = ','.join(email_config['email_receiver'])

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
            msg['From'] = email_config['email_sender']
            msg['To'] = receivers
            
            # 直接附加HTML内容
            msg.attach(MIMEText(html_content, 'html', 'utf-8'))
            
            # 发送邮件（使用SSL连接，更稳定）
            with smtplib.SMTP_SSL(email_config['smtp_server'], 465, timeout=10) as server:
                server.login(email_config['email_sender'], email_config['email_password'])
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
                with smtplib.SMTP(email_config['smtp_server'], 587, timeout=10) as server:
                    server.starttls()
                    server.login(email_config['email_sender'], email_config['email_password'])
                    server.send_message(msg)
                print("✅ 使用TLS连接发送成功！")
                return True
            except Exception as e2:
                print(f"❌ TLS连接也失败: {e2}")
                return False

    def test_email_sending(self, ai_output, email_config):

        
        # 使用你提供的AI输出作为测试内容
        test_ai_content = ai_output
        
        # 测试发送
        print("Sending Email...")
        success = self.send_html_email(test_ai_content, email_config, )
        
        if success:
            print("邮件已发送。")
        else:
            print("发送失败，请检查配置。")

    def run(self):
        print(f"📅 Target Date: {self.target_date1} to {self.target_date2}")

        print('fetching papers ...')
        papers_GA = self.get_arxiv_papers('astro-ph.GA')
        papers_LSS = self.get_arxiv_papers('astro-ph.CO')
        papers = papers_GA + papers_LSS

        print('parsing papers ...')

        n_papers = self.print_papers_summary(papers)
        if n_papers == 0:
            print("今日未抓取到相关论文，终止运行。")
            return
        print('analyzing papers with DeepSeek ...')
        ai_output = self.analyze_papers_with_deepseek(papers,)
        print('sending email ...')
        self.test_email_sending(ai_output,email_config=self.config)

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

    
