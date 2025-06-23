import React, { useEffect, useState } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { convertFileSrc } from '@tauri-apps/api/core';
import { listen } from '@tauri-apps/api/event';
import Fuse from 'fuse.js';
import './App.css';

interface VideoInfo {
  video_path: string;
  captions_path: string;
  title: string;
  channel: string;
  upload_date?: string;
  duration?: string;
  duration_seconds?: number;
  view_count?: number;
  topic?: string[];
  video_id?: string;
  source_url?: string;
  excerpt?: string;
}

interface ChannelInfo {
  url: string;
  name: string;
  enabled: boolean;
}

interface AppStatus {
  total_videos: number;
  total_channels: number;
  vault_size_mb: number;
  last_download?: string;
  vector_db_status: string;
}

interface ChannelVideos {
  channel_name: string;
  videos: VideoInfo[];
}

interface RecentVideos {
  channels: ChannelVideos[];
}

interface DownloadProgress {
  channel: string;
  status: string;
  progress: number;
  current_video: string;
  total_videos: number;
  completed_videos: number;
  log_message: string;
}

interface CaptionLine {
  index: number;
  content: string;
}

type TabType = 'dashboard' | 'channels' | 'videos' | 'search' | 'ai' | 'settings';

export default function App() {
  const [activeTab, setActiveTab] = useState<TabType>('dashboard');
  const [appStatus, setAppStatus] = useState<AppStatus | null>(null);
  
  // 비디오 관련 상태
  const [videos, setVideos] = useState<VideoInfo[]>([]);
  const [recentVideos, setRecentVideos] = useState<RecentVideos>({ channels: [] });
  const [selectedVideo, setSelectedVideo] = useState<VideoInfo | null>(null);
  const [captions, setCaptions] = useState<CaptionLine[]>([]);
  const [fuse, setFuse] = useState<Fuse<CaptionLine>>();
  
  // 채널 관련 상태
  const [channels, setChannels] = useState<ChannelInfo[]>([]);
  const [newChannelUrl, setNewChannelUrl] = useState('');
  
  // 검색 관련 상태
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<CaptionLine[]>([]);
  const [vectorSearchQuery, setVectorSearchQuery] = useState('');
  const [vectorSearchResults, setVectorSearchResults] = useState('');
  
  // AI 관련 상태
  const [aiQuestion, setAiQuestion] = useState('');
  const [aiAnswer, setAiAnswer] = useState('');
  const [aiLoading, setAiLoading] = useState(false);
  
  // 작업 상태
  const [downloadLoading, setDownloadLoading] = useState(false);
  const [downloadProgress, setDownloadProgress] = useState<DownloadProgress | null>(null);
  const [downloadLogs, setDownloadLogs] = useState<string[]>([]);
  const [showProgressModal, setShowProgressModal] = useState(false);
  
  // 벡터 임베딩 상태
  const [embedLoading, setEmbedLoading] = useState(false);
  const [embeddingProgress, setEmbeddingProgress] = useState<DownloadProgress | null>(null);
  const [embeddingLogs, setEmbeddingLogs] = useState<string[]>([]);
  const [showEmbeddingModal, setShowEmbeddingModal] = useState(false);
  
  // 정합성 검사 상태
  const [checkLoading, setCheckLoading] = useState(false);
  const [integrityProgress, setIntegrityProgress] = useState<DownloadProgress | null>(null);
  const [integrityLogs, setIntegrityLogs] = useState<string[]>([]);
  const [showIntegrityModal, setShowIntegrityModal] = useState(false);
  
  // 로딩 및 에러 상태
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [debugInfo, setDebugInfo] = useState('');

  // 초기 데이터 로드
  useEffect(() => {
    loadAppData();
    loadDebugInfo();
    
    // 다운로드 진행 상황 이벤트 리스너
    const unlistenDownload = listen<DownloadProgress>('download-progress', (event) => {
      const progress = event.payload;
      setDownloadProgress(progress);
      setDownloadLogs(prev => [...prev, progress.log_message].slice(-50)); // 최근 50개 로그만 유지
    });
    
    // 벡터 임베딩 진행 상황 이벤트 리스너
    const unlistenEmbedding = listen<DownloadProgress>('embedding-progress', (event) => {
      const progress = event.payload;
      setEmbeddingProgress(progress);
      setEmbeddingLogs(prev => [...prev, progress.log_message].slice(-50));
    });
    
    // 정합성 검사 진행 상황 이벤트 리스너
    const unlistenIntegrity = listen<DownloadProgress>('integrity-progress', (event) => {
      const progress = event.payload;
      setIntegrityProgress(progress);
      setIntegrityLogs(prev => [...prev, progress.log_message].slice(-50));
    });
    
    return () => {
      unlistenDownload.then(f => f());
      unlistenEmbedding.then(f => f());
      unlistenIntegrity.then(f => f());
    };
  }, []);

  const loadAppData = async () => {
    try {
      setLoading(true);
      const [statusResult, videosResult, channelsResult, recentResult] = await Promise.all([
        invoke<AppStatus>('get_app_status'),
        invoke<VideoInfo[]>('list_videos'),
        invoke<ChannelInfo[]>('list_channels'),
        invoke<RecentVideos>('get_recent_videos_by_channel', { limitPerChannel: 5 })
      ]);
      
      setAppStatus(statusResult);
      setVideos(videosResult);
      setChannels(channelsResult);
      setRecentVideos(recentResult);
      setError(null);
    } catch (err) {
      setError(err as string);
    } finally {
      setLoading(false);
    }
  };

  const loadDebugInfo = async () => {
    try {
      const info = await invoke<string>('get_debug_info');
      setDebugInfo(info);
    } catch (error) {
      setDebugInfo(`디버그 정보 로드 실패: ${error}`);
    }
  };

  // 선택된 비디오의 캡션 로드
  useEffect(() => {
    if (!selectedVideo) {
      setCaptions([]);
      setFuse(undefined);
      return;
    }
    
    fetch(convertFileSrc(selectedVideo.captions_path))
      .then((r) => r.text())
      .then((text) => {
        const lines = text.split(/\r?\n/).filter(Boolean);
        const docs = lines.map((content, index) => ({ index, content }));
        setCaptions(docs);
        setFuse(new Fuse(docs, { keys: ['content'], threshold: 0.3 }));
      })
      .catch((error) => {
        console.error('Failed to read captions file:', error);
      });
  }, [selectedVideo]);

  // 캡션 검색
  const searchCaptions = () => {
    if (!fuse || searchQuery.length < 2) {
      setSearchResults([]);
      return;
    }
    setSearchResults(fuse.search(searchQuery).map((x) => x.item));
  };

  // 벡터 검색
  const performVectorSearch = async () => {
    if (!vectorSearchQuery.trim()) return;
    
    try {
      const result = await invoke<string>('vector_search', { query: vectorSearchQuery });
      setVectorSearchResults(result);
    } catch (err) {
      setVectorSearchResults(`에러: ${err}`);
    }
  };

  // AI 질문
  const askAI = async () => {
    if (!aiQuestion.trim()) return;
    
    setAiLoading(true);
    try {
      const result = await invoke<string>('ask_rag', { query: aiQuestion });
      setAiAnswer(result);
    } catch (err) {
      setAiAnswer(`에러: ${err}`);
    } finally {
      setAiLoading(false);
    }
  };

  // 채널 추가
  const addChannel = async () => {
    if (!newChannelUrl.trim()) return;
    
    try {
      await invoke('add_channel', { url: newChannelUrl });
      setNewChannelUrl('');
      loadAppData();
    } catch (err) {
      alert(`채널 추가 실패: ${err}`);
    }
  };

  // 채널 삭제
  const removeChannel = async (url: string) => {
    try {
      await invoke('remove_channel', { url });
      loadAppData();
    } catch (err) {
      alert(`채널 삭제 실패: ${err}`);
    }
  };

  // 채널 토글
  const toggleChannel = async (url: string) => {
    try {
      await invoke('toggle_channel', { url });
      loadAppData();
    } catch (err) {
      alert(`채널 상태 변경 실패: ${err}`);
    }
  };

  // 비디오 다운로드 (진행 상황 포함)
  const downloadVideos = async () => {
    setDownloadLoading(true);
    setDownloadProgress(null);
    setDownloadLogs([]);
    setShowProgressModal(true);
    
    try {
      const result = await invoke<string>('download_videos_with_progress');
      // 완료 후 데이터 새로고침
      await loadAppData();
    } catch (err) {
      setDownloadLogs(prev => [...prev, `❌ 다운로드 실패: ${err}`]);
    } finally {
      setDownloadLoading(false);
    }
  };

  // 벡터 임베딩 생성 (진행 상황 포함)
  const createEmbeddings = async () => {
    setEmbedLoading(true);
    setEmbeddingProgress(null);
    setEmbeddingLogs([]);
    setShowEmbeddingModal(true);
    
    try {
      const result = await invoke<string>('create_embeddings_with_progress');
      // 완료 후 데이터 새로고침
      await loadAppData();
    } catch (err) {
      setEmbeddingLogs(prev => [...prev, `❌ 임베딩 생성 실패: ${err}`]);
    } finally {
      setEmbedLoading(false);
    }
  };

  // 데이터 정합성 검사 (진행 상황 포함)
  const checkIntegrity = async () => {
    setCheckLoading(true);
    setIntegrityProgress(null);
    setIntegrityLogs([]);
    setShowIntegrityModal(true);
    
    try {
      const result = await invoke<string>('check_integrity_with_progress');
      // 완료 후 데이터 새로고침
      await loadAppData();
    } catch (err) {
      setIntegrityLogs(prev => [...prev, `❌ 정합성 검사 실패: ${err}`]);
    } finally {
      setCheckLoading(false);
    }
  };

    // 대시보드 렌더링 함수 개선
  const renderDashboard = () => {
    if (!appStatus) return <div>로딩 중...</div>;

    const formatNumber = (num: number) => {
      if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`;
      if (num >= 1000) return `${(num / 1000).toFixed(1)}K`;
      return num.toString();
    };

    const formatDuration = (seconds: number) => {
      const minutes = Math.floor(seconds / 60);
      const remainingSeconds = seconds % 60;
      const paddedSeconds = remainingSeconds < 10 ? `0${remainingSeconds}` : remainingSeconds.toString();
      return `${minutes}:${paddedSeconds}`;
    };

    return (
      <div className="dashboard">
        <div className="dashboard-header">
          <div className="dashboard-stats">
            <div className="stat-card">
              <div className="stat-icon">🎥</div>
              <div className="stat-content">
                <div className="stat-number">{appStatus.total_videos}</div>
                <div className="stat-label">총 비디오</div>
              </div>
            </div>
            <div className="stat-card">
              <div className="stat-icon">📺</div>
              <div className="stat-content">
                <div className="stat-number">{appStatus.total_channels}</div>
                <div className="stat-label">구독 채널</div>
              </div>
            </div>
            <div className="stat-card">
              <div className="stat-icon">💾</div>
              <div className="stat-content">
                <div className="stat-number">{(appStatus.vault_size_mb / 1024).toFixed(2)}GB</div>
                <div className="stat-label">보관함 크기</div>
              </div>
            </div>
          </div>
          
          <div className="dashboard-actions">
            <button 
              onClick={downloadVideos} 
              disabled={downloadLoading}
              className={`action-btn primary ${downloadLoading ? 'loading' : ''}`}
            >
              {downloadLoading ? '📥 다운로드 중...' : '📥 비디오 다운로드'}
            </button>
            <button 
              onClick={createEmbeddings} 
              disabled={embedLoading}
              className={`action-btn secondary ${embedLoading ? 'loading' : ''}`}
            >
              {embedLoading ? '🧠 벡터 생성 중...' : '🧠 벡터 생성'}
            </button>
            <button 
              onClick={checkIntegrity} 
              disabled={checkLoading}
              className={`action-btn tertiary ${checkLoading ? 'loading' : ''}`}
            >
              {checkLoading ? '🔍 검사 중...' : '🔍 정합성 검사'}
            </button>
          </div>
        </div>

        <div className="dashboard-content">
          {recentVideos.channels.map((channel, channelIndex) => {
            // 인기 비디오 (전체 기간 중 조회수 상위 5개)
            const popularVideos = [...channel.videos]
              .sort((a: VideoInfo, b: VideoInfo) => (b.view_count || 0) - (a.view_count || 0))
              .slice(0, 5);
            
            // 최신 비디오 (전체 기간 중 최신 5개)
            const latestVideos = [...channel.videos]
              .sort((a: VideoInfo, b: VideoInfo) => {
                const dateA = a.upload_date ? new Date(a.upload_date).getTime() : 0;
                const dateB = b.upload_date ? new Date(b.upload_date).getTime() : 0;
                return dateB - dateA;
              })
              .slice(0, 5);

            return (
              <div key={channelIndex} className="channel-section">
                <div className="channel-header">
                  <h2 className="channel-title">📺 {channel.channel_name}</h2>
                </div>

                <div className="channel-content">
                  {/* 인기 비디오 섹션 */}
                  <div className="video-section">
                    <h3 className="section-title">🔥 인기 비디오</h3>
                    <div className="video-list">
                      {popularVideos.map((video: VideoInfo, index: number) => (
                        <div 
                          key={`popular-${video.video_id}-${index}`} 
                          className="video-item"
                          onClick={() => setActiveTab('videos')}
                        >
                          <div className="video-rank">#{index + 1}</div>
                          <div className="video-thumbnail-small">
                            <div className="video-duration-small">
                              {video.duration_seconds ? formatDuration(video.duration_seconds) : video.duration || 'N/A'}
                            </div>
                          </div>
                          <div className="video-details">
                            <h4 className="video-title-small">{video.title}</h4>
                            <div className="video-meta-small">
                              <span className="view-count">
                                👁️ {video.view_count ? formatNumber(video.view_count) : 'N/A'}
                              </span>
                              <span className="upload-date">
                                📅 {video.upload_date ? new Date(video.upload_date).toLocaleDateString('ko-KR') : 'N/A'}
                              </span>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* 최신 비디오 섹션 */}
                  <div className="video-section">
                    <h3 className="section-title">🆕 최신 비디오</h3>
                    <div className="video-list">
                      {latestVideos.map((video: VideoInfo, index: number) => (
                        <div 
                          key={`latest-${video.video_id}-${index}`} 
                          className="video-item"
                          onClick={() => setActiveTab('videos')}
                        >
                          <div className="video-thumbnail-small">
                            <div className="video-duration-small">
                              {video.duration_seconds ? formatDuration(video.duration_seconds) : video.duration || 'N/A'}
                            </div>
                          </div>
                          <div className="video-details">
                            <h4 className="video-title-small">{video.title}</h4>
                            <div className="video-meta-small">
                              <span className="view-count">
                                👁️ {video.view_count ? formatNumber(video.view_count) : 'N/A'}
                              </span>
                              <span className="upload-date">
                                📅 {video.upload_date ? new Date(video.upload_date).toLocaleDateString('ko-KR') : 'N/A'}
                              </span>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  if (loading) {
    return (
      <div style={styles.loadingContainer}>
        <div style={styles.spinner}></div>
        <div style={styles.loadingText}>Y-Data House 로딩 중...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div style={styles.errorContainer}>
        <div style={styles.errorIcon}>⚠️</div>
        <h2 style={styles.errorTitle}>오류가 발생했습니다</h2>
        <p style={styles.errorMessage}>{error}</p>
        <button style={styles.retryButton} onClick={loadAppData}>
          다시 시도
        </button>
      </div>
    );
  }

  return (
    <>
      {/* 진행 상황 모달 */}
      {showProgressModal && (
        <div className="modal-overlay">
          <div className="progress-modal">
            <div className="modal-header">
              <h3>📥 비디오 다운로드 진행 상황</h3>
              <button 
                className="modal-close-btn"
                onClick={() => setShowProgressModal(false)}
                disabled={downloadLoading}
              >
                ✕
              </button>
            </div>
            
            {downloadProgress && (
              <div className="progress-info">
                <div className="progress-stats">
                  <span>📺 채널: {downloadProgress.channel}</span>
                  <span>📊 상태: {downloadProgress.status}</span>
                  <span>📈 진행률: {downloadProgress.progress.toFixed(1)}%</span>
                  <span>🎬 완료: {downloadProgress.completed_videos}/{downloadProgress.total_videos}</span>
                </div>
                
                <div className="progress-bar-container">
                  <div 
                    className="progress-bar"
                    style={{ width: `${downloadProgress.progress}%` }}
                  />
                </div>
              </div>
            )}
            
            <div className="logs-container">
              <h4>📋 실시간 로그</h4>
              <div className="logs-content">
                {downloadLogs.map((log, index) => (
                  <div key={index} className="log-line">
                    {log}
                  </div>
                ))}
              </div>
            </div>
            
            <div className="modal-footer">
              {downloadLoading ? (
                <button className="btn-secondary" disabled>
                  ⏳ 다운로드 중...
                </button>
              ) : (
                <button 
                  className="btn-primary"
                  onClick={() => setShowProgressModal(false)}
                >
                  ✅ 완료
                </button>
              )}
            </div>
          </div>
        </div>
      )}
      
      {/* 벡터 임베딩 진행 상황 모달 */}
      {showEmbeddingModal && (
        <div className="modal-overlay">
          <div className="progress-modal">
            <div className="modal-header">
              <h3>🧠 벡터 임베딩 생성 진행 상황</h3>
              <button 
                className="modal-close-btn"
                onClick={() => setShowEmbeddingModal(false)}
                disabled={embedLoading}
              >
                ✕
              </button>
            </div>
            
            {embeddingProgress && (
              <div className="progress-info">
                <div className="progress-stats">
                  <span>📊 상태: {embeddingProgress.status}</span>
                  <span>📈 진행률: {embeddingProgress.progress.toFixed(1)}%</span>
                  <span>🎯 현재: {embeddingProgress.current_video}</span>
                </div>
                
                <div className="progress-bar-container">
                  <div 
                    className="progress-bar"
                    style={{ width: `${embeddingProgress.progress}%` }}
                  />
                </div>
              </div>
            )}
            
            <div className="logs-container">
              <h4>📋 실시간 로그</h4>
              <div className="logs-content">
                {embeddingLogs.map((log, index) => (
                  <div key={index} className="log-line">
                    {log}
                  </div>
                ))}
              </div>
            </div>
            
            <div className="modal-footer">
              {embedLoading ? (
                <button className="btn-secondary" disabled>
                  ⏳ 임베딩 생성 중...
                </button>
              ) : (
                <button 
                  className="btn-primary"
                  onClick={() => setShowEmbeddingModal(false)}
                >
                  ✅ 완료
                </button>
              )}
            </div>
          </div>
        </div>
      )}
      
      {/* 데이터 정합성 검사 진행 상황 모달 */}
      {showIntegrityModal && (
        <div className="modal-overlay">
          <div className="progress-modal">
            <div className="modal-header">
              <h3>🔍 데이터 정합성 검사 진행 상황</h3>
              <button 
                className="modal-close-btn"
                onClick={() => setShowIntegrityModal(false)}
                disabled={checkLoading}
              >
                ✕
              </button>
            </div>
            
            {integrityProgress && (
              <div className="progress-info">
                <div className="progress-stats">
                  <span>📊 상태: {integrityProgress.status}</span>
                  <span>📈 진행률: {integrityProgress.progress.toFixed(1)}%</span>
                  <span>🎯 현재: {integrityProgress.current_video}</span>
                </div>
                
                <div className="progress-bar-container">
                  <div 
                    className="progress-bar"
                    style={{ width: `${integrityProgress.progress}%` }}
                  />
                </div>
              </div>
            )}
            
            <div className="logs-container">
              <h4>📋 실시간 로그</h4>
              <div className="logs-content">
                {integrityLogs.map((log, index) => (
                  <div key={index} className="log-line">
                    {log}
                  </div>
                ))}
              </div>
            </div>
            
            <div className="modal-footer">
              {checkLoading ? (
                <button className="btn-secondary" disabled>
                  ⏳ 검사 중...
                </button>
              ) : (
                <button 
                  className="btn-primary"
                  onClick={() => setShowIntegrityModal(false)}
                >
                  ✅ 완료
                </button>
              )}
            </div>
          </div>
        </div>
      )}
      
      <div className="container">
      <header className="header">
        <h1>🎥 Y-Data-House Desktop</h1>
        <p>YouTube 비디오 분석 및 지식 관리 도구</p>
      </header>

      <nav className="tab-nav">
        {[
          { id: 'dashboard', icon: '📊', label: '대시보드' },
          { id: 'channels', icon: '📺', label: '채널 관리' },
          { id: 'videos', icon: '🎬', label: '비디오 목록' },
          { id: 'search', icon: '🔍', label: '벡터 검색' },
          { id: 'ai', icon: '🤖', label: 'AI 질문' },
          { id: 'settings', icon: '⚙️', label: '설정' }
        ].map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id as TabType)}
            className={activeTab === tab.id ? 'active' : ''}
          >
            {tab.icon} {tab.label}
          </button>
        ))}
      </nav>

      <main className="main-content">
        {activeTab === 'dashboard' && renderDashboard()}

        {activeTab === 'channels' && (
          <div className="tab-content">
            <h2 className="tab-title">📺 채널 관리</h2>
            
            <div className="channel-add-section">
              <input
                type="text"
                value={newChannelUrl}
                onChange={(e) => setNewChannelUrl(e.target.value)}
                placeholder="YouTube 채널 URL을 입력하세요 (예: https://www.youtube.com/@채널명)"
                className="channel-input"
                onKeyPress={(e) => e.key === 'Enter' && addChannel()}
              />
              <button onClick={addChannel} className="add-channel-button">
                ➕ 채널 추가
              </button>
            </div>

            <div className="channel-list">
              {channels.map((channel, index) => (
                <div key={index} className="channel-item">
                  <div className="channel-info">
                    <div className="channel-name">
                      {channel.enabled ? '✅' : '❌'} {channel.name}
                    </div>
                    <div className="channel-url">{channel.url}</div>
                  </div>
                  <div className="channel-actions">
                    <button 
                      onClick={() => toggleChannel(channel.url)}
                      className="channel-toggle-button"
                    >
                      {channel.enabled ? '⏸️ 비활성화' : '▶️ 활성화'}
                    </button>
                    <button 
                      onClick={() => removeChannel(channel.url)}
                      className="channel-remove-button"
                    >
                      🗑️ 삭제
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {activeTab === 'videos' && (
          <div className="tab-content">
            <h2 className="tab-title">🎬 비디오 목록</h2>
            
            <div className="video-layout">
              <div className="video-sidebar">
                <h3 className="sidebar-title">비디오 목록 ({videos.length})</h3>
                <div className="video-list">
                  {videos.map((video, index) => (
                    <div
                      key={index}
                      className={`video-item ${selectedVideo === video ? 'video-item-active' : ''}`}
                      onClick={() => setSelectedVideo(video)}
                    >
                      <div className="video-title">{video.title}</div>
                      <div className="video-channel">{video.channel}</div>
                      {video.upload_date && (
                        <div className="video-date">{video.upload_date}</div>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              <div className="video-main">
                {selectedVideo ? (
                  <>
                    <video
                      src={convertFileSrc(selectedVideo.video_path)}
                      controls
                      className="video-player"
                      onError={(e) => {
                        console.error('Video load error:', e);
                        console.log('Video path:', selectedVideo.video_path);
                        console.log('Converted path:', convertFileSrc(selectedVideo.video_path));
                      }}
                    />
                    <div className="video-info">
                      <h3 className="video-title-main">{selectedVideo.title}</h3>
                      <p className="video-channel-main">{selectedVideo.channel}</p>
                      {selectedVideo.upload_date && (
                        <p className="video-upload-date">업로드: {selectedVideo.upload_date}</p>
                      )}
                    </div>

                    <div className="caption-search">
                      <h4 className="section-title">캡션 검색</h4>
                      <div className="search-container">
                        <input
                          type="text"
                          value={searchQuery}
                          onChange={(e) => setSearchQuery(e.target.value)}
                          placeholder="캡션에서 검색..."
                          className="search-input"
                          onKeyPress={(e) => e.key === 'Enter' && searchCaptions()}
                        />
                        <button onClick={searchCaptions} className="search-button">
                          🔍 검색
                        </button>
                      </div>
                      
                      <div className="captions-container">
                        {(searchResults.length > 0 ? searchResults : captions).slice(0, 20).map((line) => (
                          <div key={line.index} className="caption-line">
                            <span className="caption-index">{line.index + 1}</span>
                            <span className="caption-text">{line.content}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </>
                ) : (
                  <div className="no-selection">
                    <div className="no-selection-icon">🎬</div>
                    <h3>비디오를 선택하세요</h3>
                    <p>왼쪽 목록에서 비디오를 클릭하여 재생하고 캡션을 확인하세요</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {activeTab === 'search' && (
          <div className="tab-content">
            <h2 className="tab-title">🔍 벡터 검색</h2>
            
            <div className="search-section">
              <h3 className="section-title">전체 비디오에서 검색</h3>
              <div className="search-container">
                <input
                  type="text"
                  value={vectorSearchQuery}
                  onChange={(e) => setVectorSearchQuery(e.target.value)}
                  placeholder="모든 비디오의 캡션에서 검색할 내용을 입력하세요..."
                  className="search-input"
                  onKeyPress={(e) => e.key === 'Enter' && performVectorSearch()}
                />
                <button onClick={performVectorSearch} className="search-button">
                  🔍 벡터 검색
                </button>
              </div>
              
              {vectorSearchResults && (
                <div className="search-results">
                  <h4 className="results-title">검색 결과:</h4>
                  <pre className="results-text">{vectorSearchResults}</pre>
                </div>
              )}
            </div>
          </div>
        )}

        {activeTab === 'ai' && (
          <div className="tab-content">
            <h2 className="tab-title">🤖 AI 질문하기</h2>
            
            <div className="ai-section">
              <h3 className="section-title">DeepSeek RAG 시스템</h3>
              <div className="ai-input-container">
                <textarea
                  value={aiQuestion}
                  onChange={(e) => setAiQuestion(e.target.value)}
                  placeholder="비디오 내용에 대해 궁금한 것을 질문하세요. 예: '부동산 투자 시 주의할 점은?', '도쿄 원룸 투자 수익률은?'"
                  className="ai-input"
                  rows={4}
                />
                <button 
                  onClick={askAI} 
                  disabled={aiLoading || !aiQuestion.trim()}
                  className={`ai-button ${aiLoading ? 'ai-button-loading' : ''}`}
                >
                  {aiLoading ? '🤔 생각하는 중...' : '💬 질문하기'}
                </button>
              </div>
              
              {aiAnswer && (
                <div className="ai-answer">
                  <h4 className="answer-title">AI 답변:</h4>
                  <pre className="answer-text">{aiAnswer}</pre>
                </div>
              )}
            </div>
          </div>
        )}

        {activeTab === 'settings' && (
          <div className="tab-content">
            <h2 className="tab-title">⚙️ 설정</h2>
            
            <div className="settings-grid">
              <div className="settings-card">
                <h3 className="card-title">🗂️ 프로젝트 정보</h3>
                <div className="card-content">
                  <div className="setting-item">
                    <span>프로젝트:</span>
                    <span>Y-Data-House</span>
                  </div>
                  <div className="setting-item">
                    <span>버전:</span>
                    <span>1.0.0</span>
                  </div>
                  <div className="setting-item">
                    <span>Vault 경로:</span>
                    <span>../vault</span>
                  </div>
                  <div className="setting-item">
                    <span>채널 설정:</span>
                    <span>../channels.txt</span>
                  </div>
                </div>
              </div>

              <div className="settings-card">
                <h3 className="card-title">🔧 도구 정보</h3>
                <div className="card-content">
                  <div className="setting-item">
                    <span>Frontend:</span>
                    <span>React + TypeScript</span>
                  </div>
                  <div className="setting-item">
                    <span>Backend:</span>
                    <span>Tauri + Rust</span>
                  </div>
                  <div className="setting-item">
                    <span>Python CLI:</span>
                    <span>ydh 패키지</span>
                  </div>
                  <div className="setting-item">
                    <span>AI:</span>
                    <span>DeepSeek + ChromaDB</span>
                  </div>
                </div>
              </div>

              <div className="settings-card">
                <h3 className="card-title">📚 사용법</h3>
                <div className="card-content">
                  <div className="usage-step">
                    <strong>1.</strong> 채널 관리에서 YouTube 채널 추가
                  </div>
                  <div className="usage-step">
                    <strong>2.</strong> 대시보드에서 비디오 다운로드
                  </div>
                  <div className="usage-step">
                    <strong>3.</strong> 벡터 임베딩 생성
                  </div>
                  <div className="usage-step">
                    <strong>4.</strong> 검색 또는 AI 질문 활용
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
    </>
  );
}

const styles = {
  container: {
    display: 'flex',
    flexDirection: 'column' as const,
    height: '100vh',
    backgroundColor: '#0f0f0f',
    color: '#ffffff',
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
  },
  
  header: {
    backgroundColor: '#1a1a1a',
    borderBottom: '1px solid #333',
    padding: '16px 24px',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  
  headerContent: {
    display: 'flex',
    alignItems: 'center',
    gap: '16px',
  },
  
  title: {
    margin: 0,
    fontSize: '24px',
    fontWeight: 700,
    background: 'linear-gradient(135deg, #ff4757, #3742fa)',
    WebkitBackgroundClip: 'text',
    WebkitTextFillColor: 'transparent',
  },
  
  subtitle: {
    color: '#888',
    fontSize: '14px',
  },
  
  headerStats: {
    display: 'flex',
    gap: '24px',
  },
  
  stat: {
    display: 'flex',
    flexDirection: 'column' as const,
    alignItems: 'center',
    gap: '4px',
  },
  
  statValue: {
    fontSize: '20px',
    fontWeight: 600,
    color: '#fff',
  },
  
  statLabel: {
    fontSize: '12px',
    color: '#888',
  },
  
  nav: {
    backgroundColor: '#1a1a1a',
    borderBottom: '1px solid #333',
    padding: '0 24px',
    display: 'flex',
    gap: '8px',
  },
  
  tabButton: {
    padding: '12px 20px',
    background: 'none',
    border: 'none',
    color: '#888',
    fontSize: '14px',
    fontWeight: 500,
    cursor: 'pointer',
    borderBottom: '2px solid transparent',
    transition: 'all 0.2s ease',
  },
  
  tabButtonActive: {
    color: '#fff',
    borderBottomColor: '#3742fa',
  },
  
  main: {
    flex: 1,
    overflow: 'auto',
    padding: '24px',
  },
  
  tabContent: {
    maxWidth: '1200px',
    margin: '0 auto',
  },
  
  tabTitle: {
    margin: '0 0 24px 0',
    fontSize: '28px',
    fontWeight: 600,
  },
  
  // Dashboard styles
  dashboardGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
    gap: '24px',
  },
  
  dashboardCard: {
    backgroundColor: '#1a1a1a',
    border: '1px solid #333',
    borderRadius: '12px',
    padding: '20px',
  },
  
  cardTitle: {
    margin: '0 0 16px 0',
    fontSize: '18px',
    fontWeight: 600,
  },
  
  cardContent: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '12px',
  },
  
  statusItem: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  
  actionButton: {
    padding: '12px 16px',
    backgroundColor: '#3742fa',
    color: 'white',
    border: 'none',
    borderRadius: '8px',
    fontSize: '14px',
    fontWeight: 600,
    cursor: 'pointer',
    transition: 'background-color 0.2s ease',
  },
  
  recentVideo: {
    padding: '8px 0',
    borderBottom: '1px solid #333',
  },
  
  recentVideoTitle: {
    fontSize: '14px',
    fontWeight: 500,
    marginBottom: '4px',
  },
  
  recentVideoChannel: {
    fontSize: '12px',
    color: '#888',
  },
  
  // Channel styles
  channelAddSection: {
    display: 'flex',
    gap: '12px',
    marginBottom: '24px',
  },
  
  channelInput: {
    flex: 1,
    padding: '12px 16px',
    backgroundColor: '#1a1a1a',
    border: '1px solid #333',
    borderRadius: '8px',
    color: '#fff',
    fontSize: '14px',
    outline: 'none',
  },
  
  addChannelButton: {
    padding: '12px 20px',
    backgroundColor: '#2ed573',
    color: 'white',
    border: 'none',
    borderRadius: '8px',
    fontSize: '14px',
    fontWeight: 600,
    cursor: 'pointer',
  },
  
  channelList: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '12px',
  },
  
  channelItem: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '16px',
    backgroundColor: '#1a1a1a',
    border: '1px solid #333',
    borderRadius: '8px',
  },
  
  channelInfo: {
    flex: 1,
  },
  
  channelName: {
    fontSize: '16px',
    fontWeight: 500,
    marginBottom: '4px',
  },
  
  channelUrl: {
    fontSize: '12px',
    color: '#888',
  },
  
  channelActions: {
    display: 'flex',
    gap: '8px',
  },
  
  channelToggleButton: {
    padding: '8px 12px',
    backgroundColor: '#ffa502',
    color: 'white',
    border: 'none',
    borderRadius: '6px',
    fontSize: '12px',
    cursor: 'pointer',
  },
  
  channelRemoveButton: {
    padding: '8px 12px',
    backgroundColor: '#ff4757',
    color: 'white',
    border: 'none',
    borderRadius: '6px',
    fontSize: '12px',
    cursor: 'pointer',
  },
  
  // Video styles
  videoLayout: {
    display: 'flex',
    gap: '24px',
    height: 'calc(100vh - 200px)',
  },
  
  videoSidebar: {
    width: '300px',
    backgroundColor: '#1a1a1a',
    border: '1px solid #333',
    borderRadius: '8px',
    padding: '16px',
    display: 'flex',
    flexDirection: 'column' as const,
  },
  
  sidebarTitle: {
    margin: '0 0 16px 0',
    fontSize: '16px',
    fontWeight: 600,
  },
  
  videoList: {
    flex: 1,
    overflowY: 'auto' as const,
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '8px',
  },
  
  videoItem: {
    padding: '12px',
    backgroundColor: '#0f0f0f',
    border: '1px solid #333',
    borderRadius: '6px',
    cursor: 'pointer',
    transition: 'all 0.2s ease',
  },
  
  videoItemActive: {
    backgroundColor: '#3742fa',
    borderColor: '#5352ed',
  },
  
  videoTitle: {
    fontSize: '14px',
    fontWeight: 500,
    marginBottom: '4px',
    lineHeight: 1.3,
  },
  
  videoChannel: {
    fontSize: '12px',
    color: '#888',
    marginBottom: '2px',
  },
  
  videoDate: {
    fontSize: '11px',
    color: '#666',
  },
  
  videoMain: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '20px',
  },
  
  videoPlayer: {
    width: '100%',
    maxHeight: '400px',
    borderRadius: '8px',
    backgroundColor: '#000',
  },
  
  videoInfo: {
    padding: '16px',
    backgroundColor: '#1a1a1a',
    border: '1px solid #333',
    borderRadius: '8px',
  },
  
  videoTitleMain: {
    margin: '0 0 8px 0',
    fontSize: '20px',
    fontWeight: 600,
  },
  
  videoChannelMain: {
    margin: '0 0 4px 0',
    color: '#888',
    fontSize: '14px',
  },
  
  videoUploadDate: {
    margin: 0,
    color: '#666',
    fontSize: '12px',
  },
  
  captionSearch: {
    backgroundColor: '#1a1a1a',
    border: '1px solid #333',
    borderRadius: '8px',
    padding: '16px',
  },
  
  sectionTitle: {
    margin: '0 0 16px 0',
    fontSize: '16px',
    fontWeight: 600,
  },
  
  searchContainer: {
    display: 'flex',
    gap: '12px',
    marginBottom: '16px',
  },
  
  searchInput: {
    flex: 1,
    padding: '10px 12px',
    backgroundColor: '#0f0f0f',
    border: '1px solid #333',
    borderRadius: '6px',
    color: '#fff',
    fontSize: '14px',
    outline: 'none',
  },
  
  searchButton: {
    padding: '10px 16px',
    backgroundColor: '#ff4757',
    color: 'white',
    border: 'none',
    borderRadius: '6px',
    fontSize: '14px',
    fontWeight: 600,
    cursor: 'pointer',
  },
  
  captionsContainer: {
    maxHeight: '200px',
    overflowY: 'auto' as const,
    backgroundColor: '#0f0f0f',
    border: '1px solid #333',
    borderRadius: '6px',
  },
  
  captionLine: {
    display: 'flex',
    padding: '8px 12px',
    borderBottom: '1px solid #333',
    gap: '12px',
  },
  
  captionIndex: {
    color: '#888',
    fontSize: '12px',
    minWidth: '30px',
    textAlign: 'right' as const,
  },
  
  captionText: {
    flex: 1,
    fontSize: '13px',
    lineHeight: 1.4,
  },
  
  noSelection: {
    display: 'flex',
    flexDirection: 'column' as const,
    alignItems: 'center',
    justifyContent: 'center',
    height: '100%',
    textAlign: 'center' as const,
    color: '#888',
  },
  
  noSelectionIcon: {
    fontSize: '64px',
    marginBottom: '16px',
  },
  
  // Search styles
  searchSection: {
    backgroundColor: '#1a1a1a',
    border: '1px solid #333',
    borderRadius: '8px',
    padding: '20px',
  },
  
  searchResults: {
    marginTop: '20px',
    backgroundColor: '#0f0f0f',
    border: '1px solid #333',
    borderRadius: '6px',
    padding: '16px',
  },
  
  resultsTitle: {
    margin: '0 0 12px 0',
    fontSize: '16px',
    fontWeight: 600,
    color: '#2ed573',
  },
  
  resultsText: {
    margin: 0,
    fontSize: '13px',
    lineHeight: 1.5,
    whiteSpace: 'pre-wrap' as const,
  },
  
  // AI styles
  aiSection: {
    backgroundColor: '#1a1a1a',
    border: '1px solid #333',
    borderRadius: '8px',
    padding: '20px',
  },
  
  aiInputContainer: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '16px',
  },
  
  aiInput: {
    padding: '12px 16px',
    backgroundColor: '#0f0f0f',
    border: '1px solid #333',
    borderRadius: '6px',
    color: '#fff',
    fontSize: '14px',
    outline: 'none',
    resize: 'vertical' as const,
    minHeight: '100px',
  },
  
  aiButton: {
    alignSelf: 'flex-start',
    padding: '12px 24px',
    backgroundColor: '#2ed573',
    color: 'white',
    border: 'none',
    borderRadius: '6px',
    fontSize: '14px',
    fontWeight: 600,
    cursor: 'pointer',
    transition: 'background-color 0.2s ease',
  },
  
  aiButtonLoading: {
    backgroundColor: '#888',
    cursor: 'not-allowed',
  },
  
  aiAnswer: {
    marginTop: '20px',
    backgroundColor: '#0f0f0f',
    border: '1px solid #333',
    borderRadius: '6px',
    padding: '16px',
  },
  
  answerTitle: {
    margin: '0 0 12px 0',
    fontSize: '16px',
    fontWeight: 600,
    color: '#2ed573',
  },
  
  answerText: {
    margin: 0,
    fontSize: '13px',
    lineHeight: 1.5,
    whiteSpace: 'pre-wrap' as const,
  },
  
  // Settings styles
  settingsGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
    gap: '24px',
  },
  
  settingsCard: {
    backgroundColor: '#1a1a1a',
    border: '1px solid #333',
    borderRadius: '8px',
    padding: '20px',
  },
  
  settingItem: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '8px 0',
    borderBottom: '1px solid #333',
  },
  
  usageStep: {
    padding: '8px 0',
    fontSize: '14px',
    lineHeight: 1.4,
  },
  
  // Loading and error styles
  loadingContainer: {
    display: 'flex',
    flexDirection: 'column' as const,
    alignItems: 'center',
    justifyContent: 'center',
    height: '100vh',
    backgroundColor: '#0f0f0f',
    color: '#ffffff',
  },
  
  spinner: {
    width: '40px',
    height: '40px',
    border: '4px solid #333',
    borderTop: '4px solid #3742fa',
    borderRadius: '50%',
    animation: 'spin 1s linear infinite',
    marginBottom: '16px',
  },
  
  loadingText: {
    fontSize: '16px',
    color: '#888',
  },
  
  errorContainer: {
    display: 'flex',
    flexDirection: 'column' as const,
    alignItems: 'center',
    justifyContent: 'center',
    height: '100vh',
    backgroundColor: '#0f0f0f',
    color: '#ffffff',
    textAlign: 'center' as const,
  },
  
  errorIcon: {
    fontSize: '64px',
    marginBottom: '24px',
  },
  
  errorTitle: {
    margin: '0 0 16px 0',
    fontSize: '28px',
    fontWeight: 600,
    color: '#ff4757',
  },
  
  errorMessage: {
    margin: '0 0 24px 0',
    color: '#888',
    fontSize: '16px',
    maxWidth: '400px',
  },
  
  retryButton: {
    padding: '12px 24px',
    backgroundColor: '#3742fa',
    color: 'white',
    border: 'none',
    borderRadius: '8px',
    fontSize: '16px',
    fontWeight: 600,
    cursor: 'pointer',
  },
};
