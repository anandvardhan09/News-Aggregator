# app.py - Main Flask application
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

load_dotenv()

app = Flask(__name__)
CORS(app)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration - Using Hugging Face free API
HF_API_KEY = os.getenv('HF_API_KEY', '')  # Optional, works without API key
HF_API_URL = "https://api-inference.huggingface.co/models/facebook/bart-large-cnn"

# News sources (RSS feeds)
NEWS_SOURCES = [
    {'name': 'TechCrunch AI', 'url': 'https://techcrunch.com/category/artificial-intelligence/feed/'},
    {'name': 'VentureBeat AI', 'url': 'https://venturebeat.com/ai/feed/'},
    {'name': 'MIT Technology Review', 'url': 'https://www.technologyreview.com/feed/'},
    {'name': 'The Verge AI', 'url': 'https://www.theverge.com/ai-artificial-intelligence/rss/index.xml'},
    {'name': 'AI News', 'url': 'https://artificialintelligence-news.com/feed/'},
]

class NewsAggregator:
    def __init__(self):
        self.articles = []
    
    def fetch_articles(self, hours_back: int = 24) -> List[Dict]:
        """Fetch articles from all news sources"""
        all_articles = []
        cutoff_time = datetime.now() - timedelta(hours=hours_back)
        
        for source in NEWS_SOURCES:
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
                        article_id = hashlib.md5(entry.title.encode()).hexdigest()
                        
                        article = {
                            'id': article_id,
                            'title': entry.title,
                            'summary': getattr(entry, 'summary', ''),
                            'link': entry.link,
                            'published': published.isoformat(),
                            'source': source['name'],
                            'content': self.clean_html(getattr(entry, 'summary', '')),
                            'ai_summary': '',
                            'sentiment': 'neutral'
                        }
                        
                        # Generate AI summary and sentiment
                        if article['content']:
                            article['ai_summary'] = self.summarize_article(article['content'])
                            article['sentiment'] = self.get_sentiment(article['title'] + ' ' + article['content'][:200])
                        
                        all_articles.append(article)
                        
            except Exception as e:
                logger.error(f"Error fetching from {source['name']}: {str(e)}")
        
        # Remove duplicates based on title similarity
        unique_articles = self.remove_duplicates(all_articles)
        return sorted(unique_articles, key=lambda x: x['published'], reverse=True)
    
    def clean_html(self, text: str) -> str:
        """Remove HTML tags from text"""
        clean = re.compile('<.*?>')
        return re.sub(clean, '', text)
    
    def remove_duplicates(self, articles: List[Dict]) -> List[Dict]:
        """Remove duplicate articles based on title similarity"""
        seen_titles = set()
        unique_articles = []
        
        for article in articles:
            title_hash = hashlib.md5(article['title'].lower().encode()).hexdigest()
            if title_hash not in seen_titles:
                seen_titles.add(title_hash)
                unique_articles.append(article)
        
        return unique_articles
    
    def summarize_article(self, content: str) -> str:
        """Generate AI summary using Hugging Face API"""
        # Clean and truncate content for API limits
        clean_content = self.clean_html(content)
        if len(clean_content) > 1000:
            clean_content = clean_content[:1000]
        
        if len(clean_content) < 50:
            return clean_content
        
        try:
            headers = {}
            if HF_API_KEY:
                headers["Authorization"] = f"Bearer {HF_API_KEY}"
            
            # Use Hugging Face BART model for summarization
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
            
            # Fallback to simple truncation
            return clean_content[:200] + "..." if len(clean_content) > 200 else clean_content
            
        except Exception as e:
            logger.error(f"Error generating summary with Hugging Face: {str(e)}")
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
                json={"inputs": text[:500]},  # Limit text length
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                if isinstance(result, list) and len(result) > 0:
                    sentiment_data = result[0]
                    if isinstance(sentiment_data, list) and len(sentiment_data) > 0:
                        return sentiment_data[0].get('label', 'neutral').lower()
            
            return 'neutral'
        except Exception as e:
            logger.error(f"Error getting sentiment: {str(e)}")
            return 'neutral'

# Initialize aggregator
aggregator = NewsAggregator()

@app.route('/')
def health_check():
    return jsonify({'status': 'healthy', 'message': 'AI News Aggregator API is running'})

@app.route('/api/news', methods=['GET'])
def get_news():
    """Get aggregated news articles"""
    try:
        hours_back = request.args.get('hours', 24, type=int)
        articles = aggregator.fetch_articles(hours_back)
        
        return jsonify({
            'success': True,
            'articles': articles,
            'count': len(articles),
            'last_updated': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Error fetching news: {str(e)}")
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

@app.route('/api/categories', methods=['GET'])
def get_categories():
    """Get article categories/topics"""
    try:
        articles = aggregator.fetch_articles(24)
        
        # Simple keyword-based categorization
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
    return jsonify({
        'success': True,
        'sources': NEWS_SOURCES
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)