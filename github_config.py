# github_config.py
import os

def get_github_config():
    """从GitHub环境变量获取配置"""
    target_date1 = os.environ.get('TARGET_DATE1', '') 
    target_date2 = os.environ.get('TARGET_DATE2', '')
    
    # 如果没有指定日期，计算昨天的日期
    if not target_date1:
        from datetime import datetime, timedelta
        target_date1 = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    if not target_data2:
        target_date2 = target_date1
    
    return {
        'target_date1': target_date1,
        'target_date2': target_date2,
        'deepseek_api_key': os.environ.get('DEEPSEEK_API_KEY', ''),
        'temperature': 0.3,
        'max_tokens': 8192,
        'thinking': True,
        'email_sender': os.environ.get('EMAIL_SENDER', ''),
        'email_password': os.environ.get('EMAIL_PASSWORD', ''),
        'smtp_server': 'smtp.qq.com',
        'smtp_port': 587,
        'email_receiver': os.environ.get('EMAIL_RECEIVER', ''), # in list
    }

