import React, { useState, useEffect } from 'react';
import { invoke } from '@tauri-apps/api/core';
import ChannelSelector from './ChannelSelector';

interface PromptData {
  version?: number;
  channel_name?: string;
  created_at?: string;
  auto_generated?: boolean;
  persona?: string;
  tone?: string;
  system_prompt?: string;
  rules?: string[];
  output_format?: {
    structure?: string;
    max_bullets?: number;
    include_video_links?: boolean;
  };
  expertise_keywords?: string[];
}

interface PromptVersion {
  version: number;
  created_at: string;
  persona: string;
  auto_generated: boolean;
}

export const PromptManagerTab: React.FC = () => {
  const [selectedChannel, setSelectedChannel] = useState<string>('');
  const [currentPrompt, setCurrentPrompt] = useState<PromptData | null>(null);
  const [promptVersions, setPromptVersions] = useState<PromptVersion[]>([]);
  const [isEditing, setIsEditing] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saveStatus, setSaveStatus] = useState<string | null>(null);

  const loadChannelPrompt = async (channelName: string) => {
    if (!channelName) return;
    
    try {
      setLoading(true);
      setError(null);
      
      // 현재 프롬프트 로드
      const promptJson = await invoke<string>('get_channel_prompt', { channelName });
      const prompt = JSON.parse(promptJson) as PromptData;
      setCurrentPrompt(prompt);
      
      // 버전 히스토리 로드 (TODO: 백엔드에서 JSON 형태로 반환하도록 개선 필요)
      // const versionsText = await invoke<string>('get_prompt_versions', { channelName });
      // setPromptVersions(parseVersions(versionsText));
      
      setSelectedChannel(channelName);
      setIsEditing(false);
      
    } catch (err) {
      console.error('프롬프트 로드 실패:', err);
      setError(`프롬프트 로드 실패: ${err}`);
    } finally {
      setLoading(false);
    }
  };

  const generateAutoPrompt = async () => {
    if (!selectedChannel) return;
    
    try {
      setLoading(true);
      setError(null);
      setSaveStatus('자동 프롬프트 생성 중...');
      
      const newVersion = await invoke<number>('auto_generate_channel_prompt', {
        channelName: selectedChannel
      });
      
      if (newVersion > 0) {
        setSaveStatus(`새 버전 v${newVersion}이 생성되었습니다.`);
        // 새로 생성된 프롬프트 로드
        await loadChannelPrompt(selectedChannel);
        
        setTimeout(() => setSaveStatus(null), 3000);
      } else {
        setError('자동 프롬프트 생성에 실패했습니다.');
      }
      
    } catch (err) {
      console.error('자동 프롬프트 생성 실패:', err);
      setError(`자동 프롬프트 생성 실패: ${err}`);
    } finally {
      setLoading(false);
    }
  };

  const savePrompt = async () => {
    if (!selectedChannel || !currentPrompt) return;
    
    try {
      setLoading(true);
      setError(null);
      setSaveStatus('저장 중...');
      
      const promptData = {
        ...currentPrompt,
        channel_name: selectedChannel,
        auto_generated: false // 수동 편집된 프롬프트
      };
      
      const newVersion = await invoke<number>('save_channel_prompt', {
        channelName: selectedChannel,
        promptData: JSON.stringify(promptData)
      });
      
      setSaveStatus(`새 버전 v${newVersion}이 저장되었습니다.`);
      await loadChannelPrompt(selectedChannel); // 새로고침
      setIsEditing(false);
      
      setTimeout(() => setSaveStatus(null), 3000);
      
    } catch (err) {
      console.error('저장 실패:', err);
      setError(`저장 실패: ${err}`);
    } finally {
      setLoading(false);
    }
  };

  const updatePromptField = (field: string, value: any) => {
    if (!currentPrompt) return;
    
    setCurrentPrompt({
      ...currentPrompt,
      [field]: value
    });
  };

  const updateRules = (rulesText: string) => {
    const rules = rulesText.split('\n').filter(r => r.trim());
    updatePromptField('rules', rules);
  };

  const formatRulesForDisplay = (rules?: string[]): string => {
    return rules ? rules.join('\n') : '';
  };

  return (
    <div className="prompt-management">
      <div className="prompt-header">
        <h2 className="tab-title">📝 프롬프트 관리</h2>
        <p className="tab-description">
          채널별 AI 프롬프트를 관리하고 편집할 수 있습니다.
        </p>
      </div>

      {/* 채널 선택 */}
      <div className="channel-selection-section">
        <ChannelSelector 
          onChannelSelect={loadChannelPrompt}
          selectedChannel={selectedChannel}
          className="prompt-channel-selector"
        />
      </div>

      {/* 로딩 및 에러 표시 */}
      {loading && (
        <div className="loading-section">
          <div className="loading-spinner"></div>
          <span>처리 중...</span>
        </div>
      )}

      {error && (
        <div className="error-section">
          <span>❌ {error}</span>
          <button onClick={() => setError(null)} className="close-error">×</button>
        </div>
      )}

      {saveStatus && (
        <div className="save-status">
          <span>✅ {saveStatus}</span>
        </div>
      )}

      {/* 프롬프트 편집기 */}
      {currentPrompt && selectedChannel && (
        <div className="prompt-editor-container">
          <div className="prompt-editor">
            <div className="editor-header">
              <h3>✏️ 프롬프트 편집</h3>
              <div className="editor-actions">
                <button 
                  onClick={generateAutoPrompt}
                  disabled={loading}
                  className="auto-generate-button"
                  title="벡터 데이터를 분석하여 자동으로 프롬프트 생성"
                >
                  🤖 자동 생성
                </button>
                
                <button 
                  onClick={() => setIsEditing(!isEditing)}
                  className="edit-toggle-button"
                >
                  {isEditing ? '📖 미리보기' : '✏️ 편집 모드'}
                </button>
              </div>
            </div>

            {/* 프롬프트 정보 표시 */}
            <div className="prompt-info">
              <div className="info-grid">
                <div className="info-item">
                  <span className="info-label">버전:</span>
                  <span className="info-value">v{currentPrompt.version || 1}</span>
                </div>
                <div className="info-item">
                  <span className="info-label">생성 방식:</span>
                  <span className={`info-value ${currentPrompt.auto_generated ? 'auto' : 'manual'}`}>
                    {currentPrompt.auto_generated ? '🤖 자동 생성' : '✏️ 수동 편집'}
                  </span>
                </div>
                <div className="info-item">
                  <span className="info-label">생성일:</span>
                  <span className="info-value">
                    {currentPrompt.created_at 
                      ? new Date(currentPrompt.created_at).toLocaleString()
                      : 'N/A'
                    }
                  </span>
                </div>
              </div>
            </div>

            {/* 편집 폼 */}
            <div className="prompt-form">
              <div className="form-group">
                <label className="form-label">페르소나:</label>
                {isEditing ? (
                  <input
                    type="text"
                    value={currentPrompt.persona || ''}
                    onChange={(e) => updatePromptField('persona', e.target.value)}
                    placeholder="예: 10년차 부동산 투자 전문가"
                    className="form-input"
                  />
                ) : (
                  <div className="form-display">{currentPrompt.persona || '없음'}</div>
                )}
              </div>

              <div className="form-group">
                <label className="form-label">톤 & 스타일:</label>
                {isEditing ? (
                  <input
                    type="text"
                    value={currentPrompt.tone || ''}
                    onChange={(e) => updatePromptField('tone', e.target.value)}
                    placeholder="예: 친근하지만 전문적인 스타일"
                    className="form-input"
                  />
                ) : (
                  <div className="form-display">{currentPrompt.tone || '없음'}</div>
                )}
              </div>

              <div className="form-group">
                <label className="form-label">시스템 프롬프트:</label>
                {isEditing ? (
                  <textarea
                    rows={6}
                    value={currentPrompt.system_prompt || ''}
                    onChange={(e) => updatePromptField('system_prompt', e.target.value)}
                    placeholder="AI의 역할과 행동 방식을 정의하세요..."
                    className="form-textarea"
                  />
                ) : (
                  <div className="form-display multiline">
                    {currentPrompt.system_prompt || '없음'}
                  </div>
                )}
              </div>

              <div className="form-group">
                <label className="form-label">답변 규칙:</label>
                {isEditing ? (
                  <textarea
                    rows={4}
                    value={formatRulesForDisplay(currentPrompt.rules)}
                    onChange={(e) => updateRules(e.target.value)}
                    placeholder="각 줄에 하나씩 규칙을 입력하세요..."
                    className="form-textarea"
                  />
                ) : (
                  <div className="form-display">
                    {currentPrompt.rules && currentPrompt.rules.length > 0 ? (
                      <ul className="rules-list">
                        {currentPrompt.rules.map((rule, index) => (
                          <li key={index}>{rule}</li>
                        ))}
                      </ul>
                    ) : (
                      '없음'
                    )}
                  </div>
                )}
              </div>

              {/* 전문 키워드 표시 */}
              {currentPrompt.expertise_keywords && currentPrompt.expertise_keywords.length > 0 && (
                <div className="form-group">
                  <label className="form-label">전문 키워드:</label>
                  <div className="keywords-display">
                    {currentPrompt.expertise_keywords.map((keyword, index) => (
                      <span key={index} className="keyword-tag">{keyword}</span>
                    ))}
                  </div>
                </div>
              )}

              {/* 출력 형식 표시 */}
              {currentPrompt.output_format && (
                <div className="form-group">
                  <label className="form-label">출력 형식:</label>
                  <div className="form-display">
                    <div>구조: {currentPrompt.output_format.structure || '기본'}</div>
                    <div>최대 bullet 수: {currentPrompt.output_format.max_bullets || 5}</div>
                    <div>
                      영상 링크 포함: {currentPrompt.output_format.include_video_links ? '예' : '아니오'}
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* 저장 버튼 */}
            {isEditing && (
              <div className="editor-footer">
                <button 
                  onClick={savePrompt}
                  disabled={loading}
                  className="save-button"
                >
                  💾 새 버전 저장
                </button>
                
                <button 
                  onClick={() => {
                    setIsEditing(false);
                    loadChannelPrompt(selectedChannel); // 변경사항 취소
                  }}
                  className="cancel-button"
                >
                  취소
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* 채널이 선택되지 않은 경우 */}
      {!selectedChannel && !loading && (
        <div className="no-channel-selected">
          <div className="empty-state">
            <span className="empty-icon">📝</span>
            <h3>채널을 선택해주세요</h3>
            <p>위에서 프롬프트를 관리할 채널을 선택하면 편집할 수 있습니다.</p>
          </div>
        </div>
      )}
    </div>
  );
};

export default PromptManagerTab;