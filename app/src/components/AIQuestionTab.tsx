import React, { useState, useEffect, useRef } from 'react';
import { invoke } from '@tauri-apps/api/core';
import ChannelSelector from './ChannelSelector';
import AIAnswerComponent from './AIAnswerComponent';

interface AIResponse {
  answer: string;
  sources?: VideoSource[];
  channel_used: string;
  model_used: string;
  response_time: number;
}

interface VideoSource {
  video_id: string;
  title: string;
  timestamp?: number;
  relevance_score: number;
  excerpt: string;
}

export const AIQuestionTab: React.FC = () => {
  const [selectedChannel, setSelectedChannel] = useState<string>('');
  const [selectedModel, setSelectedModel] = useState<string>('deepseek');
  const [query, setQuery] = useState<string>('');
  const [response, setResponse] = useState<AIResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<Array<{
    query: string;
    response: AIResponse;
    timestamp: Date;
  }>>([]);

  const queryInputRef = useRef<HTMLTextAreaElement>(null);

  const handleChannelSelect = (channelName: string) => {
    setSelectedChannel(channelName);
    setError(null);
    
    // 채널 변경 시 포커스를 질문 입력란으로 이동
    setTimeout(() => {
      queryInputRef.current?.focus();
    }, 100);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!selectedChannel) {
      setError('먼저 채널을 선택해주세요.');
      return;
    }
    
    if (!query.trim()) {
      setError('질문을 입력해주세요.');
      return;
    }

    setLoading(true);
    setError(null);
    const startTime = performance.now();

    try {
      const result = await invoke<string>('ask_ai_universal', {
        query: query.trim(),
        channelName: selectedChannel,
        model: selectedModel
      });

      const endTime = performance.now();
      const responseTime = (endTime - startTime) / 1000; // 초 단위

      const aiResponse: AIResponse = {
        answer: result,
        channel_used: selectedChannel,
        model_used: selectedModel,
        response_time: responseTime,
        sources: [] // TODO: 백엔드에서 소스 정보도 반환하도록 개선
      };

      setResponse(aiResponse);
      
      // 히스토리에 추가
      setHistory(prev => [{
        query: query.trim(),
        response: aiResponse,
        timestamp: new Date()
      }, ...prev.slice(0, 9)]); // 최근 10개만 유지
      
      // 질문 입력란 초기화
      setQuery('');
      
    } catch (err) {
      console.error('AI 질문 실패:', err);
      setError(`AI 질문 처리 중 오류가 발생했습니다: ${err}`);
    } finally {
      setLoading(false);
    }
  };

  const handleHistorySelect = (historyItem: typeof history[0]) => {
    setQuery(historyItem.query);
    setResponse(historyItem.response);
    setSelectedChannel(historyItem.response.channel_used);
    setSelectedModel(historyItem.response.model_used);
  };

  const clearHistory = () => {
    setHistory([]);
    setResponse(null);
  };

  return (
    <div className="ai-question-tab">
      <div className="ai-question-container">
        {/* 채널 및 모델 선택 섹션 */}
        <div className="selection-section">
          <div className="channel-selection-section">
            <ChannelSelector 
              onChannelSelect={handleChannelSelect}
              selectedChannel={selectedChannel}
              className="ai-channel-selector"
            />
          </div>
          
          <div className="model-selection-section">
            <label className="model-selector-label">
              🤖 AI 모델 선택
            </label>
            <select 
              value={selectedModel} 
              onChange={(e) => setSelectedModel(e.target.value)}
              className="model-selector"
              disabled={loading}
            >
              <option value="deepseek">🧠 DeepSeek (빠름)</option>
              <option value="gemini">✨ Gemini (정확함)</option>
            </select>
          </div>
        </div>

        {/* 질문 입력 섹션 */}
        <div className="question-section">
          <form onSubmit={handleSubmit} className="question-form">
            <div className="form-header">
              <h3>💬 AI에게 질문하기</h3>
              {selectedChannel && (
                <div className="selected-info">
                  <div className="selected-channel-info">
                    📺 {selectedChannel} 채널
                  </div>
                  <div className="selected-model-info">
                    {selectedModel === 'gemini' ? '✨ Gemini' : '🧠 DeepSeek'} 모델
                  </div>
                </div>
              )}
            </div>
            
            <div className="form-body">
              <textarea
                ref={queryInputRef}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={selectedChannel 
                  ? `${selectedChannel} 채널 정보를 ${selectedModel === 'gemini' ? 'Gemini' : 'DeepSeek'}로 질문해보세요...`
                  : "먼저 위에서 채널과 AI 모델을 선택해주세요"
                }
                className="question-input"
                rows={3}
                disabled={!selectedChannel || loading}
              />
              
              <div className="form-actions">
                <button 
                  type="submit" 
                  disabled={!selectedChannel || !query.trim() || loading}
                  className="submit-button"
                  data-model={selectedModel}
                >
                  {loading ? (
                    <>
                      <div className="loading-spinner small"></div>
                      AI 답변 생성 중...
                    </>
                  ) : (
                    `${selectedModel === 'gemini' ? '✨' : '🧠'} ${selectedModel === 'gemini' ? 'Gemini' : 'DeepSeek'}로 질문하기`
                  )}
                </button>
                
                {query && (
                  <button 
                    type="button" 
                    onClick={() => setQuery('')}
                    className="clear-button"
                  >
                    지우기
                  </button>
                )}
              </div>
            </div>
          </form>

          {error && (
            <div className="error-message">
              <span>❌ {error}</span>
            </div>
          )}
        </div>

        {/* 답변 섹션 */}
        {response && (
          <div className="answer-section">
            <AIAnswerComponent response={response} />
          </div>
        )}

        {/* 히스토리 섹션 */}
        {history.length > 0 && (
          <div className="history-section">
            <div className="history-header">
              <h3>📚 최근 질문 기록</h3>
              <button onClick={clearHistory} className="clear-history-button">
                전체 삭제
              </button>
            </div>
            
            <div className="history-list">
              {history.map((item, index) => (
                <div 
                  key={index} 
                  className="history-item"
                  onClick={() => handleHistorySelect(item)}
                >
                  <div className="history-query">
                    <span className="history-icon">💬</span>
                    <span className="query-text">{item.query}</span>
                  </div>
                  <div className="history-meta">
                    <span className="history-channel">📺 {item.response.channel_used}</span>
                    <span className="history-model">
                      {item.response.model_used === 'gemini' ? '✨ Gemini' : '🧠 DeepSeek'}
                    </span>
                    <span className="history-time">
                      {item.timestamp.toLocaleTimeString()}
                    </span>
                    <span className="history-response-time">
                      ⏱️ {item.response.response_time.toFixed(1)}초
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default AIQuestionTab;