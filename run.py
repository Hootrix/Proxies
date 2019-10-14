#!/usr/bin/env python
#-*- coding:utf-8 -*-
"""
@author: HJK
@modifier: Pang
"""
import os, sys, getopt, datetime, re, threading, platform, requests,json
from lxml import etree
import tempfile, zipfile

# SITES = ['http://www.proxyserverlist24.top/', 'http://www.live-socks.net/']
SITES = ['http://www.sslproxies24.top']
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; MSIE 10.0; Windows NT 6.2; Win64; x64; Trident/6.0)'}
TIMEOUT = 10
SPIDER_PROXIES = None
IP138 = 'http://2000019.ip138.com/'
IPDOTCN = 'http://ip.cn'

def echo(color, *args):
    colors = {'error': '\033[91m', 'success': '\033[94m', 'info': '\033[93m'}
    if not color in colors or platform.system() == 'Windows':
        print(' '.join(args))
    print(colors[color], ' '.join(args), '\033[0m')

def get_content(url, proxies=None, headers = HEADERS) -> requests.Response:
    ''' 根据URL和代理获得内容 '''
    echo('info', url)
    try:
        r = requests.get(url, headers=headers, proxies=proxies, timeout=TIMEOUT,allow_redirects=True, ) #允许跟踪连接跳转 针对新添加的ip.cn
        if r.status_code == requests.codes.ok:
            return r
        echo('error', '请求失败', str(r.status_code), url)
    except Exception as e:
        echo('error', url, str(e))
    o = lambda: None
    o.text = ''
    return o

def get_proxies_thread(site, proxies):
    ''' 爬取一个站的代理的线程 '''
    content = get_content(site, SPIDER_PROXIES).text
    pages = re.findall(r'<h3[\s\S]*?<a.*?(http.*?\.html).*?</a>', content)
    for page in pages:
        content = get_content(page, SPIDER_PROXIES).text
        findall_ = re.findall(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d{1,5}', content)
        if findall_:
            proxies += findall_
        else:#执行下载zip包中代理列表提取

            html = etree.fromstring(content, etree.HTMLParser())
            a_link = html.xpath('//*[contains(@class,"post-body")]/a')
            download_page_url = ''
            for i in a_link:
                href = i.attrib.get('href')
                if href and 'zip' in href:  # 存在zip关键字
                    download_page_url = href
                    break

            assert download_page_url, '未找到zip包下载页面链接'

            download_page_con = requests.get(download_page_url).text#打开zip包下载页面
            zip_url = re.search(r'href="(http[s]?://[^"]+\.zip[^"]*)"', download_page_con, re.I)
            zip_url = zip_url.group(1)#拿到zip下载url
            def get_file(filename,context):
                nonlocal proxies
                if filename.endswith('.txt'):
                    proxy_list = context.read(filename).decode('utf-8').split('\n')
                    proxies += proxy_list
                    # print( context.read(filename))
                    return False  # 终止下一个文件的读取

            read_file_for_zip(zip_url,get_file)

def get_proxies_set() -> list:
    ''' 获得所有站的代理并去重 '''
    spider_pool, proxies = [], []
    for site in SITES:
        t = threading.Thread(target=get_proxies_thread, args=(site, proxies))
        spider_pool.append(t)
        t.start()
    for t in spider_pool:
        t.join()
    return list(set(proxies))

def check_proxies_thread(check_url, proxies, callback):
    ''' 检查代理是否有效的线程 '''
    for proxy in proxies:
        proxy = proxy.strip()
        # proxy = proxy if proxy.startswith('http://') else 'http://' + proxy 可以直接ip地址
        content = get_content(check_url, proxies={'http': proxy,'https': proxy},headers={'User-Agent': 'curl/7.29.0'})# 检测http 和 https
        if content.text:
            if check_url == IP138:
                # 如果能获取到IP，则比对一下IP和代理所用IP一致则判断有效
                ip = re.findall(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', content)
                if ip and ip[0] in proxy:
                    callback(proxy)
            elif check_url == IPDOTCN:
                try:
                    if content.text and content.json()['ip'] in proxy:
                        callback(proxy)
                except json.decoder.JSONDecodeError as e:
                    echo('error', proxy, 'ip.cn response not json data.') #ip.cn请求的数据为非json
                    continue
            else:
                callback(proxy)

def check_and_save_proxies(check_url, proxies, output_file):
    ''' 验证和保存所有代理 '''
    checker_pool = []
    open(output_file, 'w').write('')
    def save_proxy(proxy):
        echo('success', proxy, 'checked ok.')
        open(output_file, 'a').write(proxy + '\n')
    for i in range(0, len(proxies), 20):
        t = threading.Thread(target=check_proxies_thread, args=(check_url, proxies[i:i+20], save_proxy))
        checker_pool.append(t)
        t.start()
    for t in checker_pool:
        t.join()


def read_file_for_zip(zip_url, callback=None):
    """
    读取zip包内的文件
    @author:Ho
    :param zip_url:zip路径/url
    :param callback:读取操作的回调函数 若函数返回false 则不会读取下一个文件
    :return:
    """
    with tempfile.TemporaryFile('w+b') as tmpfile:  # 生成临时文件

        # 判断是否为本地文件
        if os.path.isfile(zip_url):
            # 进行本地复制。没必要
            # with open(zip_url,'rb') as f:
            #     while True:
            #         chunk = f.read(1024)
            #         if not chunk:
            #             break
            #         tmpfile.write(chunk)
            tmpfile = zip_url
        else:  # 进行http请求
            r = requests.get(zip_url, stream=True)
            for chunk in r.iter_content(chunk_size=1024):
                if chunk:
                    tmpfile.write(chunk)
        assert zipfile.is_zipfile(tmpfile), '不是zip文件'
        zf = zipfile.ZipFile(tmpfile)
        for name in zf.namelist():  # list e.g. ['Brave Browser.url', 'Express VPN.url', 'ssl.txt', 'What is my IP.url']
            if callable(callback):
                # zf.read(name) #读取
                if callback(name, zf) is False:  # 函数返回false 会终止下一个文件的读取
                    break


if __name__ == '__main__':
    input_file, output_file, check_url = '', 'proxies.txt', IPDOTCN
    if len(sys.argv) > 1:
        try:
            opts, _ = getopt.getopt(sys.argv[1:], 'u:f:o:')
        except getopt.GetoptError as e:
            echo('error', str(e))
            sys.exit(2)
        for o, a in opts:
            if o in ('-f'): input_file = os.path.abspath(a)
            elif o in ('-u'): check_url = a
            elif o in ('-o'): output_file = os.path.abspath(a)
            else: assert False, 'unhandled option'
    start = datetime.datetime.now()
    proxies = open(input_file, 'r').readlines() if input_file else get_proxies_set()
    check_and_save_proxies(check_url, proxies, output_file)
    stop = datetime.datetime.now()
    note = '\n代理总数：%s\n有效代理数：%s\n结果文件：%s\n时间消耗：%s\n' % \
            (len(proxies), len(open(output_file, 'r').readlines()),
            output_file, stop - start)
    echo('success', note)
