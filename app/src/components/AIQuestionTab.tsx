import React, { useState, useEffect, useRef } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { listen } from '@tauri-apps/api/event';
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

interface AIProgress {
  step: string;
  message: string;
  progress: number;
  details?: string;
}

export const AIQuestionTab: React.FC = () => {
  const [selectedChannel, setSelectedChannel] = useState<string>('');
  const [selectedModel, setSelectedModel] = useState<string>('deepseek-chat');
  const [query, setQuery] = useState<string>('');
  const [response, setResponse] = useState<AIResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState<AIProgress | null>(null);
  const [history, setHistory] = useState<Array<{
    query: string;
    response: AIResponse;
    timestamp: Date;
  }>>([]);

  const queryInputRef = useRef<HTMLTextAreaElement>(null);

  // 진행 상황 이벤트 리스너 설정
  useEffect(() => {
    let unlisten: (() => void) | null = null;

    const setupProgressListener = async () => {
      unlisten = await listen<AIProgress>('ai-progress', (event) => {
        setProgress(event.payload);
        
        // 완료 시 progress 초기화
        if (event.payload.progress >= 100) {
          setTimeout(() => setProgress(null), 2000);
        }
      });
    };

    setupProgressListener();

    return () => {
      if (unlisten) {
        unlisten();
      }
    };
  }, []);

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
    setProgress(null);
    const startTime = performance.now();

    try {
      // 선택한 모델 사용
      const result = await invoke<string>('ask_ai_universal_with_progress', {
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
      setProgress(null);
    }
  };

  const handleHistorySelect = (historyItem: typeof history[0]) => {
    setQuery(historyItem.query);
    setResponse(historyItem.response);
    setSelectedChannel(historyItem.response.channel_used);
  };

  const clearHistory = () => {
    setHistory([]);
    setResponse(null);
  };

  const getProgressStepClass = (step: string) => {
    const normalizedStep = step.toLowerCase();
    if (normalizedStep.includes('벡터') || normalizedStep.includes('검색')) return 'step-search';
    if (normalizedStep.includes('hyde')) return 'step-hyde';
    if (normalizedStep.includes('재작성') || normalizedStep.includes('쿼리')) return 'step-rewrite';
    if (normalizedStep.includes('재순위') || normalizedStep.includes('rerank')) return 'step-rerank';
    if (normalizedStep.includes('완료') || normalizedStep.includes('생성')) return 'step-complete';
    return '';
  };

  const getModelDisplayName = (model: string) => {
    switch (model) {
      case 'deepseek-chat': return '🤖 DeepSeek Chat';
      case 'deepseek-reasoner': return '🧠 DeepSeek Reasoner';
      case 'deepseek': return '🤖 DeepSeek'; // 호환성을 위해 유지
      default: return '🤖 AI';
    }
  };

  const getModelIcon = (model: string) => {
    switch (model) {
      case 'deepseek-chat': return '🤖';
      case 'deepseek-reasoner': return '🧠';
      case 'deepseek': return '🤖'; // 호환성을 위해 유지
      default: return '🤖';
    }
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
            <h3>🤖 AI 모델 선택</h3>
            <div className="model-options">
              <select 
                value={selectedModel} 
                onChange={(e) => setSelectedModel(e.target.value)}
                className="model-selector"
              >
                <option value="deepseek-chat">🤖 DeepSeek Chat (기본)</option>
                <option value="deepseek-reasoner">🧠 DeepSeek Reasoner (추론형)</option>
              </select>
            </div>
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
                    {getModelDisplayName(selectedModel)} 사용
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
                  ? `${selectedChannel} 채널 정보를 ${getModelDisplayName(selectedModel)}로 질문해보세요...`
                  : "먼저 위에서 채널을 선택해주세요"
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
                    `${getModelIcon(selectedModel)} ${getModelDisplayName(selectedModel)}로 질문하기`
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

          {/* 진행 상황 표시 */}
          {progress && (
            <div className={`progress-section ${getProgressStepClass(progress.step)}`}>
              <div className="progress-header">
                <span className="progress-step">{progress.step}</span>
                <span className="progress-percentage">{progress.progress.toFixed(0)}%</span>
              </div>
              <div className="progress-bar">
                <div 
                  className="progress-fill" 
                  style={{ width: `${progress.progress}%` }}
                ></div>
              </div>
              <div className="progress-message">{progress.message}</div>
              {progress.details && (
                <div className="progress-details">{progress.details}</div>
              )}
            </div>
          )}

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
                      {getModelDisplayName(item.response.model_used)}
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