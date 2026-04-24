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
        
    except ModuleNotFoundError as e:
        missing_module = getattr(e, "name", "")
        if missing_module in ('github_config', 'your_paper_bot'):
            print(f'❌ 导入错误: {e}')
            print('请确保以下文件存在:')
            print('  - github_config.py')
            print('  - your_paper_bot.py')
        else:
            print(f'❌ 依赖缺失: {missing_module}')
            print('请先安装依赖: python -m pip install -r requirements.txt')
        sys.exit(1)
    except ImportError as e:
        print(f'❌ 导入错误: {e}')
        print('请检查依赖与本地文件是否完整。')
        sys.exit(1)
    except Exception as e:
        print(f'❌ 运行错误: {e}')
        sys.exit(1)

if __name__ == '__main__':
    main()
