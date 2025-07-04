import React, { useState, useEffect, useRef } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { listen } from '@tauri-apps/api/event';
import ChannelSelector from './ChannelSelector';
import AIAnswerComponent from './AIAnswerComponent';

interface VideoSource {
  video_id: string;
  title: string;
  timestamp?: number;
  relevance_score: number;
  excerpt: string;
}

interface AIResponse {
  answer: string;
  sources?: VideoSource[];
  confidence?: number;
  documents_found?: number;
  processing_time?: number;
  search_quality?: any;
  debug_info?: any;
  channel_used: string;
  model_used: string;
  response_time: number;
}

interface AIProgress {
  step: string;
  message: string;
  progress: number;
  details?: string;
}

interface ChatSession {
  id: string;
  timestamp: Date;
  query: string;
  response: AIResponse;
  channel: string;
  model: string;
}

export const AIQuestionTab: React.FC = () => {
  const [selectedChannel, setSelectedChannel] = useState<string>('');
  const [selectedModel, setSelectedModel] = useState<string>('deepseek-chat');
  const [query, setQuery] = useState<string>('');
  const [response, setResponse] = useState<AIResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState<AIProgress | null>(null);
  const [progressHistory, setProgressHistory] = useState<AIProgress[]>([]);
  const [history, setHistory] = useState<Array<{
    query: string;
    response: AIResponse;
    timestamp: Date;
  }>>([]);

  const queryInputRef = useRef<HTMLTextAreaElement>(null);

  // 컴포넌트 마운트 시 저장된 채널 로드
  useEffect(() => {
    const savedChannel = localStorage.getItem('ai-selected-channel');
    if (savedChannel) {
      setSelectedChannel(savedChannel);
    }
    
    const savedModel = localStorage.getItem('ai-selected-model');
    if (savedModel) {
      setSelectedModel(savedModel);
    }
  }, []);

  // 진행 상황 이벤트 리스너 설정 및 저장된 세션 로드
  useEffect(() => {
    let unlisten: (() => void) | null = null;

    const setupProgressListener = async () => {
      unlisten = await listen<AIProgress>('ai-progress', (event) => {
        const newProgress = event.payload;
        
        console.log('🔄 Progress 업데이트:', newProgress); // 디버깅용
        
        // 현재 진행 상황 업데이트 (애니메이션 효과를 위해 약간의 지연)
        setProgress(newProgress);
        
        // 진행 히스토리에 추가 (사고과정 추적) - 중복 방지
        setProgressHistory(prev => {
          const lastStep = prev[prev.length - 1];
          // 같은 단계가 아닌 경우에만 추가
          if (!lastStep || lastStep.step !== newProgress.step || lastStep.progress !== newProgress.progress) {
            return [...prev, newProgress].slice(-15); // 최근 15개로 증가
          }
          return prev;
        });
        
        // 완료 시 progress 초기화 (더 긴 지연으로 결과 확인 시간 제공)
        if (newProgress.progress >= 100) {
          setTimeout(() => {
            setProgress(null);
            setProgressHistory([]);
          }, 5000); // 5초로 증가
        }
      });
    };

    // 저장된 세션들 로드
    const loadSavedSessions = async () => {
      try {
        const sessionStrings = await invoke<string[]>('load_recent_sessions', { limit: 10 });
        const loadedSessions: typeof history = [];
        
        for (const sessionStr of sessionStrings) {
          try {
            const session: ChatSession = JSON.parse(sessionStr);
            // timestamp가 문자열인 경우 Date 객체로 변환
            const timestamp = typeof session.timestamp === 'string' 
              ? new Date(session.timestamp) 
              : session.timestamp;
            
            loadedSessions.push({
              query: session.query,
              response: session.response,
              timestamp
            });
          } catch (parseError) {
            console.warn('세션 파싱 실패:', parseError);
          }
        }
        
        if (loadedSessions.length > 0) {
          setHistory(loadedSessions);
          console.log(`${loadedSessions.length}개의 저장된 세션을 불러왔습니다.`);
        }
      } catch (error) {
        console.warn('저장된 세션 로드 실패:', error);
      }
    };

    setupProgressListener();
    loadSavedSessions();

    return () => {
      if (unlisten) {
        unlisten();
      }
    };
  }, []);

  const handleChannelSelect = (channelName: string) => {
    setSelectedChannel(channelName);
    setError(null);
    
    // 채널 선택을 로컬스토리지에 저장
    localStorage.setItem('ai-selected-channel', channelName);
    
    // 채널 변경 시 포커스를 질문 입력란으로 이동
    setTimeout(() => {
      queryInputRef.current?.focus();
    }, 100);
  };

  const handleModelChange = (model: string) => {
    setSelectedModel(model);
    localStorage.setItem('ai-selected-model', model);
  };

  const saveSessionToFile = async (session: ChatSession) => {
    try {
      // Tauri API를 통해 백엔드에서 파일 저장 처리
      await invoke('save_chat_session', {
        sessionData: JSON.stringify(session)
      });
      console.log('세션 저장됨');
    } catch (err) {
      console.error('세션 저장 실패:', err);
    }
  };

  const parseSourcesFromString = (sourcesData: any): VideoSource[] => {
    if (!sourcesData) return [];
    
    try {
      // 이미 VideoSource[] 형태인 경우
      if (Array.isArray(sourcesData) && sourcesData.length > 0 && 
          typeof sourcesData[0] === 'object' && 'video_id' in sourcesData[0]) {
        return sourcesData.map(source => ({
          video_id: source.video_id || `unknown_${Date.now()}`,
          title: source.title || '제목 없음',
          timestamp: source.timestamp || undefined,
          relevance_score: source.relevance_score || 0.5,
          excerpt: source.excerpt || '내용 없음'
        }));
      }
      
      // 문자열 배열인 경우 파싱
      if (Array.isArray(sourcesData)) {
        return sourcesData.map((sourceStr, index) => ({
          video_id: `source_${index}_${Date.now()}`,
          title: typeof sourceStr === 'string' ? sourceStr.slice(0, 50) : `소스 ${index + 1}`,
          relevance_score: 0.8,
          excerpt: typeof sourceStr === 'string' ? sourceStr.slice(0, 100) : '내용을 확인할 수 없습니다.'
        }));
      }
      
      // 문자열인 경우 JSON 파싱 시도
      if (typeof sourcesData === 'string') {
        try {
          const parsed = JSON.parse(sourcesData);
          return parseSourcesFromString(parsed); // 재귀 호출
        } catch (jsonError) {
          console.warn('소스 데이터 JSON 파싱 실패:', jsonError);
          return [];
        }
      }
      
    } catch (error) {
      console.warn('소스 데이터 파싱 중 오류:', error);
    }
    
    return [];
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
    setProgressHistory([]);
    const startTime = performance.now();

    try {
      // 개선된 백엔드 호출
      const resultStr = await invoke<string>('ask_ai_universal_with_progress', {
        query: query.trim(),
        channelName: selectedChannel,
        model: selectedModel
      });

      const endTime = performance.now();
      const responseTime = (endTime - startTime) / 1000;

      // JSON 파싱 시도 (개선된 에러 처리)
      let aiResponse: AIResponse;
      try {
        const parsedResult = JSON.parse(resultStr);
        aiResponse = {
          answer: parsedResult.answer || resultStr,
          sources: parseSourcesFromString(parsedResult.sources),
          confidence: parsedResult.confidence || 0,
          documents_found: parsedResult.documents_found || 0,
          processing_time: parsedResult.processing_time || 0,
          search_quality: parsedResult.search_quality || {},
          debug_info: parsedResult.debug_info || {},
          channel_used: selectedChannel,
          model_used: selectedModel,
          response_time: responseTime
        };
      } catch (parseError) {
        console.warn('JSON 파싱 실패, 부분 추출 시도:', parseError);
        
        // 부분적으로 잘린 JSON에서 answer만 추출 시도
        let extractedAnswer = resultStr;
        
        try {
          // answer 필드만 추출 시도
          const answerMatch = resultStr.match(/"answer":\s*"([^"]*(?:\\.[^"]*)*)"/);
          if (answerMatch && answerMatch[1]) {
            extractedAnswer = answerMatch[1]
              .replace(/\\n/g, '\n')
              .replace(/\\"/g, '"')
              .replace(/\\\\/g, '\\');
          } else {
            // answer 필드가 없으면 JSON 구조 제거하고 텍스트만 추출
            extractedAnswer = resultStr
              .replace(/^[^"]*"answer":\s*"/i, '')
              .replace(/",\s*"[^"]*":\s*.*$/i, '')
              .replace(/\\n/g, '\n')
              .replace(/\\"/g, '"')
              .replace(/\\\\/g, '\\');
          }
        } catch (extractError) {
          console.warn('부분 추출 실패, 원본 사용:', extractError);
          // JSON 구조가 보이지 않도록 정리
          extractedAnswer = resultStr
            .replace(/^\s*{\s*/, '')
            .replace(/\s*}\s*$/, '')
            .replace(/"[^"]*":\s*/g, '')
            .replace(/,\s*$/, '')
            .trim();
        }
        
        aiResponse = {
          answer: extractedAnswer || '응답을 처리하는 중 오류가 발생했습니다.',
          sources: [],
          confidence: 0.5,
          channel_used: selectedChannel,
          model_used: selectedModel,
          response_time: responseTime
        };
      }

      setResponse(aiResponse);
      
      // 히스토리에 추가
      setHistory(prev => [{
        query: query.trim(),
        response: aiResponse,
        timestamp: new Date()
      }, ...prev.slice(0, 9)]); // 최근 10개만 유지

      // 세션을 파일로 저장
      const session: ChatSession = {
        id: Date.now().toString(),
        timestamp: new Date(),
        query: query.trim(),
        response: aiResponse,
        channel: selectedChannel,
        model: selectedModel
      };
      await saveSessionToFile(session);
      
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
  };

  const clearHistory = async () => {
    try {
      // 백엔드에서 모든 세션 파일 삭제
      const result = await invoke<string>('clear_all_sessions');
      console.log('세션 파일 삭제 완료:', result);
      
      // 프론트엔드 상태 초기화
      setHistory([]);
      setResponse(null);
    } catch (error) {
      console.error('히스토리 삭제 실패:', error);
      // 파일 삭제 실패해도 메모리에서는 삭제
      setHistory([]);
      setResponse(null);
    }
  };

  const getProgressStepClass = (step: string) => {
    const normalizedStep = step.toLowerCase();
    if (normalizedStep.includes('init')) return 'step-init';
    if (normalizedStep.includes('query_analysis')) return 'step-analysis';
    if (normalizedStep.includes('vector') || normalizedStep.includes('검색')) return 'step-search';
    if (normalizedStep.includes('hyde')) return 'step-hyde';
    if (normalizedStep.includes('rewrite') || normalizedStep.includes('쿼리')) return 'step-rewrite';
    if (normalizedStep.includes('merge')) return 'step-merge';
    if (normalizedStep.includes('context')) return 'step-context';
    if (normalizedStep.includes('ai_thinking')) return 'step-thinking';
    if (normalizedStep.includes('result_processing')) return 'step-processing';
    if (normalizedStep.includes('complete') || normalizedStep.includes('완료')) return 'step-complete';
    return '';
  };

  const getModelDisplayName = (model: string) => {
    switch (model) {
      case 'deepseek-chat': return '🤖 DeepSeek Chat';
      case 'deepseek-reasoner': return '🧠 DeepSeek Reasoner';
      case 'deepseek': return '🤖 DeepSeek';
      default: return '🤖 AI';
    }
  };

  const getModelIcon = (model: string) => {
    switch (model) {
      case 'deepseek-chat': return '🤖';
      case 'deepseek-reasoner': return '🧠';
      case 'deepseek': return '🤖';
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
                onChange={(e) => handleModelChange(e.target.value)}
                className="model-selector"
              >
                <option value="deepseek-chat">🤖 DeepSeek Chat (기본)</option>
                <option value="deepseek-reasoner">🧠 DeepSeek Reasoner (추론형)</option>
              </select>
            </div>
          </div>
        </div>

        {/* 진행 상황 표시 섹션 (개선됨) */}
        {(loading || progress) && (
          <div className="progress-section">
            <div className="current-progress">
              {progress && (
                <div className="progress-item current">
                  <div className="progress-header">
                    <span className={`progress-step ${getProgressStepClass(progress.step)}`}>
                      {progress.message}
                    </span>
                    <span className="progress-percentage">{progress.progress.toFixed(1)}%</span>
                  </div>
                  <div className="progress-bar">
                    <div 
                      className="progress-fill" 
                      style={{ width: `${progress.progress}%` }}
                    ></div>
                  </div>
                  {progress.details && (
                    <div className="progress-details">{progress.details}</div>
                  )}
                </div>
              )}
            </div>
            
            {/* 사고과정 히스토리 */}
            {progressHistory.length > 0 && (
              <div className="progress-history">
                <h4>🧠 AI 사고과정:</h4>
                <div className="progress-steps">
                  {progressHistory.map((step, index) => (
                    <div key={index} className={`progress-step-item ${getProgressStepClass(step.step)}`}>
                      <div className="step-icon">✓</div>
                      <div className="step-content">
                        <div className="step-message">{step.message}</div>
                        {step.details && <div className="step-details">{step.details}</div>}
                      </div>
                      <div className="step-time">{step.progress.toFixed(0)}%</div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

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
                </div>
            </div>
            
            {error && (
              <div className="error-message">
                ⚠️ {error}
              </div>
            )}
          </form>
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