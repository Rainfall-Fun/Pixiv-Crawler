import scrapy
import re
from urllib import parse
from ..utils.PixivError import *
from ..items import ImageItem
from scrapy.http.cookies import CookieJar
import requests
import codecs
import configparser
import os
import json
from ..settings import prj_dir
import math
from scrapy import Spider
from scrapy import signals
from ..utils.imgData import ImgData
import pickle

cf = configparser.ConfigParser()
os.chdir(prj_dir)
cf.read_file(codecs.open("settings.ini", 'r', 'utf-8-sig'))

class pixivSpider(Spider):
    name = "pixivSpider"
    def __init__(self):
        super().__init__()
        self.DAILY_ST = cf.getint('DAILY', 'FROM')
        self.DAILY_END = cf.getint('DAILY', 'TO')
        start_page = (self.DAILY_ST-1)//50+1
        end_page = math.ceil(self.DAILY_END/50)+1
        self.ENTRY_URLS = {
            'COLLECTION': 'https://www.pixiv.net/bookmark.php',
            'ARTIST': ['https://www.pixiv.net/member_illust.php?id={0}'.format(pid) for pid in cf.get('ART', 'ID').split(' ')],
            'SEARCH': 'https://www.pixiv.net/search.php?s_mode=s_tag&word={0}'.format('%20'.join(cf.get('SRH', 'TAGS').split(" "))),
            'DAILY': ['https://www.pixiv.net/ranking.php?mode=daily&p={0}&format=json'.format(i) for i in range(start_page, end_page)],
        }
        self.ENTRY_FUNC = {
            'COLLECTION': self.collection,
            'ARTIST': self.artist,
            'SEARCH': self.search,
            'DAILY': self.daily
        }
        self.R18 = cf.getboolean('IMG', 'R18')
        self.MIN_WIDTH = cf.getint('IMG', 'MIN_WIDTH')
        self.MIN_HEIGHT = cf.getint('IMG', 'MIN_HEIGHT')
        self.MIN_FAV = cf.getint('IMG', 'MIN_FAV')
        self.entry = cf.get('PRJ', 'TARGET')
        self.account = cf.get('PRJ', 'ACCOUNT')
        self.password = cf.get('PRJ', 'PASSWORD')
        self.MULTI_IMAGE_ENABLED = cf.getboolean('IMG', 'MULTI_IMG_ENABLED')
        self.data = []
        self.maxsize = 1e9
        self.collection_num = -1
        self.process = 0
        self.all = 0

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super(pixivSpider, cls).from_crawler(crawler, *args, **kwargs)
        crawler.signals.connect(spider.spider_closed, signal=signals.spider_closed)
        return spider

    # allowed_domains = []
    start_urls = ['https://accounts.pixiv.net/login?lang=zh&source=pc&view_type=page&ref=wwwtop_accounts_index']
    agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/60.0.3112.113 Safari/537.36"

    header = {
        'Origin': 'https://accounts.pixiv.net',
        # 'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/54.0.2840.59 Safari/537.36',
        'User-Agent': agent,
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'Referer': 'https://accounts.pixiv.net/login?lang=zh&source=pc&view_type=page&ref=wwwtop_accounts_index',
        'X-Requested-With': 'XMLHttpRequest',
    }
    cookie = 'p_ab_id=3; p_ab_id_2=4; bookmark_tag_type=count; bookmark_tag_order=desc; show_welcome_modal=1; ' \
             'module_orders_mypage=%5B%7B%22name%22%3A%22recommended_illusts%22%2C%22visible%22%3Atrue%7D%2C%7B%2' \
             '2name%22%3A%22everyone_new_illusts%22%2C%22visible%22%3Atrue%7D%2C%7B%22name%22%3A%22following_new_il' \
             'lusts%22%2C%22visible%22%3Atrue%7D%2C%7B%22name%22%3A%22mypixiv_new_illusts%22%2C%22visible%22%3Atrue%7' \
             'D%2C%7B%22name%22%3A%22fanbox%22%2C%22visible%22%3Atrue%7D%2C%7B%22name%22%3A%22featured_tags%22%2C%22vis' \
             'ible%22%3Atrue%7D%2C%7B%22name%22%3A%22contests%22%2C%22visible%22%3Atrue%7D%2C%7B%22name%22%3A%22sense' \
             'i_courses%22%2C%22visible%22%3Atrue%7D%2C%7B%22name%22%3A%22spotlight%22%2C%22visible%22%3Atrue%7D%2' \
             'C%7B%22name%22%3A%22booth_follow_items%22%2C%22visible%22%3Atrue%7D%5D; device_token=480d576b6ad09b5a6' \
             '02e6f6fbb4b9593; __utmt=1; PHPSESSID=9deed4b733371c19ed8a86cf5b0c1c18; __utma=235335808.2088567130.' \
             '1501534936.1505413439.1505417847.41; __utmb=235335808.2.10.1505417847; __utmc=235335808; __utmz=235335808' \
             '.1505333595.35.9.utmcsr=accounts.pixiv.net|utmccn=(referral)|utmcmd=referral|utmcct=/login; __utmv=235335808' \
             '.|2=login%20ever=yes=1^3=plan=normal=1^5=gender=male=1^6=user_id=17759808=1^9=p_ab_id=3=1^10=p_ab_id_2=4=1^11' \
             '=lang=zh=1; login_bc=1; _ga=GA1.2.2088567130.1501534936; _gid=GA1.2.321153936.1505067374; _ga=GA1.3.2088567130.' \
             '1501534936; _gid=GA1.3.321153936.1505067374'

    # 入口
    def start_requests(self):
        if os.path.isfile(os.path.join(prj_dir, '.cookie')):
            #TODO: cookie不正确时跳转至login
            return self.center(None)
        else:
            return [scrapy.Request(self.start_urls[0], headers=self.header, callback=self.login )]

    def login(self, response):
        index_request = requests.get('http://www.pixiv.net', headers=self.header)
        index_cookie = index_request.cookies
        index_html = index_request.text
        pixiv_token = re.search(r'pixiv.context.token = (")(.*?)(")', index_html).group()
        start = pixiv_token.find('"')
        token = pixiv_token[start + 1:-1]
        # post_key = re.match('.*"pixivAccount.postKey":"(\w+?)"', response.text, re.S).group(1)
        print("please login")
        account = self.account if self.account else input("account >")
        password = self.password if self.password else input("password >")
        post_data = {
            "pixiv_id": account,
            "password": password,
            "captcha": "",
            "g_recaptcha_response": "",
            "post_key": token,
            "source": "pc",
            "ref": "wwwtop_accounts_index",
            "return_to": "http://www.pixiv.net/",
        }
        return [scrapy.FormRequest("https://accounts.pixiv.net/api/login?lang=zh",
                                   headers=self.header, formdata=post_data,
                                   callback=self.center, cookies=dict(index_cookie))]

    # 功能分支
    def center(self, response):
        self.process = 0
        # print(self.ENTRY_URLS[self.entry])
        if isinstance(self.ENTRY_URLS[self.entry], str):
            yield scrapy.Request(self.ENTRY_URLS[self.entry], headers=self.header, callback=self.ENTRY_FUNC[self.entry])
        else:
            print(len(self.ENTRY_URLS[self.entry]))
            for url in self.ENTRY_URLS[self.entry]:
                yield scrapy.Request(url, headers=self.header,
                                     callback=self.ENTRY_FUNC[self.entry])

    def collection(self, response):
        self.update_process(response, ".column-label .count-badge::text", 'Crawling collections...')
        image_items = response.css('._image-items.js-legacy-mark-unmark-list li.image-item')
        self.process+=len(image_items)
        all_collection_urls = []
        for image_item in image_items:
            # 对于已经删除的图片 可能会包含在image_items中，但无法提取bookmark，在转为int时报错，程序到此终止
            img_bookmark = image_item.css('ul li a.bookmark-count._ui-tooltip::text').extract_first('')
            if img_bookmark and  int(img_bookmark) >= self.MIN_FAV:
                all_collection_urls.append(image_item.css('a.work._work::attr(href)').extract_first(''))
        all_collection_urls = [parse.urljoin(response.url, url) for url in all_collection_urls]
        next_page_url = response.css('.column-order-menu .pager-container .next ._button::attr(href)').extract_first("")
        # ???
        if self.tryNextPage(next_page_url):
            next_page_url = parse.urljoin(response.url, next_page_url)
            yield scrapy.Request(next_page_url, headers=self.header, callback=self.collection)
        for url in all_collection_urls:
            yield scrapy.Request(url, headers=self.header, callback=self.image_page)

    def artist(self, response):
        self.update_process(response, "div._unit.manage-unit span.count-badge::text",
                            "Artist: {0}".format(response.css("._user-profile-card .profile a.user-name::text").extract_first('unknown')))
        all_works_url = response.css('ul._image-items li.image-item a.work._work::attr(href)').extract()
        all_works_url = [parse.urljoin(response.url, url) for url in all_works_url]
        self.process+=len(all_works_url)
        next_page_url = response.css('.column-order-menu .pager-container .next ._button::attr(href)').extract_first("")
        if self.tryNextPage(next_page_url):
            next_page_url = parse.urljoin(response.url, next_page_url)
            yield scrapy.Request(next_page_url, headers=self.header, callback=self.artist)
        for url in all_works_url:
            yield scrapy.Request(url, headers=self.header, callback=self.image_page)

    def search(self, response):
        if len(self.data) > self.maxsize:
            return
        js_text = response.css("div.layout-body div._unit input#js-mount-point-search-result-list::attr(data-items)").extract_first('Not Found')
        if js_text == "Not Found":
            print("json接口变动，烦请issue")
        js = json.loads(js_text)
        self.update_process(response, '._unit .column-header span.count-badge::text', 'Searching {0}'.format(cf.get('SRH', 'TAGS')))
        # image_items = response.css("ul li.image-item")
        self.process += len(js)
        all_works_url = []
        for image_item in js:
            if image_item["bookmarkCount"] >= self.MIN_FAV:
                all_works_url.append(('https://www.pixiv.net/member_illust.php?mode=medium&illust_id={0}'.format(image_item["illustId"]),
                                      image_item['bookmarkCount']))
        next_page_url = response.css('.column-order-menu .pager-container .next ._button::attr(href)').extract_first("")
        if self.tryNextPage(next_page_url):
            next_page_url = parse.urljoin(response.url, next_page_url)
            yield scrapy.Request(next_page_url, headers=self.header, callback=self.search)
        for url, bookmarkCount in all_works_url:
            request = scrapy.Request(url, headers=self.header, callback=self.image_page)  # 就是这里改成提取数据
            request.meta['collection'] = bookmarkCount
            yield request

    def daily(self, response):
        self.all = self.DAILY_END - self.DAILY_ST + 1
        print("crawling process {0}/{1}".format(self.process, self.all))
        js = json.loads(response.text)
        for image_item in js['contents']:
            if not (image_item['rank'] < self.DAILY_ST or image_item['rank'] > self.DAILY_END):
                self.process += 1
                yield scrapy.Request('https://www.pixiv.net/member_illust.php?mode=medium&illust_id={0}'.format(image_item['illust_id']),
                                     headers=self.header, callback=self.image_page)

    def image_page(self, response):
        if len(self.data) >= self.maxsize:
            return
        all_img_data = response.css('._unit._work-detail-unit .work-info ul li::text').extract()
        if 'R-18' in all_img_data[-1]:
            r18 = True
        else:
            r18 = False
        # R18 总在最后一个 多张作品与分辨率不兼容
        name = response.css("._unit._work-detail-unit .work-info h1.title::text").extract_first('')  # 没有把name传递到多图部分，多图部分没有log name
        img_title = response.css('section.work-info h1.title::text').extract_first("")
        img_title = img_title.replace(os.sep, '_')
        img_title = img_title.replace('/', '_')
        pid = re.match('.*id=(\d+)' ,response.request._url).group(1)
        view = int(response.css(".work-info .score dl .view-count::text").extract_first('-1'))
        praise = int(response.css(".work-info .score dl .rated-count::text").extract_first('-1'))
        try:
            print("Crawling {0}".format(name))
        except Exception as e:
            print("log部分暂未处理日语编码问题 不影响下载")
            pass
        finally:
            pass
        for img_data in all_img_data:
            # print(img_data)
            if '多张作品' in img_data:
                # self.data.append(ImgData(img_title, pid, r18, view, praise, response.meta['collection']))
                # return
                if self.MULTI_IMAGE_ENABLED:
                    see_more = response.css('.works_display .read-more.js-click-trackable::attr(href)').extract_first("")
                    see_more = parse.urljoin(response.url, see_more)
                    yield scrapy.Request(see_more, callback=self.multiImgPage)
                    return
                else:
                    return
            if '×' in img_data:
                img_width, img_height = list(map(int, img_data.split('×')))



        if (img_width < self.MIN_WIDTH or img_height < self.MIN_HEIGHT) or (self.R18 ^ r18):
            return
        self.data.append(ImgData(img_title, pid, r18, view, praise, response.meta['collection'], img_height, img_width))
        img_item = ImageItem()
        img_url = response.css('div._illust_modal.ui-modal-close-box div.wrapper img.original-image::attr(data-src)').extract_first('')
        img_title = response.css('section.work-info h1.title::text').extract_first("")
        if not img_url:
            raise UnmatchError("Unsupported gif image or not enough authority to visit the page when crawling {0}".format(response.url))
        img_item["img_url"] = [img_url]
        img_item['title'] = img_title
        img_item['pid'] = re.match('.*/(\d+)_p0.*', img_url).group(1)
        img_item['referer'] = response.url
        yield img_item

    def multiImgPage(self, response):
        # 多张图片的分辨率筛选交给pipeline去做
        son_urls = response.css('.manga .item-container a.full-size-container._ui-tooltip::attr(href)').extract()
        son_urls = [parse.urljoin(response.url, url) for url in son_urls]
        for url in son_urls:
            yield scrapy.Request(url, callback=self.multiImgPageSingle)

    # 未添加title
    def multiImgPageSingle(self, response):
        img_title = response.css('head title::text').extract_first("")
        img_title = img_title.replace(os.sep, '_')
        img_title = img_title.replace('/', '_')
        img_url = response.css('body img::attr(src)').extract_first("")
        img_item = ImageItem()
        img_item["img_url"] = [img_url]
        img_item["title"] = img_title
        img_item['pid'] = re.match('.*/(\d+_p\d*).*', img_url).group(1)
        img_item['referer'] = response.url
        yield img_item

    def update_process(self, response, restr, log):
        # 适用于 xxx件
        if self.collection_num == -1:
            print("login successfully")
            # print(log.encode('gbk').decode('gbk'))  # 由于控制台程序中会出编码问题，这里先取消log 不会
            self.collection_num = response.css(restr).extract_first('')[:-1]
            print("found {0} result(s)".format(self.collection_num))
            if not self.collection_num:
                raise UnmatchError("collection_num not matched")
            self.all = self.collection_num
        else:
            print("crawling process {0}/{1}".format(self.process, self.all))

    def tryNextPage(self, next_page_url):
        if next_page_url:
            return True
        else:
            print("reached the last page")
            return False

    def spider_closed(self, spider):
        f = open("data_{0}.json".format('_'.join(cf.get('SRH', 'TAGS').split(" "))), 'w')
        # pickle.dump(self.data, f, 0)
        # li = [item.__dict__() for item in self.data]
        data = [item.__dict__() for item in self.data]
        json.dump(data, f)
        print("Crawling complete, got {0} data".format(len(self.data)))
        f.close()


