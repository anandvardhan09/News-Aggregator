# app.py - Main Flask application with MongoDB
from flask import Flask, jsonify, request
from flask_cors import CORS
import feedparser
import requests
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
import logging
from typing import List, Dict
import re
import hashlib
import json
from pymongo import MongoClient
from bson import ObjectId

load_dotenv()

app = Flask(__name__)
CORS(app)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
HF_API_KEY = os.getenv('HF_API_KEY', '')
HF_API_URL = "https://api-inference.huggingface.co/models/facebook/bart-large-cnn"
MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/ai_news')

# Initialize MongoDB
try:
    client = MongoClient(MONGODB_URI)
    db = client.get_default_database() if MONGODB_URI != 'mongodb://localhost:27017/ai_news' else client.ai_news
    articles_collection = db.articles
    sources_collection = db.sources
    logger.info("MongoDB connected successfully")
except Exception as e:
    logger.error(f"MongoDB connection failed: {str(e)}")
    client = None
    db = None

# News sources (RSS feeds)
NEWS_SOURCES = [
    {'name': 'TechCrunch AI', 'url': 'https://techcrunch.com/category/artificial-intelligence/feed/', 'active': True},
    {'name': 'VentureBeat AI', 'url': 'https://venturebeat.com/ai/feed/', 'active': True},
    {'name': 'MIT Technology Review', 'url': 'https://www.technologyreview.com/feed/', 'active': True},
    {'name': 'The Verge AI', 'url': 'https://www.theverge.com/ai-artificial-intelligence/rss/index.xml', 'active': True},
    {'name': 'AI News', 'url': 'https://artificialintelligence-news.com/feed/', 'active': True},
]

class NewsAggregator:
    def __init__(self):
        self.articles = []
        self.initialize_sources()
    
    def initialize_sources(self):
        """Initialize sources in MongoDB"""
        if db is not None:
            try:
                for source in NEWS_SOURCES:
                    sources_collection.update_one(
                        {'name': source['name']},
                        {'$set': source},
                        upsert=True
                    )
            except Exception as e:
                logger.error(f"Error initializing sources: {str(e)}")
    
    def fetch_articles(self, hours_back: int = 24) -> List[Dict]:
        """Fetch articles from all news sources"""
        cutoff_time = datetime.now() - timedelta(hours=hours_back)
        
        # Try to get cached articles from MongoDB first
        if db is not None:
            try:
                cached_articles = list(articles_collection.find({
                    'published': {'$gte': cutoff_time.isoformat()},
                    'created_at': {'$gte': cutoff_time}
                }).sort('published', -1))
                
                if cached_articles:
                    # Convert ObjectId to string for JSON serialization
                    for article in cached_articles:
                        article['_id'] = str(article['_id'])
                    logger.info(f"Returning {len(cached_articles)} cached articles")
                    return cached_articles
            except Exception as e:
                logger.error(f"Error fetching cached articles: {str(e)}")
        
        # Fetch fresh articles if no cache or cache is old
        all_articles = []
        active_sources = self.get_active_sources()
        
        for source in active_sources:
            try:
                logger.info(f"Fetching from {source['name']}")
                feed = feedparser.parse(source['url'])
                
                for entry in feed.entries:
                    # Parse publish date
                    published = datetime.now()
                    if hasattr(entry, 'published_parsed') and entry.published_parsed:
                        published = datetime(*entry.published_parsed[:6])
                    
                    # Only include recent articles
                    if published > cutoff_time:
                        # Create unique ID for deduplication
                        content = self.clean_html(getattr(entry, 'summary', ''))
                        article_id = hashlib.md5((entry.title + source['name']).encode()).hexdigest()
                        
                        article = {
                            'id': article_id,
                            'title': entry.title,
                            'summary': getattr(entry, 'summary', ''),
                            'link': entry.link,
                            'published': published.isoformat(),
                            'source': source['name'],
                            'content': content,
                            'ai_summary': '',
                            'sentiment': 'neutral',
                            'created_at': datetime.now(),
                            'updated_at': datetime.now()
                        }
                        
                        # Generate AI summary and sentiment
                        if article['content']:
                            article['ai_summary'] = self.summarize_article(article['content'])
                            article['sentiment'] = self.get_sentiment(article['title'] + ' ' + article['content'][:200])
                        
                        all_articles.append(article)
                        
            except Exception as e:
                logger.error(f"Error fetching from {source['name']}: {str(e)}")
        
        # Remove duplicates and save to MongoDB
        unique_articles = self.remove_duplicates(all_articles)
        self.save_articles_to_db(unique_articles)
        
        return sorted(unique_articles, key=lambda x: x['published'], reverse=True)
    
    def get_active_sources(self) -> List[Dict]:
        """Get active sources from MongoDB or fallback to default"""
        if db is not None:
            try:
                sources = list(sources_collection.find({'active': True}))
                if sources:
                    return sources
            except Exception as e:
                logger.error(f"Error fetching sources from DB: {str(e)}")
        
        return NEWS_SOURCES
    
    def save_articles_to_db(self, articles: List[Dict]):
        """Save articles to MongoDB"""
        if db is not None and articles:
            try:
                for article in articles:
                    articles_collection.update_one(
                        {'id': article['id']},
                        {'$set': article},
                        upsert=True
                    )
                logger.info(f"Saved {len(articles)} articles to database")
            except Exception as e:
                logger.error(f"Error saving articles to DB: {str(e)}")
    
    def clean_html(self, text: str) -> str:
        """Remove HTML tags from text"""
        clean = re.compile('<.*?>')
        return re.sub(clean, '', text)
    
    def remove_duplicates(self, articles: List[Dict]) -> List[Dict]:
        """Remove duplicate articles based on title similarity"""
        seen_titles = set()
        unique_articles = []
        
        for article in articles:
            title_key = article['title'].lower().strip()
            if title_key not in seen_titles:
                seen_titles.add(title_key)
                unique_articles.append(article)
        
        return unique_articles
    
    def summarize_article(self, content: str) -> str:
        """Generate AI summary using Hugging Face API"""
        clean_content = self.clean_html(content)
        if len(clean_content) > 1000:
            clean_content = clean_content[:1000]
        
        if len(clean_content) < 50:
            return clean_content
        
        try:
            headers = {}
            if HF_API_KEY:
                headers["Authorization"] = f"Bearer {HF_API_KEY}"
            
            response = requests.post(
                HF_API_URL,
                headers=headers,
                json={
                    "inputs": clean_content,
                    "parameters": {
                        "max_length": 100,
                        "min_length": 30,
                        "do_sample": False
                    }
                },
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                if isinstance(result, list) and len(result) > 0:
                    return result[0].get('summary_text', clean_content[:200] + "...")
                elif isinstance(result, dict) and 'summary_text' in result:
                    return result['summary_text']
            
            return clean_content[:200] + "..." if len(clean_content) > 200 else clean_content
            
        except Exception as e:
            logger.error(f"Error generating summary: {str(e)}")
            return clean_content[:200] + "..." if len(clean_content) > 200 else clean_content
    
    def get_sentiment(self, text: str) -> str:
        """Get sentiment analysis using Hugging Face"""
        try:
            headers = {}
            if HF_API_KEY:
                headers["Authorization"] = f"Bearer {HF_API_KEY}"
            
            response = requests.post(
                "https://api-inference.huggingface.co/models/cardiffnlp/twitter-roberta-base-sentiment-latest",
                headers=headers,
                json={"inputs": text[:500]},
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                if isinstance(result, list) and len(result) > 0:
                    sentiment_data = result[0]
                    if isinstance(sentiment_data, list) and len(sentiment_data) > 0:
                        label = sentiment_data[0].get('label', 'neutral').lower()
                        # Map sentiment labels
                        if 'pos' in label:
                            return 'positive'
                        elif 'neg' in label:
                            return 'negative'
                        else:
                            return 'neutral'
            
            return 'neutral'
        except Exception as e:
            logger.error(f"Error getting sentiment: {str(e)}")
            return 'neutral'

# Initialize aggregator
aggregator = NewsAggregator()

@app.route('/')
def health_check():
    return jsonify({
        'status': 'healthy', 
        'message': 'AI News Aggregator API is running',
        'mongodb_connected': db is not None,
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/news', methods=['GET'])
def get_news():
    """Get aggregated news articles"""
    try:
        hours_back = request.args.get('hours', 24, type=int)
        force_refresh = request.args.get('refresh', 'false').lower() == 'true'
        
        if force_refresh and db is not None:
            # Clear cache for forced refresh
            try:
                cutoff_time = datetime.now() - timedelta(hours=hours_back)
                articles_collection.delete_many({'created_at': {'$gte': cutoff_time}})
            except Exception as e:
                logger.error(f"Error clearing cache: {str(e)}")
        
        articles = aggregator.fetch_articles(hours_back)
        
        return jsonify({
            'success': True,
            'articles': articles,
            'count': len(articles),
            'last_updated': datetime.now().isoformat(),
            'cached': not force_refresh
        })
    except Exception as e:
        logger.error(f"Error fetching news: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/categories', methods=['GET'])
def get_categories():
    """Get article categories/topics"""
    try:
        articles = aggregator.fetch_articles(24)
        
        categories = {
            'Machine Learning': 0,
            'Natural Language Processing': 0,
            'Computer Vision': 0,
            'Robotics': 0,
            'Ethics & AI': 0,
            'Business & AI': 0,
            'Research': 0,
            'General': 0
        }
        
        keywords = {
            'Machine Learning': ['machine learning', 'ml', 'neural network', 'deep learning', 'algorithm'],
            'Natural Language Processing': ['nlp', 'language model', 'chatbot', 'text', 'gpt'],
            'Computer Vision': ['computer vision', 'image', 'vision', 'opencv', 'detection'],
            'Robotics': ['robot', 'robotics', 'autonomous', 'automation'],
            'Ethics & AI': ['ethics', 'bias', 'fairness', 'regulation', 'policy'],
            'Business & AI': ['business', 'startup', 'investment', 'market', 'company'],
            'Research': ['research', 'paper', 'study', 'university', 'academic']
        }
        
        for article in articles:
            text = (article['title'] + ' ' + article['content']).lower()
            categorized = False
            
            for category, category_keywords in keywords.items():
                if any(keyword in text for keyword in category_keywords):
                    categories[category] += 1
                    categorized = True
                    break
            
            if not categorized:
                categories['General'] += 1
        
        return jsonify({
            'success': True,
            'categories': categories
        })
    except Exception as e:
        logger.error(f"Error getting categories: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/sources', methods=['GET'])
def get_sources():
    """Get available news sources"""
    try:
        sources = aggregator.get_active_sources()
        return jsonify({
            'success': True,
            'sources': sources
        })
    except Exception as e:
        logger.error(f"Error getting sources: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/summarize', methods=['POST'])
def summarize_article():
    """Summarize a specific article"""
    try:
        data = request.get_json()
        content = data.get('content', '')
        
        if not content:
            return jsonify({'success': False, 'error': 'Content is required'}), 400
        
        summary = aggregator.summarize_article(content)
        
        return jsonify({
            'success': True,
            'summary': summary
        })
    except Exception as e:
        logger.error(f"Error summarizing article: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/sentiment', methods=['POST'])
def analyze_sentiment():
    """Analyze sentiment of text"""
    try:
        data = request.get_json()
        text = data.get('text', '')
        
        if not text:
            return jsonify({'success': False, 'error': 'Text is required'}), 400
        
        sentiment = aggregator.get_sentiment(text)
        
        return jsonify({
            'success': True,
            'sentiment': sentiment
        })
    except Exception as e:
        logger.error(f"Error analyzing sentiment: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)