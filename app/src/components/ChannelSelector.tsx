import React, { useState, useEffect } from 'react';
import { invoke } from '@tauri-apps/api/core';

interface ChannelInfo {
  name: string;
  video_count: number;
  description?: string;
  last_updated?: string;
}

interface ChannelSelectorProps {
  onChannelSelect: (channel: string) => void;
  selectedChannel?: string;
  className?: string;
}

export const ChannelSelector: React.FC<ChannelSelectorProps> = ({ 
  onChannelSelect, 
  selectedChannel,
  className = ""
}) => {
  const [channels, setChannels] = useState<ChannelInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadChannels();
  }, []);

  const loadChannels = async () => {
    try {
      setLoading(true);
      setError(null);
      const result = await invoke<ChannelInfo[]>('get_available_channels_for_ai');
      setChannels(result);
    } catch (err) {
      console.error('채널 목록 로드 실패:', err);
      setError('채널 목록을 불러올 수 없습니다.');
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className={`channel-loading ${className}`}>
        <div className="loading-spinner"></div>
        <span>채널 목록 로딩 중...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className={`channel-error ${className}`}>
        <div className="error-message">
          <span>⚠️ {error}</span>
          <button onClick={loadChannels} className="retry-button">
            다시 시도
          </button>
        </div>
      </div>
    );
  }

  if (channels.length === 0) {
    return (
      <div className={`channel-empty ${className}`}>
        <div className="empty-message">
          <span>📺 사용 가능한 채널이 없습니다.</span>
          <p>먼저 벡터 임베딩을 생성해주세요.</p>
        </div>
      </div>
    );
  }

  return (
    <div className={`channel-selector ${className}`}>
      <h3 className="channel-selector-title">🎯 질문할 채널 선택</h3>
      <div className="channel-grid">
        {channels.map(channel => (
          <div 
            key={channel.name} 
            className={`channel-card ${selectedChannel === channel.name ? 'selected' : ''}`}
            onClick={() => onChannelSelect(channel.name)}
          >
            <div className="channel-header">
              <div className="channel-name">{channel.name}</div>
              <div className="channel-stats">{channel.video_count}개 영상</div>
            </div>
            
            {channel.description && (
              <div className="channel-description">{channel.description}</div>
            )}
            
            {channel.last_updated && (
              <div className="channel-updated">
                최근 업데이트: {new Date(channel.last_updated).toLocaleDateString()}
              </div>
            )}
            
            {selectedChannel === channel.name && (
              <div className="channel-selected-indicator">✓</div>
            )}
          </div>
        ))}
      </div>
      
      <div className="channel-actions">
        <button onClick={loadChannels} className="refresh-button">
          🔄 새로고침
        </button>
      </div>
    </div>
  );
};

export default ChannelSelector;