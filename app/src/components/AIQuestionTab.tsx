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
  const [abortController, setAbortController] = useState<AbortController | null>(null);
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
      console.log('🔍 파싱할 소스 데이터:', sourcesData);
      
      // 이미 VideoSource[] 형태인 경우
      if (Array.isArray(sourcesData) && sourcesData.length > 0 && 
          typeof sourcesData[0] === 'object' && 'video_id' in sourcesData[0]) {
        return sourcesData.map((source, index) => ({
          video_id: source.video_id || `unknown_${Date.now()}_${index}`,
          title: source.title || source.video_title || `영상 ${index + 1}`,
          timestamp: source.timestamp || undefined,
          relevance_score: source.relevance_score || source.similarity || 0.8,
          excerpt: source.excerpt || source.content || source.description || '내용 없음'
        }));
      }
      
      // 백엔드에서 SearchDocument 객체 배열로 오는 경우
      if (Array.isArray(sourcesData) && sourcesData.length > 0 && 
          typeof sourcesData[0] === 'object') {
        return sourcesData.map((doc, index) => {
          console.log(`📄 처리 중인 문서 ${index}:`, doc);
          
          // 다양한 필드명 확인
          const videoId = doc.video_id || doc.id || doc.document_id || `video_${index}_${Date.now()}`;
          const title = doc.title || doc.video_title || doc.name || `📺 영상 ${index + 1}`;
          const relevance = doc.relevance_score || doc.similarity || doc.score || 0.8;
          const content = doc.excerpt || doc.content || doc.description || doc.text || '내용 없음';
          
          return {
            video_id: videoId,
            title: title,
            timestamp: doc.timestamp || undefined,
            relevance_score: relevance,
            excerpt: content.length > 100 ? content.substring(0, 100) + '...' : content
          };
        });
      }
      
      // 문자열 배열인 경우 파싱
      if (Array.isArray(sourcesData)) {
        return sourcesData.map((sourceStr, index) => {
          console.log(`📝 문자열 소스 ${index}:`, sourceStr);
          
          // YouTube video ID 패턴 검사 (11자리 영숫자)
          const youtubeIdMatch = typeof sourceStr === 'string' ? 
            sourceStr.match(/[a-zA-Z0-9_-]{11}/) : null;
          
          return {
            video_id: youtubeIdMatch ? youtubeIdMatch[0] : `source_${index}_${Date.now()}`,
            title: typeof sourceStr === 'string' ? 
              (sourceStr.length > 50 ? sourceStr.substring(0, 50) + '...' : sourceStr) : 
              `소스 ${index + 1}`,
            relevance_score: 0.8,
            excerpt: typeof sourceStr === 'string' ? 
              (sourceStr.length > 100 ? sourceStr.substring(0, 100) + '...' : sourceStr) : 
              '내용을 확인할 수 없습니다.'
          };
        });
      }
      
      // 문자열인 경우 JSON 파싱 시도
      if (typeof sourcesData === 'string') {
        try {
          const parsed = JSON.parse(sourcesData);
          return parseSourcesFromString(parsed); // 재귀 호출
        } catch (jsonError) {
          console.warn('소스 데이터 JSON 파싱 실패:', jsonError);
          
          // 단일 문자열에서 YouTube ID 추출 시도
          const youtubeIdMatch = sourcesData.match(/[a-zA-Z0-9_-]{11}/);
          if (youtubeIdMatch) {
            return [{
              video_id: youtubeIdMatch[0],
              title: '영상 제목 추출 중...',
              relevance_score: 0.7,
              excerpt: sourcesData.substring(0, 100)
            }];
          }
          
          return [];
        }
      }
      
    } catch (error) {
      console.error('소스 데이터 파싱 중 오류:', error);
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
    
    // AbortController 생성 및 설정
    const controller = new AbortController();
    setAbortController(controller);
    
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
      setAbortController(null);
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

  const abortSearch = async () => {
    if (abortController) {
      console.log('🛑 검색 중단 요청');
      abortController.abort();
      
      try {
        // 백엔드에도 중단 신호 전송
        await invoke('abort_ai_search');
      } catch (error) {
        console.warn('백엔드 중단 신호 전송 실패:', error);
      }
      
      setLoading(false);
      setProgress(null);
      setProgressHistory([]);
      setAbortController(null);
      setError('검색이 사용자에 의해 중단되었습니다.');
    }
  };

  const getProgressStepClass = (step: string) => {
    const normalizedStep = step.toLowerCase();
    console.log('🎨 단계 분류:', step, '->', normalizedStep);
    
    // 🚀 RAG 시스템 초기화 중...
    if (normalizedStep.includes('rag') || normalizedStep.includes('시스템') || 
        normalizedStep.includes('초기화') || normalizedStep.includes('init')) return 'step-init';
    
    // 🧠 질문 분석 중...
    if (normalizedStep.includes('질문') || normalizedStep.includes('분석') || 
        normalizedStep.includes('analysis')) return 'step-analysis';
    
    // 🔍 검색 준비 중... / 🔍 벡터 데이터베이스 검색 중...
    if (normalizedStep.includes('검색') || normalizedStep.includes('벡터') || 
        normalizedStep.includes('데이터베이스') || normalizedStep.includes('search') || 
        normalizedStep.includes('vector') || normalizedStep.includes('준비')) return 'step-search';
    
    // 🎯 HyDE 문서 생성 중...
    if (normalizedStep.includes('hyde') || normalizedStep.includes('문서') || 
        normalizedStep.includes('가상')) return 'step-hyde';
    
    // 🔄 쿼리 재작성 중...
    if (normalizedStep.includes('쿼리') || normalizedStep.includes('재작성') || 
        normalizedStep.includes('rewrite')) return 'step-rewrite';
    
    // 🔗 검색 결과 병합 중...
    if (normalizedStep.includes('병합') || normalizedStep.includes('결과') || 
        normalizedStep.includes('merge') || normalizedStep.includes('중복')) return 'step-merge';
    
    // 📖 컨텍스트 구성 중...
    if (normalizedStep.includes('컨텍스트') || normalizedStep.includes('구성') || 
        normalizedStep.includes('context') || normalizedStep.includes('정리')) return 'step-context';
    
    // 🤖 AI 답변 생성 중...
    if (normalizedStep.includes('ai') || normalizedStep.includes('답변') || 
        normalizedStep.includes('생성') || normalizedStep.includes('thinking') ||
        normalizedStep.includes('작성')) return 'step-thinking';
    
    // 처리 중 단계
    if (normalizedStep.includes('processing') || normalizedStep.includes('처리')) return 'step-processing';
    
    // 완료 단계
    if (normalizedStep.includes('complete') || normalizedStep.includes('완료')) return 'step-complete';
    
    // 기본값 - 진행 중으로 처리
    console.log('⚠️ 매칭되지 않은 단계:', step);
    return 'step-processing';
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
            <div className="progress-header-controls">
              <h4>🔄 AI 처리 중...</h4>
              {loading && abortController && (
                <button 
                  onClick={abortSearch}
                  className="abort-button"
                  type="button"
                >
                  🛑 검색 중단
                </button>
              )}
            </div>
            
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
            
            {/* 사고과정 히스토리 - 가로형 체크박스 스타일 */}
            {progressHistory.length > 0 && (
              <div className="progress-history horizontal">
                <h4>🧠 AI 사고과정:</h4>
                <div className="progress-steps-horizontal">
                  {progressHistory.map((step, index) => (
                    <div key={index} className={`progress-step-horizontal ${getProgressStepClass(step.step)}`}>
                      <div className="step-checkbox">
                        <div className="checkbox-mark">✓</div>
                      </div>
                      <div className="step-label">
                        <div className="step-title">{step.message}</div>
                        <div className="step-percentage">{step.progress.toFixed(0)}%</div>
                      </div>
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