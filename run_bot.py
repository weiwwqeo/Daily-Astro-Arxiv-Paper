import os
import sys

def main():
    try:
        from github_config import get_github_config
        from your_paper_bot import DailyPaperBot 
        print('running DailyPaperBot')
        config = get_github_config()
        bot = DailyPaperBot(config)
        bot.run()
        
    except ImportError as e:
        print(f'❌ 导入错误: {e}')
        print('请确保以下文件存在:')
        print('  - github_config.py')
        print('  - your_paper_bot.py (请替换为实际文件名)')
        sys.exit(1)
    except Exception as e:
        print(f'❌ 运行错误: {e}')
        sys.exit(1)

if __name__ == '__main__':
    main()
