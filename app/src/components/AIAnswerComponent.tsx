import React from 'react';

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
  channel_used: string;
  model_used: string;
  response_time: number;
}

interface AIAnswerComponentProps {
  response: AIResponse;
}

export const AIAnswerComponent: React.FC<AIAnswerComponentProps> = ({ response }) => {
  const openVideoAtTimestamp = (videoId: string, timestamp?: number) => {
    const url = `https://youtube.com/watch?v=${videoId}${timestamp ? `&t=${timestamp}s` : ''}`;
    window.open(url, '_blank');
  };

  const formatTimestamp = (seconds?: number) => {
    if (!seconds) return '';
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
  };

  const copyAnswer = async () => {
    try {
      await navigator.clipboard.writeText(response.answer);
      // TODO: 복사 성공 표시
    } catch (err) {
      console.error('복사 실패:', err);
    }
  };

  const getModelDisplayName = (model: string) => {
    switch (model) {
      case 'deepseek': return '🤖 DeepSeek';
      default: return '🤖 AI';
    }
  };

  // 답변을 마크다운 스타일로 렌더링하는 간단한 함수
  const renderAnswer = (text: string) => {
    // 간단한 마크다운 파싱 (볼드, 이탤릭, 리스트 등)
    const lines = text.split('\n');
    
    return lines.map((line, index) => {
      // 헤딩 처리
      if (line.startsWith('### ')) {
        return <h4 key={index} className="answer-h4">{line.slice(4)}</h4>;
      }
      if (line.startsWith('## ')) {
        return <h3 key={index} className="answer-h3">{line.slice(3)}</h3>;
      }
      if (line.startsWith('# ')) {
        return <h2 key={index} className="answer-h2">{line.slice(2)}</h2>;
      }
      
      // 리스트 처리
      if (line.startsWith('- ')) {
        return <li key={index} className="answer-li">{line.slice(2)}</li>;
      }
      
      // 볼드 처리
      if (line.includes('**')) {
        const parts = line.split('**');
        return (
          <p key={index} className="answer-p">
            {parts.map((part, i) => 
              i % 2 === 1 ? <strong key={i}>{part}</strong> : part
            )}
          </p>
        );
      }
      
      // 빈 줄
      if (line.trim() === '') {
        return <br key={index} />;
      }
      
      // 일반 텍스트
      return <p key={index} className="answer-p">{line}</p>;
    });
  };

  return (
    <div className="ai-response">
      <div className="ai-response-header">
        <div className="response-info">
          <span className="channel-badge">📺 {response.channel_used}</span>
          <span className={`model-indicator ${response.model_used}`}>
            {getModelDisplayName(response.model_used)}
          </span>
          <span className="response-time">⏱️ {response.response_time.toFixed(1)}초</span>
        </div>
        
        <div className="response-actions">
          <button onClick={copyAnswer} className="copy-button" title="답변 복사">
            📋 복사
          </button>
        </div>
      </div>
      
      <div className="answer-content">
        <div className="answer-text">
          {renderAnswer(response.answer)}
        </div>
      </div>
      
      {response.sources && response.sources.length > 0 && (
        <div className="sources-section">
          <h4 className="sources-title">📚 참고 영상</h4>
          <div className="sources-list">
            {response.sources.map((source, i) => (
              <div 
                key={i} 
                className="source-item"
                onClick={() => openVideoAtTimestamp(source.video_id, source.timestamp)}
              >
                <div className="source-main">
                  <div className="source-header">
                    <span className="source-title">{source.title}</span>
                    <span className="source-relevance">
                      {(source.relevance_score * 100).toFixed(1)}% 관련
                    </span>
                  </div>
                  
                  <div className="source-details">
                    {source.timestamp && (
                      <span className="source-timestamp">
                        🕐 {formatTimestamp(source.timestamp)}
                      </span>
                    )}
                    <span className="source-excerpt">
                      {source.excerpt.slice(0, 100)}...
                    </span>
                  </div>
                </div>
                
                <div className="source-action">
                  <span className="source-link-icon">🔗</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
      
      <div className="response-footer">
        <div className="response-meta">
          <span className="generation-info">
            🤖 AI 답변 • {response.channel_used} 채널 기반
          </span>
        </div>
      </div>
    </div>
  );
};

export default AIAnswerComponent;