# -*- coding: utf-8 -*-
import os
import os.path
import sys
import sqlite3
import json
import time
import MeCab
import numpy as np
import gensim
import datetime as dt
import urllib.request
import urllib.parse
from pyquery import PyQuery as pq
import re
import logging


class NewsBase:
    def __init__(self, dbfile):
        self.conn = sqlite3.connect(dbfile)
        logging.basicConfig(
            filename=os.getcwd()+'/../log/news_'+dt.datetime.now().strftime('%Y%m%d')+'.log',
            level=logging.ERROR)
        self.logger = logging.getLogger(__name__)

    def __del__(self):
        self.conn.close()
    
    def writeArticle(self, article):
        c = self.conn.cursor()
        try:
            c.execute("""
                INSERT INTO news(
                    title,
                    category,
                    date,
                    url,
                    article
                ) VALUES (?, ?, ?, ?, ?)""",
                [article['title'],
                 article['category'],
                 article['date'],
                 article['url'],
                 article['article']])
            self.conn.commit()
            self.logger.debug('Commit:' + article['title'])
        except sqlite3.IntegrityError as e:
            self.logger.debug('Not commit:' + article['title'] + str(e))
            self.conn.rollback()
            raise
        except sqlite3.OperationalError as e:
            self.logger.error(str(e))
            self.conn.close()
            sys.exit()
            
    def countArticles(self, title=''):
        conditions = ''
        if title:
            conditions = ' WHERE title =\'' + title + '\''
        c = self.conn.cursor()
        c.execute('SELECT count(*) FROM news' + conditions)
        (count,)=c.fetchone()
        return count

class YahooNews(NewsBase):
    def __init__(self, dbfile):
        super().__init__(dbfile)
        
    def __del__(self):
        super().__del__()
        
    def extractArticle(self, url):
        article = ''
        opener = urllib.request.build_opener()
        try:
            html = opener.open(urllib.request.Request(url)).read().decode('utf-8')
            time.sleep(2)

            if pq(html).find("a.newsLink:contains('[続きを読む]')"):
                detail_url = pq(html).find("a.newsLink:contains('[続きを読む]')").attr('href')
                html = opener.open(urllib.request.Request(detail_url)).read().decode('utf-8')
                time.sleep(1)
            if pq(html).find('p.ynDetailText'):
                article = pq(html).find('p.ynDetailText').text()
            elif pq(html).find('p.hbody'):
                article = pq(html).find('p.hbody').text()
            else:
                elems = pq(html).find('div,p,td')
                max_count = 0
                for el in elems:
                    count = 0
                    el_html = str(pq(el).html(method='html'))
                    if not '<script' in el_html:
                        count += el_html.count('。')
                        count += el_html.count('、')
                        count += el_html.count('！')
                        count += el_html.count('？')
                        if max_count < count:
                            article = pq(el).text()
                            max_count = count
            return article
        except urllib.error.HTTPError:
            return ''

    def updateNewsDB(self, page_no = 1):
        write_count = 0
        url = 'http://news.yahoo.co.jp/list/?p='+str(page_no)
        regex_date = r'^20'
        pattern_date = re.compile(regex_date)
        stop_flag = False

        opener = urllib.request.build_opener()
        html = opener.open(urllib.request.Request(url)).read().decode('utf-8')
        time.sleep(2)
        self.logger.debug(url)
        before_count = self.countArticles()
        for li in pq(html).find('ul.list').children():
            a = pq(li).find('a').eq(0)
            if a:
                title = pq(a).find('span.ttl').text()
                if self.countArticles(title) == 0:
                    date = pq(a).find('span.supple > span.date').text()
                    if not pattern_date.match(date):
                        date = str(dt.datetime.now().year)+'-'+date                    
                    date = re.sub(r'-(\d)',r'-0\1',date.split("(")[0].replace('/','-'))
                    href = pq(a).attr('href')
                    article = self.extractArticle(href)

                    if not article: self.logger.debug('Not found article:' + title + href)

                    try:
                        self.writeArticle({
                            'title':title,
                            'category': pq(a).find('span.supple > span.cate').text(),
                            'date': date,
                            'url': href,
                            'article': article
                        })
                        write_count += 1
                    except sqlite3.IntegrityError:
                        pass
                else:
                    self.logger.debug('Skip: ' + title + ' (registerd)')

            else:
                div = pq(li).find('div').eq(0)
                self.logger.debug('Not found link tag.', pq(div).find('span.ttl').text())

        after_count = self.countArticles()
        self.logger.debug('Update DB:' + str(before_count) + '->' + str(after_count))    

        if not write_count:
            raise Exception('No article was written.')


class MsnNews(NewsBase):
    def __init__(self, dbfile):
        super().__init__(dbfile)

    def __del__(self):
        super().__del__()

    def extractArticle(self, url):
        article = ''
        opener = urllib.request.build_opener()
        url = urllib.parse.quote_plus(url, "/:?=&")
        try:
            html = opener.open(urllib.request.Request(url)).read()#.decode('utf-8')
            time.sleep(2)
            article_tag = pq(html).find("div[data-aop='articlebody']")
            for p in pq(article_tag).find('p'):
                article += pq(p).text()
            return article
        except urllib.error.HTTPError:
            return ''

    def extractDate(self, url):
        regex_delta = r'([0-9]+)(日前)$'
        pattern_delta = re.compile(regex_delta)
        
        date = dt.datetime.now()
        opener = urllib.request.build_opener()
        url = urllib.parse.quote_plus(url, "/:?=&")
        try:
            html = opener.open(urllib.request.Request(url)).read()#.decode('utf-8')
            time.sleep(2)
            delta =  pq(html).find('span.time').eq(0).text()
            if pattern_delta.match(delta):
                m = pattern_delta.search(delta)
                date = date - dt.timedelta(days=(int(m.group(1))))
            return date.strftime("%Y-%m-%d")
        except urllib.error.HTTPError:
            return ''

    def updateNewsDB(self):
        write_count = 0
        base_url = 'http://www.msn.com'
        categories = {
            '国内': 'national',
            '海外': 'world',
            'ビジネス': 'money',
            'テクノロジー': 'techandscience',
            '話題': 'opinion',
            'エンタメ': 'entertainment',
            'スポーツ': 'sports'
        }
        regex_href = r'^/ja-jp/news/.+'
        pattern_href = re.compile(regex_href)
        stop_flag = False

        opener = urllib.request.build_opener()
        for cate_name, cate in categories.items():
            url = base_url+'/ja-jp/news/'+cate
            html = opener.open(urllib.request.Request(url)).read()
            time.sleep(2)
            self.logger.debug(url)
            before_count = self.countArticles()
            for a in pq(html).find('a'):
                if pattern_href.match(pq(a).attr('href')):
                    title = pq(a).text()
                    if self.countArticles(title) == 0:
                        href = base_url + pq(a).attr('href')
                        date = self.extractDate(href)
                        time.sleep(1)
                        category = cate_name
                        article = self.extractArticle(href)
                        if not article: self.logger.debug('Not found article:' + title + href)

                        try:
                            self.writeArticle({
                                'title':title,
                                'category': category,
                                'date': date,
                                'url': href,
                                'article': article
                            })
                            write_count += 1
                        except sqlite3.IntegrityError:
                            pass
                    else:
                        self.logger.debug('Skip: ' + title + ' (registerd)')


            after_count = self.countArticles()
            self.logger.debug('Update DB:' + str(before_count) + '->'+ str(after_count))    
            if not write_count:
                self.logger.debug('No article was written.')


class NewsML:
    data_path = os.getcwd() + '/../data/'
    dbfile = data_path + 'news.db'
    stop_word_file = data_path + 'ja_stop_words.txt'
    word2vec_file = data_path + 'news_model.word2vec.bin'
    doc2vec_file = data_path + 'news_model.doc2vec'
    apiUrl = 'https://www.googleapis.com/urlshortener/v1/url?key='
    ggl_api_key = ''
    positives = []
    neologd_path = '/usr/lib64/mecab/dic/mecab-ipadic-neologd'

    def __init__(self, positives = [], ggl_api_key = ''):
        logging.basicConfig(filename=os.getcwd()+'/../log/news.log',level=logging.ERROR)
        self.logger = logging.getLogger(__name__)
        self.positives = positives

    def updateNews(self):
        self.logger.info('Start: ' + sys._getframe().f_code.co_name)
        msn_news = MsnNews(self.dbfile)
        msn_news.updateNewsDB()

        yahoo_news = YahooNews(self.dbfile)
        start_page = 1
        last_page = start_page+10
        ex_count = 0
        for page_no in range(start_page,last_page+1):
            try:
                yahoo_news.updateNewsDB(page_no)
            except Exception as e:
                ex_count += 1
                if ex_count > 1:
                    break
        self.addArticleWakati()
        self.logger.info('Finish: ' + sys._getframe().f_code.co_name)


    def getStopWords(self):
        self.logger.info('Start: ' + sys._getframe().f_code.co_name)

        if not os.path.isfile(self.stop_word_file):
            url = 'http://svn.sourceforge.jp/svnroot/slothlib/CSharp/Version1/SlothLib/NLP/Filter/StopWord/word/Japanese.txt'
            urllib.request.urlretrieve(url, self.stop_word_file)
        
        slothlib_stopwords = [line.strip() for line in open(self.stop_word_file, 'r')]
        slothlib_stopwords = [ss for ss in slothlib_stopwords if not ss==u'']

        self.logger.info('Finish: ' + sys._getframe().f_code.co_name)

        return slothlib_stopwords + ['の', '[' ,']']


    def addArticleWakati(self):
        self.logger.info('Start: ' + sys._getframe().f_code.co_name)
        
        try:
            tagger = MeCab.Tagger(' -d ' + self.neologd_path)
        except RuntimeError as e:
            self.logger.error(str(e))
            sys.exit() 

        with sqlite3.connect(self.dbfile) as conn:
            c = conn.cursor()
            rows = c.execute("""
                SELECT title,article
                  FROM news
                  WHERE article !=''
                    AND article_wakati IS NULL
                  ORDER BY date""")
            

            tagger.parse('') #parseToNodeの引数型エラー回避

            count = 0
            stop_words = self.getStopWords()
            for (title, article) in rows:
                self.logger.debug('Target article : ' + title)

                node = tagger.parseToNode(article)
                article_wakati=[]
                while node:
                    features = node.feature.split(',')
                    if features[0] in ['名詞'] \
                        and not features[1] in ['数'] \
                        and node.surface not in stop_words:
                        article_wakati.append(node.surface)
                    node = node.next
                conn.execute("""
                    UPDATE news 
                      SET article_wakati=?
                      WHERE title=?""",[' '.join(article_wakati),title])
                conn.commit()
                count += 1
            self.logger.info('Add wakati count: ' + str(count))
        self.logger.info('Finish: ' + sys._getframe().f_code.co_name)


    def excludeNews(self, news_id):
        self.logger.info('Start: ' + sys._getframe().f_code.co_name)

        with sqlite3.connect(self.dbfile) as conn:
            conn.execute("""
                UPDATE news 
                  SET recommended=1
                  WHERE id=?""",[news_id])
            conn.commit()
        self.logger.info('Finish: ' + sys._getframe().f_code.co_name)


    def getSentences(self, dates=[], ex_recommend=False):
        sentences=[]
        with sqlite3.connect(self.dbfile) as conn:
            c = conn.cursor()
            condition_text = ''
            if len(dates) > 0 or ex_recommend:
                conditions = []
                if len(dates) > 0:
                    dates = list(map(lambda d: '\''+d+'\'', dates))
                    conditions.append('(date = '+' OR date = '.join(dates)+')')
                if ex_recommend:
                    conditions.append('(recommended IS NULL)')

                condition_text = ' WHERE ' + ' AND '.join(conditions)
            sql = 'SELECT title, article_wakati FROM news' + \
                condition_text + \
                ' ORDER BY date'
            self.logger.info('Sentence SQL: ' + sql)

            rows = c.execute(sql)

            for (title, article_wakati) in rows:
                article_words=str(article_wakati).split(" ")
                sentences.append(
                    gensim.models.doc2vec.LabeledSentence(
                        words=article_words,tags=[title]))
        return sentences


    def buildModel(self):
        self.logger.info('Start: ' + sys._getframe().f_code.co_name)

        model = gensim.models.Doc2Vec(alpha=.025, min_alpha=.025, min_count=5,size=200, window=5, workers=1)
        sentences = self.getSentences()
        model.build_vocab(sentences)
         
        for epoch in range(10):
            model.train(sentences,total_examples=model.corpus_count,epochs=model.iter)
            model.alpha -= 0.002
            model.min_alpha = model.alpha  

        model.wv.save_word2vec_format(self.word2vec_file,binary=True)
        self.logger.info('Save word2vec model: ' + self.word2vec_file)

        model.save(self.doc2vec_file)
        self.logger.info('Save doc2vec model: ' + self.doc2vec_file)

        self.logger.info('Finish: ' + sys._getframe().f_code.co_name)

    def saveWordWeights(self):
        word2vec_model = gensim.models.KeyedVectors.load_word2vec_format(self.word2vec_file,binary=True)

        weights = []
        for positive in self.positives:
            try:
                weights.append((positive, 1.0))
                weights += word2vec_model.most_similar(positive, topn=15)
            except KeyError as e:
                self.logger.debug(str(e))
        with sqlite3.connect(self.dbfile) as conn:
            c = conn.cursor()
            try:
                c.execute("UPDATE scores SET deleted=1")
                conn.commit()
            except sqlite3.IntegrityError as e:
                self.logger.debug('Not commit:' + article['title'] + str(e))
                conn.rollback()
                raise
            except sqlite3.OperationalError as e:
                self.logger.error(str(e))
                conn.close()
                sys.exit()

            for weight in weights:
                try:
                    c.execute("""
                        INSERT INTO scores(
                            word,
                            score
                        ) VALUES (?, ?)""",weight)
                    conn.commit()
                except sqlite3.IntegrityError as e:
                    self.logger.debug('Not commit:' + article['title'] + str(e))
                    conn.rollback()
                    raise
                except sqlite3.OperationalError as e:
                    self.logger.error(str(e))
                    conn.close()
                    sys.exit()

    def loadWordWeights(self):
        weights = []
        with sqlite3.connect(self.dbfile) as conn:
            c = conn.cursor()
            rows = c.execute("""
                SELECT word, score
                  FROM scores
                  WHERE deleted IS NULL
                  ORDER BY score""")
            weights = [row for row in rows]
        return weights
 
    def getRecomendAirticles(self, topn=1, short_url=False, term_days=1):
        self.logger.info('Start: ' + sys._getframe().f_code.co_name)

        scores = []
        tops = []
        now = dt.datetime.now()
        today = now.strftime("%Y-%m-%d")
        end_day = (now - dt.timedelta(days=term_days)).strftime("%Y-%m-%d")
        for sentence in self.getSentences(dates = [end_day, today], ex_recommend = True):
            words = sentence[0]
            title = sentence[1][0]
            weights = self.loadWordWeights()
            score = sum(map(lambda w,s=weights: sum([v for (k,v) in s if k == w]),words))/len(words)
            if(score > 0):
                scores.append([title,score])

        scores = sorted(scores, key=lambda t: t[1], reverse=True) # desc sort by score value
        with sqlite3.connect(self.dbfile) as conn:
            c = conn.cursor()
            for s in scores[:topn]:
                c.execute('SELECT id, url FROM news WHERE title = ?',[s[0]])
                (news_id, news_url,) = c.fetchone()
                if short_url:
                    news_url = self.getShortUrl(news_url)
                tops.append({'id':news_id, 'title':s[0], 'url':news_url})

        self.logger.info('Finish: ' + sys._getframe().f_code.co_name)
        return tops

    def getShortUrl(self, target_url):
        self.logger.info('Start: ' + sys._getframe().f_code.co_name)
        self.logger.debug('Target url: ' + target_url)

        obj = {'longUrl' : target_url} 
        json_data = json.dumps(obj).encode("utf-8")
        short_url = ''
        request = urllib.request.Request(
            self.apiUrl + self.ggl_api_key, 
            data = json_data, 
            method = 'POST',
            headers = {'Content-Type' : 'application/json'})
        with urllib.request.urlopen(request) as response:
            response_body = response.read().decode("utf-8")
            result_objs = json.loads(response_body)
            if 'id' in result_objs:
                short_url = result_objs['id']

        self.logger.debug('Short url: ' + target_url)
        self.logger.info('Finish: ' + sys._getframe().f_code.co_name)

        return short_url
