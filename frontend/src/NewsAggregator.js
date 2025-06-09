import React, { useState, useEffect } from 'react';
import { RefreshCw, ExternalLink, Calendar, Tag, TrendingUp, AlertCircle } from 'lucide-react';

const NewsAggregator = () => {
  const [articles, setArticles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [categories, setCategories] = useState({});
  const [selectedCategory, setSelectedCategory] = useState('all');
  const [lastUpdated, setLastUpdated] = useState(null);

  const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:5000';

  const fetchNews = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_URL}/api/news`);
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      const data = await response.json();
      
      if (data.success) {
        setArticles(data.articles);
        setLastUpdated(data.last_updated);
      } else {
        throw new Error(data.error || 'Failed to fetch news');
      }
    } catch (err) {
      setError(`Failed to fetch news: ${err.message}`);
      console.error('Error fetching news:', err);
    } finally {
      setLoading(false);
    }
  };

  const fetchCategories = async () => {
    try {
      const response = await fetch(`${API_URL}/api/categories`);
      if (response.ok) {
        const data = await response.json();
        if (data.success) {
          setCategories(data.categories);
        }
      }
    } catch (err) {
      console.error('Error fetching categories:', err);
    }
  };

  useEffect(() => {
    fetchNews();
    fetchCategories();
  }, []);

  const getSentimentColor = (sentiment) => {
    switch (sentiment?.toLowerCase()) {
      case 'positive': return 'text-green-600 bg-green-50';
      case 'negative': return 'text-red-600 bg-red-50';
      default: return 'text-gray-600 bg-gray-50';
    }
  };

  const filteredArticles = selectedCategory === 'all' 
    ? articles 
    : articles.filter(article => {
        const text = (article.title + ' ' + article.content).toLowerCase();
        const categoryKeywords = {
          'Machine Learning': ['machine learning', 'ml', 'neural network', 'deep learning'],
          'Natural Language Processing': ['nlp', 'language model', 'chatbot', 'gpt'],
          'Computer Vision': ['computer vision', 'image', 'vision', 'detection'],
          'Robotics': ['robot', 'robotics', 'autonomous'],
          'Ethics & AI': ['ethics', 'bias', 'fairness', 'regulation'],
          'Business & AI': ['business', 'startup', 'investment', 'market'],
          'Research': ['research', 'paper', 'study', 'academic']
        };
        
        const keywords = categoryKeywords[selectedCategory] || [];
        return keywords.some(keyword => text.includes(keyword));
      });

  if (error) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 p-4">
        <div className="max-w-4xl mx-auto">
          <div className="bg-red-50 border border-red-200 rounded-lg p-6 text-center">
            <AlertCircle className="mx-auto h-12 w-12 text-red-500 mb-4" />
            <h2 className="text-xl font-semibold text-red-800 mb-2">Error Loading News</h2>
            <p className="text-red-600 mb-4">{error}</p>
            <button
              onClick={fetchNews}
              className="bg-red-600 text-white px-4 py-2 rounded-lg hover:bg-red-700 transition-colors"
            >
              Try Again
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100">
      {/* Header */}
      <header className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 py-6">
          <div className="flex justify-between items-center">
            <div>
              <h1 className="text-3xl font-bold text-gray-900 flex items-center gap-2">
                <TrendingUp className="h-8 w-8 text-indigo-600" />
                AI News Aggregator
              </h1>
              <p className="text-gray-600 mt-1">Stay updated with the latest AI developments</p>
            </div>
            <button
              onClick={fetchNews}
              disabled={loading}
              className="flex items-center gap-2 bg-indigo-600 text-white px-4 py-2 rounded-lg hover:bg-indigo-700 disabled:opacity-50 transition-colors"
            >
              <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
              Refresh
            </button>
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 py-8">
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-8">
          {/* Sidebar */}
          <div className="lg:col-span-1">
            <div className="bg-white rounded-xl shadow-sm p-6 sticky top-8">
              <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
                <Tag className="h-5 w-5" />
                Categories
              </h3>
              
              <div className="space-y-2">
                <button
                  onClick={() => setSelectedCategory('all')}
                  className={`w-full text-left px-3 py-2 rounded-lg transition-colors ${
                    selectedCategory === 'all' 
                      ? 'bg-indigo-100 text-indigo-700' 
                      : 'text-gray-600 hover:bg-gray-100'
                  }`}
                >
                  All Articles ({articles.length})
                </button>
                
                {Object.entries(categories).map(([category, count]) => (
                  count > 0 && (
                    <button
                      key={category}
                      onClick={() => setSelectedCategory(category)}
                      className={`w-full text-left px-3 py-2 rounded-lg transition-colors ${
                        selectedCategory === category 
                          ? 'bg-indigo-100 text-indigo-700' 
                          : 'text-gray-600 hover:bg-gray-100'
                      }`}
                    >
                      {category} ({count})
                    </button>
                  )
                ))}
              </div>

              {lastUpdated && (
                <div className="mt-6 pt-6 border-t">
                  <p className="text-sm text-gray-500 flex items-center gap-2">
                    <Calendar className="h-4 w-4" />
                    Last updated: {new Date(lastUpdated).toLocaleTimeString()}
                  </p>
                </div>
              )}
            </div>
          </div>

          {/* Main Content */}
          <div className="lg:col-span-3">
            {loading ? (
              <div className="bg-white rounded-xl shadow-sm p-8 text-center">
                <RefreshCw className="mx-auto h-8 w-8 text-indigo-600 animate-spin mb-4" />
                <p className="text-gray-600">Loading latest AI news...</p>
              </div>
            ) : (
              <div className="space-y-6">
                <div className="flex justify-between items-center">
                  <h2 className="text-xl font-semibold text-gray-900">
                    {selectedCategory === 'all' ? 'Latest Articles' : selectedCategory}
                    <span className="text-gray-500 font-normal ml-2">
                      ({filteredArticles.length} articles)
                    </span>
                  </h2>
                </div>

                {filteredArticles.length === 0 ? (
                  <div className="bg-white rounded-xl shadow-sm p-8 text-center">
                    <p className="text-gray-600">No articles found for this category.</p>
                  </div>
                ) : (
                  filteredArticles.map((article) => (
                    <article
                      key={article.id}
                      className="bg-white rounded-xl shadow-sm hover:shadow-md transition-shadow p-6"
                    >
                      <div className="flex justify-between items-start mb-3">
                        <h3 className="text-xl font-semibold text-gray-900 line-clamp-2 flex-1">
                          {article.title}
                        </h3>
                        <span className={`ml-4 px-2 py-1 rounded-full text-xs font-medium ${getSentimentColor(article.sentiment)}`}>
                          {article.sentiment || 'neutral'}
                        </span>
                      </div>

                      <div className="flex items-center gap-4 text-sm text-gray-500 mb-4">
                        <span className="font-medium">{article.source}</span>
                        <span>•</span>
                        <span>{new Date(article.published).toLocaleDateString()}</span>
                      </div>

                      <div className="space-y-3">
                        {article.ai_summary && (
                          <div className="bg-indigo-50 rounded-lg p-4">
                            <h4 className="text-sm font-medium text-indigo-900 mb-2">AI Summary</h4>
                            <p className="text-indigo-800 text-sm leading-relaxed">
                              {article.ai_summary}
                            </p>
                          </div>
                        )}

                        {article.content && (
                          <p className="text-gray-600 leading-relaxed line-clamp-3">
                            {article.content}
                          </p>
                        )}
                      </div>

                      <div className="mt-4 pt-4 border-t flex justify-between items-center">
                        <a
                          href={article.link}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-2 text-indigo-600 hover:text-indigo-700 font-medium transition-colors"
                        >
                          Read Full Article
                          <ExternalLink className="h-4 w-4" />
                        </a>
                      </div>
                    </article>
                  ))
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default NewsAggregator;