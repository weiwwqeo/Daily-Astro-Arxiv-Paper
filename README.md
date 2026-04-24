# Daily-Astro-Arxiv-Paper
Daily. Get papers about high-z galaxies and galactic cosmology on Arxiv, filter interested ones, translate (to Chinese/ 翻译成中文) and send email to specific users.


- 📅 自动运行：每天运行 (UTC 21:40 / 北京时间次日 05:40, UTC+8)，默认抓取前两天到前一天（D-2 到 D-1）论文 
- 🤖 智能分析：使用LLM筛选High-z Galaxy相关Paper
- 📧 邮件发送：生成HTML格式邮件

## Quick Start

1. Fork
2. Set GitHub Secrets
   在仓库设置中 (`Settings → Secrets → Actions → New repository secret`) 添加：
    
    | Secret | 说明 |
    |--------|------|
    | `DEEPSEEK_API_KEY` | DeepSeek API密钥 |
    | `EMAIL_SENDER` | 发件邮箱（QQ邮箱） |
    | `EMAIL_PASSWORD` | QQ邮箱授权码 |
    | `EMAIL_RECEIVER` | 收件邮箱，用逗号隔开， e.g. abc@gmail.com,ddd@qq.com|


3. Test
  "Actions" 标签页 -- 选择 "Daily Galactic Cosmology Paper Digest" 工作流 -- 点击 "Run workflow" 输入日期 `YYYYMMDD`（也兼容 `YYYY-MM-DD`）手动运行 -- 检查邮箱是否收到测试邮件

## Notes
以下是本project采用的设置，可以根据你自己的需要更改`your_paper_bot.py`。
* 邮件部分用的是qq mail，可以自行修改。
* 目前LLM用的是Deepseek V3.2 (思考），可以自行选择。请确认API-key有效，额度充足。一次运行消耗token不超过0.1¥。
* 本project基于arxiv的API，感兴趣的领域（e.g. astro-ph.EP,astro-ph.GA 等）可以自己更改
* LLM一次性接受和输出的token长度有最大限制，如果当天筛选出的相关paper太多，可能导致输出不完整。

*Developing*
