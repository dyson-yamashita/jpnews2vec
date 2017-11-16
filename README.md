# JpNews2vec

JpNews2vec create word2vec and doc2vec models from japanese news articles.
The JpNews2vec uses gensim to create the models.

## Confirmed environments
- Python 3.5.2 :: Anaconda custom (64-bit)
- gensim: 1.0.1
- sqlite3: 2.6.0
- MeCab: 0.996
- pyquery: 1.2.17

etc.

## Tutorial

### Git clone
git clone https://github.com/dyson-yamashita/jpnews2vec.git

### Prepare SQLite3 DB schema
```
$ cd jpnews2vec/data 
$ sqlite3 news.db
```
Create SQLite3 tables.
```
CREATE TABLE news (
        id integer PRIMARY KEY,
        title text UNIQUE,
        category text,
        date text,
        url text,
        article text,
        article_wakati text,
        recommended integer);

CREATE TABLE scores (
        id integer PRIMARY KEY,
        word text,
        score REAL,
        deleted integer);
```

### Get news articles
```
cd ../jpnews2vec
python news_batch.py
```
It takes a few minutes.


## Sample
```python
import sys
sys.path.append('../jpnews2vec')
from news import NewsML

# Specify positive words(keywords).
news_ml = NewsML(positives=['AI'])

# Get news articles(same news_batch.py).
news_ml.updateNews()

# Create word2vec and doc2vec models.
news_ml.buildModel()

# Get words that similar positive words.
news_ml.saveWordWeights()

# Get recommend articles.
# Argument topn is number of articles.
news_ml.getRecomendAirticles(topn=3)
```
