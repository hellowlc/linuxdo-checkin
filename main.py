import os
import random
import time
import functools
import sys

from loguru import logger
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from tabulate import tabulate

# 重试装饰器保持不变
def retry_decorator(retries=3):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == retries - 1:  # 最后一次尝试
                        logger.error(f"函数 {func.__name__} 最终执行失败: {str(e)}")
                    else:
                        logger.warning(f"函数 {func.__name__} 第 {attempt + 1}/{retries} 次尝试失败: {str(e)}")
                    time.sleep(2)  # 增加等待时间，避免过于频繁重试
            return None  # 返回 None 表示失败
        return wrapper
    return decorator

os.environ.pop("DISPLAY", None)
os.environ.pop("DYLD_LIBRARY_PATH", None)

USERNAME = os.environ.get("USERNAME")
PASSWORD = os.environ.get("PASSWORD")

HOME_URL = "https://linux.do/"


class LinuxDoBrowser:
    def __init__(self) -> None:
        self.pw = sync_playwright().start()
        self.browser = self.pw.firefox.launch(headless=True, timeout=30000)  # 可以调整超时
        self.context = self.browser.new_context()
        self.page = self.context.new_page()
        self.page.goto(HOME_URL)
        self.page.wait_for_load_state("networkidle")  # 等待页面完全加载

    @retry_decorator(retries=5)  # 应用重试装饰器到 login 方法，增加重试次数
    def login(self):
        logger.info("开始登录")
        
        try:
            # 等待登录按钮可见、可交互，并设置较长的超时时间
            self.page.wait_for_selector(".login-button .d-button-label", state="visible", timeout=60000)
            
            # 点击登录按钮
            self.page.click(".login-button .d-button-label")
            
            # 等待可能的弹窗或 iframe 加载（例如 Google 登录对话框）
            # 如果知道 iframe 的选择器，可以添加等待
            try:
                self.page.wait_for_selector('iframe[title="Sign in with Google Dialog"]', state="visible", timeout=10000)
                # 如果需要切换到 iframe：
                # frame = self.page.frame_locator('iframe[title="Sign in with Google Dialog"]')
                # frame.locator("#some-element-in-iframe").click()  # 替换为实际元素
                logger.warning("检测到 Google 登录对话框，正在等待...")
            except PlaywrightTimeoutError:
                logger.info("未检测到额外对话框，继续操作。")
            
            # 填充用户名和密码
            self.page.wait_for_selector("#login-account-name", state="visible")
            self.page.fill("#login-account-name", USERNAME)
            
            self.page.wait_for_selector("#login-account-password", state="visible")
            self.page.fill("#login-account-password", PASSWORD)
            
            # 点击登录按钮
            self.page.wait_for_selector("#login-button", state="visible")
            self.page.click("#login-button")
            
            # 等待登录完成，检查用户元素出现
            self.page.wait_for_load_state("networkidle")  # 等待网络空闲
            self.page.wait_for_selector("#current-user", timeout=30000)  # 等待特定元素出现
            
            user_ele = self.page.query_selector("#current-user")
            if user_ele:
                logger.info("登录成功")
                return True
            else:
                logger.error("登录失败: 用户元素未找到")
                return False
        except PlaywrightTimeoutError as e:
            logger.error(f"登录超时: {str(e)}")
            raise  # 抛出异常，让装饰器捕获并重试
        except Exception as e:
            logger.error(f"登录过程中发生错误: {str(e)}")
            raise  # 抛出异常，让装饰器捕获

    def click_topic(self):
        topic_list = self.page.query_selector_all("#list-area .title")
        logger.info(f"发现 {len(topic_list)} 个主题帖")
        for topic in topic_list:
            self.click_one_topic(topic.get_attribute("href"))

    @retry_decorator()
    def click_one_topic(self, topic_url):
        page = self.context.new_page()
        page.goto(HOME_URL + topic_url)
        if random.random() < 0.3:  # 0.3 * 30 = 9
            self.click_like(page)
        self.browse_post(page)
        page.close()

    def browse_post(self, page):
        prev_url = None
        # 开始自动滚动，最多滚动10次
        for _ in range(10):
            # 随机滚动一段距离
            scroll_distance = random.randint(550, 650)  # 随机滚动 550-650 像素
            logger.info(f"向下滚动 {scroll_distance} 像素...")
            page.evaluate(f"window.scrollBy(0, {scroll_distance})")
            logger.info(f"已加载页面: {page.url}")

            if random.random() < 0.03:  # 33 * 4 = 132
                logger.success("随机退出浏览")
                break

            # 检查是否到达页面底部
            at_bottom = page.evaluate("window.scrollY + window.innerHeight >= document.body.scrollHeight")
            current_url = page.url
            if current_url != prev_url:
                prev_url = current_url
            elif at_bottom and prev_url == current_url:
                logger.success("已到达页面底部，退出浏览")
                break

            # 动态随机等待
            wait_time = random.uniform(2, 4)  # 随机等待 2-4 秒
            logger.info(f"等待 {wait_time:.2f} 秒...")
            time.sleep(wait_time)

    def run(self):
        if not self.login():
            logger.error("登录失败，程序终止")
            sys.exit(1)  # 使用非零退出码终止整个程序
        self.click_topic()
        self.print_connect_info()

    def click_like(self, page):
        try:
            # 专门查找未点赞的按钮
            like_button = page.locator('.discourse-reactions-reaction-button[title="点赞此帖子"]').first
            if like_button:
                logger.info("找到未点赞的帖子，准备点赞")
                like_button.click()
                logger.info("点赞成功")
                time.sleep(random.uniform(1, 2))
            else:
                logger.info("帖子可能已经点过赞了")
        except Exception as e:
            logger.error(f"点赞失败: {str(e)}")

    def print_connect_info(self):
        logger.info("获取连接信息")
        page = self.context.new_page()
        page.goto("https://connect.linux.do/")
        rows = page.query_selector_all("table tr")

        info = []

        for row in rows:
            cells = row.query_selector_all("td")
            if len(cells) >= 3:
                project = cells[0].text_content().strip()
                current = cells[1].text_content().strip()
                requirement = cells[2].text_content().strip()
                info.append([project, current, requirement])

        print("--------------Connect Info-----------------")
        print(tabulate(info, headers=["项目", "当前", "要求"], tablefmt="pretty"))

        page.close()


if __name__ == "__main__":
    if not USERNAME or not PASSWORD:
        print("Please set USERNAME and PASSWORD")
        exit(1)
    l = LinuxDoBrowser()
    l.run()
