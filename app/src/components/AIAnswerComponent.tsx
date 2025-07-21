import React, { useState } from 'react';
import { invoke } from '@tauri-apps/api/core';

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

interface VideoDetails {
  video_id: string;
  title: string;
  transcript: string;
  duration?: number;
  upload_date?: string;
  description?: string;
}

interface AIAnswerComponentProps {
  response: AIResponse;
}

export const AIAnswerComponent: React.FC<AIAnswerComponentProps> = ({ response }) => {
  const [expandedVideos, setExpandedVideos] = useState<Set<string>>(new Set());
  const [videoDetails, setVideoDetails] = useState<Map<string, VideoDetails>>(new Map());
  const [loadingVideos, setLoadingVideos] = useState<Set<string>>(new Set());

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

  const formatDuration = (seconds?: number) => {
    if (!seconds) return '';
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const remainingSecs = seconds % 60;
    
    if (hours > 0) {
      return `${hours}:${minutes.toString().padStart(2, '0')}:${remainingSecs.toString().padStart(2, '0')}`;
    }
    return `${minutes}:${remainingSecs.toString().padStart(2, '0')}`;
  };

  const toggleVideoExpansion = async (videoId: string) => {
    const newExpanded = new Set(expandedVideos);
    
    if (expandedVideos.has(videoId)) {
      // 접기
      newExpanded.delete(videoId);
    } else {
      // 펼치기 - 비디오 상세 정보 로드
      newExpanded.add(videoId);
      
      if (!videoDetails.has(videoId)) {
        setLoadingVideos(prev => new Set(prev).add(videoId));
        
        try {
          console.log(`🔍 비디오 상세 정보 요청: videoId=${videoId}, channel=${response.channel_used}`);
          
          // 백엔드에서 비디오 상세 정보 로드
          const details = await invoke<VideoDetails>('get_video_details', {
            videoId: videoId,
            channelName: response.channel_used
          });
          
          console.log(`✅ 비디오 상세 정보 로드 성공:`, details);
          setVideoDetails(prev => new Map(prev).set(videoId, details));
        } catch (err) {
          console.error(`❌ 비디오 ${videoId} 상세 정보 로드 실패:`, err);
          
          // 실패 시에도 sources에서 가져온 정보 활용
          const sourceInfo = response.sources?.find(s => s.video_id === videoId);
          const fallbackTitle = sourceInfo?.title !== videoId ? sourceInfo?.title : `영상 ${videoId}`;
          
          setVideoDetails(prev => new Map(prev).set(videoId, {
            video_id: videoId,
            title: fallbackTitle || `영상 ${videoId}`,
            transcript: sourceInfo?.excerpt || '자막 정보를 불러올 수 없습니다.'
          }));
        } finally {
          setLoadingVideos(prev => {
            const newSet = new Set(prev);
            newSet.delete(videoId);
            return newSet;
          });
        }
      }
    }
    
    setExpandedVideos(newExpanded);
  };

  const copyAnswer = async () => {
    try {
      await navigator.clipboard.writeText(response.answer);
      // TODO: 복사 성공 표시
    } catch (err) {
      console.error('복사 실패:', err);
    }
  };

  const copyTranscript = async (transcript: string) => {
    try {
      await navigator.clipboard.writeText(transcript);
    } catch (err) {
      console.error('자막 복사 실패:', err);
    }
  };

  const getModelDisplayName = (model: string) => {
    switch (model) {
      case 'deepseek-chat': return '🤖 DeepSeek Chat';
      case 'deepseek-reasoner': return '🧠 DeepSeek Reasoner';
      case 'deepseek': return '🤖 DeepSeek';
      default: return '🤖 AI';
    }
  };

  const getConfidenceColor = (confidence?: number) => {
    if (!confidence) return '#666';
    if (confidence >= 0.8) return '#4CAF50'; // 높음: 초록
    if (confidence >= 0.6) return '#FF9800'; // 중간: 주황
    return '#F44336'; // 낮음: 빨강
  };

  const getConfidenceText = (confidence?: number) => {
    if (!confidence) return '알 수 없음';
    if (confidence >= 0.8) return '높음';
    if (confidence >= 0.6) return '중간';
    return '낮음';
  };

  // 답변을 마크다운 스타일로 렌더링하는 간단한 함수
  const renderAnswer = (text: string) => {
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
      
      // 비디오 참조 처리 [video_id] 형태
      if (line.includes('[') && line.includes(']')) {
        const videoIdMatch = line.match(/\[([^\]]+)\]/g);
        if (videoIdMatch) {
          const parts = line.split(/\[([^\]]+)\]/);
          return (
            <p key={index} className="answer-p">
              {parts.map((part, i) => {
                if (i % 2 === 1) {
                  // 비디오 ID 부분
                  return (
                    <span 
                      key={i} 
                      className="video-reference"
                      onClick={() => openVideoAtTimestamp(part)}
                      title={`영상 ${part} 보기`}
                    >
                      [{part}]
                    </span>
                  );
                }
                return part;
              })}
            </p>
          );
        }
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
          {response.confidence !== undefined && (
            <span 
              className="confidence-indicator"
              style={{ color: getConfidenceColor(response.confidence) }}
              title={`신뢰도: ${(response.confidence * 100).toFixed(1)}%`}
            >
              🎯 신뢰도: {getConfidenceText(response.confidence)} ({(response.confidence * 100).toFixed(1)}%)
            </span>
          )}
          {response.documents_found && (
            <span className="documents-found">📄 {response.documents_found}개 문서</span>
          )}
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
          <h4 className="sources-title">
            🎬 관련 영상 ({response.sources.length}개)
            <span className="sources-subtitle">클릭하여 영상과 자막 확인</span>
          </h4>
          <div className="sources-list">
            {response.sources.map((source, i) => (
              <div key={i} className="source-item">
                <div className="source-header" onClick={() => toggleVideoExpansion(source.video_id)}>
                  <div className="source-main">
                    <div className="source-title-row">
                      <span className="source-expand-icon">
                        {expandedVideos.has(source.video_id) ? '▼' : '▶'}
                      </span>
                      <span className="source-title">{source.title}</span>
                      <span className="source-relevance">
                        {(source.relevance_score * 100).toFixed(1)}% 관련
                      </span>
                    </div>
                    
                    <div className="source-details">
                      <span className="source-video-id">🆔 {source.video_id}</span>
                      {source.timestamp && (
                        <span className="source-timestamp">
                          🕐 {formatTimestamp(source.timestamp)}
                        </span>
                      )}
                      <span className="source-excerpt">
                        {source.excerpt.slice(0, 80)}...
                      </span>
                    </div>
                  </div>
                  
                  <div className="source-actions">
                    <button 
                      className="video-link-button"
                      onClick={(e) => {
                        e.stopPropagation();
                        openVideoAtTimestamp(source.video_id, source.timestamp);
                      }}
                      title="YouTube에서 보기"
                    >
                      🔗 보기
                    </button>
                  </div>
                </div>

                {/* 확장된 비디오 상세 정보 */}
                {expandedVideos.has(source.video_id) && (
                  <div className="video-details-expanded">
                    {loadingVideos.has(source.video_id) ? (
                      <div className="video-loading">
                        <div className="loading-spinner small"></div>
                        <span>비디오 정보 로딩 중...</span>
                      </div>
                    ) : (
                      videoDetails.get(source.video_id) && (
                        <div className="video-details">
                          <div className="video-info">
                            <div className="video-meta">
                              {videoDetails.get(source.video_id)?.duration && (
                                <span className="video-duration">
                                  ⏱️ {formatDuration(videoDetails.get(source.video_id)?.duration)}
                                </span>
                              )}
                              {videoDetails.get(source.video_id)?.upload_date && (
                                <span className="video-date">
                                  📅 {new Date(videoDetails.get(source.video_id)!.upload_date!).toLocaleDateString()}
                                </span>
                              )}
                            </div>
                            
                            {videoDetails.get(source.video_id)?.description && (
                              <div className="video-description">
                                <h5>📝 설명:</h5>
                                <p>{videoDetails.get(source.video_id)?.description?.slice(0, 200)}...</p>
                              </div>
                            )}
                          </div>
                          
                          <div className="video-transcript">
                            <div className="transcript-header">
                              <h5>📜 자막:</h5>
                              <button 
                                className="copy-transcript-button"
                                onClick={() => copyTranscript(videoDetails.get(source.video_id)?.transcript || '')}
                                title="자막 복사"
                              >
                                📋 자막 복사
                              </button>
                            </div>
                            <div className="transcript-content">
                              {videoDetails.get(source.video_id)?.transcript?.slice(0, 500)}
                              {(videoDetails.get(source.video_id)?.transcript?.length || 0) > 500 && '...'}
                            </div>
                          </div>
                        </div>
                      )
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
      
    </div>
  );
};

export default AIAnswerComponent;