# github_config.py
import os

def get_github_config():
    """从GitHub环境变量获取配置"""
    target_date1 = os.environ.get('TARGET_DATE1', '')
    target_date2 = os.environ.get('TARGET_DATE2', '')
    
    # 如果没有指定日期，默认抓取前两天到前一天（D-2 到 D-1）
    if not target_date1:
        from datetime import datetime, timedelta, timezone
        now_utc = datetime.now(timezone.utc)
        target_date1 = (now_utc - timedelta(days=2)).strftime('%Y%m%d')
        target_date2 = (now_utc - timedelta(days=1)).strftime('%Y%m%d')
    if not target_date2:  # 仅指定了 target_date1 时，target_date2 与其一致
        target_date2 = target_date1

    # 兼容 YYYY-MM-DD 与 YYYYMMDD 两种输入
    target_date1 = target_date1.replace('-', '')
    target_date2 = target_date2.replace('-', '')

    # 清理并过滤空收件人
    raw_receivers = os.environ.get('EMAIL_RECEIVER', '')
    email_receivers = [x.strip() for x in raw_receivers.split(',') if x.strip()]

    thinking_raw = os.environ.get('THINKING', 'true').strip().lower()
    thinking = thinking_raw in ('1', 'true', 'yes', 'on')
    
    return {
        'target_date1': target_date1,
        'target_date2': target_date2,
        'deepseek_api_key': os.environ.get('DEEPSEEK_API_KEY', ''),
        'deepseek_model': os.environ.get('DEEPSEEK_MODEL', '').strip(),
        'temperature': 0.3,
        'max_tokens': 8192,
        'thinking': thinking,
        'email_sender': os.environ.get('EMAIL_SENDER', ''),
        'email_password': os.environ.get('EMAIL_PASSWORD', ''),
        'smtp_server': os.environ.get('SMTP_SERVER', 'smtp.qq.com'),
        'smtp_port': int(os.environ.get('SMTP_PORT', '587')),
        'email_receiver': email_receivers,
        # arXiv抓取容错参数（固定配置，不依赖环境变量）
        'arxiv_delay_seconds': 3.0,
        'arxiv_num_retries': 3,
        'arxiv_fetch_attempts': 4,
        'arxiv_backoff_seconds': 8.0,
        # DeepSeek分块并发参数（固定配置，不依赖环境变量）
        'deepseek_chunk_size': 10,
        'deepseek_parallel_workers': 4,
        'deepseek_retry_attempts': 3,
        'deepseek_backoff_seconds': 4.0,
    }
